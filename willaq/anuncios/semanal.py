"""
Guarda la configuración para generar los anuncios semanales de un curso: qué
curso, y qué día/hora se publican los anuncios de inicio y fin de semana.

La fecha de inicio y fin del curso NO se guarda aquí: se pide una sola vez
por curso desde la tarjeta de "Cursos activos" (ver willaq/cursos/fechas.py)
y esta configuración la lee de ahí cuando la necesita.

Por ahora esto solo valida y guarda esa configuración (una por curso, en
un archivo local). Calcular las fechas de cada semana y generar el Excel
de anuncios a partir de esto es un paso futuro, todavía no implementado.
"""

import json

from willaq.config import DIR_DATOS
from willaq.cursos.fechas import obtener_fechas_curso

RUTA_CONFIGURACION = DIR_DATOS / "anuncios_semanales.json"

CAMPOS_REQUERIDOS = (
    "curso_codigo",
    "curso_nombre",
    "dia_inicio_semana",
    "hora_inicio_semana",
    "dia_fin_semana",
    "hora_fin_semana",
)

# Orden real de los días de la semana (lunes primero), usado para validar que
# el día de inicio de semana quede antes que el de fin de semana. Debe
# coincidir con los valores que genera el select del panel (DIAS_SEMANA en
# app.js, en minúsculas).
ORDEN_DIAS_SEMANA = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")


def _cargar_configuraciones() -> dict:
    try:
        if RUTA_CONFIGURACION.exists():
            return json.loads(RUTA_CONFIGURACION.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def reiniciar_configuraciones():
    """Borra todas las configuraciones guardadas de anuncios semanales.

    Se usa cuando el docente vuelve a obtener la lista de cursos activos: esa
    lista es la base de todo el flujo, así que al renovarla se empieza de
    cero también aquí (ver 'Obtener Cursos Activos' en el panel web).
    """
    DIR_DATOS.mkdir(parents=True, exist_ok=True)
    RUTA_CONFIGURACION.write_text("{}", encoding="utf-8")


def obtener_configuracion_semanal(curso_codigo: str):
    """Devuelve la configuración ya guardada de un curso, o None si no hay ninguna.

    Sirve para precargar el asistente cuando el docente vuelve a abrir el
    mismo curso, en vez de que tenga que volver a escribir todo.
    """
    return _cargar_configuraciones().get(curso_codigo)


def guardar_configuracion_semanal(datos: dict) -> dict:
    """Valida y guarda la configuración de anuncios semanales de un curso.

    Se guarda una configuración por curso (identificado por su código), en
    datos/anuncios_semanales.json, para no perder la de otros cursos ni la
    de una visita anterior al mismo curso.

    Devuelve {"estado": "ok", ...datos guardados} o
    {"estado": "error", "error": "..."} si falta algo o las fechas/días no
    tienen sentido.
    """
    faltantes = [campo for campo in CAMPOS_REQUERIDOS if not datos.get(campo)]
    if faltantes:
        return {"estado": "error", "error": f"Faltan campos: {', '.join(faltantes)}"}

    fechas_curso = obtener_fechas_curso(datos["curso_codigo"])
    if not fechas_curso:
        return {
            "estado": "error",
            "error": 'Primero configura la fecha de inicio y fin de este curso desde "Cursos activos".',
        }

    dia_inicio_semana = datos["dia_inicio_semana"]
    dia_fin_semana = datos["dia_fin_semana"]

    if dia_inicio_semana == dia_fin_semana:
        return {"estado": "error", "error": "El día de inicio y el día de fin de semana no pueden ser el mismo."}

    try:
        indice_inicio = ORDEN_DIAS_SEMANA.index(dia_inicio_semana)
        indice_fin = ORDEN_DIAS_SEMANA.index(dia_fin_semana)
    except ValueError:
        return {"estado": "error", "error": "No se reconoció uno de los días de la semana."}

    if indice_inicio >= indice_fin:
        return {
            "estado": "error",
            "error": "El día de anuncio de inicio de semana debe ser antes que el día de anuncio de fin de semana.",
        }

    # "confirmar_fecha_pasada" y "regularizar_fecha_manual" son opcionales y
    # mutuamente excluyentes: si el curso ya empezó, por defecto los anuncios
    # se generan solo desde hoy; cualquiera de estas dos casillas cambia ese
    # punto de corte (desde la fecha real de inicio del curso, o desde una
    # fecha elegida a mano), pero no ambas a la vez.
    confirmar_fecha_pasada = bool(datos.get("confirmar_fecha_pasada"))
    regularizar_fecha_manual = bool(datos.get("regularizar_fecha_manual"))

    if confirmar_fecha_pasada and regularizar_fecha_manual:
        return {
            "estado": "error",
            "error": "Solo puedes elegir una forma de regularizar: desde el inicio del curso, o desde una fecha manual.",
        }

    fecha_regularizacion_manual = datos.get("fecha_regularizacion_manual") or ""
    if regularizar_fecha_manual:
        if not fecha_regularizacion_manual:
            return {"estado": "error", "error": "Selecciona la fecha desde la cual deseas regularizar."}
        if not (
            fechas_curso["fecha_inicio_curso"] <= fecha_regularizacion_manual <= fechas_curso["fecha_fin_curso"]
        ):
            return {
                "estado": "error",
                "error": "La fecha de regularización debe estar dentro del rango de fechas del curso.",
            }

    # "eliminar_anuncios_existentes" también es opcional: por ahora solo se
    # guarda la intención del docente; el borrado real ocurrirá cuando exista
    # la función de publicar anuncios en Blackboard (todavía no implementada).
    configuraciones = _cargar_configuraciones()
    configuracion_curso = {campo: datos[campo] for campo in CAMPOS_REQUERIDOS}
    configuracion_curso["confirmar_fecha_pasada"] = confirmar_fecha_pasada
    configuracion_curso["regularizar_fecha_manual"] = regularizar_fecha_manual
    configuracion_curso["fecha_regularizacion_manual"] = fecha_regularizacion_manual if regularizar_fecha_manual else ""
    configuracion_curso["eliminar_anuncios_existentes"] = bool(datos.get("eliminar_anuncios_existentes"))
    configuraciones[datos["curso_codigo"]] = configuracion_curso

    DIR_DATOS.mkdir(parents=True, exist_ok=True)
    RUTA_CONFIGURACION.write_text(
        json.dumps(configuraciones, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return {"estado": "ok", **configuracion_curso}
