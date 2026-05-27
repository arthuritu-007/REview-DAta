from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ValidationRule:
    id: str
    name: str
    description: str
    rule_type: str
    severity: str


def get_default_rules() -> list[ValidationRule]:
    return [
        ValidationRule(
            id="campos_obligatorios_no_nulos",
            name="Campos obligatorios no nulos",
            description="No se permiten campos vacíos o nulos en campos obligatorios.",
            rule_type="campos_obligatorios",
            severity="Alta",
        ),
        ValidationRule(
            id="conductor_asignado",
            name="Conductor asignado",
            description="Todo viaje deberá contar obligatoriamente con un conductor asignado.",
            rule_type="campos_obligatorios",
            severity="Alta",
        ),
        ValidationRule(
            id="carta_porte_existente",
            name="Carta Porte asociada",
            description="Debe existir Carta Porte asociada al viaje.",
            rule_type="campos_obligatorios",
            severity="Alta",
        ),
        ValidationRule(
            id="no_duplicidad_cliente_fecha_direccion",
            name="No duplicidad cliente+fecha+dirección",
            description="No duplicidad por combinación cliente + fecha + dirección.",
            rule_type="logica",
            severity="Alta",
        ),
        ValidationRule(
            id="formato_numero_empleado",
            name="Formato número de empleado",
            description="Número de empleado: longitud obligatoria de 12 o 13 caracteres.",
            rule_type="formato",
            severity="Alta",
        ),
        ValidationRule(
            id="formato_placas",
            name="Formato placas",
            description="Las placas deberán cumplir con el formato oficial autorizado (validación por expresión regular).",
            rule_type="formato",
            severity="Alta",
        ),
        ValidationRule(
            id="formato_fecha_dd_mm_yyyy",
            name="Formato de fechas DD-MM-YYYY",
            description="Las fechas deberán registrarse en formato estándar DD-MM-YYYY.",
            rule_type="formato",
            severity="Alta",
        ),
        ValidationRule(
            id="peso_en_rango_0_35",
            name="Peso en rango 0–35",
            description="El peso de carga deberá encontrarse dentro del rango de 0 a 35 toneladas.",
            rule_type="rango",
            severity="Alta",
        ),
        ValidationRule(
            id="fecha_salida_no_futura",
            name="Fecha de salida no futura",
            description="Fecha de salida no puede ser futura.",
            rule_type="rango",
            severity="Alta",
        ),
        ValidationRule(
            id="logica_fechas_llegada_no_menor_salida",
            name="Fecha de llegada >= salida",
            description="Fecha de llegada no puede ser menor a fecha de salida.",
            rule_type="logica",
            severity="Alta",
        ),
        ValidationRule(
            id="contrato_csv_viajes",
            name="Contrato de datos (CSV viajes)",
            description="Valida el contrato por columna: requeridos, formatos, tipos, catálogos y valores sospechosos.",
            rule_type="contrato",
            severity="Alta",
        ),
        ValidationRule(
            id="reglas_negocio_viajes",
            name="Reglas de negocio (viajes)",
            description="Valida reglas de negocio: botón pánico, cambios operativos, coherencia de horarios y ruta.",
            rule_type="logica",
            severity="Alta",
        ),
    ]
