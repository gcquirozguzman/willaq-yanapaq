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

Antes de guardar, se valida que la nueva fecha/hora no se cruce con
ninguna otra sesión ya existente (de este mismo curso o de cualquier
otro), tomando en cuenta tanto el horario semanal "base" de cada curso
como sus propias reprogramaciones ya guardadas.
"""

import json

from willaq.config import DIR_DATOS
from willaq.cursos.fechas import obtener_fechas_curso, obtener_todas_las_fechas
from willaq.dictado.sesiones import generar_fechas_sesiones, obtener_todas_las_configuraciones

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


def _se_superponen(inicio_a: str, fin_a: str, inicio_b: str, fin_b: str) -> bool:
    """Compara dos rangos "HH:MM"-"HH:MM" (comparables como texto)."""
    return inicio_a < fin_b and inicio_b < fin_a


def _sesiones_efectivas_curso(
    config_sesiones: dict, fechas_curso: dict, reprogramaciones_curso: dict, excluir_fecha_original: str = None
) -> list:
    """Sesiones reales de un curso (fecha/hora ya con reprogramaciones aplicadas).

    'excluir_fecha_original' se usa para no comparar la sesión que se está
    reprogramando contra sí misma.
    """
    base = generar_fechas_sesiones(
        fechas_curso["fecha_inicio_curso"], fechas_curso["fecha_fin_curso"], config_sesiones["horarios"]
    )

    efectivas = []
    for sesion in base:
        if sesion["fecha"] == excluir_fecha_original:
            continue
        cambio = reprogramaciones_curso.get(sesion["fecha"])
        if cambio:
            efectivas.append({
                "fecha": cambio["fecha_nueva"],
                "hora_inicio": cambio["hora_inicio"],
                "hora_fin": cambio["hora_fin"],
            })
        else:
            efectivas.append(sesion)

    return efectivas


def _buscar_cruce_de_horario(curso_codigo: str, fecha_original: str, fecha_nueva: str, hora_inicio: str, hora_fin: str):
    """Busca si la sesión propuesta se cruza con alguna sesión ya existente.

    Revisa todos los cursos con horario de dictado configurado (incluido el
    mismo curso, para detectar choques con sus otras sesiones), usando sus
    fechas de inicio/fin y sus reprogramaciones ya guardadas.

    Devuelve el nombre del curso con el que se cruza, o None si no hay cruce.
    """
    todas_fechas = obtener_todas_las_fechas()
    todas_configuraciones = obtener_todas_las_configuraciones()
    todas_reprogramaciones = _cargar_configuraciones()

    for otro_curso, config in todas_configuraciones.items():
        fechas_otro_curso = todas_fechas.get(otro_curso)
        if not fechas_otro_curso:
            continue

        excluir = fecha_original if otro_curso == curso_codigo else None
        efectivas = _sesiones_efectivas_curso(
            config, fechas_otro_curso, todas_reprogramaciones.get(otro_curso, {}), excluir_fecha_original=excluir
        )

        for sesion in efectivas:
            if sesion["fecha"] == fecha_nueva and _se_superponen(hora_inicio, hora_fin, sesion["hora_inicio"], sesion["hora_fin"]):
                return config.get("curso_nombre") or otro_curso

    return None


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

    curso_cruzado = _buscar_cruce_de_horario(curso_codigo, fecha_original, fecha_nueva, hora_inicio, hora_fin)
    if curso_cruzado:
        return {
            "estado": "error",
            "error": f'Esa fecha y hora se cruzan con una sesión de "{curso_cruzado}".',
        }

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
