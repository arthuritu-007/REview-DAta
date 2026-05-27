from __future__ import annotations

import os
import re
import shutil
import uuid
from datetime import datetime
import json
import csv
import urllib.request
import urllib.error
import contextvars

from core.interfaces import IDataService
from core.reports.pdf_report import export_findings_pdf
from core.rules.rule_catalog import get_default_rules
from core.validation.validators import (
    ValidationFinding,
    validate_campos_obligatorios,
    validate_carta_porte,
    validate_conductor_asignado,
    validate_fecha_salida_no_futura,
    validate_formato_fechas,
    validate_formato_horas,
    validate_formato_numero_empleado,
    validate_formato_placas,
    validate_logica_fechas,
    validate_no_duplicidad,
    validate_peso_rango,
)
from infrastructure.database import Database
from services.auth_service import AuthService


_SESSION_CTX: contextvars.ContextVar[dict | None] = contextvars.ContextVar("reviewdata_session", default=None)


def _normalize_column_name(name: str) -> str:
    return "".join(ch for ch in (name or "").strip().lower().replace(" ", "_") if ch.isalnum() or ch == "_")


def _guess_folio_column(columns: list[str]) -> str | None:
    normalized_to_original = {_normalize_column_name(c): c for c in columns}
    for key in ("folio_reporte", "folioreporte", "folio"):
        if key in normalized_to_original:
            return normalized_to_original[key]
    for norm, original in normalized_to_original.items():
        if "folio" in norm and "reporte" in norm:
            return original
    return None


_DEFAULT_CONTRACT = {
    "Folio_reporte": {"required": True, "type": "regex", "regex": r"^FR-\d{3}$", "no_contains": ["ERROR"], "severity": "Alta"},
    "Numero_remision": {"required": True, "type": "regex", "regex": r"^REM-\d{4}$", "no_contains": ["ERROR"], "severity": "Alta"},
    "Numero_operador": {"required": True, "type": "int", "no_contains": ["ERROR"], "severity": "Alta"},
    "Nombre_operador": {"required": True, "type": "person_name", "no_contains": ["ERROR"], "severity": "Media"},
    "Fecha_reporte": {"required": True, "type": "date", "preferred_format": "YYYY-MM-DD", "no_contains": ["ERROR"], "severity": "Alta"},
    "Descripcion": {"required": True, "type": "text", "no_contains": ["ERROR"], "severity": "Media"},
    "OC": {"required": True, "type": "regex", "regex": r"^OC-\d{4}$", "no_contains": ["ERROR"], "severity": "Media"},
    "Origen_destino": {"required": True, "type": "route", "no_contains": ["ERROR"], "severity": "Alta"},
    "Ruta_autorizada": {"required": True, "type": "text", "no_contains": ["ERROR"], "severity": "Alta"},
    "Remitente_cliente": {"required": True, "type": "text", "no_contains": ["ERROR"], "severity": "Media"},
    "Remitente_origen": {"required": True, "type": "text", "no_contains": ["ERROR"], "severity": "Media"},
    "Remitente_cp": {"required": True, "type": "regex", "regex": r"^\d{5}$", "no_contains": ["ERROR"], "severity": "Alta"},
    "Remitente_ciudad": {"required": True, "type": "text", "no_contains": ["ERROR"], "severity": "Media"},
    "Remitente_colonia": {"required": True, "type": "text", "no_contains": ["ERROR"], "severity": "Media"},
    "Remitente_calle": {"required": True, "type": "text", "no_contains": ["ERROR"], "severity": "Media"},
    "Destinatario_cliente": {"required": True, "type": "text", "no_contains": ["ERROR"], "severity": "Media"},
    "Destinatario_origen": {"required": True, "type": "text", "no_contains": ["ERROR"], "severity": "Media"},
    "Destinatario_cp": {"required": True, "type": "regex", "regex": r"^\d{5}$", "no_contains": ["ERROR"], "severity": "Alta"},
    "Destinatario_ciudad": {"required": True, "type": "text", "no_contains": ["ERROR"], "severity": "Media"},
    "Destinatario_colonia": {"required": True, "type": "text", "no_contains": ["ERROR"], "severity": "Media"},
    "Destinatario_calle": {"required": True, "type": "text", "no_contains": ["ERROR"], "severity": "Media"},
    "Consumo_estimado_diesel": {"required": True, "type": "float", "min": 0.000001, "no_contains": ["ERROR"], "severity": "Alta"},
    "Casetas_peaje": {"required": True, "type": "int", "min": 0, "no_contains": ["ERROR"], "severity": "Media"},
    "Hora_salida_base": {"required": True, "type": "time", "no_contains": ["ERROR"], "severity": "Alta"},
    "Hora_aproximada_llegada": {"required": True, "type": "time", "no_contains": ["ERROR"], "severity": "Alta"},
    "Placas_tracto": {"required": True, "type": "regex", "regex": r"^[A-Z]{3}-\d{3}$", "no_contains": ["ERROR"], "severity": "Alta"},
    "Tipo_numero_remolques": {"required": True, "type": "int", "allowed": [0, 1, 2], "no_contains": ["ERROR"], "severity": "Alta"},
    "Dollies": {"required": True, "type": "si_no", "no_contains": ["ERROR"], "severity": "Media"},
    "Cambio_ruta": {"required": True, "type": "si_no", "no_contains": ["ERROR"], "severity": "Alta"},
    "Cambio_operador_emergencia": {"required": True, "type": "si_no", "no_contains": ["ERROR"], "severity": "Alta"},
    "Boton_panico": {"required": True, "type": "si_no", "no_contains": ["ERROR"], "severity": "Crítica"},
    "Carga_gasolina": {"required": True, "type": "si_no", "no_contains": ["ERROR"], "severity": "Media"},
}


def _is_empty_text(v: str) -> bool:
    return (v or "").strip() == ""


def _parse_date_any(text: str) -> datetime | None:
    s = (text or "").strip()
    if not s:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(s, fmt)
        except Exception:
            continue
    return None


def _parse_time_any(text: str) -> datetime | None:
    s = (text or "").strip()
    if not s:
        return None
    for fmt in ("%H:%M", "%H:%M:%S"):
        try:
            return datetime.strptime(s, fmt)
        except Exception:
            continue
    return None


def _looks_like_garbage(text: str) -> bool:
    s = (text or "").strip()
    if not s:
        return False
    lowered = s.lower()
    if lowered in {
        "error",
        "err",
        "n/a",
        "na",
        "null",
        "none",
        "nan",
        "undefined",
        "desconocido",
        "sin dato",
        "s/d",
        "sd",
        "xxx",
        "xxxx",
        "---",
        "--",
    }:
        return True
    if re.fullmatch(r"[#?]{3,}", s):
        return True
    if re.fullmatch(r"(.)\1{3,}", s):
        return True
    return False


def _normalize_yes_no(value: str) -> str | None:
    s = (value or "").strip().lower()
    if not s:
        return None
    if s in ("si", "sí", "s"):
        return "Si"
    if s in ("no", "n"):
        return "No"
    return None


