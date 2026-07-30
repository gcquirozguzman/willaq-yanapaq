"""
Reprogramaciones puntuales de sesiones de dictado: cuando una sesión
individual se mueve de fecha y/o de hora (por ejemplo, un imprevisto de un
día puntual), sin tener que rehacer todo el horario semanal del curso.

Se guardan en datos/reprogramaciones_sesiones.json como
{curso_codigo: {fecha_original: {fecha_nueva, hora_inicio, hora_fin, detalle}}},
identificando cada sesión por su fecha original: dentro de un curso solo
puede haber una sesión por fecha, según el horario semanal configurado en
willaq/dictado/sesiones.py. 'detalle' es el motivo del cambio (obligatorio),
para que quede constancia de por qué se movió esa sesión puntual.

El cálculo de qué sesiones existen (fechas/horas originales) sigue
haciéndose en el panel (JavaScript), igual que en sesiones.py; este módulo
solo guarda las excepciones puntuales que el docente indica.
"""

import json

from willaq.config import DIR_DATOS
from willaq.cursos.fechas import obtener_fechas_curso

RUTA_CONFIGURACION = DIR_DATOS / "reprogramaciones_sesiones.json"


def _cargar_configuraciones() -> dict:
    try:
        if RUTA_CONFIGURACION.exists():
            return json.loads(RUTA_CONFIGURACION.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def obtener_reprogramaciones_curso(curso_codigo: str) -> dict:
    """Devuelve {fecha_original: {fecha_nueva, hora_inicio, hora_fin, detalle}} de un curso."""
    return _cargar_configuraciones().get(curso_codigo, {})


def reiniciar_configuraciones():
    """Borra todas las reprogramaciones guardadas.

    Se usa cuando el docente vuelve a obtener la lista de cursos activos,
    igual que con las demás configuraciones que dependen de esa lista (ver
    'Obtener Cursos Activos' en el panel web).
    """
    DIR_DATOS.mkdir(parents=True, exist_ok=True)
    RUTA_CONFIGURACION.write_text("{}", encoding="utf-8")


def guardar_reprogramacion(datos: dict) -> dict:
    """Valida y guarda la reprogramación de una sesión puntual.

    Devuelve {"estado": "ok", "reprogramaciones": {...del curso...}} o
    {"estado": "error", "error": "..."}.
    """
    curso_codigo = datos.get("curso_codigo")
    fecha_original = datos.get("fecha_original")
    fecha_nueva = datos.get("fecha_nueva")
    hora_inicio = datos.get("hora_inicio")
    hora_fin = datos.get("hora_fin")
    detalle = str(datos.get("detalle") or "").strip()

    if not curso_codigo or not fecha_original or not fecha_nueva or not hora_inicio or not hora_fin:
        return {"estado": "error", "error": "Completa la nueva fecha y hora."}

    if not detalle:
        return {"estado": "error", "error": "Indica el detalle (motivo) del cambio."}

    if hora_fin <= hora_inicio:
        return {"estado": "error", "error": "La hora de fin debe ser posterior a la de inicio."}

    fechas_curso = obtener_fechas_curso(curso_codigo)
    if fechas_curso and not (
        fechas_curso["fecha_inicio_curso"] <= fecha_nueva <= fechas_curso["fecha_fin_curso"]
    ):
        return {"estado": "error", "error": "La nueva fecha debe estar dentro del rango del curso."}

    configuraciones = _cargar_configuraciones()
    configuraciones.setdefault(curso_codigo, {})[fecha_original] = {
        "fecha_nueva": fecha_nueva,
        "hora_inicio": hora_inicio,
        "hora_fin": hora_fin,
        "detalle": detalle,
    }

    DIR_DATOS.mkdir(parents=True, exist_ok=True)
    RUTA_CONFIGURACION.write_text(json.dumps(configuraciones, ensure_ascii=False), encoding="utf-8")

    return {"estado": "ok", "reprogramaciones": configuraciones[curso_codigo]}
