"""
Guarda la fecha de inicio y fin de cada curso, elegidas por el docente desde
la tarjeta de "Cursos activos" del panel web.

Estas fechas son la fuente única de la verdad para el rango de un curso:
"Generar Anuncios Semanales" y "Generar Sesiones Dictado" ya no las piden en
sus propios formularios, sino que las leen de aquí a partir del curso
elegido. Así se configuran una sola vez por curso y se comparten entre
ambas herramientas.
"""

import json

from willaq.config import DIR_DATOS

RUTA_CONFIGURACION = DIR_DATOS / "fechas_cursos.json"

CAMPOS_REQUERIDOS = ("curso_codigo", "fecha_inicio_curso", "fecha_fin_curso")


def _cargar_configuraciones() -> dict:
    try:
        if RUTA_CONFIGURACION.exists():
            return json.loads(RUTA_CONFIGURACION.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def obtener_fechas_curso(curso_codigo: str):
    """Devuelve {"fecha_inicio_curso": ..., "fecha_fin_curso": ...} de un curso, o None."""
    return _cargar_configuraciones().get(curso_codigo)


def obtener_todas_las_fechas() -> dict:
    """Devuelve el diccionario completo {curso_codigo: {fecha_inicio_curso, fecha_fin_curso}}."""
    return _cargar_configuraciones()


def guardar_fechas_curso(datos: dict) -> dict:
    """Valida y guarda la fecha de inicio y fin de un curso.

    Devuelve {"estado": "ok", ...datos guardados} o
    {"estado": "error", "error": "..."}.
    """
    faltantes = [campo for campo in CAMPOS_REQUERIDOS if not datos.get(campo)]
    if faltantes:
        return {"estado": "error", "error": f"Faltan campos: {', '.join(faltantes)}"}

    if datos["fecha_fin_curso"] <= datos["fecha_inicio_curso"]:
        return {"estado": "error", "error": "La fecha de fin del curso debe ser posterior a la de inicio."}

    configuraciones = _cargar_configuraciones()
    configuracion_curso = {
        "fecha_inicio_curso": datos["fecha_inicio_curso"],
        "fecha_fin_curso": datos["fecha_fin_curso"],
    }
    configuraciones[datos["curso_codigo"]] = configuracion_curso

    DIR_DATOS.mkdir(parents=True, exist_ok=True)
    RUTA_CONFIGURACION.write_text(
        json.dumps(configuraciones, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return {"estado": "ok", "curso_codigo": datos["curso_codigo"], **configuracion_curso}


def reiniciar_configuraciones():
    """Borra todas las fechas de curso guardadas.

    Se usa cuando el docente vuelve a obtener la lista de cursos activos: esa
    lista es la base de todo el flujo, así que al renovarla se empieza de
    cero también aquí (ver 'Obtener Cursos Activos' en el panel web).
    """
    DIR_DATOS.mkdir(parents=True, exist_ok=True)
    RUTA_CONFIGURACION.write_text("{}", encoding="utf-8")
