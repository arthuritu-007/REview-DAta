from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import pandas as pd


@dataclass(frozen=True)
class ValidationFinding:
    rule_id: str
    field: str
    value: str
    description: str
    severity: str
    row_index: int | None


def _is_empty(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and pd.isna(value):
        return True
    if isinstance(value, str) and value.strip() == "":
        return True
    return False


def _parse_date_dd_mm_yyyy(value: Any) -> datetime | None:
    if _is_empty(value):
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).strip()
    for fmt in ("%d-%m-%Y", "%d/%m/%Y", "%Y-%m-%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def _parse_time_hh_mm(value: Any) -> datetime | None:
    if _is_empty(value):
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).strip()
    for fmt in ("%H:%M", "%H:%M:%S"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def validate_campos_obligatorios(df: pd.DataFrame, required_columns: list[str]) -> list[ValidationFinding]:
    findings: list[ValidationFinding] = []
    if not required_columns:
        return findings
    missing = [c for c in required_columns if c not in df.columns]
    for c in missing:
        findings.append(
            ValidationFinding(
                rule_id="campos_obligatorios_no_nulos",
                field=c,
                value="",
                description=f"Columna obligatoria no existe: {c}",
                severity="Alta",
                row_index=None,
            )
        )
    present = [c for c in required_columns if c in df.columns]
    for c in present:
        series = df[c]
        for idx, v in series.items():
            if _is_empty(v):
                findings.append(
                    ValidationFinding(
                        rule_id="campos_obligatorios_no_nulos",
                        field=c,
                        value="",
                        description="Campo obligatorio vacío o nulo",
                        severity="Alta",
                        row_index=int(idx),
                    )
                )
    return findings


def validate_conductor_asignado(df: pd.DataFrame, conductor_col: str | None) -> list[ValidationFinding]:
    if not conductor_col or conductor_col not in df.columns:
        return [
            ValidationFinding(
                rule_id="conductor_asignado",
                field=conductor_col or "conductor",
                value="",
                description="No se configuró la columna de conductor para validar",
                severity="Alta",
                row_index=None,
            )
        ]
    findings: list[ValidationFinding] = []
    for idx, v in df[conductor_col].items():
        if _is_empty(v):
            findings.append(
                ValidationFinding(
                    rule_id="conductor_asignado",
                    field=conductor_col,
                    value="",
                    description="Viaje sin conductor asignado",
                    severity="Alta",
                    row_index=int(idx),
                )
            )
    return findings


def validate_carta_porte(df: pd.DataFrame, carta_porte_col: str | None) -> list[ValidationFinding]:
    if not carta_porte_col or carta_porte_col not in df.columns:
        return [
            ValidationFinding(
                rule_id="carta_porte_existente",
                field=carta_porte_col or "carta_porte",
                value="",
                description="No se configuró la columna de Carta Porte para validar",
                severity="Alta",
                row_index=None,
            )
        ]
    findings: list[ValidationFinding] = []
    for idx, v in df[carta_porte_col].items():
        if _is_empty(v):
            findings.append(
                ValidationFinding(
                    rule_id="carta_porte_existente",
                    field=carta_porte_col,
                    value="",
                    description="Viaje sin Carta Porte asociada",
                    severity="Alta",
                    row_index=int(idx),
                )
            )
    return findings


def validate_no_duplicidad(df: pd.DataFrame, cliente_col: str | None, fecha_col: str | None, direccion_col: str | None) -> list[ValidationFinding]:
    cols = [cliente_col, fecha_col, direccion_col]
    if any(c is None or c == "" for c in cols) or any(c not in df.columns for c in cols if c):
        return [
            ValidationFinding(
                rule_id="no_duplicidad_cliente_fecha_direccion",
                field="cliente+fecha+direccion",
                value="",
                description="No se configuraron columnas válidas para duplicidad (cliente, fecha, dirección)",
                severity="Alta",
                row_index=None,
            )
        ]
    subset = [cliente_col, fecha_col, direccion_col]  # type: ignore[list-item]
    dup_mask = df.duplicated(subset=subset, keep=False)
    findings: list[ValidationFinding] = []
    for idx in df.index[dup_mask]:
        values = [df.at[idx, c] for c in subset]
        findings.append(
            ValidationFinding(
                rule_id="no_duplicidad_cliente_fecha_direccion",
                field=",".join(subset),
                value=" | ".join("" if _is_empty(v) else str(v) for v in values),
                description="Registro duplicado por combinación cliente+fecha+dirección",
                severity="Alta",
                row_index=int(idx),
            )
        )
    return findings


def validate_formato_numero_empleado(df: pd.DataFrame, empleado_col: str | None) -> list[ValidationFinding]:
    if not empleado_col or empleado_col not in df.columns:
        return [
            ValidationFinding(
                rule_id="formato_numero_empleado",
                field=empleado_col or "numero_empleado",
                value="",
                description="No se configuró la columna de número de empleado para validar",
                severity="Alta",
                row_index=None,
            )
        ]
    findings: list[ValidationFinding] = []
    for idx, v in df[empleado_col].items():
        if _is_empty(v):
            continue
        text = str(v).strip()
        if len(text) not in (12, 13):
            findings.append(
                ValidationFinding(
                    rule_id="formato_numero_empleado",
                    field=empleado_col,
                    value=text,
                    description="Longitud inválida: se requiere 12 o 13 caracteres",
                    severity="Alta",
                    row_index=int(idx),
                )
            )
    return findings


def validate_formato_placas(df: pd.DataFrame, placas_col: str | None, pattern: str | None = None) -> list[ValidationFinding]:
    if not placas_col or placas_col not in df.columns:
        return [
            ValidationFinding(
                rule_id="formato_placas",
                field=placas_col or "placas",
                value="",
                description="No se configuró la columna de placas para validar",
                severity="Alta",
                row_index=None,
            )
        ]
    regex = re.compile(pattern or r"^[A-Z0-9\-]{5,10}$")
    findings: list[ValidationFinding] = []
    for idx, v in df[placas_col].items():
        if _is_empty(v):
            continue
        text = str(v).strip().upper()
        if not regex.match(text):
            findings.append(
                ValidationFinding(
                    rule_id="formato_placas",
                    field=placas_col,
                    value=text,
                    description="Formato de placas inválido",
                    severity="Alta",
                    row_index=int(idx),
                )
            )
    return findings


def validate_formato_fechas(df: pd.DataFrame, date_columns: list[str]) -> list[ValidationFinding]:
    findings: list[ValidationFinding] = []
    for c in date_columns:
        if c not in df.columns:
            findings.append(
                ValidationFinding(
                    rule_id="formato_fecha_dd_mm_yyyy",
                    field=c,
                    value="",
                    description=f"Columna de fecha no existe: {c}",
                    severity="Alta",
                    row_index=None,
                )
            )
            continue
        for idx, v in df[c].items():
            if _is_empty(v):
                continue
            parsed = _parse_date_dd_mm_yyyy(v)
            if parsed is None:
                findings.append(
                    ValidationFinding(
                        rule_id="formato_fecha_dd_mm_yyyy",
                        field=c,
                        value=str(v),
                        description="Fecha con formato inválido (se requiere DD-MM-YYYY)",
                        severity="Alta",
                        row_index=int(idx),
                    )
                )
    return findings


def validate_formato_horas(df: pd.DataFrame, time_columns: list[str]) -> list[ValidationFinding]:
    findings: list[ValidationFinding] = []
    for c in time_columns:
        if c not in df.columns:
            findings.append(
                ValidationFinding(
                    rule_id="formato_hora_hh_mm",
                    field=c,
                    value="",
                    description=f"Columna de hora no existe: {c}",
                    severity="Alta",
                    row_index=None,
                )
            )
            continue
        for idx, v in df[c].items():
            if _is_empty(v):
                continue
            parsed = _parse_time_hh_mm(v)
            if parsed is None:
                findings.append(
                    ValidationFinding(
                        rule_id="formato_hora_hh_mm",
                        field=c,
                        value=str(v),
                        description="Hora con formato inválido (se requiere HH:MM)",
                        severity="Alta",
                        row_index=int(idx),
                    )
                )
    return findings


def validate_peso_rango(df: pd.DataFrame, peso_col: str | None) -> list[ValidationFinding]:
    if not peso_col or peso_col not in df.columns:
        return [
            ValidationFinding(
                rule_id="peso_en_rango_0_35",
                field=peso_col or "peso",
                value="",
                description="No se configuró la columna de peso para validar",
                severity="Alta",
                row_index=None,
            )
        ]
    series = pd.to_numeric(df[peso_col], errors="coerce")
    findings: list[ValidationFinding] = []
    for idx, v in series.items():
        if pd.isna(v):
            original = df.at[idx, peso_col]
            if _is_empty(original):
                continue
            findings.append(
                ValidationFinding(
                    rule_id="peso_en_rango_0_35",
                    field=peso_col,
                    value=str(original),
                    description="Peso no numérico",
                    severity="Alta",
                    row_index=int(idx),
                )
            )
            continue
        if v <= 0 or v > 35:
            findings.append(
                ValidationFinding(
                    rule_id="peso_en_rango_0_35",
                    field=peso_col,
                    value=str(v),
                    description="Peso fuera de rango permitido (0–35)",
                    severity="Alta",
                    row_index=int(idx),
                )
            )
    return findings


def validate_fecha_salida_no_futura(df: pd.DataFrame, fecha_salida_col: str | None) -> list[ValidationFinding]:
    if not fecha_salida_col or fecha_salida_col not in df.columns:
        return [
            ValidationFinding(
                rule_id="fecha_salida_no_futura",
                field=fecha_salida_col or "fecha_salida",
                value="",
                description="No se configuró la columna de fecha de salida para validar",
                severity="Alta",
                row_index=None,
            )
        ]
    today = datetime.now().date()
    findings: list[ValidationFinding] = []
    for idx, v in df[fecha_salida_col].items():
        parsed = _parse_date_dd_mm_yyyy(v)
        if parsed is None:
            continue
        if parsed.date() > today:
            findings.append(
                ValidationFinding(
                    rule_id="fecha_salida_no_futura",
                    field=fecha_salida_col,
                    value=str(v),
                    description="Fecha de salida futura",
                    severity="Alta",
                    row_index=int(idx),
                )
            )
    return findings


def validate_logica_fechas(df: pd.DataFrame, fecha_salida_col: str | None, fecha_llegada_col: str | None) -> list[ValidationFinding]:
    if not fecha_salida_col or not fecha_llegada_col or fecha_salida_col not in df.columns or fecha_llegada_col not in df.columns:
        return [
            ValidationFinding(
                rule_id="logica_fechas_llegada_no_menor_salida",
                field="fecha_salida+fecha_llegada",
                value="",
                description="No se configuraron columnas válidas para lógica de fechas (salida y llegada)",
                severity="Alta",
                row_index=None,
            )
        ]
    findings: list[ValidationFinding] = []
    for idx in df.index:
        salida = _parse_date_dd_mm_yyyy(df.at[idx, fecha_salida_col])
        llegada = _parse_date_dd_mm_yyyy(df.at[idx, fecha_llegada_col])
        if salida is None or llegada is None:
            continue
        if llegada < salida:
            findings.append(
                ValidationFinding(
                    rule_id="logica_fechas_llegada_no_menor_salida",
                    field=f"{fecha_salida_col},{fecha_llegada_col}",
                    value=f"{df.at[idx, fecha_salida_col]} -> {df.at[idx, fecha_llegada_col]}",
                    description="Fecha de llegada menor a fecha de salida",
                    severity="Alta",
                    row_index=int(idx),
                )
            )
    return findings