class DataService(IDataService):
    def __init__(self, db: Database):
        self._db = db
        self._auth = AuthService(db)
        self._session = None
        self._datasets: list[dict] = []
        self._runs: list[dict] = []
        self._findings: list[dict] = []
        self._reports: list[dict] = []
        self._rules = get_default_rules()
        self._recommendations = {
            "campos_obligatorios_no_nulos": "Completa los campos obligatorios antes de registrar el viaje.",
            "conductor_asignado": "Asigna un conductor válido al viaje antes de procesarlo.",
            "carta_porte_existente": "Registra la Carta Porte del viaje para mantener trazabilidad.",
            "no_duplicidad_cliente_fecha_direccion": "Valida y depura duplicados por cliente, fecha y dirección.",
            "formato_numero_empleado": "Normaliza el número de empleado para que tenga 12 o 13 caracteres.",
            "formato_placas": "Ajusta el formato de placas al patrón autorizado y elimina espacios extra.",
            "formato_fecha_dd_mm_yyyy": "Convierte fechas al formato DD-MM-YYYY de forma consistente.",
            "formato_hora_hh_mm": "Convierte horas al formato HH:MM de forma consistente.",
            "peso_en_rango_0_35": "Corrige pesos fuera del rango permitido (0–35) y verifica unidades.",
            "fecha_salida_no_futura": "Corrige fechas de salida futuras y revisa la captura de datos.",
            "logica_fechas_llegada_no_menor_salida": "Verifica la coherencia entre fecha de salida y llegada.",
            "contrato_csv_viajes": "Asegura que el CSV cumpla el contrato: formatos, tipos, catálogos y campos requeridos.",
            "reglas_negocio_viajes": "Revisa reglas de negocio: botón pánico, cambios operativos, coherencia de horarios y ruta.",
        }
        base_dir = (os.environ.get("REVIEWDATA_DATA_DIR") or "").strip()
        if not base_dir:
            base_dir = (os.environ.get("LOCALAPPDATA") or "").strip()
        if not base_dir:
            base_dir = (os.environ.get("APPDATA") or "").strip()
        if not base_dir:
            base_dir = os.path.expanduser("~")
        self._storage_dir = os.path.join(base_dir, "ReviewData", "storage", "datasets")
        os.makedirs(self._storage_dir, exist_ok=True)
        self._init_rules_from_db()

    def _init_rules_from_db(self):
        if not self._db_enabled():
            return
        try:
            rows = self._db.fetch_all("SELECT id, name, description, rule_type, severity, active FROM rules ORDER BY created_at ASC")
            if not rows:
                for r in self._rules:
                    self._db.execute_query(
                        """
                        INSERT INTO rules (id, name, description, rule_type, severity, active)
                        VALUES (%s, %s, %s, %s, %s, TRUE)
                        ON CONFLICT (id) DO NOTHING
                        """,
                        (r.id, r.name, r.description, r.rule_type, r.severity),
                    )
            else:
                existing_ids = {str(r.get("id", "")) for r in rows if isinstance(r, dict)}
                for r in self._rules:
                    if r.id in existing_ids:
                        continue
                    self._db.execute_query(
                        """
                        INSERT INTO rules (id, name, description, rule_type, severity, active)
                        VALUES (%s, %s, %s, %s, %s, TRUE)
                        ON CONFLICT (id) DO NOTHING
                        """,
                        (r.id, r.name, r.description, r.rule_type, r.severity),
                    )
                self._rules = [
                    type(self._rules[0])(
                        id=str(r.get("id", "")),
                        name=str(r.get("name", "")),
                        description=str(r.get("description", "")),
                        rule_type=str(r.get("rule_type", "")),
                        severity=str(r.get("severity", "")),
                    )
                    for r in rows
                    if isinstance(r, dict)
                ]
        except Exception:
            return

    def _db_enabled(self) -> bool:
        return bool(getattr(self._db, "conn", None))

    def _get_session(self) -> dict | None:
        s = _SESSION_CTX.get()
        if s is not None:
            return s
        return self._session

    def _set_session(self, session: dict | None) -> None:
        _SESSION_CTX.set(session)
        self._session = session

    def _get_limit(self, env_key: str, default: int) -> int:
        raw = (os.environ.get(env_key) or "").strip()
        if not raw:
            return int(default)
        if raw.isdigit():
            return int(raw)
        return int(default)

    def _normalize_severity(self, value: str) -> str:
        s = str(value or "").strip()
        if not s:
            return "Alta"
        s = s.replace("CrÝtica", "Cr\u00edtica").replace("Crýtica", "Cr\u00edtica").replace("Ý", "\u00ed").replace("ý", "\u00ed")
        s = s.replace("CrÃ­tica", "Cr\u00edtica").replace("CrÃ\xadtica", "Cr\u00edtica")
        lowered = s.lower()
        if lowered in ("critica", "crítica"):
            return "Cr\u00edtica"
        if lowered in ("alta",):
            return "Alta"
        if lowered in ("media",):
            return "Media"
        if lowered in ("baja",):
            return "Baja"
        if lowered == "critica":
            return "Cr\u00edtica"
        return s

    def _parse_json(self, value, default):
        if value is None:
            return default
        if isinstance(value, (dict, list)):
            return value
        if isinstance(value, (bytes, bytearray)):
            try:
                value = bytes(value).decode("utf-8", errors="replace")
            except Exception:
                return default
        if isinstance(value, str):
            s = value.strip()
            if not s:
                return default
            try:
                return json.loads(s)
            except Exception:
                return default
        return default

    def _format_dt(self, value) -> tuple[str | None, str | None]:
        if value is None:
            return None, None
        dt = None
        if isinstance(value, datetime):
            dt = value
        elif isinstance(value, str):
            s = value.strip()
            if not s:
                return None, None
            try:
                dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
            except Exception:
                dt = None
        if not dt:
            return None, None
        return dt.strftime("%d-%m-%Y"), dt.strftime("%H:%M")

    def _get_contract(self) -> dict:
        return dict(_DEFAULT_CONTRACT)

    def _explain_finding(self, rule_id: str, field: str, description: str, value: str) -> tuple[str, str, str]:
        rid = (rule_id or "").strip()
        f = (field or "").strip()
        desc = (description or "").strip()
        val = (value or "").strip()
        contract = self._get_contract()

        def rec_for_contract(col: str) -> str:
            spec = contract.get(col) or {}
            t = str(spec.get("type") or "text")
            if t == "date":
                return "Corregir la fecha o normalizar el formato a YYYY-MM-DD."
            if t == "time":
                return "Corregir la hora o normalizar el formato a HH:mm."
            if t == "si_no":
                return "Normalizar valores a Si/No (por ejemplo: no -> No)."
            if t == "regex":
                rx = str(spec.get("regex") or "").strip()
                return f"Ajustar el valor para cumplir el patrón: {rx}."
            if t in ("int", "float"):
                return "Corregir el valor para que sea numérico y cumpla el rango permitido."
            if t == "route":
                return "Corregir el formato a Ciudad-Ciudad (ejemplo: CDMX-Veracruz)."
            if t == "person_name":
                return "Corregir el nombre: solo letras y espacios; evitar números o texto basura."
            return "Corregir el valor para cumplir el contrato del dataset."

        error_type = ""
        if "no existe" in desc.lower():
            error_type = "missing_column"
        elif "vacío" in desc.lower() or "nulo" in desc.lower():
            error_type = "required_empty"
        elif "formato" in desc.lower() or "inválid" in desc.lower():
            error_type = "invalid_format"
        elif "rango" in desc.lower():
            error_type = "out_of_range"
        elif "duplic" in desc.lower():
            error_type = "duplicate"
        elif rid in ("reglas_negocio_viajes", "logica_fechas_llegada_no_menor_salida"):
            error_type = "business_rule"
        else:
            error_type = "validation"

        expected = ""
        recommendation = self._recommendations.get(rid, "")

        if rid == "contrato_csv_viajes":
            col = f.split(",")[0].strip()
            spec = contract.get(col) or {}
            t = str(spec.get("type") or "text")
            if t == "regex":
                expected = f"Debe cumplir regex: {spec.get('regex')}"
            elif t == "int":
                expected = "Debe ser entero"
                if "allowed" in spec:
                    expected += f" (permitidos: {spec.get('allowed')})"
                if "min" in spec:
                    expected += f" (>= {spec.get('min')})"
            elif t == "float":
                expected = "Debe ser número decimal"
                if "min" in spec:
                    expected += f" (>= {spec.get('min')})"
            elif t == "date":
                expected = "Fecha válida"
                if str(spec.get("preferred_format") or "") == "YYYY-MM-DD":
                    expected = "Formato recomendado: YYYY-MM-DD"
            elif t == "time":
                expected = "Formato HH:mm"
            elif t == "si_no":
                expected = "Valores permitidos: Si, No"
            elif t == "route":
                expected = "Formato esperado: Ciudad-Ciudad"
            elif t == "person_name":
                expected = "Debe parecer nombre humano (sin números ni texto basura)"
            else:
                expected = "Cumplir contrato del dataset"
            recommendation = rec_for_contract(col)
            if "ERROR" in val.upper():
                recommendation = "Rechazar o corregir registros con ERROR en campos críticos."

        if rid == "reglas_negocio_viajes":
            if "Boton_panico" in f:
                expected = "Si Boton_panico = Si, se clasifica como crítico"
                recommendation = "Revisar el evento, activar protocolo y corregir captura si fue error."
            elif "Hora_salida_base" in f or "Hora_aproximada_llegada" in f:
                expected = "Hora_aproximada_llegada debe ser mayor que Hora_salida_base"
                recommendation = "Corregir horas o revisar si el viaje cruza día; si cruza día, capturar fecha correcta."
            elif "Origen_destino" in f or "Ruta_autorizada" in f:
                expected = "Origen/destino debe coincidir con la ruta autorizada"
                recommendation = "Verificar ruta autorizada, origen/destino y ajustar catálogo de rutas."
            else:
                expected = "Cumplir reglas de negocio del proceso"
                recommendation = "Revisar el registro y justificar el evento operativo si aplica."

        if rid == "campos_obligatorios_no_nulos":
            expected = "No debe estar vacío"
            recommendation = "Completar el campo obligatorio antes de procesar."
        if rid == "formato_placas":
            expected = "Formato de placas válido (ej. ABC-123)"
            if not recommendation:
                recommendation = "Normalizar y validar placas con regex; corregir registros inválidos."
        if rid == "formato_fecha_dd_mm_yyyy":
            expected = "Formato DD-MM-YYYY"
            if not recommendation:
                recommendation = "Normalizar fechas y corregir valores inválidos."
        if rid == "formato_hora_hh_mm":
            expected = "Formato HH:MM"
        if rid == "no_duplicidad_cliente_fecha_direccion":
            expected = "No duplicados por cliente+fecha+dirección"
            if not recommendation:
                recommendation = "Eliminar o consolidar duplicados."
        if rid == "peso_en_rango_0_35":
            expected = "Peso entre 0 y 35"
        if rid == "fecha_salida_no_futura":
            expected = "Fecha de salida no puede ser futura"
        if rid == "logica_fechas_llegada_no_menor_salida":
            expected = "Fecha de llegada >= fecha de salida"

        return expected, recommendation, error_type

    def _business_impact(self, rule_id: str, field: str) -> str:
        rid = (rule_id or "").strip().lower()
        f = (field or "").strip().lower()
        if "boton_panico" in f:
            return "Puede ocultar una emergencia operativa o alertas críticas."
        if "cambio_ruta" in f or "ruta" in f or "origen_destino" in f:
            return "Afecta control operativo, auditoría de rutas y planeación."
        if "placas" in f:
            return "Afecta trazabilidad de unidades y auditoría."
        if "hora" in f:
            return "Afecta cálculo de tiempos de entrega y cumplimiento."
        if "cp" in f or "postal" in f or "codigo_postal" in f:
            return "Afecta análisis geográfico, planeación de rutas y reportes."
        if "diesel" in f or "consumo" in f:
            return "Afecta costos operativos, eficiencia y proyecciones."
        if "duplic" in rid or "duplic" in f:
            return "Afecta reportes y puede duplicar eventos/operaciones."
        if "obligatorio" in rid or "required" in rid:
            return "Afecta integridad del dataset y procesos posteriores."
        return "Impacta calidad de datos y confiabilidad de reportes operativos."

    def _profile_csv(self, file_path: str, contract: dict) -> dict:
        max_rows = self._get_limit("REVIEWDATA_PROFILE_MAX_ROWS", 200000)
        max_samples = self._get_limit("REVIEWDATA_PROFILE_SAMPLE_ROWS", 5000)
        max_anomalies = self._get_limit("REVIEWDATA_PROFILE_MAX_ANOMALIES", 200)
        max_unique_track = self._get_limit("REVIEWDATA_PROFILE_MAX_UNIQUES", 5000)

        expected_cols = list(contract.keys())
        required_cols = [c for c, spec in contract.items() if bool(spec.get("required", False))]

        profile = {
            "rows": 0,
            "columns": [],
            "column_count": 0,
            "missing_columns": [],
            "extra_columns": [],
            "empty_counts": {},
            "unique_counts": {},
            "inferred_types": {},
            "numeric_columns": [],
            "text_columns": [],
            "date_columns": [],
            "time_columns": [],
            "categorical_columns": [],
            "anomalies": [],
            "contract_ok": False,
            "contract_issues": {},
            "quality_score": 0,
            "notes": [],
        }

        path = str(file_path or "").strip()
        if not path or not os.path.exists(path):
            profile["notes"].append("Archivo no disponible para profiling.")
            return profile

        empty_counts: dict[str, int] = {}
        unique_sets: dict[str, set] = {}
        type_counters: dict[str, dict[str, int]] = {}
        contract_issues: dict[str, dict] = {}
        anomalies: list[dict] = []

        compiled_regex: dict[str, re.Pattern] = {}
        for col, spec in contract.items():
            rx = str(spec.get("regex") or "").strip()
            if rx:
                try:
                    compiled_regex[col] = re.compile(rx)
                except Exception:
                    pass

        def add_anomaly(column: str, row_index: int | None, value: str, reason: str, severity: str):
            if len(anomalies) >= max_anomalies:
                return
            anomalies.append(
                {"column": column, "row_index": row_index, "value": value, "reason": reason, "severity": severity}
            )

        def bump_issue(column: str, key: str, extra=None):
            st = contract_issues.setdefault(column, {"invalid": 0, "reasons": {}})
            st["invalid"] = int(st.get("invalid", 0) or 0) + 1
            reasons = st.setdefault("reasons", {})
            reasons[key] = int(reasons.get(key, 0) or 0) + 1
            if extra is not None:
                st.setdefault("examples", [])
                if isinstance(st["examples"], list) and len(st["examples"]) < 5:
                    st["examples"].append(extra)

        def infer_type(col: str, raw: str):
            s = (raw or "").strip()
            if not s:
                return
            c = type_counters.setdefault(col, {})
            if _normalize_yes_no(s) is not None:
                c["si_no"] = int(c.get("si_no", 0) or 0) + 1
                return
            if re.fullmatch(r"[-+]?\d+", s):
                c["int"] = int(c.get("int", 0) or 0) + 1
                return
            if re.fullmatch(r"[-+]?\d+(\.\d+)?", s):
                c["float"] = int(c.get("float", 0) or 0) + 1
                return
            if _parse_time_any(s) is not None:
                c["time"] = int(c.get("time", 0) or 0) + 1
                return
            if _parse_date_any(s) is not None:
                c["date"] = int(c.get("date", 0) or 0) + 1
                return
            c["text"] = int(c.get("text", 0) or 0) + 1

        def validate_value(col: str, row_index: int | None, raw: str):
            spec = contract.get(col)
            if not isinstance(spec, dict):
                return
            s = (raw or "").strip()
            sev = str(spec.get("severity") or "Media")
            no_contains = spec.get("no_contains") or []
            for tok in no_contains:
                t = str(tok or "").strip()
                if t and t.lower() in s.lower():
                    bump_issue(col, "contains_forbidden", {"value": s})
                    add_anomaly(col, row_index, s, f"Contiene '{t}'", sev)
                    return
            if _looks_like_garbage(s):
                bump_issue(col, "garbage", {"value": s})
                add_anomaly(col, row_index, s, "Valor sospechoso / basura", sev)
                return
            t = str(spec.get("type") or "text").strip()
            if t == "regex":
                rx = compiled_regex.get(col)
                if rx and s and not rx.match(s.strip().upper() if col == "Placas_tracto" else s.strip()):
                    bump_issue(col, "regex", {"value": s})
                    add_anomaly(col, row_index, s, "Formato inválido", sev)
                    return
            if t == "int":
                if s and not re.fullmatch(r"[-+]?\d+", s):
                    bump_issue(col, "not_int", {"value": s})
                    add_anomaly(col, row_index, s, "Debe ser entero", sev)
                    return
                if s and "min" in spec:
                    try:
                        if int(s) < int(spec.get("min")):
                            bump_issue(col, "min", {"value": s})
                            add_anomaly(col, row_index, s, "Fuera de rango (min)", sev)
                            return
                    except Exception:
                        pass
                if s and "allowed" in spec:
                    try:
                        allowed = set(int(x) for x in (spec.get("allowed") or []))
                        if allowed and int(s) not in allowed:
                            bump_issue(col, "allowed", {"value": s})
                            add_anomaly(col, row_index, s, "Valor fuera de catálogo", sev)
                            return
                    except Exception:
                        pass
            if t == "float":
                if s and not re.fullmatch(r"[-+]?\d+(\.\d+)?", s):
                    bump_issue(col, "not_float", {"value": s})
                    add_anomaly(col, row_index, s, "Debe ser número decimal", sev)
                    return
                if s and "min" in spec:
                    try:
                        if float(s) < float(spec.get("min")):
                            bump_issue(col, "min", {"value": s})
                            add_anomaly(col, row_index, s, "Fuera de rango (min)", sev)
                            return
                    except Exception:
                        pass
            if t == "date":
                if s and _parse_date_any(s) is None:
                    bump_issue(col, "invalid_date", {"value": s})
                    add_anomaly(col, row_index, s, "Fecha inválida", sev)
                    return
                if s and _parse_date_any(s) is not None:
                    if str(spec.get("preferred_format") or "") == "YYYY-MM-DD" and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
                        bump_issue(col, "non_preferred_format", {"value": s})
            if t == "time":
                if s and _parse_time_any(s) is None:
                    bump_issue(col, "invalid_time", {"value": s})
                    add_anomaly(col, row_index, s, "Hora inválida", sev)
                    return
            if t == "si_no":
                if s and _normalize_yes_no(s) is None:
                    bump_issue(col, "invalid_si_no", {"value": s})
                    add_anomaly(col, row_index, s, "Debe ser Si/No", sev)
                    return
            if t == "route":
                if s and "-" not in s:
                    bump_issue(col, "invalid_route", {"value": s})
                    add_anomaly(col, row_index, s, "Formato esperado: Ciudad-Ciudad", sev)
                    return
            if t == "person_name":
                if s and re.search(r"\d", s):
                    bump_issue(col, "name_has_digits", {"value": s})
                    add_anomaly(col, row_index, s, "Nombre no debe contener números", sev)
                    return
                if s and _looks_like_garbage(s):
                    bump_issue(col, "garbage", {"value": s})
                    add_anomaly(col, row_index, s, "Nombre sospechoso", sev)
                    return

        try:
            with open(path, "r", newline="", encoding="utf-8-sig", errors="replace") as f:
                reader = csv.DictReader(f)
                cols = [str(c) for c in (reader.fieldnames or []) if str(c or "").strip()]
                profile["columns"] = cols
                profile["column_count"] = len(cols)
                for c in cols:
                    empty_counts[c] = 0
                    unique_sets[c] = set()
                    type_counters[c] = {}

                missing_cols = [c for c in required_cols if c not in cols]
                extra_cols = [c for c in cols if c not in expected_cols]
                profile["missing_columns"] = missing_cols
                profile["extra_columns"] = extra_cols

                folio_col = _guess_folio_column(cols) or ""
                folio_uniques: set[str] = set()

                for idx, row in enumerate(reader):
                    if idx >= max_rows:
                        profile["notes"].append(f"Profiling parcial: se procesaron solo {max_rows} filas.")
                        break
                    profile["rows"] = idx + 1
                    for c in cols:
                        raw = row.get(c)
                        txt = "" if raw is None else str(raw)
                        if _is_empty_text(txt):
                            empty_counts[c] += 1
                        else:
                            if idx < max_samples and len(unique_sets[c]) < max_unique_track:
                                unique_sets[c].add(txt.strip())
                        if idx < max_samples:
                            infer_type(c, txt)
                        if c in contract and idx < max_samples:
                            validate_value(c, idx, txt)

                    if folio_col and folio_col in row:
                        fv = str(row.get(folio_col) or "").strip()
                        if fv:
                            folio_uniques.add(fv)

                profile["folios"] = len(folio_uniques) if folio_uniques else int(profile["rows"] or 0)
        except Exception:
            profile["notes"].append("No se pudo leer el CSV para profiling.")
            return profile

        profile["empty_counts"] = dict(empty_counts)
        profile["unique_counts"] = {c: len(s) for c, s in unique_sets.items()}

        inferred: dict[str, str] = {}
        numeric_cols = []
        date_cols = []
        time_cols = []
        text_cols = []
        categorical_cols = []

        for c, counts in type_counters.items():
            if not counts:
                inferred[c] = "unknown"
                continue
            best = max(counts.items(), key=lambda kv: int(kv[1] or 0))[0]
            inferred[c] = best
        for c, t in inferred.items():
            if t in ("int", "float"):
                numeric_cols.append(c)
            elif t == "date":
                date_cols.append(c)
            elif t == "time":
                time_cols.append(c)
            else:
                text_cols.append(c)

        rows = int(profile.get("rows", 0) or 0)
        for c in profile["columns"]:
            u = int(profile["unique_counts"].get(c, 0) or 0)
            if rows > 0 and u > 0:
                if u <= 20 or (u / max(1, min(rows, max_samples))) <= 0.05:
                    categorical_cols.append(c)

        profile["inferred_types"] = inferred
        profile["numeric_columns"] = numeric_cols
        profile["date_columns"] = date_cols
        profile["time_columns"] = time_cols
        profile["text_columns"] = text_cols
        profile["categorical_columns"] = categorical_cols
        profile["anomalies"] = anomalies
        profile["contract_issues"] = contract_issues
        contract_ok = (len(profile["missing_columns"]) == 0) and (sum(int(v.get("invalid", 0) or 0) for v in contract_issues.values()) == 0)
        profile["contract_ok"] = bool(contract_ok)

        score = 100
        score -= 10 * len(profile["missing_columns"])
        for c in required_cols:
            if c in empty_counts and rows > 0:
                pct = int((empty_counts[c] / max(1, rows)) * 100)
                score -= min(10, max(0, pct // 10))
        score -= min(40, int(len(anomalies) * 0.5))
        score = max(0, min(100, int(score)))
        profile["quality_score"] = score
        return profile

    def _dataset_cache_path(self, dataset_id: str, name: str) -> str:
        safe_name = os.path.basename(str(name or "").strip()) or "dataset.csv"
        safe_name = "".join(ch if (ch.isalnum() or ch in " ._-()[]") else "_" for ch in safe_name)
        safe_name = safe_name.strip() or "dataset.csv"
        if not safe_name.lower().endswith(".csv"):
            safe_name = safe_name + ".csv"
        return os.path.join(self._storage_dir, f"{dataset_id}_{safe_name}")

    def _ensure_dataset_file(self, ds: dict) -> bool:
        path = str(ds.get("stored_path") or "")
        if path and os.path.exists(path):
            return True
        file_bytes = ds.get("file_bytes")
        dataset_id = str(ds.get("id") or "").strip()
        if file_bytes is None and self._db_enabled() and dataset_id:
            try:
                rows = self._db.fetch_all("SELECT file_bytes, name FROM datasets WHERE id = %s LIMIT 1", (dataset_id,))
                if rows and isinstance(rows[0], dict):
                    file_bytes = rows[0].get("file_bytes")
                    if not ds.get("name"):
                        ds["name"] = str(rows[0].get("name") or "dataset.csv")
                    ds["file_bytes"] = file_bytes
            except Exception:
                file_bytes = None
        if file_bytes is None:
            return False
        if isinstance(file_bytes, memoryview):
            file_bytes = file_bytes.tobytes()
        if not isinstance(file_bytes, (bytes, bytearray)):
            return False
        if not file_bytes:
            return False
        name = str(ds.get("name") or "dataset.csv")
        if not dataset_id:
            return False
        cache_path = self._dataset_cache_path(dataset_id, name)
        try:
            os.makedirs(os.path.dirname(cache_path), exist_ok=True)
            with open(cache_path, "wb") as f:
                f.write(bytes(file_bytes))
            ds["stored_path"] = cache_path
            return True
        except Exception:
            return False

    def _dataset_is_usable(self, ds: dict) -> bool:
        if not (bool(ds.get("id")) and bool(ds.get("name"))):
            return False
        if self._db_enabled():
            return True
        return (ds.get("file_bytes") is not None) or bool(ds.get("stored_path"))

    def _normalize_dataset(self, ds: dict) -> dict:
        out = dict(ds or {})
        out["id"] = str(out.get("id") or "").strip()
        out["name"] = str(out.get("name") or "").strip()
        out["type"] = str(out.get("type") or "CSV").strip() or "CSV"
        try:
            out["records"] = int(out.get("records") or 0)
        except Exception:
            out["records"] = 0
        try:
            out["folios"] = int(out.get("folios") or out.get("records") or 0)
        except Exception:
            out["folios"] = out.get("records") or 0
        out["status"] = str(out.get("status") or "Cargado")
        out["user_email"] = str(out.get("user_email") or "")
        out["stored_path"] = str(out.get("stored_path") or "")
        out["schema"] = self._parse_json(out.get("schema"), {})
        out["columns"] = self._parse_json(out.get("columns"), [])
        if not isinstance(out["columns"], list):
            out["columns"] = []
        profile_json = out.get("profile_json")
        if profile_json is not None and out.get("profile") is None:
            out["profile"] = self._parse_json(profile_json, {})
        out["profile"] = self._parse_json(out.get("profile"), {})
        contract_issues_json = out.get("contract_issues_json")
        if contract_issues_json is not None and out.get("contract_issues") is None:
            out["contract_issues"] = self._parse_json(contract_issues_json, {})
        out["contract_issues"] = self._parse_json(out.get("contract_issues"), {})
        out["contract_ok"] = bool(out.get("contract_ok", out.get("profile", {}).get("contract_ok", False)))
        try:
            out["quality_score"] = int(out.get("quality_score", out.get("profile", {}).get("quality_score", 0)) or 0)
        except Exception:
            out["quality_score"] = 0

        if not out.get("date") or not out.get("time"):
            d, t = self._format_dt(out.get("created_at"))
            if d and not out.get("date"):
                out["date"] = d
            if t and not out.get("time"):
                out["time"] = t
        return out

    def _run_is_usable(self, run: dict) -> bool:
        return bool(run.get("id")) and bool(run.get("dataset_id"))

    def _normalize_run(self, run: dict) -> dict:
        out = dict(run or {})
        out["id"] = str(out.get("id") or "").strip()
        out["dataset_id"] = str(out.get("dataset_id") or "").strip()
        out["dataset_name"] = str(out.get("dataset_name") or "")
        out["user_email"] = str(out.get("user_email") or "")
        out["date"] = str(out.get("date") or "")
        out["time"] = str(out.get("time") or "")
        try:
            out["total_records"] = int(out.get("total_records") or 0)
        except Exception:
            out["total_records"] = 0
        try:
            out["inconsistencies"] = int(out.get("inconsistencies") or 0)
        except Exception:
            out["inconsistencies"] = 0
        out["status"] = str(out.get("status") or "Completado")
        try:
            out["quality_score"] = int(out.get("quality_score") or 0)
        except Exception:
            out["quality_score"] = 0
        out["rules_applied"] = self._parse_json(out.get("rules_applied"), self._parse_json(out.get("rules_applied_json"), []))
        out["rules_passed"] = self._parse_json(out.get("rules_passed"), self._parse_json(out.get("rules_passed_json"), []))
        out["rules_failed"] = self._parse_json(out.get("rules_failed"), self._parse_json(out.get("rules_failed_json"), []))
        if not isinstance(out["rules_applied"], list):
            out["rules_applied"] = []
        if not isinstance(out["rules_passed"], list):
            out["rules_passed"] = []
        if not isinstance(out["rules_failed"], list):
            out["rules_failed"] = []
        return out

    def _normalize_finding(self, finding: dict) -> dict:
        out = dict(finding or {})
        out["id"] = str(out.get("id") or "").strip()
        out["run_id"] = str(out.get("run_id") or "").strip()
        out["dataset_id"] = str(out.get("dataset_id") or "").strip()
        out["rule_id"] = str(out.get("rule_id") or "").strip()
        out["rule_name"] = str(out.get("rule_name") or out.get("rule_id") or "")
        out["field"] = str(out.get("field") or "")
        out["value"] = str(out.get("value") or "")
        out["description"] = str(out.get("description") or "")
        out["severity"] = self._normalize_severity(str(out.get("severity") or "Alta"))
        out["date"] = str(out.get("date") or "")
        out["time"] = str(out.get("time") or "")
        out["error_type"] = str(out.get("error_type") or "")
        out["expected"] = str(out.get("expected") or "")
        out["recommendation"] = str(out.get("recommendation") or "")
        out["business_impact"] = str(out.get("business_impact") or "")
        if out.get("row_index") is None:
            out["row_index"] = None
        else:
            try:
                out["row_index"] = int(out.get("row_index"))
            except Exception:
                out["row_index"] = None
        return out

    def _normalize_report(self, report: dict) -> dict:
        out = dict(report or {})
        out["id"] = str(out.get("id") or "").strip()
        out["run_id"] = str(out.get("run_id") or "").strip()
        out["dataset_id"] = str(out.get("dataset_id") or "").strip()
        out["dataset_name"] = str(out.get("dataset_name") or "")
        out["format"] = str(out.get("format") or "PDF")
        out["status"] = str(out.get("status") or "Completado")
        out["generated_at"] = str(out.get("generated_at") or "")
        return out

    def _log_activity(self, module: str, action: str, description: str):
        email = ""
        s = self._get_session()
        if s:
            email = str(s.get("email", "") or "")
        if not email:
            email = "system"
        entry = {"user_email": email, "module": module, "action": action, "description": description, "created_at": datetime.now().isoformat()}
        if self._db_enabled():
            self._db.execute_query(
                "INSERT INTO activity_log (user_email, module, action, description) VALUES (%s, %s, %s, %s)",
                (email, module, action, description),
            )
        return entry

    def _load_from_db(self):
        if not self._db_enabled():
            return
        try:
            rules = self._db.fetch_all("SELECT id, name, description, rule_type, severity, active FROM rules ORDER BY created_at ASC")
            if not rules:
                for r in self._rules:
                    self._db.execute_query(
                        """
                        INSERT INTO rules (id, name, description, rule_type, severity, active)
                        VALUES (%s, %s, %s, %s, %s, TRUE)
                        ON CONFLICT (id) DO NOTHING
                        """,
                        (r.id, r.name, r.description, r.rule_type, r.severity),
                    )
            else:
                self._rules = [
                    type(self._rules[0])(
                        id=str(r.get("id", "")),
                        name=str(r.get("name", "")),
                        description=str(r.get("description", "")),
                        rule_type=str(r.get("rule_type", "")),
                        severity=str(r.get("severity", "")),
                    )
                    for r in rules
                ]
            raw_datasets = list(
                self._db.fetch_all(
                    """
                    SELECT id, name, type, records, folios, status, user_email, stored_path,
                           schema_json, columns_json, created_at
                    FROM datasets
                    ORDER BY created_at DESC
                    """
                )
            )
            datasets = []
            for d in raw_datasets:
                if not isinstance(d, dict):
                    continue
                schema_json = d.get("schema_json")
                columns_json = d.get("columns_json")
                d = dict(d)
                if schema_json is not None and d.get("schema") is None:
                    d["schema"] = self._parse_json(schema_json, {})
                if columns_json is not None and d.get("columns") is None:
                    d["columns"] = self._parse_json(columns_json, [])
                ds = self._normalize_dataset(d)
                datasets.append(ds)
            self._datasets = [d for d in datasets if self._dataset_is_usable(d)]

            raw_runs = list(self._db.fetch_all("SELECT * FROM runs ORDER BY created_at DESC"))
            self._runs = [self._normalize_run(r) for r in raw_runs if isinstance(r, dict)]

            raw_findings = list(self._db.fetch_all("SELECT * FROM findings ORDER BY created_at DESC"))
            self._findings = [self._normalize_finding(f) for f in raw_findings if isinstance(f, dict)]

            raw_reports = list(self._db.fetch_all("SELECT * FROM reports ORDER BY created_at DESC"))
            self._reports = [self._normalize_report(r) for r in raw_reports if isinstance(r, dict)]
        except Exception:
            return

    def get_suggested_required_columns(self) -> list[str]:
        fallback = [
            "Folio_reporte",
            "Numero_remision",
            "Numero_operador",
            "Nombre_operador",
            "Fecha_reporte",
            "Descripcion",
            "OC",
            "Origen_destino",
            "Ruta_autorizada",
            "Remitente_cliente",
        ]
        if not getattr(self._db, "conn", None):
            return list(fallback)
        rows = self._db.fetch_all(
            "SELECT column_name FROM suggested_required_columns WHERE active = TRUE ORDER BY id ASC"
        )
        if not rows:
            return list(fallback)
        return [str(r.get("column_name", "")).strip() for r in rows if str(r.get("column_name", "")).strip()]

    def authenticate(self, email: str, password: str) -> dict | None:
        session = self._auth.authenticate(email, password)
        if not session:
            return None
        self._log_activity("Login", "Autenticación", f"Inicio de sesión: {session.email}")
        return {
            "token": session.token,
            "user_id": session.user_id,
            "email": session.email,
            "expires_at": session.expires_at_iso,
            "role": session.role,
        }

    def set_session(self, token: str) -> bool:
        verified = self._auth.verify_token(token)
        if not verified:
            self._set_session(None)
            return False
        self._set_session(
            {
            "token": verified.token,
            "user_id": verified.user_id,
            "email": verified.email,
            "expires_at": verified.expires_at_iso,
            "role": verified.role,
            }
        )
        return True

    def get_current_user(self) -> dict | None:
        s = self._get_session()
        return dict(s) if s else None

    def _require_session(self) -> dict:
        session = self._get_session()
        if not session:
            raise ValueError("Sesión no válida. Inicia sesión para continuar.")
        verified = self._auth.verify_token(session.get("token", ""))
        if not verified:
            self._set_session(None)
            raise ValueError("Sesión expirada o token inválido. Inicia sesión nuevamente.")
        session = dict(session)
        session["role"] = verified.role
        self._set_session(session)
        return session

    def get_datasets_page(self, offset: int = 0, limit: int = 200) -> dict:
        off = max(0, int(offset or 0))
        lim = max(1, min(2000, int(limit or 200)))
        if self._db_enabled():
            total_rows = self._db.fetch_all("SELECT COUNT(*) AS n FROM datasets")
            total = int((total_rows[0].get("n") if total_rows and isinstance(total_rows[0], dict) else 0) or 0)
            rows = self._db.fetch_all(
                """
                SELECT id, name, type, records, folios, status, user_email, stored_path,
                       contract_ok, quality_score, created_at
                FROM datasets
                ORDER BY created_at DESC
                OFFSET %s LIMIT %s
                """,
                (off, lim),
            )
            items = [self._normalize_dataset(r) for r in rows if isinstance(r, dict)]
            return {"items": items, "total": total, "offset": off, "limit": lim}

        rows = list(self._datasets)
        total = len(rows)
        return {"items": rows[off : off + lim], "total": total, "offset": off, "limit": lim}

    def get_all_datasets(self) -> list:
        if self._db_enabled():
            limit = self._get_limit("REVIEWDATA_DB_MAX_DATASETS", 2000)
            raw_datasets = list(
                self._db.fetch_all(
                    """
                    SELECT id, name, type, records, folios, status, user_email, stored_path,
                           schema_json, columns_json, profile_json, contract_ok, contract_issues_json, quality_score, created_at
                    FROM datasets
                    ORDER BY created_at DESC
                    LIMIT %s
                    """
                    ,
                    (int(limit),),
                )
            )
            datasets = []
            for d in raw_datasets:
                if not isinstance(d, dict):
                    continue
                schema_json = d.get("schema_json")
                columns_json = d.get("columns_json")
                d = dict(d)
                if schema_json is not None and d.get("schema") is None:
                    d["schema"] = self._parse_json(schema_json, {})
                if columns_json is not None and d.get("columns") is None:
                    d["columns"] = self._parse_json(columns_json, [])
                profile_json = d.get("profile_json")
                if profile_json is not None and d.get("profile") is None:
                    d["profile"] = self._parse_json(profile_json, {})
                contract_issues_json = d.get("contract_issues_json")
                if contract_issues_json is not None and d.get("contract_issues") is None:
                    d["contract_issues"] = self._parse_json(contract_issues_json, {})
                ds = self._normalize_dataset(d)
                if self._dataset_is_usable(ds):
                    datasets.append(ds)
            self._datasets = list(datasets)
            return list(datasets)
        return list(self._datasets)

    def _get_dataset_meta(self, dataset_id: str) -> dict | None:
        did = str(dataset_id or "").strip()
        if not did:
            return None
        ds = next((d for d in self._datasets if str(d.get("id") or "") == did), None)
        if ds:
            return dict(ds)
        if self._db_enabled():
            rows = self._db.fetch_all(
                "SELECT id, name, stored_path, file_bytes, created_at FROM datasets WHERE id = %s LIMIT 1",
                (did,),
            )
            if rows and isinstance(rows[0], dict):
                return dict(rows[0])
        return None

    def get_dataset_columns(self, dataset_id: str) -> list[str]:
        did = str(dataset_id or "").strip()
        if not did:
            return []
        if self._db_enabled():
            rows = self._db.fetch_all("SELECT columns_json FROM datasets WHERE id = %s LIMIT 1", (did,))
            if rows and isinstance(rows[0], dict):
                cols = self._parse_json(rows[0].get("columns_json"), [])
                if isinstance(cols, list):
                    return [str(c) for c in cols if str(c)]
            return []
        ds = next((d for d in self._datasets if d["id"] == did), None)
        if not ds:
            return []
        return list(ds.get("columns", []))

    def import_dataset(self, file_path: str, schema: dict, original_filename: str | None = None) -> dict:
        session = self._require_session()
        name = os.path.basename(original_filename or file_path)
        ext = name.split(".")[-1].lower()
        if ext != "csv":
            raise ValueError("Solo se aceptan archivos CSV.")

        try:
            with open(file_path, "rb") as f:
                file_bytes = f.read()
        except Exception:
            file_bytes = None

        contract = self._get_contract()
        profile = self._profile_csv(file_path, contract)
        columns = [str(c) for c in (profile.get("columns") or [])]
        try:
            records = int(profile.get("rows") or 0)
        except Exception:
            records = 0
        try:
            folios = int(profile.get("folios") or records or 0)
        except Exception:
            folios = records
        required_columns = [c for c, spec in contract.items() if bool((spec or {}).get("required", False))]
        date_columns = [c for c, spec in contract.items() if str((spec or {}).get("type") or "") == "date"]
        time_columns = [c for c, spec in contract.items() if str((spec or {}).get("type") or "") == "time"]

        now = datetime.now()
        dataset_id = str(uuid.uuid4())
        safe_name = os.path.basename(str(name or "dataset.csv"))
        safe_name = "".join(ch if (ch.isalnum() or ch in " ._-()[]") else "_" for ch in safe_name).strip() or "dataset.csv"
        if not safe_name.lower().endswith(".csv"):
            safe_name = safe_name + ".csv"
        stamp = now.strftime("%Y%m%d_%H%M%S")
        stored_name = f"{stamp}_{dataset_id[:8]}_{safe_name}"
        stored_path = os.path.join(self._storage_dir, stored_name)
        shutil.copyfile(file_path, stored_path)
        dataset = {
            "id": dataset_id,
            "name": f"{stamp}_{safe_name}",
            "type": "CSV",
            "records": records,
            "folios": folios,
            "date": now.strftime("%d-%m-%Y"),
            "time": now.strftime("%H:%M"),
            "status": "Cargado",
            "user_email": session.get("email", ""),
            "stored_path": stored_path,
            "schema": {"required_columns": required_columns, "date_columns": date_columns, "time_columns": time_columns},
            "columns": columns,
            "file_bytes": file_bytes,
            "profile": profile,
            "contract_ok": bool(profile.get("contract_ok", False)),
            "contract_issues": profile.get("contract_issues", {}),
            "quality_score": int(profile.get("quality_score", 0) or 0),
        }
        self._datasets.insert(0, dataset)
        self._log_activity("Datasets", "Carga", f"Dataset cargado: {dataset['name']} ({dataset_id[:8]})")
        if self._db_enabled():
            self._db.execute_query(
                """
                INSERT INTO datasets (id, name, type, records, folios, status, user_email, stored_path, schema_json, columns_json, file_bytes, profile_json, contract_ok, contract_issues_json, quality_score)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO NOTHING
                """,
                (
                    dataset_id,
                    dataset["name"],
                    "CSV",
                    records,
                    folios,
                    "Cargado",
                    session.get("email", ""),
                    stored_path,
                    json.dumps(dataset["schema"], ensure_ascii=False),
                    json.dumps(columns, ensure_ascii=False),
                    file_bytes,
                    json.dumps(profile, ensure_ascii=False),
                    bool(profile.get("contract_ok", False)),
                    json.dumps(profile.get("contract_issues", {}), ensure_ascii=False),
                    int(profile.get("quality_score", 0) or 0),
                ),
            )
            try:
                self._upsert_suggested_expectations(dataset_id, profile)
            except Exception:
                pass
        return dict(dataset)

    def get_rules(self) -> list[dict]:
        if self._db_enabled():
            rows = self._db.fetch_all("SELECT id, name, description, rule_type, severity, active FROM rules ORDER BY created_at ASC")
            if rows:
                return [
                    {
                        "id": str(r.get("id", "")),
                        "name": str(r.get("name", "")),
                        "description": str(r.get("description", "")),
                        "type": str(r.get("rule_type", "")),
                        "severity": str(r.get("severity", "")),
                        "active": bool(r.get("active", True)),
                    }
                    for r in rows
                ]
        return [{"id": r.id, "name": r.name, "description": r.description, "type": r.rule_type, "severity": r.severity, "active": True} for r in self._rules]

    def _validate_contract_df(self, df, contract: dict) -> list[ValidationFinding]:
        max_findings = self._get_limit("REVIEWDATA_VALIDATION_MAX_FINDINGS", 5000)
        findings: list[ValidationFinding] = []
        compiled: dict[str, re.Pattern] = {}
        for col, spec in contract.items():
            rx = str((spec or {}).get("regex") or "").strip()
            if rx:
                try:
                    compiled[col] = re.compile(rx)
                except Exception:
                    pass

        for col, spec in contract.items():
            if len(findings) >= max_findings:
                break
            spec = spec or {}
            required = bool(spec.get("required", False))
            severity = self._normalize_severity(str(spec.get("severity") or "Alta"))
            col_type = str(spec.get("type") or "text")
            no_contains = spec.get("no_contains") or []

            if col not in df.columns:
                if required:
                    findings.append(
                        ValidationFinding(
                            rule_id="contrato_csv_viajes",
                            field=col,
                            value="",
                            description=f"Columna obligatoria no existe: {col}",
                            severity=severity,
                            row_index=None,
                        )
                    )
                continue

            series = df[col]
            for idx, v in series.items():
                if len(findings) >= max_findings:
                    break
                text = "" if v is None else str(v).strip()
                if required and _is_empty_text(text):
                    findings.append(
                        ValidationFinding(
                            rule_id="contrato_csv_viajes",
                            field=col,
                            value="",
                            description="Campo obligatorio vacío o nulo",
                            severity=severity,
                            row_index=int(idx),
                        )
                    )
                    continue
                if _is_empty_text(text):
                    continue
                for tok in no_contains:
                    t = str(tok or "").strip()
                    if t and t.lower() in text.lower():
                        findings.append(
                            ValidationFinding(
                                rule_id="contrato_csv_viajes",
                                field=col,
                                value=text,
                                description=f"Contiene valor prohibido: {t}",
                                severity=severity,
                                row_index=int(idx),
                            )
                        )
                        break
                if findings and findings[-1].row_index == int(idx) and findings[-1].field == col and "prohibido" in findings[-1].description:
                    continue
                if _looks_like_garbage(text):
                    findings.append(
                        ValidationFinding(
                            rule_id="contrato_csv_viajes",
                            field=col,
                            value=text,
                            description="Valor sospechoso / basura",
                            severity=severity,
                            row_index=int(idx),
                        )
                    )
                    continue

                if col_type == "regex":
                    rx = compiled.get(col)
                    check = text.upper() if col == "Placas_tracto" else text
                    if rx and not rx.match(check):
                        findings.append(
                            ValidationFinding(
                                rule_id="contrato_csv_viajes",
                                field=col,
                                value=text,
                                description="Formato inválido",
                                severity=severity,
                                row_index=int(idx),
                            )
                        )
                        continue
                if col_type == "int":
                    if not re.fullmatch(r"[-+]?\d+", text):
                        findings.append(
                            ValidationFinding(
                                rule_id="contrato_csv_viajes",
                                field=col,
                                value=text,
                                description="Debe ser entero",
                                severity=severity,
                                row_index=int(idx),
                            )
                        )
                        continue
                    if "min" in spec:
                        try:
                            if int(text) < int(spec.get("min")):
                                findings.append(
                                    ValidationFinding(
                                        rule_id="contrato_csv_viajes",
                                        field=col,
                                        value=text,
                                        description="Fuera de rango (min)",
                                        severity=severity,
                                        row_index=int(idx),
                                    )
                                )
                                continue
                        except Exception:
                            pass
                    if "allowed" in spec:
                        try:
                            allowed = set(int(x) for x in (spec.get("allowed") or []))
                            if allowed and int(text) not in allowed:
                                findings.append(
                                    ValidationFinding(
                                        rule_id="contrato_csv_viajes",
                                        field=col,
                                        value=text,
                                        description="Valor fuera de catálogo",
                                        severity=severity,
                                        row_index=int(idx),
                                    )
                                )
                                continue
                        except Exception:
                            pass
                if col_type == "float":
                    if not re.fullmatch(r"[-+]?\d+(\.\d+)?", text):
                        findings.append(
                            ValidationFinding(
                                rule_id="contrato_csv_viajes",
                                field=col,
                                value=text,
                                description="Debe ser número decimal",
                                severity=severity,
                                row_index=int(idx),
                            )
                        )
                        continue
                    if "min" in spec:
                        try:
                            if float(text) < float(spec.get("min")):
                                findings.append(
                                    ValidationFinding(
                                        rule_id="contrato_csv_viajes",
                                        field=col,
                                        value=text,
                                        description="Fuera de rango (min)",
                                        severity=severity,
                                        row_index=int(idx),
                                    )
                                )
                                continue
                        except Exception:
                            pass
                if col_type == "date":
                    parsed = _parse_date_any(text)
                    if parsed is None:
                        findings.append(
                            ValidationFinding(
                                rule_id="contrato_csv_viajes",
                                field=col,
                                value=text,
                                description="Fecha inválida",
                                severity=severity,
                                row_index=int(idx),
                            )
                        )
                        continue
                    if str(spec.get("preferred_format") or "") == "YYYY-MM-DD" and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
                        findings.append(
                            ValidationFinding(
                                rule_id="contrato_csv_viajes",
                                field=col,
                                value=text,
                                description="Formato no recomendado (sugerir YYYY-MM-DD)",
                                severity="Media",
                                row_index=int(idx),
                            )
                        )
                        continue
                if col_type == "time":
                    if _parse_time_any(text) is None:
                        findings.append(
                            ValidationFinding(
                                rule_id="contrato_csv_viajes",
                                field=col,
                                value=text,
                                description="Hora inválida",
                                severity=severity,
                                row_index=int(idx),
                            )
                        )
                        continue
                if col_type == "si_no":
                    if _normalize_yes_no(text) is None:
                        findings.append(
                            ValidationFinding(
                                rule_id="contrato_csv_viajes",
                                field=col,
                                value=text,
                                description="Debe ser Si/No",
                                severity=severity,
                                row_index=int(idx),
                            )
                        )
                        continue
                if col_type == "route":
                    if "-" not in text:
                        findings.append(
                            ValidationFinding(
                                rule_id="contrato_csv_viajes",
                                field=col,
                                value=text,
                                description="Formato esperado: Ciudad-Ciudad",
                                severity=severity,
                                row_index=int(idx),
                            )
                        )
                        continue
                if col_type == "person_name":
                    if re.search(r"\d", text):
                        findings.append(
                            ValidationFinding(
                                rule_id="contrato_csv_viajes",
                                field=col,
                                value=text,
                                description="Nombre no debe contener números",
                                severity=severity,
                                row_index=int(idx),
                            )
                        )
                        continue
        return findings

    def _get_ai_expectation_rules(self, rule_ids: list[str]) -> list[dict]:
        if not self._db_enabled():
            return []
        ids = [str(x or "").strip() for x in (rule_ids or []) if str(x or "").strip()]
        if not ids:
            return []
        rows = self._db.fetch_all(
            "SELECT id, name, description, rule_type, severity, active, parameters_json FROM rules WHERE id = ANY(%s::text[])",
            (ids,),
        )
        out = []
        for r in rows or []:
            if not isinstance(r, dict):
                continue
            if not bool(r.get("active", True)):
                continue
            if str(r.get("rule_type") or "").strip() != "ai_expectation":
                continue
            out.append(
                {
                    "id": str(r.get("id") or ""),
                    "name": str(r.get("name") or ""),
                    "description": str(r.get("description") or ""),
                    "severity": self._normalize_severity(str(r.get("severity") or "Media")),
                    "parameters": self._parse_json(r.get("parameters_json"), {}),
                }
            )
        return out

    def _apply_ai_expectation_rule(self, df, rule: dict) -> list[ValidationFinding]:
        params = rule.get("parameters") or {}
        if not isinstance(params, dict):
            params = {}
        et = str(params.get("expectation_type") or "").strip()
        col = str(params.get("column_name") or "").strip()
        if not et or not col:
            return []
        if col not in df.columns:
            return []
        sev = self._normalize_severity(str(rule.get("severity") or "Media"))
        max_findings = self._get_limit("REVIEWDATA_VALIDATION_MAX_FINDINGS", 5000)
        findings: list[ValidationFinding] = []

        def is_empty(v) -> bool:
            try:
                return _is_empty_text("" if v is None else str(v))
            except Exception:
                return True

        if et == "non_null":
            for idx, v in df[col].items():
                if len(findings) >= max_findings:
                    break
                if is_empty(v):
                    findings.append(
                        ValidationFinding(
                            rule_id=str(rule.get("id") or ""),
                            field=col,
                            value="",
                            description="Campo requerido vacío o nulo (AI expectation)",
                            severity=sev,
                            row_index=int(idx),
                        )
                    )
            return findings

        if et == "regex":
            rx = str(params.get("regex") or "").strip()
            if not rx:
                return []
            try:
                compiled = re.compile(rx)
            except Exception:
                return []
            ignore_empty = bool(params.get("ignore_empty", True))
            for idx, v in df[col].items():
                if len(findings) >= max_findings:
                    break
                s = "" if v is None else str(v).strip()
                if ignore_empty and not s:
                    continue
                if s and not compiled.match(s):
                    findings.append(
                        ValidationFinding(
                            rule_id=str(rule.get("id") or ""),
                            field=col,
                            value=s,
                            description=f"Formato inválido (AI expectation): {rx}",
                            severity=sev,
                            row_index=int(idx),
                        )
                    )
            return findings

        if et == "allowed_values":
            allowed = params.get("allowed_values")
            if not isinstance(allowed, list) or not allowed:
                return []
            allowed_set = {str(x) for x in allowed if str(x)}
            ignore_empty = bool(params.get("ignore_empty", True))
            for idx, v in df[col].items():
                if len(findings) >= max_findings:
                    break
                s = "" if v is None else str(v).strip()
                if ignore_empty and not s:
                    continue
                if s and s not in allowed_set:
                    findings.append(
                        ValidationFinding(
                            rule_id=str(rule.get("id") or ""),
                            field=col,
                            value=s,
                            description="Valor fuera de catálogo (AI expectation)",
                            severity=sev,
                            row_index=int(idx),
                        )
                    )
            return findings

        if et == "unique":
            series = df[col].astype(str).fillna("").map(lambda x: x.strip())
            series = series[series != ""]
            dup = series[series.duplicated(keep=False)]
            if dup.empty:
                return []
            for idx, v in dup.items():
                if len(findings) >= max_findings:
                    break
                findings.append(
                    ValidationFinding(
                        rule_id=str(rule.get("id") or ""),
                        field=col,
                        value=str(v),
                        description="Valor duplicado (AI expectation UNIQUE)",
                        severity=sev,
                        row_index=int(idx),
                    )
                )
            return findings

        if et == "numeric_range":
            mn = params.get("min")
            mx = params.get("max")
            try:
                mn_f = float(mn) if mn is not None else None
            except Exception:
                mn_f = None
            try:
                mx_f = float(mx) if mx is not None else None
            except Exception:
                mx_f = None
            if mn_f is None and mx_f is None:
                return []
            series = df[col]
            import pandas as pd

            nums = pd.to_numeric(series, errors="coerce")
            for idx, v in nums.items():
                if len(findings) >= max_findings:
                    break
                if pd.isna(v):
                    continue
                if mn_f is not None and float(v) < mn_f:
                    findings.append(
                        ValidationFinding(
                            rule_id=str(rule.get("id") or ""),
                            field=col,
                            value=str(series.at[idx]),
                            description=f"Fuera de rango (min {mn_f}) (AI expectation)",
                            severity=sev,
                            row_index=int(idx),
                        )
                    )
                    continue
                if mx_f is not None and float(v) > mx_f:
                    findings.append(
                        ValidationFinding(
                            rule_id=str(rule.get("id") or ""),
                            field=col,
                            value=str(series.at[idx]),
                            description=f"Fuera de rango (max {mx_f}) (AI expectation)",
                            severity=sev,
                            row_index=int(idx),
                        )
                    )
            return findings

        return []

    def _compute_dataset_health(self, findings: list[ValidationFinding], total_records: int) -> dict:
        total = max(1, int(total_records or 0))
        weights = {"Crítica": 10, "Alta": 5, "Media": 2, "Baja": 1}
        counts = {"Crítica": 0, "Alta": 0, "Media": 0, "Baja": 0}
        penalty = 0
        affected_rows: set[int] = set()
        structural = 0
        for f in findings:
            sev = self._normalize_severity(str(getattr(f, "severity", "") or "Alta"))
            counts[sev] = int(counts.get(sev, 0) or 0) + 1
            penalty += int(weights.get(sev, 5))
            ri = getattr(f, "row_index", None)
            if ri is None:
                structural += 1
            else:
                try:
                    affected_rows.add(int(ri))
                except Exception:
                    pass

        base = penalty / float(total)
        structural_pen = 0.0
        if structural:
            structural_pen = min(20.0, structural * 2.5)
        row_pen = min(35.0, (len(affected_rows) / float(total)) * 35.0)
        score = int(round(100.0 - (base + structural_pen + row_pen)))
        score = max(0, min(100, score))

        grade = "Crítico"
        if score >= 90:
            grade = "Excelente"
        elif score >= 75:
            grade = "Bueno"
        elif score >= 60:
            grade = "Riesgo"

        explanation = {
            "penalty_per_row": round(base, 2),
            "structural_penalty": round(structural_pen, 2),
            "affected_rows_pct": int(round((len(affected_rows) / float(total)) * 100.0)),
            "counts": counts,
        }
        return {"score": score, "grade": grade, "explanation": explanation, "counts": counts}

    def _validate_business_rules_df(self, df) -> list[ValidationFinding]:
        max_findings = self._get_limit("REVIEWDATA_VALIDATION_MAX_FINDINGS", 5000)
        findings: list[ValidationFinding] = []

        def col_text(col: str, v) -> str:
            return "" if v is None else str(v).strip()

        panic_col = "Boton_panico"
        if panic_col in df.columns:
            for idx, v in df[panic_col].items():
                if len(findings) >= max_findings:
                    break
                yn = _normalize_yes_no(col_text(panic_col, v))
                if yn == "Si":
                    findings.append(
                        ValidationFinding(
                            rule_id="reglas_negocio_viajes",
                            field=panic_col,
                            value="Si",
                            description="Botón pánico activado",
                            severity="Cr\u00edtica",
                            row_index=int(idx),
                        )
                    )

        change_route_col = "Cambio_ruta"
        if change_route_col in df.columns:
            for idx, v in df[change_route_col].items():
                if len(findings) >= max_findings:
                    break
                yn = _normalize_yes_no(col_text(change_route_col, v))
                if yn == "Si":
                    findings.append(
                        ValidationFinding(
                            rule_id="reglas_negocio_viajes",
                            field=change_route_col,
                            value="Si",
                            description="Cambio de ruta detectado (evento operativo)",
                            severity="Alta",
                            row_index=int(idx),
                        )
                    )

        emerg_col = "Cambio_operador_emergencia"
        if emerg_col in df.columns:
            for idx, v in df[emerg_col].items():
                if len(findings) >= max_findings:
                    break
                yn = _normalize_yes_no(col_text(emerg_col, v))
                if yn == "Si":
                    findings.append(
                        ValidationFinding(
                            rule_id="reglas_negocio_viajes",
                            field=emerg_col,
                            value="Si",
                            description="Cambio de operador por emergencia",
                            severity="Alta",
                            row_index=int(idx),
                        )
                    )

        hs_col = "Hora_salida_base"
        hl_col = "Hora_aproximada_llegada"
        if hs_col in df.columns and hl_col in df.columns:
            for idx in df.index:
                if len(findings) >= max_findings:
                    break
                hs = _parse_time_any(col_text(hs_col, df.at[idx, hs_col]))
                hl = _parse_time_any(col_text(hl_col, df.at[idx, hl_col]))
                if hs is None or hl is None:
                    continue
                if hl <= hs:
                    findings.append(
                        ValidationFinding(
                            rule_id="reglas_negocio_viajes",
                            field=f"{hs_col},{hl_col}",
                            value=f"{df.at[idx, hs_col]} -> {df.at[idx, hl_col]}",
                            description="Hora de llegada debe ser posterior a hora de salida",
                            severity="Alta",
                            row_index=int(idx),
                        )
                    )

        od_col = "Origen_destino"
        ra_col = "Ruta_autorizada"
        if od_col in df.columns and ra_col in df.columns:
            for idx in df.index:
                if len(findings) >= max_findings:
                    break
                od = col_text(od_col, df.at[idx, od_col])
                ra = col_text(ra_col, df.at[idx, ra_col])
                if not od or not ra:
                    continue
                if "-" not in ra:
                    continue
                if od.lower() not in ra.lower():
                    findings.append(
                        ValidationFinding(
                            rule_id="reglas_negocio_viajes",
                            field=f"{od_col},{ra_col}",
                            value=f"{od} | {ra}",
                            description="Origen/destino no coincide con ruta autorizada (heurístico)",
                            severity="Media",
                            row_index=int(idx),
                        )
                    )

        return findings

    def run_validation(self, dataset_id: str, rule_ids: list[str], mapping: dict) -> dict:
        session = self._require_session()
        did = str(dataset_id or "").strip()
        ds = next((d for d in self._datasets if d["id"] == did), None)
        if not ds and self._db_enabled() and did:
            rows = self._db.fetch_all(
                "SELECT id, name, type, records, folios, status, user_email, stored_path, schema_json, columns_json, file_bytes, created_at FROM datasets WHERE id = %s LIMIT 1",
                (did,),
            )
            if rows and isinstance(rows[0], dict):
                raw = dict(rows[0])
                if raw.get("schema") is None and raw.get("schema_json") is not None:
                    raw["schema"] = self._parse_json(raw.get("schema_json"), {})
                if raw.get("columns") is None and raw.get("columns_json") is not None:
                    raw["columns"] = self._parse_json(raw.get("columns_json"), [])
                ds = self._normalize_dataset(raw)
        if not ds:
            raise ValueError("Dataset no encontrado.")

        self._ensure_dataset_file(ds)
        dataset_path = str(ds.get("stored_path") or "")
        if not dataset_path or not os.path.exists(dataset_path):
            raise ValueError("Archivo del dataset no disponible en la BD. Vuelve a cargar el dataset para almacenarlo en PostgreSQL.")

        import pandas as pd

        df = pd.read_csv(dataset_path)
        now = datetime.now()
        run_id = str(uuid.uuid4())
        selected = set(rule_ids or [])
        skipped_rules: list[dict] = []

        def col_ok(col: str | None) -> bool:
            c = str(col or "").strip()
            return bool(c) and c in df.columns

        def skip_rule(rule_id: str, reason: str) -> None:
            if rule_id in selected:
                selected.discard(rule_id)
                skipped_rules.append({"rule_id": rule_id, "reason": reason})

        if "conductor_asignado" in selected and not col_ok(mapping.get("conductor_col")):
            skip_rule("conductor_asignado", "Falta mapear columna de conductor")
        if "carta_porte_existente" in selected and not col_ok(mapping.get("carta_porte_col")):
            skip_rule("carta_porte_existente", "Falta mapear columna de Carta Porte")
        if "no_duplicidad_cliente_fecha_direccion" in selected:
            if not col_ok(mapping.get("cliente_col")) or not col_ok(mapping.get("fecha_col")) or not col_ok(mapping.get("direccion_col")):
                skip_rule("no_duplicidad_cliente_fecha_direccion", "Falta mapear columnas (cliente/fecha/dirección)")
        if "formato_numero_empleado" in selected and not col_ok(mapping.get("empleado_col")):
            skip_rule("formato_numero_empleado", "Falta mapear columna de número de empleado")
        if "formato_placas" in selected and not col_ok(mapping.get("placas_col")):
            skip_rule("formato_placas", "Falta mapear columna de placas")
        if "formato_fecha_dd_mm_yyyy" in selected:
            date_columns = mapping.get("date_columns") or []
            date_columns = [c for c in list(date_columns) if col_ok(str(c))]
            if not date_columns:
                skip_rule("formato_fecha_dd_mm_yyyy", "Falta mapear columnas de fecha")
            else:
                mapping = dict(mapping or {})
                mapping["date_columns"] = date_columns
        if "peso_en_rango_0_35" in selected and not col_ok(mapping.get("peso_col")):
            skip_rule("peso_en_rango_0_35", "Falta mapear columna de peso")
        if "fecha_salida_no_futura" in selected and not col_ok(mapping.get("fecha_salida_col")):
            skip_rule("fecha_salida_no_futura", "Falta mapear columna de fecha de salida")
        if "logica_fechas_llegada_no_menor_salida" in selected:
            if not col_ok(mapping.get("fecha_salida_col")) or not col_ok(mapping.get("fecha_llegada_col")):
                skip_rule("logica_fechas_llegada_no_menor_salida", "Falta mapear columnas (fecha salida/fecha llegada)")

        schema = ds.get("schema", {}) or {}
        required_columns = mapping.get("required_columns") or schema.get("required_columns", [])
        date_columns = mapping.get("date_columns") or schema.get("date_columns", [])

        findings = []
        if "campos_obligatorios_no_nulos" in selected:
            findings.extend(validate_campos_obligatorios(df, list(required_columns)))
        if "conductor_asignado" in selected:
            findings.extend(validate_conductor_asignado(df, mapping.get("conductor_col")))
        if "carta_porte_existente" in selected:
            findings.extend(validate_carta_porte(df, mapping.get("carta_porte_col")))
        if "no_duplicidad_cliente_fecha_direccion" in selected:
            findings.extend(validate_no_duplicidad(df, mapping.get("cliente_col"), mapping.get("fecha_col"), mapping.get("direccion_col")))
        if "formato_numero_empleado" in selected:
            findings.extend(validate_formato_numero_empleado(df, mapping.get("empleado_col")))
        if "formato_placas" in selected:
            findings.extend(validate_formato_placas(df, mapping.get("placas_col"), mapping.get("placas_regex")))
        if "formato_fecha_dd_mm_yyyy" in selected:
            findings.extend(validate_formato_fechas(df, list(date_columns)))
        if "peso_en_rango_0_35" in selected:
            findings.extend(validate_peso_rango(df, mapping.get("peso_col")))
        if "fecha_salida_no_futura" in selected:
            findings.extend(validate_fecha_salida_no_futura(df, mapping.get("fecha_salida_col")))
        if "logica_fechas_llegada_no_menor_salida" in selected:
            findings.extend(validate_logica_fechas(df, mapping.get("fecha_salida_col"), mapping.get("fecha_llegada_col")))
        if "contrato_csv_viajes" in selected:
            findings.extend(self._validate_contract_df(df, self._get_contract()))
        if "reglas_negocio_viajes" in selected:
            findings.extend(self._validate_business_rules_df(df))
        ai_rules = self._get_ai_expectation_rules(list(selected))
        for rr in ai_rules:
            findings.extend(self._apply_ai_expectation_rule(df, rr))

        rules_applied_input = list(dict.fromkeys(list(rule_ids or [])))
        rules_applied = [rid for rid in rules_applied_input if rid in selected]
        failed_ids = {f.rule_id for f in findings}
        rules_failed = [rid for rid in rules_applied if rid in failed_ids]
        rules_passed = [rid for rid in rules_applied if rid not in failed_ids]

        health = self._compute_dataset_health(findings, int(len(df)))
        quality_score = int(health.get("score") or 0)
        quality_grade = str(health.get("grade") or "")
        health_explanation = health.get("explanation") or {}

        run = {
            "id": run_id,
            "dataset_id": dataset_id,
            "dataset_name": ds["name"],
            "user_email": session.get("email", ""),
            "date": now.strftime("%d-%m-%Y"),
            "time": now.strftime("%H:%M"),
            "total_records": int(len(df)),
            "inconsistencies": int(len(findings)),
            "quality_score": quality_score,
            "quality_grade": quality_grade,
            "health_explanation": health_explanation,
            "rules_applied": list(rules_applied),
            "rules_passed": list(rules_passed),
            "rules_failed": list(rules_failed),
            "rules_skipped": list(skipped_rules),
            "status": "Completado",
        }
        self._runs.insert(0, run)
        self._log_activity("Validaciones", "Ejecución", f"Validación ejecutada: {ds['name']} ({run_id[:8]})")
        if self._db_enabled():
            self._db.execute_query(
                """
                INSERT INTO runs (id, dataset_id, dataset_name, user_email, date, time, total_records, inconsistencies, quality_score, rules_applied_json, rules_passed_json, rules_failed_json, status)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO NOTHING
                """,
                (
                    run_id,
                    dataset_id,
                    ds["name"],
                    session.get("email", ""),
                    run["date"],
                    run["time"],
                    run["total_records"],
                    run["inconsistencies"],
                    int(run["quality_score"]),
                    json.dumps(run["rules_applied"], ensure_ascii=False),
                    json.dumps(run["rules_passed"], ensure_ascii=False),
                    json.dumps(run["rules_failed"], ensure_ascii=False),
                    run["status"],
                ),
            )

        rule_name = {r["id"]: r["name"] for r in self.get_rules()}
        for f in findings:
            finding_id = str(uuid.uuid4())
            expected = ""
            recommendation = ""
            error_type = ""
            business_impact = ""
            try:
                rid = str(getattr(f, "rule_id", "") or "")
                field = str(getattr(f, "field", "") or "")
                desc = str(getattr(f, "description", "") or "")
                val = str(getattr(f, "value", "") or "")
                expected, recommendation, error_type = self._explain_finding(rid, field, desc, val)
                business_impact = self._business_impact(rid, field)
            except Exception:
                expected, recommendation, error_type, business_impact = "", "", "", ""
            row = {
                "id": finding_id,
                "run_id": run_id,
                "dataset_id": dataset_id,
                "rule_id": f.rule_id,
                "rule_name": rule_name.get(f.rule_id, f.rule_id),
                "field": f.field,
                "value": f.value,
                "description": f.description,
                "severity": f.severity,
                "error_type": error_type,
                "expected": expected,
                "recommendation": recommendation,
                "business_impact": business_impact,
                "date": now.strftime("%d-%m-%Y"),
                "time": now.strftime("%H:%M"),
                "row_index": f.row_index,
            }
            self._findings.append(row)
            if self._db_enabled():
                self._db.execute_query(
                    """
                    INSERT INTO findings (id, run_id, dataset_id, rule_id, rule_name, field, value, description, severity, error_type, expected, recommendation, business_impact, date, time, row_index)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (id) DO NOTHING
                    """,
                    (
                        finding_id,
                        run_id,
                        dataset_id,
                        row["rule_id"],
                        row["rule_name"],
                        row["field"],
                        str(row["value"]),
                        row["description"],
                        row["severity"],
                        row["error_type"],
                        row["expected"],
                        row["recommendation"],
                        row["business_impact"],
                        row["date"],
                        row["time"],
                        row["row_index"],
                    ),
                )
        try:
            if self._db_enabled():
                self._persist_ai_post_run(run, list(findings))
        except Exception:
            pass
        auto_pdf = (os.environ.get("REVIEWDATA_AUTO_PDF_ON_VALIDATE") or "").strip()
        if not auto_pdf:
            auto_pdf = "1"
        if auto_pdf not in ("0", "false", "no", "off"):
            pdf_path = (os.environ.get("REVIEWDATA_VALIDATION_PDF_PATH") or "").strip()
            if not pdf_path and os.name == "nt":
                pdf_path = r"c:\Users\domin\Documents\trae_projects\pro\Reporte_Inconsistencias_Final.pdf"
            if pdf_path:
                try:
                    os.makedirs(os.path.dirname(pdf_path), exist_ok=True)
                except Exception:
                    pass
                try:
                    self.export_run_pdf(run_id, pdf_path)
                    run["pdf_generated"] = True
                    run["pdf_path"] = pdf_path
                except Exception as e:
                    run["pdf_generated"] = False
                    run["pdf_error"] = str(e)
        return dict(run)

    def get_runs(self, dataset_id: str | None = None) -> list[dict]:
        if self._db_enabled():
            limit = self._get_limit("REVIEWDATA_DB_MAX_RUNS", 2000)
            if dataset_id:
                rows = self._db.fetch_all(
                    """
                    SELECT id, dataset_id, dataset_name, user_email, date, time, total_records, inconsistencies,
                           quality_score, rules_applied_json, rules_passed_json, rules_failed_json,
                           status, created_at
                    FROM runs
                    WHERE dataset_id = %s
                    ORDER BY created_at DESC
                    LIMIT %s
                    """,
                    (str(dataset_id), int(limit)),
                )
            else:
                rows = self._db.fetch_all(
                    """
                    SELECT id, dataset_id, dataset_name, user_email, date, time, total_records, inconsistencies,
                           quality_score, rules_applied_json, rules_passed_json, rules_failed_json,
                           status, created_at
                    FROM runs
                    ORDER BY created_at DESC
                    LIMIT %s
                    """,
                    (int(limit),),
                )
            out = [self._normalize_run(r) for r in rows if isinstance(r, dict)]
            self._runs = out
            return list(out)
        if not dataset_id:
            return list(self._runs)
        return [r for r in self._runs if r.get("dataset_id") == dataset_id]

    def get_runs_page(self, dataset_id: str | None = None, offset: int = 0, limit: int = 200) -> dict:
        off = max(0, int(offset or 0))
        lim = max(1, min(2000, int(limit or 200)))
        if self._db_enabled():
            params: list = []
            where = ""
            if dataset_id:
                where = " WHERE dataset_id = %s"
                params.append(str(dataset_id))
            total_rows = self._db.fetch_all("SELECT COUNT(*) AS n FROM runs" + where, tuple(params))
            total = int((total_rows[0].get("n") if total_rows and isinstance(total_rows[0], dict) else 0) or 0)
            sql = (
                """
                SELECT id, dataset_id, dataset_name, user_email, date, time, total_records, inconsistencies,
                       quality_score, rules_applied_json, rules_passed_json, rules_failed_json,
                       status, created_at
                FROM runs
                """
                + where
                + " ORDER BY created_at DESC OFFSET %s LIMIT %s"
            )
            page_params = tuple(params + [off, lim])
            rows = self._db.fetch_all(sql, page_params)
            items = [self._normalize_run(r) for r in rows if isinstance(r, dict)]
            return {"items": items, "total": total, "offset": off, "limit": lim}

        rows = self.get_runs(dataset_id=dataset_id)
        total = len(rows)
        return {"items": rows[off : off + lim], "total": total, "offset": off, "limit": lim}

    def get_findings(self, dataset_id: str | None = None, run_id: str | None = None) -> list[dict]:
        if self._db_enabled():
            limit = self._get_limit("REVIEWDATA_DB_MAX_FINDINGS", 5000)
            where = []
            params = []
            if dataset_id:
                where.append("dataset_id = %s")
                params.append(str(dataset_id))
            if run_id:
                where.append("run_id = %s")
                params.append(str(run_id))
            sql = """
            SELECT id, run_id, dataset_id, rule_id, rule_name, field, value, description, severity,
                   error_type, expected, recommendation, business_impact,
                   date, time, row_index, created_at
            FROM findings
            """
            if where:
                sql += " WHERE " + " AND ".join(where)
            sql += " ORDER BY created_at DESC LIMIT %s"
            params.append(int(limit))
            rows = self._db.fetch_all(sql, tuple(params))
            out = [self._normalize_finding(f) for f in rows if isinstance(f, dict)]
            if not dataset_id and not run_id:
                self._findings = out
            return list(out)
        result = self._findings
        if dataset_id:
            result = [f for f in result if f.get("dataset_id") == dataset_id]
        if run_id:
            result = [f for f in result if f.get("run_id") == run_id]
        return list(result)

    def get_findings_page(
        self,
        dataset_id: str | None = None,
        run_id: str | None = None,
        offset: int = 0,
        limit: int = 200,
    ) -> dict:
        off = max(0, int(offset or 0))
        lim = max(1, min(2000, int(limit or 200)))
        if self._db_enabled():
            where = []
            params = []
            if dataset_id:
                where.append("dataset_id = %s")
                params.append(str(dataset_id))
            if run_id:
                where.append("run_id = %s")
                params.append(str(run_id))
            where_sql = (" WHERE " + " AND ".join(where)) if where else ""
            total_rows = self._db.fetch_all("SELECT COUNT(*) AS n FROM findings" + where_sql, tuple(params))
            total = int((total_rows[0].get("n") if total_rows and isinstance(total_rows[0], dict) else 0) or 0)
            sql = (
                """
                SELECT id, run_id, dataset_id, rule_id, rule_name, field, value, description, severity,
                       error_type, expected, recommendation, business_impact,
                       date, time, row_index, created_at
                FROM findings
                """
                + where_sql
                + " ORDER BY created_at DESC OFFSET %s LIMIT %s"
            )
            page_params = tuple(params + [off, lim])
            rows = self._db.fetch_all(sql, page_params)
            items = [self._normalize_finding(f) for f in rows if isinstance(f, dict)]
            return {"items": items, "total": total, "offset": off, "limit": lim}

        rows = self.get_findings(dataset_id=dataset_id, run_id=run_id)
        total = len(rows)
        return {"items": rows[off : off + lim], "total": total, "offset": off, "limit": lim}

    def export_run_pdf(self, run_id: str, output_path: str) -> None:
        run = next((r for r in self._runs if r["id"] == run_id), None)
        if not run and self._db_enabled():
            rows = self._db.fetch_all("SELECT * FROM runs WHERE id = %s LIMIT 1", (str(run_id),))
            if rows:
                run = self._normalize_run(rows[0])
        if not run:
            raise ValueError("Ejecución no encontrada.")
        did = str(run.get("dataset_id") or "").strip()
        findings_all = self.get_findings(dataset_id=did or None, run_id=run_id)
        if did:
            findings_all = [f for f in findings_all if str((f or {}).get("dataset_id") or "") == did]
        max_pdf = self._get_limit("REVIEWDATA_PDF_MAX_FINDINGS", 800)
        findings = list(findings_all)[: int(max_pdf)]
        recs = self.get_recommendations(run_id=run_id)
        ai_ins = self.get_ai_insights(run_id) if self._db_enabled() else []
        ai_recs = self.get_ai_recommendations(run_id) if self._db_enabled() else []
        drift = self.get_dataset_drift(run_id) if self._db_enabled() else []
        fixes = self.get_auto_fix_suggestions(run_id) if self._db_enabled() else []
        export_findings_pdf(
            output_path=output_path,
            dataset_name=run.get("dataset_name", ""),
            run_id=run_id,
            run_date=f"{run.get('date', '')} {run.get('time', '')}",
            user_email=run.get("user_email", ""),
            total_records=int(run.get("total_records", 0)),
            quality_score=int(run.get("quality_score", 0) or 0),
            rules_applied=list(run.get("rules_applied") or []),
            rules_passed=list(run.get("rules_passed") or []),
            rules_failed=list(run.get("rules_failed") or []),
            findings=findings,
            total_findings=int(len(findings_all)),
            recommendations=recs,
            ai_insights=ai_ins,
            ai_recommendations=ai_recs,
            drift=drift,
            auto_fix_count=int(len(fixes)),
        )
        report_id = f"pdf_{run_id}"
        now = datetime.now().strftime("%d-%m-%Y %H:%M")
        report = {
            "id": report_id,
            "run_id": run_id,
            "dataset_id": run.get("dataset_id", ""),
            "dataset_name": run.get("dataset_name", ""),
            "format": "PDF",
            "status": "Completado",
            "generated_at": now,
        }
        self._reports = [r for r in self._reports if str(r.get("id") or "") != report_id]
        self._reports.insert(0, report)
        self._log_activity("Reportes", "Generación", f"Reporte PDF generado: {run_id[:8]}")
        if self._db_enabled():
            self._db.execute_query(
                """
                INSERT INTO reports (id, run_id, dataset_id, dataset_name, format, status, generated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                    run_id = EXCLUDED.run_id,
                    dataset_id = EXCLUDED.dataset_id,
                    dataset_name = EXCLUDED.dataset_name,
                    format = EXCLUDED.format,
                    status = EXCLUDED.status,
                    generated_at = EXCLUDED.generated_at
                """,
                (
                    report_id,
                    run_id,
                    report.get("dataset_id", ""),
                    report.get("dataset_name", ""),
                    "PDF",
                    "Completado",
                    now,
                ),
            )

    def get_stats_overview(self, dataset_id: str | None = None) -> dict:
        if not self._db_enabled():
            runs = self.get_runs(dataset_id=dataset_id)
            findings = self.get_findings(dataset_id=dataset_id)
            sev = {}
            for f in findings:
                s = self._normalize_severity(str(f.get("severity") or "Alta"))
                sev[s] = int(sev.get(s, 0) or 0) + 1
            avg_score = 0
            if runs:
                avg_score = int(sum(int(r.get("quality_score") or 0) for r in runs) / max(1, len(runs)))
            by_col = {}
            for f in findings:
                c = str(f.get("field") or "")
                by_col[c] = int(by_col.get(c, 0) or 0) + 1
            top_cols = [{"field": k, "count": v} for k, v in sorted(by_col.items(), key=lambda kv: kv[1], reverse=True)[:12]]
            return {"avg_quality_score": avg_score, "errors_by_severity": sev, "top_columns": top_cols}

        params = []
        run_where = ""
        finding_where = ""
        if dataset_id:
            run_where = " WHERE dataset_id = %s"
            finding_where = " WHERE dataset_id = %s"
            params = [str(dataset_id)]

        rows = self._db.fetch_all("SELECT AVG(quality_score) AS v FROM runs" + run_where, tuple(params))
        avg_score = int(float((rows[0].get("v") if rows and isinstance(rows[0], dict) else 0) or 0))

        sev_rows = self._db.fetch_all(
            "SELECT severity, COUNT(*) AS n FROM findings" + finding_where + " GROUP BY severity ORDER BY n DESC",
            tuple(params),
        )
        sev = {}
        for r in sev_rows:
            if not isinstance(r, dict):
                continue
            key = self._normalize_severity(str(r.get("severity") or "Alta"))
            sev[key] = int(r.get("n") or 0)

        top_cols_rows = self._db.fetch_all(
            "SELECT field, COUNT(*) AS n FROM findings" + finding_where + " GROUP BY field ORDER BY n DESC LIMIT 12",
            tuple(params),
        )
        top_cols = [{"field": str(r.get("field") or ""), "count": int(r.get("n") or 0)} for r in top_cols_rows if isinstance(r, dict)]

        ds_rows = self._db.fetch_all(
            """
            SELECT dataset_id, dataset_name,
                   AVG(quality_score) AS avg_score,
                   SUM(inconsistencies) AS total_incons
            FROM runs
            """
            + run_where
            + " GROUP BY dataset_id, dataset_name ORDER BY avg_score ASC NULLS LAST LIMIT 10",
            tuple(params),
        )
        datasets_problematic = []
        for r in ds_rows:
            if not isinstance(r, dict):
                continue
            datasets_problematic.append(
                {
                    "dataset_id": str(r.get("dataset_id") or ""),
                    "dataset_name": str(r.get("dataset_name") or ""),
                    "avg_score": int(float(r.get("avg_score") or 0)),
                    "total_inconsistencies": int(r.get("total_incons") or 0),
                }
            )

        run_rows = self._db.fetch_all(
            "SELECT rules_passed_json, rules_failed_json FROM runs" + run_where + " ORDER BY created_at DESC LIMIT 500",
            tuple(params),
        )
        passed = 0
        failed = 0
        for r in run_rows:
            if not isinstance(r, dict):
                continue
            rp = self._parse_json(r.get("rules_passed_json"), [])
            rf = self._parse_json(r.get("rules_failed_json"), [])
            if isinstance(rp, list):
                passed += len(rp)
            if isinstance(rf, list):
                failed += len(rf)
        pct_rules_ok = 0
        denom = passed + failed
        if denom > 0:
            pct_rules_ok = int((passed / denom) * 100)

        return {
            "avg_quality_score": avg_score,
            "errors_by_severity": sev,
            "top_columns": top_cols,
            "datasets_problematic": datasets_problematic,
            "pct_rules_ok": pct_rules_ok,
        }

    def _upsert_suggested_expectations(self, dataset_id: str, profile: dict) -> None:
        if not self._db_enabled():
            return
        did = str(dataset_id or "").strip()
        if not did:
            return
        p = profile if isinstance(profile, dict) else {}
        cols: list[str] = [str(c) for c in (p.get("columns") or []) if str(c)]
        if not cols:
            return
        rows = max(1, int(p.get("rows") or 0) or 1)
        inferred = p.get("inferred_types") or {}
        empty_counts = p.get("empty_counts") or {}
        unique_counts = p.get("unique_counts") or {}
        contract = self._get_contract()

        def mk_id(column: str, et: str, params: dict) -> str:
            base = json.dumps(params, ensure_ascii=False, sort_keys=True)
            return str(uuid.uuid5(uuid.NAMESPACE_URL, f"suggested:{did}:{column}:{et}:{base}"))

        suggestions: list[dict] = []
        for c in cols:
            norm = _normalize_column_name(c)
            t = str(inferred.get(c) or inferred.get(norm) or "").strip().lower()
            empty_n = int(empty_counts.get(c, 0) or 0)
            uniq_n = int(unique_counts.get(c, 0) or 0)
            empty_rate = empty_n / float(rows)
            uniq_rate = uniq_n / float(max(1, rows))

            if norm in {_normalize_column_name(k) for k, v in contract.items() if bool((v or {}).get("required", False))}:
                params = {"expectation_type": "non_null", "column_name": c}
                suggestions.append(
                    {
                        "id": mk_id(c, "non_null", params),
                        "dataset_id": did,
                        "column_name": c,
                        "expectation_type": "non_null",
                        "parameters": params,
                        "confidence": 90,
                        "reason": "Columna requerida en contrato; se sugiere no nulos.",
                    }
                )

            if ("cp" in norm or "postal" in norm) and (t in ("int", "text", "unknown", "")):
                params = {"expectation_type": "regex", "column_name": c, "regex": r"^\d{5}$", "ignore_empty": True}
                suggestions.append(
                    {
                        "id": mk_id(c, "cp_regex", params),
                        "dataset_id": did,
                        "column_name": c,
                        "expectation_type": "regex",
                        "parameters": params,
                        "confidence": 92,
                        "reason": "Nombre de columna sugiere código postal; se sugiere regex de 5 dígitos.",
                    }
                )

            if "placa" in norm:
                params = {"expectation_type": "regex", "column_name": c, "regex": r"^[A-Z]{3}-\d{3}$", "ignore_empty": True}
                suggestions.append(
                    {
                        "id": mk_id(c, "placas_regex", params),
                        "dataset_id": did,
                        "column_name": c,
                        "expectation_type": "regex",
                        "parameters": params,
                        "confidence": 88,
                        "reason": "Nombre de columna sugiere placas; se sugiere formato ABC-123.",
                    }
                )

            if t == "si_no" or norm.endswith("_si_no") or "si_no" in norm or norm.startswith("boton_panico"):
                params = {"expectation_type": "allowed_values", "column_name": c, "allowed_values": ["Si", "No"], "ignore_empty": True}
                suggestions.append(
                    {
                        "id": mk_id(c, "si_no", params),
                        "dataset_id": did,
                        "column_name": c,
                        "expectation_type": "allowed_values",
                        "parameters": params,
                        "confidence": 86,
                        "reason": "Se detectan valores tipo Si/No; se sugiere catálogo permitido.",
                    }
                )

            if uniq_rate >= 0.98 and rows >= 20:
                params = {"expectation_type": "unique", "column_name": c}
                suggestions.append(
                    {
                        "id": mk_id(c, "unique", params),
                        "dataset_id": did,
                        "column_name": c,
                        "expectation_type": "unique",
                        "parameters": params,
                        "confidence": 78,
                        "reason": "Alta cardinalidad; se sugiere regla UNIQUE.",
                    }
                )

            if empty_rate >= 0.6 and rows >= 20:
                params = {"expectation_type": "non_null", "column_name": c}
                suggestions.append(
                    {
                        "id": mk_id(c, "nonnull_from_missing", params),
                        "dataset_id": did,
                        "column_name": c,
                        "expectation_type": "non_null",
                        "parameters": params,
                        "confidence": 70,
                        "reason": "Muchos nulos; se sugiere definir expectativa (no nulos o revisar captura).",
                    }
                )

        for s in suggestions[:200]:
            try:
                self._db.execute_query(
                    """
                    INSERT INTO suggested_expectations (id, dataset_id, column_name, expectation_type, parameters_json, confidence, reason, status)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, 'suggested')
                    ON CONFLICT (id) DO NOTHING
                    """,
                    (
                        str(s["id"]),
                        did,
                        str(s["column_name"]),
                        str(s["expectation_type"]),
                        json.dumps(s["parameters"], ensure_ascii=False),
                        int(s["confidence"]),
                        str(s["reason"]),
                    ),
                )
            except Exception:
                continue

    def get_suggested_expectations(self, dataset_id: str) -> list[dict]:
        if not self._db_enabled():
            return []
        did = str(dataset_id or "").strip()
        if not did:
            return []
        rows = self._db.fetch_all(
            """
            SELECT id, dataset_id, column_name, expectation_type, parameters_json, confidence, reason, status, created_at
            FROM suggested_expectations
            WHERE dataset_id = %s
            ORDER BY created_at DESC
            LIMIT 500
            """,
            (did,),
        )
        out = []
        for r in rows or []:
            if not isinstance(r, dict):
                continue
            out.append(
                {
                    "id": str(r.get("id") or ""),
                    "dataset_id": str(r.get("dataset_id") or ""),
                    "column_name": str(r.get("column_name") or ""),
                    "expectation_type": str(r.get("expectation_type") or ""),
                    "parameters": self._parse_json(r.get("parameters_json"), {}),
                    "confidence": int(r.get("confidence") or 0),
                    "reason": str(r.get("reason") or ""),
                    "status": str(r.get("status") or "suggested"),
                    "created_at": str(r.get("created_at") or ""),
                }
            )
        return out

    def accept_suggested_expectations(self, dataset_id: str, expectation_ids: list[str]) -> dict:
        session = self._require_session()
        if str(session.get("role", "user")) != "admin":
            raise ValueError("Acceso denegado: se requiere rol admin.")
        if not self._db_enabled():
            raise ValueError("BD no disponible.")
        did = str(dataset_id or "").strip()
        ids = [str(x or "").strip() for x in (expectation_ids or []) if str(x or "").strip()]
        if not did or not ids:
            return {"ok": False, "created_rules": 0}
        rows = self._db.fetch_all(
            "SELECT id, column_name, expectation_type, parameters_json, confidence, reason FROM suggested_expectations WHERE dataset_id = %s AND id = ANY(%s::text[])",
            (did, ids),
        )
        created = 0
        for r in rows or []:
            if not isinstance(r, dict):
                continue
            sid = str(r.get("id") or "").strip()
            col = str(r.get("column_name") or "").strip()
            params = self._parse_json(r.get("parameters_json"), {})
            if not sid or not col or not isinstance(params, dict):
                continue
            rid = f"ai_exp_{sid[:8]}_{_normalize_column_name(col)[:18]}"
            conf = int(r.get("confidence") or 0)
            sev = "Media" if conf < 85 else "Alta"
            name = f"AI Expectation: {col}"
            desc = str(r.get("reason") or "").strip() or "Regla sugerida por AI profiling."
            try:
                self._db.execute_query(
                    """
                    INSERT INTO rules (id, name, description, rule_type, severity, active, parameters_json)
                    VALUES (%s, %s, %s, 'ai_expectation', %s, TRUE, %s)
                    ON CONFLICT (id) DO UPDATE SET
                        name = EXCLUDED.name,
                        description = EXCLUDED.description,
                        rule_type = EXCLUDED.rule_type,
                        severity = EXCLUDED.severity,
                        active = TRUE,
                        parameters_json = EXCLUDED.parameters_json
                    """,
                    (rid, name, desc, sev, json.dumps(params, ensure_ascii=False)),
                )
                created += 1
            except Exception:
                continue
            try:
                self._db.execute_query("UPDATE suggested_expectations SET status = 'accepted' WHERE id = %s", (sid,))
            except Exception:
                pass
        return {"ok": True, "created_rules": int(created)}

    def _persist_ai_post_run(self, run: dict, findings: list[ValidationFinding]) -> None:
        if not self._db_enabled():
            return
        rid = str(run.get("id") or "").strip()
        did = str(run.get("dataset_id") or "").strip()
        if not rid or not did:
            return
        health = self._compute_dataset_health(findings, int(run.get("total_records") or 0))
        counts = health.get("counts") or {"Crítica": 0, "Alta": 0, "Media": 0, "Baja": 0}
        score = int(health.get("score") or 0)
        grade = str(health.get("grade") or "")
        explanation = json.dumps(health.get("explanation") or {}, ensure_ascii=False)

        self._db.execute_query("DELETE FROM dataset_health WHERE run_id = %s", (rid,))
        self._db.execute_query(
            """
            INSERT INTO dataset_health (id, run_id, score, grade, explanation, critical_count, high_count, medium_count, low_count)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (id) DO UPDATE SET
                score = EXCLUDED.score,
                grade = EXCLUDED.grade,
                explanation = EXCLUDED.explanation,
                critical_count = EXCLUDED.critical_count,
                high_count = EXCLUDED.high_count,
                medium_count = EXCLUDED.medium_count,
                low_count = EXCLUDED.low_count
            """,
            (
                f"health_{rid}",
                rid,
                int(score),
                grade,
                explanation,
                int(counts.get("Crítica", 0) or 0),
                int(counts.get("Alta", 0) or 0),
                int(counts.get("Media", 0) or 0),
                int(counts.get("Baja", 0) or 0),
            ),
        )

        self._db.execute_query("DELETE FROM ai_insights WHERE run_id = %s", (rid,))
        self._db.execute_query("DELETE FROM ai_recommendations WHERE run_id = %s", (rid,))
        self._db.execute_query("DELETE FROM dataset_drift WHERE current_run_id = %s", (rid,))
        self._db.execute_query("DELETE FROM auto_fix_suggestions WHERE run_id = %s", (rid,))

        by_col: dict[str, list[ValidationFinding]] = {}
        by_rule: dict[str, int] = {}
        for f in findings:
            field = str(getattr(f, "field", "") or "")
            col = field.split(",")[0].strip()
            by_col.setdefault(col, []).append(f)
            by_rule[str(getattr(f, "rule_id", "") or "")] = int(by_rule.get(str(getattr(f, "rule_id", "") or ""), 0) or 0) + 1

        top_cols = sorted(((k, len(v)) for k, v in by_col.items()), key=lambda kv: kv[1], reverse=True)[:10]
        top_rules = sorted(by_rule.items(), key=lambda kv: kv[1], reverse=True)[:6]

        total_findings = max(1, int(len(findings)))
        loc_keys = ("origen", "destino", "ruta", "cp", "postal", "direccion", "ciudad", "estado")
        loc_errs = 0
        crit_cols: dict[str, int] = {}
        for col, fs in by_col.items():
            if any(k in col.lower() for k in loc_keys):
                loc_errs += len(fs)
            for ff in fs:
                sev = self._normalize_severity(str(getattr(ff, "severity", "") or "Alta"))
                if sev == "Crítica":
                    crit_cols[col] = int(crit_cols.get(col, 0) or 0) + 1

        insights: list[dict] = []
        if loc_errs:
            pct = int(round((loc_errs / float(total_findings)) * 100.0))
            if pct >= 50:
                insights.append(
                    {
                        "type": "detected",
                        "title": "AI DETECTED",
                        "description": f"El {pct}% de los errores provienen de campos de ubicación/ruta.",
                        "severity": "Alta",
                    }
                )
        if crit_cols:
            topc = sorted(crit_cols.items(), key=lambda kv: kv[1], reverse=True)[:2]
            total_crit = sum(crit_cols.values())
            pct = int(round((sum(v for _, v in topc) / float(max(1, total_crit))) * 100.0))
            if pct >= 70:
                insights.append(
                    {
                        "type": "warning",
                        "title": "AI WARNING",
                        "description": f"Los errores críticos están concentrados en: {', '.join(k for k, _ in topc)}.",
                        "severity": "Crítica",
                    }
                )
        if top_rules:
            insights.append(
                {
                    "type": "summary",
                    "title": "AI INSIGHT",
                    "description": f"Reglas más fallidas: {', '.join(f'{k} ({v})' for k, v in top_rules[:3])}.",
                    "severity": "Media",
                }
            )

        prev = self._db.fetch_all(
            "SELECT id, quality_score, inconsistencies, total_records FROM runs WHERE dataset_id = %s AND id <> %s ORDER BY created_at DESC LIMIT 1",
            (did, rid),
        )
        prev_id = ""
        if prev and isinstance(prev[0], dict):
            prev_id = str(prev[0].get("id") or "")
            try:
                prev_score = int(prev[0].get("quality_score") or 0)
            except Exception:
                prev_score = 0
            diff = prev_score - int(score)
            if diff >= 10:
                insights.append(
                    {
                        "type": "warning",
                        "title": "AI WARNING",
                        "description": f"La calidad del dataset bajó {diff} puntos respecto al último run.",
                        "severity": "Alta",
                    }
                )

        if not insights:
            insights.append({"type": "info", "title": "AI INSIGHTS", "description": "Sin anomalías inusuales detectadas en este run.", "severity": "Baja"})

        for it in insights[:12]:
            self._db.execute_query(
                "INSERT INTO ai_insights (id, run_id, type, title, description, severity) VALUES (%s, %s, %s, %s, %s, %s)",
                (str(uuid.uuid4()), rid, str(it["type"]), str(it["title"]), str(it["description"]), self._normalize_severity(str(it["severity"]))),
            )

        for col, n in top_cols[:8]:
            fs = by_col.get(col, [])
            worst = "Baja"
            for ff in fs:
                s = self._normalize_severity(str(getattr(ff, "severity", "") or "Alta"))
                if s == "Crítica":
                    worst = "Crítica"
                    break
                if s == "Alta" and worst not in ("Crítica", "Alta"):
                    worst = "Alta"
                if s == "Media" and worst == "Baja":
                    worst = "Media"
            priority = "Baja"
            if worst == "Crítica":
                priority = "Crítica"
            elif worst == "Alta":
                priority = "Alta"
            elif worst == "Media":
                priority = "Media"
            problem = f"Alta concentración de errores en la columna '{col}' ({n})."
            base = "Revisar valores inválidos y aplicar normalización/validación consistente."
            if "cp" in col.lower() or "postal" in col.lower():
                base = "Aplicar validación regex ^\\d{5}$ y crear catálogo de códigos por ciudad."
            if "placa" in col.lower():
                base = "Normalizar mayúsculas y validar placas con regex ^[A-Z]{3}-\\d{3}$."
            if "fecha" in col.lower():
                base = "Normalizar fechas al formato esperado y corregir valores inválidos."
            impact = self._business_impact("", col)
            can_fix = bool("normalizar" in base.lower() or "trim" in base.lower() or "mayúsculas" in base.lower())
            self._db.execute_query(
                """
                INSERT INTO ai_recommendations (id, run_id, rule_id, column_name, problem, recommendation, priority, business_impact, can_auto_fix)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (str(uuid.uuid4()), rid, None, col, problem, base, priority, impact, bool(can_fix)),
            )

        if prev_id:
            try:
                prev_rows = int(prev[0].get("total_records") or 0)
            except Exception:
                prev_rows = 0
            try:
                prev_inc = int(prev[0].get("inconsistencies") or 0)
            except Exception:
                prev_inc = 0

            cur_rows = int(run.get("total_records") or 0)
            cur_inc = int(run.get("inconsistencies") or 0)

            def add_drift(dt: str, field: str, pv: str, cv: str, diff: str, sev: str, expl: str):
                self._db.execute_query(
                    """
                    INSERT INTO dataset_drift (id, dataset_id, current_run_id, previous_run_id, drift_type, field, previous_value, current_value, difference, severity, explanation)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (str(uuid.uuid4()), did, rid, prev_id, dt, field, pv, cv, diff, self._normalize_severity(sev), expl),
                )

            if prev_rows and cur_rows:
                pct = int(round(((cur_rows - prev_rows) / float(max(1, prev_rows))) * 100.0))
                if abs(pct) >= 20:
                    add_drift("rows", "rows", str(prev_rows), str(cur_rows), f"{pct}%", "Media", "Cambio significativo en cantidad de filas.")
            if prev_inc and cur_inc:
                pct = int(round(((cur_inc - prev_inc) / float(max(1, prev_inc))) * 100.0))
                if pct >= 30:
                    add_drift("errors", "inconsistencies", str(prev_inc), str(cur_inc), f"+{pct}%", "Alta", "Aumento relevante de inconsistencias vs run anterior.")
            prev_score = int(prev[0].get("quality_score") or 0) if prev and isinstance(prev[0], dict) else 0
            if prev_score and score:
                drop = prev_score - score
                if drop >= 10:
                    add_drift("score", "quality_score", str(prev_score), str(score), f"-{drop}", "Alta", "Caída de score de calidad vs run anterior.")

            cur_by_field = self._db.fetch_all("SELECT field, COUNT(*) AS n FROM findings WHERE run_id = %s GROUP BY field", (rid,))
            prev_by_field = self._db.fetch_all("SELECT field, COUNT(*) AS n FROM findings WHERE run_id = %s GROUP BY field", (prev_id,))
            prev_map = {str(r.get("field") or ""): int(r.get("n") or 0) for r in prev_by_field or [] if isinstance(r, dict)}
            for r in cur_by_field or []:
                if not isinstance(r, dict):
                    continue
                f = str(r.get("field") or "")
                n = int(r.get("n") or 0)
                p = int(prev_map.get(f, 0) or 0)
                if p < 5 or n < 8:
                    continue
                pct = int(round(((n - p) / float(max(1, p))) * 100.0))
                if pct >= 45:
                    add_drift("field_errors", f, str(p), str(n), f"+{pct}%", "Media", f"Aumento de errores en el campo '{f}'.")

        try:
            cur_ds_rows = self._db.fetch_all(
                "SELECT id, type, user_email, columns_json, profile_json FROM datasets WHERE id = %s LIMIT 1",
                (did,),
            )
            cur_ds = cur_ds_rows[0] if cur_ds_rows and isinstance(cur_ds_rows[0], dict) else None
            if cur_ds:
                cur_type = str(cur_ds.get("type") or "").strip() or "CSV"
                cur_user = str(cur_ds.get("user_email") or "").strip()
                cur_cols = self._parse_json(cur_ds.get("columns_json"), [])
                if not isinstance(cur_cols, list):
                    cur_cols = []
                cur_profile = self._parse_json(cur_ds.get("profile_json"), {})
                if not isinstance(cur_profile, dict):
                    cur_profile = {}

                prev_ds_rows = self._db.fetch_all(
                    """
                    SELECT id, columns_json, profile_json
                    FROM datasets
                    WHERE type = %s AND user_email = %s AND id <> %s
                    ORDER BY created_at DESC
                    LIMIT 1
                    """,
                    (cur_type, cur_user, did),
                )
                prev_ds = prev_ds_rows[0] if prev_ds_rows and isinstance(prev_ds_rows[0], dict) else None
                if prev_ds:
                    prev_did = str(prev_ds.get("id") or "").strip()
                    prev_run_rows = self._db.fetch_all(
                        "SELECT id FROM runs WHERE dataset_id = %s ORDER BY created_at DESC LIMIT 1",
                        (prev_did,),
                    )
                    prev_run_id = str(prev_run_rows[0].get("id") or "").strip() if prev_run_rows and isinstance(prev_run_rows[0], dict) else ""
                    if prev_run_id:
                        prev_cols = self._parse_json(prev_ds.get("columns_json"), [])
                        if not isinstance(prev_cols, list):
                            prev_cols = []
                        prev_profile = self._parse_json(prev_ds.get("profile_json"), {})
                        if not isinstance(prev_profile, dict):
                            prev_profile = {}

                        try:
                            cur_rows = int(cur_profile.get("rows") or 0)
                        except Exception:
                            cur_rows = 0
                        try:
                            prev_rows = int(prev_profile.get("rows") or 0)
                        except Exception:
                            prev_rows = 0

                        def _insert_drift(dt: str, field: str, pv: str, cv: str, diff: str, sev: str, expl: str):
                            self._db.execute_query(
                                """
                                INSERT INTO dataset_drift (id, dataset_id, current_run_id, previous_run_id, drift_type, field, previous_value, current_value, difference, severity, explanation)
                                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                                """,
                                (str(uuid.uuid4()), did, rid, prev_run_id, dt, field, pv, cv, diff, self._normalize_severity(sev), expl),
                            )

                        drift_items: list[tuple[str, str, str, str, str, str, str]] = []

                        if prev_rows and cur_rows:
                            pct = int(round(((cur_rows - prev_rows) / float(max(1, prev_rows))) * 100.0))
                            if abs(pct) >= 20:
                                drift_items.append(
                                    ("rows", "rows", str(prev_rows), str(cur_rows), f"{pct}%", "Media", "Cambio significativo en cantidad de filas vs dataset anterior.")
                                )

                        if prev_cols and cur_cols:
                            prev_set = {str(c) for c in prev_cols if str(c)}
                            cur_set = {str(c) for c in cur_cols if str(c)}
                            new_cols = sorted(list(cur_set - prev_set))[:20]
                            missing_cols = sorted(list(prev_set - cur_set))[:20]
                            if abs(len(cur_set) - len(prev_set)) >= 3:
                                drift_items.append(
                                    (
                                        "columns",
                                        "columns",
                                        str(len(prev_set)),
                                        str(len(cur_set)),
                                        str(len(cur_set) - len(prev_set)),
                                        "Alta",
                                        "Cambio relevante en cantidad de columnas vs dataset anterior.",
                                    )
                                )
                            for c in new_cols:
                                drift_items.append(("new_column", c, "", c, "+1", "Media", "Columna nueva vs dataset anterior."))
                            for c in missing_cols:
                                drift_items.append(("missing_column", c, c, "", "-1", "Alta", "Columna faltante vs dataset anterior."))

                        cur_empty = cur_profile.get("empty_counts") if isinstance(cur_profile.get("empty_counts"), dict) else {}
                        prev_empty = prev_profile.get("empty_counts") if isinstance(prev_profile.get("empty_counts"), dict) else {}
                        cur_unique = cur_profile.get("unique_counts") if isinstance(cur_profile.get("unique_counts"), dict) else {}
                        prev_unique = prev_profile.get("unique_counts") if isinstance(prev_profile.get("unique_counts"), dict) else {}

                        common_cols = sorted(list({str(c) for c in cur_cols if str(c)} & {str(c) for c in prev_cols if str(c)}))
                        if prev_rows >= 30 and cur_rows >= 30 and common_cols:
                            for c in common_cols[:120]:
                                try:
                                    ce = int(cur_empty.get(c) or 0)
                                except Exception:
                                    ce = 0
                                try:
                                    pe = int(prev_empty.get(c) or 0)
                                except Exception:
                                    pe = 0
                                cur_pct = int(round((ce / float(max(1, cur_rows))) * 100.0))
                                prev_pct = int(round((pe / float(max(1, prev_rows))) * 100.0))
                                dp = cur_pct - prev_pct
                                if abs(dp) >= 10:
                                    sev = "Alta" if abs(dp) >= 20 else "Media"
                                    drift_items.append(
                                        (
                                            "null_pct",
                                            c,
                                            f"{prev_pct}%",
                                            f"{cur_pct}%",
                                            f"{dp:+d}pp",
                                            sev,
                                            "Cambio en porcentaje de nulos/vacíos vs dataset anterior.",
                                        )
                                    )

                                try:
                                    cu = int(cur_unique.get(c) or 0)
                                except Exception:
                                    cu = 0
                                try:
                                    pu = int(prev_unique.get(c) or 0)
                                except Exception:
                                    pu = 0
                                cur_u = int(round((cu / float(max(1, cur_rows))) * 100.0))
                                prev_u = int(round((pu / float(max(1, prev_rows))) * 100.0))
                                du = cur_u - prev_u
                                if abs(du) >= 15:
                                    sev = "Media"
                                    if abs(du) >= 30:
                                        sev = "Alta"
                                    drift_items.append(
                                        (
                                            "unique_pct",
                                            c,
                                            f"{prev_u}%",
                                            f"{cur_u}%",
                                            f"{du:+d}pp",
                                            sev,
                                            "Cambio en porcentaje de valores únicos vs dataset anterior.",
                                        )
                                    )

                        for dt, field, pv, cv, diff, sev, expl in drift_items[:60]:
                            _insert_drift(dt, field, pv, cv, diff, sev, expl)
        except Exception:
            pass

        def suggest_fix(value: str, column: str) -> tuple[str | None, str | None, int]:
            v0 = "" if value is None else str(value)
            v = v0
            if v != v.strip():
                return v.strip(), "trim_spaces", 95
            if "placa" in column.lower():
                up = v.upper()
                if up != v:
                    return up, "upper", 85
            if "si" in v.lower() or "no" in v.lower():
                n = _normalize_yes_no(v)
                if n is not None and n != v:
                    return n, "normalize_yes_no", 90
            cleaned = re.sub(r"[\u200b\u200c\u200d\ufeff]", "", v)
            if cleaned != v:
                return cleaned, "remove_invisible", 80
            return None, None, 0

        for f in findings[:4000]:
            col = str(getattr(f, "field", "") or "").split(",")[0].strip()
            ov = "" if getattr(f, "value", None) is None else str(getattr(f, "value", ""))
            fixed, fix_type, conf = suggest_fix(ov, col)
            if not fixed or not fix_type:
                continue
            self._db.execute_query(
                """
                INSERT INTO auto_fix_suggestions (id, run_id, finding_id, column_name, original_value, fixed_value, fix_type, confidence, requires_approval, status)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, TRUE, 'suggested')
                """,
                (str(uuid.uuid4()), rid, None, col, ov, str(fixed), fix_type, int(conf)),
            )

    def get_ai_insights(self, run_id: str) -> list[dict]:
        if not self._db_enabled():
            return []
        rid = str(run_id or "").strip()
        if not rid:
            return []
        rows = self._db.fetch_all(
            "SELECT id, run_id, type, title, description, severity, created_at FROM ai_insights WHERE run_id = %s ORDER BY created_at DESC",
            (rid,),
        )
        return [
            {
                "id": str(r.get("id") or ""),
                "run_id": str(r.get("run_id") or ""),
                "type": str(r.get("type") or ""),
                "title": str(r.get("title") or ""),
                "description": str(r.get("description") or ""),
                "severity": self._normalize_severity(str(r.get("severity") or "Media")),
                "created_at": str(r.get("created_at") or ""),
            }
            for r in rows
            if isinstance(r, dict)
        ]

    def get_ai_recommendations(self, run_id: str) -> list[dict]:
        if not self._db_enabled():
            return []
        rid = str(run_id or "").strip()
        if not rid:
            return []
        rows = self._db.fetch_all(
            """
            SELECT id, run_id, rule_id, column_name, problem, recommendation, priority, business_impact, can_auto_fix, created_at
            FROM ai_recommendations
            WHERE run_id = %s
            ORDER BY created_at DESC
            """,
            (rid,),
        )
        out = []
        for r in rows or []:
            if not isinstance(r, dict):
                continue
            out.append(
                {
                    "id": str(r.get("id") or ""),
                    "run_id": str(r.get("run_id") or ""),
                    "rule_id": r.get("rule_id"),
                    "column_name": str(r.get("column_name") or ""),
                    "problem": str(r.get("problem") or ""),
                    "recommendation": str(r.get("recommendation") or ""),
                    "priority": str(r.get("priority") or ""),
                    "business_impact": str(r.get("business_impact") or ""),
                    "can_auto_fix": bool(r.get("can_auto_fix", False)),
                    "created_at": str(r.get("created_at") or ""),
                }
            )
        return out

    def get_dataset_drift(self, run_id: str) -> list[dict]:
        if not self._db_enabled():
            return []
        rid = str(run_id or "").strip()
        if not rid:
            return []
        rows = self._db.fetch_all(
            """
            SELECT id, dataset_id, current_run_id, previous_run_id, drift_type, field, previous_value, current_value, difference, severity, explanation, created_at
            FROM dataset_drift
            WHERE current_run_id = %s
            ORDER BY created_at DESC
            """,
            (rid,),
        )
        out = []
        for r in rows or []:
            if not isinstance(r, dict):
                continue
            out.append(
                {
                    "id": str(r.get("id") or ""),
                    "dataset_id": str(r.get("dataset_id") or ""),
                    "current_run_id": str(r.get("current_run_id") or ""),
                    "previous_run_id": str(r.get("previous_run_id") or ""),
                    "drift_type": str(r.get("drift_type") or ""),
                    "field": str(r.get("field") or ""),
                    "previous_value": str(r.get("previous_value") or ""),
                    "current_value": str(r.get("current_value") or ""),
                    "difference": str(r.get("difference") or ""),
                    "severity": self._normalize_severity(str(r.get("severity") or "Media")),
                    "explanation": str(r.get("explanation") or ""),
                    "created_at": str(r.get("created_at") or ""),
                }
            )
        return out

    def get_auto_fix_suggestions(self, run_id: str) -> list[dict]:
        if not self._db_enabled():
            return []
        rid = str(run_id or "").strip()
        if not rid:
            return []
        rows = self._db.fetch_all(
            """
            SELECT id, run_id, finding_id, column_name, original_value, fixed_value, fix_type, confidence, requires_approval, status, created_at
            FROM auto_fix_suggestions
            WHERE run_id = %s
            ORDER BY created_at DESC
            LIMIT 2000
            """,
            (rid,),
        )
        out = []
        for r in rows or []:
            if not isinstance(r, dict):
                continue
            out.append(
                {
                    "id": str(r.get("id") or ""),
                    "run_id": str(r.get("run_id") or ""),
                    "column_name": str(r.get("column_name") or ""),
                    "original_value": str(r.get("original_value") or ""),
                    "fixed_value": str(r.get("fixed_value") or ""),
                    "fix_type": str(r.get("fix_type") or ""),
                    "confidence": int(r.get("confidence") or 0),
                    "requires_approval": bool(r.get("requires_approval", True)),
                    "status": str(r.get("status") or "suggested"),
                    "created_at": str(r.get("created_at") or ""),
                }
            )
        return out

    def build_auto_fixed_csv(self, run_id: str, suggestion_ids: list[str] | None = None) -> str:
        if not self._db_enabled():
            raise ValueError("BD no disponible.")
        rid = str(run_id or "").strip()
        if not rid:
            raise ValueError("run_id requerido.")
        run_rows = self._db.fetch_all("SELECT dataset_id FROM runs WHERE id = %s LIMIT 1", (rid,))
        if not run_rows or not isinstance(run_rows[0], dict):
            raise ValueError("Run no encontrado.")
        did = str(run_rows[0].get("dataset_id") or "").strip()
        ds = self._get_dataset_meta(did)
        if not ds:
            raise ValueError("Dataset no encontrado.")
        self._ensure_dataset_file(ds)
        path = str(ds.get("stored_path") or "")
        if not path or not os.path.exists(path):
            raise ValueError("Archivo del dataset no disponible.")

        ids = [str(x or "").strip() for x in (suggestion_ids or []) if str(x or "").strip()]
        if ids:
            rows = self._db.fetch_all(
                "SELECT id, column_name, fix_type FROM auto_fix_suggestions WHERE run_id = %s AND id = ANY(%s::text[])",
                (rid, ids),
            )
        else:
            rows = self._db.fetch_all(
                "SELECT id, column_name, fix_type FROM auto_fix_suggestions WHERE run_id = %s AND status = 'suggested' ORDER BY created_at DESC LIMIT 2000",
                (rid,),
            )
        ops: dict[tuple[str, str], list[str]] = {}
        for r in rows or []:
            if not isinstance(r, dict):
                continue
            col = str(r.get("column_name") or "").strip()
            ft = str(r.get("fix_type") or "").strip()
            sid = str(r.get("id") or "").strip()
            if not col or not ft or not sid:
                continue
            ops.setdefault((col, ft), []).append(sid)

        if not ops:
            raise ValueError("No hay auto-fixes sugeridos para aplicar.")

        import pandas as pd

        df = pd.read_csv(path, dtype=str, keep_default_na=False)

        def clean_invisible(s: str) -> str:
            return re.sub(r"[\u200b\u200c\u200d\ufeff]", "", s or "")

        for (col, ft), _ids in ops.items():
            if col not in df.columns:
                continue
            series = df[col].astype(str)
            if ft == "trim_spaces":
                df[col] = series.map(lambda x: (x or "").strip())
            elif ft == "upper":
                df[col] = series.map(lambda x: (x or "").upper())
            elif ft == "normalize_yes_no":
                df[col] = series.map(lambda x: _normalize_yes_no(x) or (x or "").strip())
            elif ft == "remove_invisible":
                df[col] = series.map(lambda x: clean_invisible((x or "")))

        base_dir = (os.environ.get("REVIEWDATA_DATA_DIR") or "").strip()
        if not base_dir:
            base_dir = str((Path.cwd() / "_web_storage").resolve())
            os.environ["REVIEWDATA_DATA_DIR"] = base_dir
        out_dir = Path(base_dir) / "tmp"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = str(out_dir / f"autofix_{rid[:8]}.csv")
        df.to_csv(out_path, index=False, encoding="utf-8")

        try:
            if ids:
                self._db.execute_query("UPDATE auto_fix_suggestions SET status = 'applied' WHERE id = ANY(%s::text[])", (ids,))
            else:
                all_ids = [sid for _, sids in ops.items() for sid in sids]
                if all_ids:
                    self._db.execute_query("UPDATE auto_fix_suggestions SET status = 'applied' WHERE id = ANY(%s::text[])", (all_ids,))
        except Exception:
            pass

        return out_path

    def get_grouped_findings(self, run_id: str, limit: int = 200) -> list[dict]:
        if not self._db_enabled():
            return []
        rid = str(run_id or "").strip()
        if not rid:
            return []
        lim = max(1, min(1000, int(limit or 200)))
        rows = self._db.fetch_all(
            """
            SELECT rule_id, rule_name, field, error_type, expected, description, recommendation, business_impact,
                   MIN(id) AS sample_finding_id,
                   COUNT(*) AS n,
                   MAX(
                       CASE
                           WHEN severity = 'Crítica' THEN 4
                           WHEN severity = 'Alta' THEN 3
                           WHEN severity = 'Media' THEN 2
                           WHEN severity = 'Baja' THEN 1
                           ELSE 0
                       END
                   ) AS sev_rank
            FROM findings
            WHERE run_id = %s
            GROUP BY rule_id, rule_name, field, error_type, expected, description, recommendation, business_impact
            ORDER BY n DESC
            LIMIT %s
            """,
            (rid, lim),
        )
        sev_map = {4: "Crítica", 3: "Alta", 2: "Media", 1: "Baja"}
        out = []
        for r in rows or []:
            if not isinstance(r, dict):
                continue
            out.append(
                {
                    "rule_id": str(r.get("rule_id") or ""),
                    "rule_name": str(r.get("rule_name") or ""),
                    "field": str(r.get("field") or ""),
                    "error_type": str(r.get("error_type") or ""),
                    "expected": str(r.get("expected") or ""),
                    "description": str(r.get("description") or ""),
                    "recommendation": str(r.get("recommendation") or ""),
                    "business_impact": str(r.get("business_impact") or ""),
                    "sample_finding_id": str(r.get("sample_finding_id") or ""),
                    "count": int(r.get("n") or 0),
                    "worst_severity": sev_map.get(int(r.get("sev_rank") or 0), "Media"),
                }
            )
        return out

    def _get_finding_row(self, finding_id: str) -> dict | None:
        if not self._db_enabled():
            return None
        fid = str(finding_id or "").strip()
        if not fid:
            return None
        rows = self._db.fetch_all(
            """
            SELECT id, run_id, dataset_id, rule_id, rule_name, field, value, description, severity,
                   error_type, expected, recommendation, business_impact, row_index, created_at
            FROM findings
            WHERE id = %s
            LIMIT 1
            """,
            (fid,),
        )
        if rows and isinstance(rows[0], dict):
            return rows[0]
        return None

    def explain_finding(self, finding_id: str) -> dict:
        row = self._get_finding_row(finding_id)
        if not row:
            raise ValueError("Hallazgo no encontrado.")
        col = str(row.get("field") or "")
        rule = str(row.get("rule_name") or row.get("rule_id") or "")
        desc = str(row.get("description") or "")
        expected = str(row.get("expected") or "")
        rec = str(row.get("recommendation") or "")
        impact = str(row.get("business_impact") or "")
        sev = self._normalize_severity(str(row.get("severity") or "Media"))

        parts: list[str] = []
        if rule:
            parts.append(f"Regla: {rule}.")
        if col:
            parts.append(f"Campo: {col}.")
        if desc:
            parts.append(f"Qué pasó: {desc}.")
        if expected:
            parts.append(f"Qué se esperaba: {expected}.")
        if impact:
            parts.append(f"Impacto operativo: {impact}.")
        if rec:
            parts.append(f"Acción sugerida: {rec}.")
        explanation = " ".join(p.strip() for p in parts if p.strip()).strip()
        if not explanation:
            explanation = "No hay suficiente información para explicar este hallazgo."

        return {
            "finding_id": str(row.get("id") or ""),
            "run_id": str(row.get("run_id") or ""),
            "dataset_id": str(row.get("dataset_id") or ""),
            "severity": sev,
            "explanation": explanation,
            "business_impact": impact,
            "recommendation": rec,
        }

    def create_rule_from_finding(self, finding_id: str) -> dict:
        row = self._get_finding_row(finding_id)
        if not row:
            raise ValueError("Hallazgo no encontrado.")

        col = str(row.get("field") or "").split(",")[0].strip()
        if not col:
            raise ValueError("Campo inválido para crear regla.")
        error_type = str(row.get("error_type") or "").strip().lower()
        expected = str(row.get("expected") or "").strip()
        desc = str(row.get("description") or "").strip()
        val = str(row.get("value") or "").strip()
        sev = self._normalize_severity(str(row.get("severity") or "Media"))

        et = ""
        params: dict = {"column_name": col}
        reason = ""

        if expected.startswith("^") and expected.endswith("$"):
            et = "regex"
            params["regex"] = expected
            reason = "Se detectó un patrón esperado (regex) en el hallazgo."
        elif error_type == "regex":
            et = "regex"
            params["regex"] = expected if expected else "^.+$"
            reason = "El hallazgo indica formato inválido; se generó regla de regex."
        elif "cp" in col.lower() or "postal" in col.lower():
            et = "regex"
            params["regex"] = r"^\d{5}$"
            reason = "La columna parece código postal; se sugiere regex de 5 dígitos."
        elif "placa" in col.lower():
            et = "regex"
            params["regex"] = r"^[A-Z]{3}-\d{3}$"
            reason = "La columna parece placas; se sugiere regex AAA-999."
        elif _normalize_yes_no(val) is not None or "si_no" in error_type:
            et = "allowed_values"
            params["allowed_values"] = ["Si", "No"]
            reason = "Se detectó campo tipo Si/No; se sugiere catálogo permitido."
        elif "requerid" in desc.lower() or "vacío" in desc.lower() or "nulo" in desc.lower() or error_type in ("required", "non_null"):
            et = "non_null"
            reason = "El hallazgo sugiere campo obligatorio vacío; se generó regla non-null."
        elif "duplic" in desc.lower() or error_type in ("unique", "duplicate"):
            et = "unique"
            reason = "El hallazgo sugiere duplicados; se generó regla UNIQUE."

        if not et:
            return {"ok": False, "message": "No se pudo derivar una regla segura desde este hallazgo."}

        rule_id = f"ai_from_finding_{uuid.uuid4()}"
        name = f"AI Expectation: {col}"
        description = f"Generada desde hallazgo {str(row.get('id') or '')[:8]} · {desc}" if desc else f"Generada desde hallazgo {str(row.get('id') or '')[:8]}"
        parameters_json = json.dumps({"expectation_type": et, **params}, ensure_ascii=False)

        self._db.execute_query(
            """
            INSERT INTO rules (id, name, description, rule_type, severity, active, parameters_json)
            VALUES (%s, %s, %s, 'ai_expectation', %s, TRUE, %s)
            ON CONFLICT (id) DO NOTHING
            """,
            (rule_id, name, description, sev, parameters_json),
        )
        self._log_activity("Reglas", "AI", f"Regla creada desde hallazgo: {rule_id}")
        return {"ok": True, "rule_id": rule_id, "name": name, "expectation_type": et, "reason": reason}

    def answer_nl_query(self, question: str, dataset_id: str | None = None, run_id: str | None = None) -> dict:
        q = str(question or "").strip()
        if not q:
            return {"intent": "unknown", "answer": "Pregunta vacía.", "data": {}}
        text = q.lower()
        intent = "summary_run"
        if "crític" in text or "critico" in text:
            intent = "critical_findings"
        elif "columna" in text and ("más" in text or "mas" in text):
            intent = "top_columns"
        elif "recomend" in text:
            intent = "recommendations"
        elif "score" in text or "calidad" in text:
            intent = "score_explanation"
        elif "compar" in text or "drift" in text:
            intent = "compare_runs"

        rid = str(run_id or "").strip()
        did = str(dataset_id or "").strip()

        if not rid and did and self._db_enabled():
            rows = self._db.fetch_all("SELECT id FROM runs WHERE dataset_id = %s ORDER BY created_at DESC LIMIT 1", (did,))
            if rows and isinstance(rows[0], dict):
                rid = str(rows[0].get("id") or "")

        if intent == "critical_findings":
            fs = self.get_findings(run_id=rid) if rid else []
            crit = [f for f in fs if str(f.get("severity") or "") == "Crítica"][:200]
            return {"intent": intent, "answer": f"Se encontraron {len(crit)} hallazgos críticos (muestra).", "data": {"items": crit}}
        if intent == "top_columns":
            ov = self.get_stats_overview(dataset_id=did or None)
            return {"intent": intent, "answer": "Columnas más problemáticas (top).", "data": {"top_columns": ov.get("top_columns") or []}}
        if intent == "recommendations":
            recs = self.get_ai_recommendations(rid) if rid else []
            if not recs:
                recs = self.get_recommendations(rid) if rid else []
            return {"intent": intent, "answer": "Recomendaciones para este run.", "data": {"items": recs}}
        if intent == "score_explanation":
            if not rid or not self._db_enabled():
                return {"intent": intent, "answer": "No hay run disponible para explicar score.", "data": {}}
            rows = self._db.fetch_all("SELECT score, grade, explanation FROM dataset_health WHERE run_id = %s ORDER BY created_at DESC LIMIT 1", (rid,))
            if rows and isinstance(rows[0], dict):
                return {"intent": intent, "answer": "Explicación del score de salud.", "data": {"score": int(rows[0].get("score") or 0), "grade": str(rows[0].get("grade") or ""), "explanation": self._parse_json(rows[0].get("explanation"), {})}}
            return {"intent": intent, "answer": "Sin explicación disponible.", "data": {}}
        if intent == "compare_runs":
            drift = self.get_dataset_drift(rid) if rid else []
            return {"intent": intent, "answer": "Cambios detectados vs run anterior.", "data": {"items": drift}}

        ov = self.get_stats_overview(dataset_id=did or None)
        return {"intent": intent, "answer": "Resumen del dataset.", "data": {"overview": ov}}

    def get_recommendations(self, run_id: str) -> list[dict]:
        rid = str(run_id or "").strip()
        if not rid:
            return []
        findings = self.get_findings(run_id=rid)

        run = next((r for r in self._runs if str(r.get("id") or "") == rid), None)
        if not run and self._db_enabled():
            rows = self._db.fetch_all(
                "SELECT id, rules_applied_json, rules_passed_json, rules_failed_json FROM runs WHERE id = %s LIMIT 1",
                (rid,),
            )
            if rows and isinstance(rows[0], dict):
                run = dict(rows[0])

        rules_applied = self._parse_json((run or {}).get("rules_applied"), self._parse_json((run or {}).get("rules_applied_json"), []))
        rules_passed = self._parse_json((run or {}).get("rules_passed"), self._parse_json((run or {}).get("rules_passed_json"), []))
        rules_failed = self._parse_json((run or {}).get("rules_failed"), self._parse_json((run or {}).get("rules_failed_json"), []))
        if not isinstance(rules_applied, list):
            rules_applied = []
        if not isinstance(rules_passed, list):
            rules_passed = []
        if not isinstance(rules_failed, list):
            rules_failed = []

        rule_ids: list[str] = [str(x) for x in rules_failed if str(x)]
        if not rule_ids:
            seen = set()
            for f in findings:
                fr = str(f.get("rule_id") or "").strip()
                if fr and fr not in seen:
                    seen.add(fr)
                    rule_ids.append(fr)
        if not rule_ids:
            return []

        existing: dict[str, dict] = {}
        if self._db_enabled():
            rows = self._db.fetch_all(
                "SELECT rule_id, recommendation, action_type, source FROM recommendations WHERE rule_id = ANY(%s::text[])",
                (list(rule_ids),),
            )
            for r in rows or []:
                rule_id = str(r.get("rule_id", "")).strip()
                if not rule_id:
                    continue
                existing[rule_id] = {
                    "rule_id": rule_id,
                    "recommendation": str(r.get("recommendation", "") or ""),
                    "action_type": str(r.get("action_type", "") or ""),
                    "source": str(r.get("source", "") or ""),
                }

        missing = [rid for rid in rule_ids if rid not in existing]

        generated: list[dict] = []
        if missing:
            api_key = (os.environ.get("REVIEWDATA_OPENROUTER_API_KEY") or os.environ.get("REVIEWDATA_LLM_API_KEY") or "").strip()
            if api_key:
                generated = self._generate_recommendations_via_llm(missing, findings)
                if self._db_enabled() and generated:
                    for rec in generated:
                        rid = str(rec.get("rule_id", "")).strip()
                        txt = str(rec.get("recommendation", "") or "").strip()
                        if not rid or not txt:
                            continue
                        action_type = str(rec.get("action_type", "") or "").strip() or None
                        source = str(rec.get("source", "") or "").strip() or "llm"
                        self._db.execute_query(
                            """
                            INSERT INTO recommendations (rule_id, recommendation, action_type, source, updated_at)
                            VALUES (%s, %s, %s, %s, now())
                            ON CONFLICT (rule_id) DO UPDATE
                            SET recommendation = EXCLUDED.recommendation,
                                action_type = EXCLUDED.action_type,
                                source = EXCLUDED.source,
                                updated_at = now()
                            """,
                            (rid, txt, action_type, source),
                        )
                        existing[rid] = {"rule_id": rid, "recommendation": txt, "action_type": action_type or "", "source": source}

        out = []
        rules_map = {str(r.get("id") or ""): str(r.get("name") or "") for r in self.get_rules() if isinstance(r, dict)}
        by_rule: dict[str, list[dict]] = {}
        for f in findings:
            fr = str(f.get("rule_id") or "").strip()
            if not fr:
                continue
            arr = by_rule.setdefault(fr, [])
            if len(arr) < 5000:
                arr.append(f)

        sev_order = ["Crítica", "Alta", "Media", "Baja"]
        sev_rank = {k: i for i, k in enumerate(sev_order)}
        passed_set = {str(x) for x in rules_passed}
        failed_set = {str(x) for x in rules_failed}

        for r_id in rule_ids:
            fs = by_rule.get(r_id, [])
            sev_counts = {k: 0 for k in sev_order}
            worst = "Baja"
            for f in fs:
                s = self._normalize_severity(str(f.get("severity") or "Alta"))
                if s not in sev_counts:
                    sev_counts[s] = 0
                sev_counts[s] += 1
                if sev_rank.get(s, 3) < sev_rank.get(worst, 3):
                    worst = s

            status = "ok"
            if str(r_id) in failed_set or fs:
                status = "fail"
            if str(r_id) in passed_set and not fs:
                status = "ok"

            base = existing.get(r_id) or {
                "rule_id": r_id,
                "recommendation": self._recommendations.get(r_id, "Revisar la inconsistencia y aplicar corrección."),
                "action_type": "",
                "source": "static",
            }
            rec_txt = str(base.get("recommendation") or "").strip()
            if status == "ok" and not rec_txt:
                rec_txt = "Sin inconsistencias detectadas para esta regla."

            examples = []
            for f in fs[:3]:
                examples.append(
                    {
                        "field": str(f.get("field") or ""),
                        "value": str(f.get("value") or ""),
                        "description": str(f.get("description") or ""),
                        "severity": self._normalize_severity(str(f.get("severity") or "Alta")),
                        "row_index": f.get("row_index"),
                    }
                )

            out.append(
                {
                    "rule_id": r_id,
                    "rule_name": rules_map.get(r_id, r_id),
                    "status": status,
                    "findings_count": int(len(fs)),
                    "worst_severity": worst,
                    "severity_counts": sev_counts,
                    "examples": examples,
                    "recommendation": rec_txt,
                    "action_type": str(base.get("action_type") or ""),
                    "source": str(base.get("source") or ""),
                }
            )
        return out

    def get_dashboard_stats(self) -> dict:
        if self._db_enabled():
            ds = self._db.fetch_all("SELECT COUNT(*) AS n FROM datasets")
            runs = self._db.fetch_all("SELECT COUNT(*) AS n FROM runs")
            inc = self._db.fetch_all("SELECT COUNT(*) AS n FROM findings")
            sev_rows = self._db.fetch_all("SELECT severity, COUNT(*) AS n FROM findings GROUP BY severity")
            counts = {"Cr\u00edtica": 0}
            for r in sev_rows or []:
                sev = self._normalize_severity(str(r.get("severity", "") or ""))
                counts[sev] = counts.get(sev, 0) + int(r.get("n", 0) or 0)
            latest_run_rows = self._db.fetch_all(
                "SELECT id, dataset_name, quality_score, created_at FROM runs ORDER BY created_at DESC LIMIT 1"
            )
            latest_run = latest_run_rows[0] if latest_run_rows and isinstance(latest_run_rows[0], dict) else {}
            latest_id = str(latest_run.get("id") or "").strip()
            prev_score = None
            if latest_id:
                prev_rows = self._db.fetch_all(
                    "SELECT quality_score FROM runs WHERE id <> %s ORDER BY created_at DESC LIMIT 1",
                    (latest_id,),
                )
                if prev_rows and isinstance(prev_rows[0], dict):
                    try:
                        prev_score = int(prev_rows[0].get("quality_score") or 0)
                    except Exception:
                        prev_score = None
            health_score = None
            health_grade = ""
            if latest_id:
                hrows = self._db.fetch_all(
                    "SELECT score, grade FROM dataset_health WHERE run_id = %s ORDER BY created_at DESC LIMIT 1",
                    (latest_id,),
                )
                if hrows and isinstance(hrows[0], dict):
                    try:
                        health_score = int(hrows[0].get("score") or 0)
                    except Exception:
                        health_score = None
                    health_grade = str(hrows[0].get("grade") or "")
            latest_quality = None
            try:
                latest_quality = int(latest_run.get("quality_score") or 0)
            except Exception:
                latest_quality = None
            health_delta = None
            if latest_quality is not None and prev_score is not None:
                health_delta = int(latest_quality) - int(prev_score)
            return {
                "datasets": int((ds or [{}])[0].get("n", 0) or 0),
                "validations": int((runs or [{}])[0].get("n", 0) or 0),
                "inconsistencies": int((inc or [{}])[0].get("n", 0) or 0),
                "critical": int(counts.get("Cr\u00edtica", 0) or 0),
                "latest_run_id": latest_id,
                "latest_dataset_name": str(latest_run.get("dataset_name") or ""),
                "latest_quality_score": latest_quality,
                "latest_health_score": health_score,
                "latest_health_grade": health_grade,
                "latest_score_delta": health_delta,
            }
        return {
            "datasets": len(self._datasets),
            "validations": len(self._runs),
            "inconsistencies": len(self._findings),
            "critical": sum(1 for f in self._findings if f.get("severity") == "Cr\u00edtica"),
        }

    def get_severity_counts(self, dataset_id: str | None = None) -> dict:
        counts = {"Cr\u00edtica": 0, "Alta": 0, "Media": 0, "Baja": 0}
        if self._db_enabled():
            if dataset_id:
                rows = self._db.fetch_all(
                    "SELECT severity, COUNT(*) AS n FROM findings WHERE dataset_id = %s GROUP BY severity",
                    (str(dataset_id),),
                )
            else:
                rows = self._db.fetch_all("SELECT severity, COUNT(*) AS n FROM findings GROUP BY severity")
            for r in rows or []:
                sev = self._normalize_severity(str(r.get("severity", "") or ""))
                n = int(r.get("n", 0) or 0)
                if sev not in counts:
                    counts[sev] = 0
                counts[sev] += n
            return counts
        findings = self.get_findings(dataset_id=dataset_id)
        for f in findings:
            sev = self._normalize_severity(str(f.get("severity", "Alta") or "Alta"))
            if sev not in counts:
                counts[sev] = 0
            counts[sev] += 1
        return counts

    def get_trends(self, days: int = 7, dataset_id: str | None = None) -> dict:
        d = max(1, min(90, int(days or 7)))
        if not self._db_enabled():
            return {"days": d, "quality_trend": [], "errors_trend": [], "runs_by_hour": [], "valid_trend": [], "drift_trend": []}

        params_runs: list = []
        where_runs = " WHERE created_at >= now() - (%s || ' days')::interval"
        params_runs.append(str(d))
        if dataset_id:
            where_runs += " AND dataset_id = %s"
            params_runs.append(str(dataset_id))

        rows = self._db.fetch_all(
            """
            SELECT to_char(date_trunc('day', created_at), 'YYYY-MM-DD') AS day,
                   AVG(quality_score) AS avg_score,
                   COUNT(*) AS runs,
                   SUM(inconsistencies) AS total_incons
            FROM runs
            """
            + where_runs
            + " GROUP BY day ORDER BY day ASC",
            tuple(params_runs),
        )
        quality_trend = []
        for r in rows or []:
            if not isinstance(r, dict):
                continue
            quality_trend.append(
                {
                    "day": str(r.get("day") or ""),
                    "avg_quality_score": int(float(r.get("avg_score") or 0)),
                    "runs": int(r.get("runs") or 0),
                    "inconsistencies": int(r.get("total_incons") or 0),
                }
            )

        params_find: list = []
        where_find = " WHERE created_at >= now() - (%s || ' days')::interval"
        params_find.append(str(d))
        if dataset_id:
            where_find += " AND dataset_id = %s"
            params_find.append(str(dataset_id))

        frows = self._db.fetch_all(
            "SELECT to_char(date_trunc('day', created_at), 'YYYY-MM-DD') AS day, COUNT(*) AS n FROM findings"
            + where_find
            + " GROUP BY day ORDER BY day ASC",
            tuple(params_find),
        )
        errors_trend = [{"day": str(r.get("day") or ""), "count": int(r.get("n") or 0)} for r in frows or [] if isinstance(r, dict)]

        hparams: list = []
        hwhere = " WHERE created_at >= now() - interval '24 hours'"
        if dataset_id:
            hwhere += " AND dataset_id = %s"
            hparams.append(str(dataset_id))
        hrows = self._db.fetch_all(
            "SELECT to_char(date_trunc('hour', created_at), 'YYYY-MM-DD HH24:00') AS hour, COUNT(*) AS n FROM runs"
            + hwhere
            + " GROUP BY hour ORDER BY hour ASC",
            tuple(hparams),
        )
        runs_by_hour = [{"hour": str(r.get("hour") or ""), "count": int(r.get("n") or 0)} for r in hrows or [] if isinstance(r, dict)]

        vparams: list = []
        vwhere = " WHERE created_at >= now() - (%s || ' days')::interval"
        vparams.append(str(d))
        if dataset_id:
            vwhere += " AND dataset_id = %s"
            vparams.append(str(dataset_id))
        vrows = self._db.fetch_all(
            """
            WITH runs_scope AS (
                SELECT id, created_at, total_records
                FROM runs
            """
            + vwhere
            + """
            ),
            affected AS (
                SELECT f.run_id, COUNT(DISTINCT f.row_index) AS affected_rows
                FROM findings f
                JOIN runs_scope r ON r.id = f.run_id
                WHERE f.row_index IS NOT NULL
                GROUP BY f.run_id
            )
            SELECT to_char(date_trunc('day', r.created_at), 'YYYY-MM-DD') AS day,
                   SUM(r.total_records) AS total_records,
                   SUM(COALESCE(a.affected_rows, 0)) AS affected_rows
            FROM runs_scope r
            LEFT JOIN affected a ON a.run_id = r.id
            GROUP BY day
            ORDER BY day ASC
            """,
            tuple(vparams),
        )
        valid_trend = []
        for r in vrows or []:
            if not isinstance(r, dict):
                continue
            tr = int(r.get("total_records") or 0)
            ar = int(r.get("affected_rows") or 0)
            pct = 0
            if tr > 0:
                pct = int(round((max(0, tr - ar) / float(tr)) * 100.0))
            valid_trend.append({"day": str(r.get("day") or ""), "valid_pct": pct, "total_records": tr, "affected_rows": ar})

        dparams: list = []
        dwhere = " WHERE created_at >= now() - (%s || ' days')::interval"
        dparams.append(str(d))
        if dataset_id:
            dwhere += " AND dataset_id = %s"
            dparams.append(str(dataset_id))
        drows = self._db.fetch_all(
            """
            SELECT to_char(date_trunc('day', created_at), 'YYYY-MM-DD') AS day,
                   COUNT(*) AS n,
                   SUM(CASE WHEN severity = 'Crítica' THEN 1 ELSE 0 END) AS critical,
                   SUM(CASE WHEN severity = 'Alta' THEN 1 ELSE 0 END) AS high,
                   SUM(CASE WHEN severity = 'Media' THEN 1 ELSE 0 END) AS medium,
                   SUM(CASE WHEN severity = 'Baja' THEN 1 ELSE 0 END) AS low
            FROM dataset_drift
            """
            + dwhere
            + " GROUP BY day ORDER BY day ASC",
            tuple(dparams),
        )
        drift_trend = []
        for r in drows or []:
            if not isinstance(r, dict):
                continue
            drift_trend.append(
                {
                    "day": str(r.get("day") or ""),
                    "count": int(r.get("n") or 0),
                    "critical": int(r.get("critical") or 0),
                    "high": int(r.get("high") or 0),
                    "medium": int(r.get("medium") or 0),
                    "low": int(r.get("low") or 0),
                }
            )

        return {
            "days": d,
            "quality_trend": quality_trend,
            "errors_trend": errors_trend,
            "runs_by_hour": runs_by_hour,
            "valid_trend": valid_trend,
            "drift_trend": drift_trend,
        }

    def get_global_ai_insights_24h(self, dataset_id: str | None = None) -> list[dict]:
        if not self._db_enabled():
            return []

        params_today: list = []
        where_runs_today = " WHERE created_at >= now() - interval '24 hours'"
        where_runs_prev = " WHERE created_at < now() - interval '24 hours' AND created_at >= now() - interval '48 hours'"
        if dataset_id:
            where_runs_today += " AND dataset_id = %s"
            where_runs_prev += " AND dataset_id = %s"
            params_today.append(str(dataset_id))

        r_today = self._db.fetch_all("SELECT AVG(quality_score) AS v FROM runs" + where_runs_today, tuple(params_today))
        r_prev = self._db.fetch_all("SELECT AVG(quality_score) AS v FROM runs" + where_runs_prev, tuple(params_today))
        avg_today = float((r_today[0].get("v") if r_today and isinstance(r_today[0], dict) else 0) or 0)
        avg_prev = float((r_prev[0].get("v") if r_prev and isinstance(r_prev[0], dict) else 0) or 0)

        insights: list[dict] = []
        if avg_prev > 0:
            drop = avg_prev - avg_today
            if drop >= 10:
                pct = int((drop / max(1.0, avg_prev)) * 100)
                insights.append(
                    {
                        "type": "warning",
                        "title": "AI WARNING",
                        "message": f"Dataset quality dropped {pct}% since yesterday.",
                        "meta": {"avg_today": int(avg_today), "avg_yesterday": int(avg_prev)},
                    }
                )

        fparams: list = []
        where_find_today = " WHERE created_at >= now() - interval '24 hours'"
        where_find_prev = " WHERE created_at < now() - interval '24 hours' AND created_at >= now() - interval '48 hours'"
        if dataset_id:
            where_find_today += " AND dataset_id = %s"
            where_find_prev += " AND dataset_id = %s"
            fparams.append(str(dataset_id))

        like_cp = " AND (lower(field) LIKE '%cp%' OR lower(field) LIKE '%postal%')"
        cp_today = self._db.fetch_all("SELECT COUNT(*) AS n FROM findings" + where_find_today + like_cp, tuple(fparams))
        cp_prev = self._db.fetch_all("SELECT COUNT(*) AS n FROM findings" + where_find_prev + like_cp, tuple(fparams))
        n_today = int((cp_today[0].get("n") if cp_today and isinstance(cp_today[0], dict) else 0) or 0)
        n_prev = int((cp_prev[0].get("n") if cp_prev and isinstance(cp_prev[0], dict) else 0) or 0)
        if n_today >= 10 and n_prev >= 1:
            inc = n_today - n_prev
            pct = int((inc / max(1, n_prev)) * 100)
            if pct >= 30:
                insights.append(
                    {
                        "type": "detected",
                        "title": "AI DETECTED",
                        "message": f"Spike in invalid postal codes (+{pct}%).",
                        "meta": {"today": n_today, "yesterday": n_prev},
                    }
                )

        top_today = self._db.fetch_all(
            "SELECT field, COUNT(*) AS n FROM findings" + where_find_today + " GROUP BY field ORDER BY n DESC LIMIT 8",
            tuple(fparams),
        )
        top_prev = self._db.fetch_all(
            "SELECT field, COUNT(*) AS n FROM findings" + where_find_prev + " GROUP BY field ORDER BY n DESC LIMIT 50",
            tuple(fparams),
        )
        prev_map = {str(r.get("field") or ""): int(r.get("n") or 0) for r in top_prev or [] if isinstance(r, dict)}
        best = None
        for r in top_today or []:
            if not isinstance(r, dict):
                continue
            f = str(r.get("field") or "")
            n = int(r.get("n") or 0)
            p = int(prev_map.get(f, 0) or 0)
            if p <= 0 or n < 8:
                continue
            pct = int(((n - p) / max(1, p)) * 100)
            if pct < 40:
                continue
            cand = {"field": f, "pct": pct, "today": n, "yesterday": p}
            if not best or cand["pct"] > best["pct"]:
                best = cand
        if best:
            insights.append(
                {
                    "type": "detected",
                    "title": "AI DETECTED",
                    "message": f"Spike in invalid values for '{best['field']}' (+{best['pct']}%).",
                    "meta": best,
                }
            )

        if not insights:
            insights.append({"type": "info", "title": "AI INSIGHTS", "message": "No unusual anomalies detected in the last 24 hours.", "meta": {}})
        return insights

    def _generate_recommendations_via_llm(self, rule_ids: list[str], findings: list[dict]) -> list[dict]:
        api_key = (os.environ.get("REVIEWDATA_OPENROUTER_API_KEY") or os.environ.get("REVIEWDATA_LLM_API_KEY") or "").strip()
        if not api_key:
            return []
        base_url = (os.environ.get("REVIEWDATA_OPENROUTER_BASE_URL") or os.environ.get("REVIEWDATA_LLM_BASE_URL") or "https://openrouter.ai/api/v1").strip().rstrip("/")
        model = (os.environ.get("REVIEWDATA_OPENROUTER_MODEL") or os.environ.get("REVIEWDATA_LLM_MODEL") or "openai/gpt-4o-mini").strip()
        timeout_s = int((os.environ.get("REVIEWDATA_LLM_TIMEOUT") or "30").strip() or "30")

        rule_meta = {r.id: {"name": r.name, "description": r.description, "rule_type": r.rule_type, "severity": r.severity} for r in self._rules}

        examples_by_rule: dict[str, list[dict]] = {}
        for f in findings:
            rid = str(f.get("rule_id", "") or "").strip()
            if not rid or rid not in rule_ids:
                continue
            arr = examples_by_rule.setdefault(rid, [])
            if len(arr) >= 3:
                continue
            arr.append(
                {
                    "field": f.get("field", ""),
                    "value": f.get("value", ""),
                    "description": f.get("description", ""),
                    "severity": f.get("severity", ""),
                }
            )

        payload_rules = []
        for rid in rule_ids:
            meta = rule_meta.get(rid, {})
            payload_rules.append(
                {
                    "rule_id": rid,
                    "name": meta.get("name", ""),
                    "description": meta.get("description", ""),
                    "rule_type": meta.get("rule_type", ""),
                    "severity": meta.get("severity", ""),
                    "examples": examples_by_rule.get(rid, []),
                }
            )

        system_prompt = (
            "Eres un asistente experto en calidad de datos para un sistema de validación de datasets.\n"
            "Debes generar recomendaciones claras, accionables y cortas para corregir inconsistencias.\n"
            "Responde SOLO JSON válido (sin texto adicional)."
        )
        user_prompt = {
            "task": "Generar recomendaciones por regla",
            "rules": payload_rules,
            "output_format": [
                {"rule_id": "string", "recommendation": "string", "action_type": "string"},
            ],
        }

        body = json.dumps(
            {
                "model": model,
                "temperature": 0.2,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": json.dumps(user_prompt, ensure_ascii=False)},
                ],
            },
            ensure_ascii=False,
        ).encode("utf-8")

        req = urllib.request.Request(
            url=f"{base_url}/chat/completions",
            data=body,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout_s) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as e:
            try:
                _ = e.read()
            except Exception:
                pass
            return []
        except Exception:
            return []

        try:
            data = json.loads(raw)
            content = (((data.get("choices") or [])[0] or {}).get("message") or {}).get("content") or ""
        except Exception:
            return []

        content = str(content).strip()
        if not content:
            return []

        parsed = None
        try:
            parsed = json.loads(content)
        except Exception:
            start = content.find("[")
            end = content.rfind("]")
            if start != -1 and end != -1 and end > start:
                try:
                    parsed = json.loads(content[start : end + 1])
                except Exception:
                    parsed = None
        if not isinstance(parsed, list):
            return []

        out = []
        for item in parsed:
            if not isinstance(item, dict):
                continue
            rid = str(item.get("rule_id", "") or "").strip()
            rec = str(item.get("recommendation", "") or "").strip()
            if not rid or not rec:
                continue
            if rid not in rule_ids:
                continue
            out.append(
                {
                    "rule_id": rid,
                    "recommendation": rec,
                    "action_type": str(item.get("action_type", "") or "").strip(),
                    "source": "llm",
                }
            )
        return out

    def get_reports(self) -> list[dict]:
        if self._db_enabled():
            limit = self._get_limit("REVIEWDATA_DB_MAX_REPORTS", 2000)
            rows = self._db.fetch_all(
                """
                SELECT id, run_id, dataset_id, dataset_name, format, status, generated_at, created_at
                FROM (
                    SELECT DISTINCT ON (run_id)
                        id, run_id, dataset_id, dataset_name, format, status, generated_at, created_at
                    FROM reports
                    ORDER BY run_id, created_at DESC
                ) t
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (int(limit),),
            )
            out = [self._normalize_report(r) for r in rows if isinstance(r, dict)]
            self._reports = list(out)
            return list(out)
        return list(self._reports)

    def get_reports_page(self, offset: int = 0, limit: int = 200) -> dict:
        off = max(0, int(offset or 0))
        lim = max(1, min(2000, int(limit or 200)))
        if self._db_enabled():
            total_rows = self._db.fetch_all("SELECT COUNT(DISTINCT run_id) AS n FROM reports")
            total = int((total_rows[0].get("n") if total_rows and isinstance(total_rows[0], dict) else 0) or 0)
            rows = self._db.fetch_all(
                """
                SELECT id, run_id, dataset_id, dataset_name, format, status, generated_at, created_at
                FROM (
                    SELECT DISTINCT ON (run_id)
                        id, run_id, dataset_id, dataset_name, format, status, generated_at, created_at
                    FROM reports
                    ORDER BY run_id, created_at DESC
                ) t
                ORDER BY created_at DESC
                OFFSET %s LIMIT %s
                """,
                (off, lim),
            )
            items = [self._normalize_report(r) for r in rows if isinstance(r, dict)]
            return {"items": items, "total": total, "offset": off, "limit": lim}

        rows = list(self._reports)
        total = len(rows)
        return {"items": rows[off : off + lim], "total": total, "offset": off, "limit": lim}

    def get_activity(self, limit: int = 200) -> list[dict]:
        if self._db_enabled():
            return list(self._db.fetch_all("SELECT * FROM activity_log ORDER BY created_at DESC LIMIT %s", (int(limit),)))
        return []

    def get_admin_summary(self) -> dict:
        if self._db_enabled():
            users = self._db.fetch_all("SELECT COUNT(*) AS n FROM users WHERE active = TRUE")
            datasets = self._db.fetch_all("SELECT COUNT(*) AS n FROM datasets")
            validations = self._db.fetch_all("SELECT COUNT(*) AS n FROM runs")
            reports = self._db.fetch_all("SELECT COUNT(*) AS n FROM reports")
            return {
                "users": int(users[0].get("n", 0)) if users else 0,
                "datasets": int(datasets[0].get("n", 0)) if datasets else 0,
                "validations": int(validations[0].get("n", 0)) if validations else 0,
                "reports": int(reports[0].get("n", 0)) if reports else 0,
            }
        return {"users": 1 if self._get_session() else 0, "datasets": len(self._datasets), "validations": len(self._runs), "reports": len(self._reports)}

    def list_users(self) -> list[dict]:
        if self._db_enabled():
            return list(self._db.fetch_all("SELECT id, email, role, active, created_at FROM users ORDER BY created_at DESC"))
        email = ""
        role = "user"
        s = self._get_session()
        if s:
            email = str(s.get("email", ""))
            role = str(s.get("role", "user"))
        return [{"id": "local", "email": email, "role": role, "active": True, "created_at": datetime.now().isoformat()}] if email else []

    def _validate_email(self, email: str) -> str:
        e = (email or "").strip()
        if not e:
            raise ValueError("Email requerido.")
        if len(e) > 254:
            raise ValueError("Email demasiado largo.")
        if " " in e or "\t" in e or "\n" in e or "\r" in e:
            raise ValueError("Email inválido.")
        parts = e.split("@")
        if len(parts) != 2:
            raise ValueError("Email inválido.")
        local, domain = parts[0], parts[1]
        if not local or not domain:
            raise ValueError("Email inválido.")
        if len(local) > 64:
            raise ValueError("Email inválido.")
        email_re = re.compile(r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)+$")
        if not email_re.fullmatch(e):
            raise ValueError("Email inválido. Debe ser un correo válido.")
        return e

    def _validate_password(self, password: str) -> str:
        p = str(password or "")
        if not p:
            raise ValueError("Contraseña requerida.")
        if len(p) < 10:
            raise ValueError("Contraseña inválida. Mínimo 10 caracteres.")
        if len(p) > 64:
            raise ValueError("Contraseña inválida. Máximo 64 caracteres.")
        if re.search(r"\s", p):
            raise ValueError("Contraseña inválida. No debe contener espacios.")
        if not re.search(r"[A-Za-z]", p):
            raise ValueError("Contraseña inválida. Debe incluir al menos una letra.")
        if not re.search(r"\d", p):
            raise ValueError("Contraseña inválida. Debe incluir al menos un número.")
        if any(ord(ch) < 33 or ord(ch) > 126 for ch in p):
            raise ValueError("Contraseña inválida. Usa caracteres imprimibles (sin espacios).")
        return p

    def create_user(self, email: str, password: str, role: str = "user", active: bool = True) -> dict:
        session = self._require_session()
        if str(session.get("role", "user")) != "admin":
            raise ValueError("Acceso denegado: se requiere rol admin.")
        e = self._validate_email(email)
        p = self._validate_password(password)
        role = (role or "user").strip().lower()
        if role not in ("admin", "user"):
            role = "user"
        from services.auth_service import _sha256

        user_id = str(uuid.uuid4())
        if self._db_enabled():
            exists = self._db.fetch_all("SELECT 1 AS x FROM users WHERE lower(email) = lower(%s) LIMIT 1", (e,))
            if exists:
                raise ValueError("El usuario ya existe.")
            ok = self._db.execute_query(
                """
                INSERT INTO users (id, email, password_hash, role, active)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (email) DO NOTHING
                """,
                (user_id, e, _sha256(p), role, bool(active)),
            )
            if not ok:
                raise ValueError("No se pudo crear el usuario.")
        self._log_activity("Admin", "Crear usuario", f"Usuario creado: {e} ({role})")
        return {"id": user_id, "email": e, "role": role, "active": bool(active)}

    def update_user(self, user_id: str, role: str | None = None, active: bool | None = None) -> bool:
        session = self._require_session()
        if str(session.get("role", "user")) != "admin":
            raise ValueError("Acceso denegado: se requiere rol admin.")
        uid = (user_id or "").strip()
        if not uid:
            return False
        if role is None and active is None:
            return False
        if role is not None:
            r = (role or "user").strip().lower()
            if r not in ("admin", "user"):
                r = "user"
            role = r

        sets = []
        params = []
        if role is not None:
            sets.append("role = %s")
            params.append(role)
        if active is not None:
            sets.append("active = %s")
            params.append(bool(active))
        params.append(uid)
        q = "UPDATE users SET " + ", ".join(sets) + " WHERE id = %s"
        ok = bool(self._db.execute_query(q, tuple(params)))
        if ok:
            self._log_activity("Admin", "Actualizar usuario", f"Usuario actualizado: {uid[:8]}")
        return ok

    def reset_user_password(self, user_id: str, new_password: str) -> bool:
        session = self._require_session()
        if str(session.get("role", "user")) != "admin":
            raise ValueError("Acceso denegado: se requiere rol admin.")
        uid = (user_id or "").strip()
        if not uid:
            return False
        p = self._validate_password(new_password)
        from services.auth_service import _sha256

        ok = bool(self._db.execute_query("UPDATE users SET password_hash = %s WHERE id = %s", (_sha256(p), uid)))
        if ok:
            self._log_activity("Admin", "Reset contraseña", f"Contraseña actualizada: {uid[:8]}")
        return ok

    def delete_user(self, user_id: str) -> bool:
        session = self._require_session()
        if str(session.get("role", "user")) != "admin":
            raise ValueError("Acceso denegado: se requiere rol admin.")
        uid = (user_id or "").strip()
        if not uid:
            return False
        me = str(session.get("user_id", "") or "").strip()
        if me and me == uid:
            raise ValueError("No puedes eliminar tu propio usuario.")
        ok = bool(self._db.execute_query("DELETE FROM users WHERE id = %s", (uid,)))
        if ok:
            self._log_activity("Admin", "Eliminar usuario", f"Usuario eliminado: {uid[:8]}")
        return ok

    def set_rule_active(self, rule_id: str, active: bool) -> bool:
        session = self._require_session()
        if str(session.get("role", "user")) != "admin":
            raise ValueError("Acceso denegado: se requiere rol admin.")
        rid = (rule_id or "").strip()
        if not rid:
            return False
        if self._db_enabled():
            ok = self._db.execute_query("UPDATE rules SET active = %s WHERE id = %s", (bool(active), rid))
            self._log_activity("Admin", "Reglas", f"Regla {'activada' if active else 'desactivada'}: {rid}")
            return bool(ok)
        return False

    def create_rule(self, rule_id: str, name: str, description: str, rule_type: str, severity: str, active: bool = True) -> bool:
        session = self._require_session()
        if str(session.get("role", "user")) != "admin":
            raise ValueError("Acceso denegado: se requiere rol admin.")
        rid = (rule_id or "").strip()
        if not rid:
            raise ValueError("ID de regla requerido.")
        sev = self._normalize_severity(severity)
        if sev not in ("Crítica", "Alta", "Media", "Baja"):
            sev = "Alta"
        if self._db_enabled():
            ok = self._db.execute_query(
                """
                INSERT INTO rules (id, name, description, rule_type, severity, active)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                    name = EXCLUDED.name,
                    description = EXCLUDED.description,
                    rule_type = EXCLUDED.rule_type,
                    severity = EXCLUDED.severity,
                    active = EXCLUDED.active
                """,
                ((rid), (name or "").strip(), (description or "").strip(), (rule_type or "").strip(), sev, bool(active)),
            )
            self._log_activity("Admin", "Reglas", f"Regla guardada: {rid}")
            return bool(ok)
        return False

    def get_dataset_row_preview(self, dataset_id: str, row_index: int) -> dict | None:
        ds = self._get_dataset_meta(dataset_id)
        if not ds:
            return None
        self._ensure_dataset_file(ds)
        path = str(ds.get("stored_path") or "")
        if not path or not os.path.exists(path):
            return None
        try:
            idx = int(row_index)
        except Exception:
            return None
        if idx < 0:
            return None

        cache = getattr(self, "_row_preview_cache", None)
        if cache is None:
            cache = {}
            setattr(self, "_row_preview_cache", cache)
        cache_key = (dataset_id, idx)
        if cache_key in cache:
            return dict(cache[cache_key])

        row = None
        with open(path, "r", newline="", encoding="utf-8-sig", errors="replace") as f:
            reader = csv.DictReader(f)
            for i, r in enumerate(reader):
                if i == idx:
                    row = {k: ("" if v is None else str(v)) for k, v in r.items()}
                    break
        if row is None:
            return None

        result = {"dataset_id": dataset_id, "row_index": idx, "row": row, "columns": list(row.keys())}
        if len(cache) > 200:
            try:
                cache.pop(next(iter(cache.keys())))
            except Exception:
                cache.clear()
        cache[cache_key] = result
        return dict(result)

    def get_dataset_preview(self, dataset_id: str, offset: int = 0, limit: int = 20) -> dict:
        ds = self._get_dataset_meta(dataset_id)
        if not ds:
            raise ValueError("Dataset no encontrado.")
        self._ensure_dataset_file(ds)
        path = str(ds.get("stored_path") or "")
        if not path or not os.path.exists(path):
            raise ValueError("Archivo del dataset no disponible.")
        try:
            off = max(0, int(offset))
        except Exception:
            off = 0
        try:
            lim = max(1, min(200, int(limit)))
        except Exception:
            lim = 20
        rows: list[dict] = []
        columns: list[str] = []
        with open(path, "r", newline="", encoding="utf-8-sig", errors="replace") as f:
            reader = csv.DictReader(f)
            columns = [str(c) for c in (reader.fieldnames or [])]
            for i, r in enumerate(reader):
                if i < off:
                    continue
                if len(rows) >= lim:
                    break
                rows.append({k: ("" if v is None else str(v)) for k, v in (r or {}).items()})
        return {"dataset_id": dataset_id, "offset": off, "limit": lim, "columns": columns, "rows": rows}

    def get_dataset_profile(self, dataset_id: str) -> dict:
        ds = next((d for d in self._datasets if d.get("id") == dataset_id), None)
        if not ds and self._db_enabled():
            rows = self._db.fetch_all(
                "SELECT id, profile_json, contract_ok, contract_issues_json, quality_score FROM datasets WHERE id = %s LIMIT 1",
                (dataset_id,),
            )
            if rows and isinstance(rows[0], dict):
                ds = dict(rows[0])
        if ds and self._db_enabled():
            meta = self._get_dataset_meta(dataset_id)
            if meta:
                ds = dict(meta) | dict(ds)
        if not ds:
            raise ValueError("Dataset no encontrado.")
        profile_json = ds.get("profile_json")
        profile = ds.get("profile")
        if profile is None and profile_json is not None:
            profile = self._parse_json(profile_json, {})
        profile = self._parse_json(profile, {})
        if profile:
            return profile
        contract = self._get_contract()
        self._ensure_dataset_file(ds)
        path = str(ds.get("stored_path") or "")
        computed = self._profile_csv(path, contract)
        return computed
