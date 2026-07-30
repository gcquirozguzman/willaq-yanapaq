"""
Guarda la configuración para generar las sesiones de dictado de un curso: qué
curso, y a qué hora dicta cada día de la semana (algunos días pueden no
tener clase).

La fecha de inicio y fin del curso NO se guarda aquí: se pide una sola vez
por curso desde la tarjeta de "Cursos activos" (ver willaq/cursos/fechas.py)
y esta configuración la lee de ahí cuando la necesita.

Igual que con los anuncios semanales, esto solo valida y guarda la
configuración (una por curso). El cálculo real de las fechas de cada
sesión se hace principalmente en el panel (JavaScript) cuando el docente
abre "Ver Sesiones de Dictado", para poder marcar ahí mismo los feriados
en rojo; 'generar_fechas_sesiones' de acá abajo es la misma lógica del
lado del servidor, usada solo para validar cruces de horario al
reprogramar una sesión puntual (ver willaq/dictado/reprogramaciones.py).
"""

import json
from datetime import date, timedelta

from willaq.config import DIR_DATOS
from willaq.cursos.fechas import obtener_fechas_curso

RUTA_CONFIGURACION = DIR_DATOS / "sesiones_dictado.json"

DIAS_SEMANA = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")

CAMPOS_REQUERIDOS = (
    "curso_codigo",
    "curso_nombre",
    "horarios",
)


def _cargar_configuraciones() -> dict:
    try:
        if RUTA_CONFIGURACION.exists():
            return json.loads(RUTA_CONFIGURACION.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def obtener_configuracion_sesiones(curso_codigo: str):
    """Devuelve la configuración ya guardada de un curso, o None si no hay ninguna."""
    return _cargar_configuraciones().get(curso_codigo)


def obtener_todas_las_configuraciones() -> dict:
    """Devuelve {curso_codigo: configuración} de todos los cursos con horario guardado.

    Se usa para saber, desde la tarjeta de cada curso en "Cursos activos", si
    ya tiene un horario de dictado configurado o no.
    """
    return _cargar_configuraciones()


def generar_fechas_sesiones(fecha_inicio_curso: str, fecha_fin_curso: str, horarios: dict) -> list:
    """Genera las sesiones "base" (sin reprogramaciones) entre dos fechas.

    Devuelve una lista de {"fecha", "hora_inicio", "hora_fin"}, una por cada
    día entre fecha_inicio_curso y fecha_fin_curso (incluidos) que tenga
    horario configurado, en el mismo orden en que las genera el panel.
    """
    inicio = date.fromisoformat(fecha_inicio_curso)
    fin = date.fromisoformat(fecha_fin_curso)

    sesiones = []
    fecha = inicio
    while fecha <= fin:
        horario = horarios.get(DIAS_SEMANA[fecha.weekday()])
        if horario:
            sesiones.append({
                "fecha": fecha.isoformat(),
                "hora_inicio": horario["hora_inicio"],
                "hora_fin": horario["hora_fin"],
            })
        fecha += timedelta(days=1)

    return sesiones


def reiniciar_configuraciones():
    """Borra todas las configuraciones guardadas de sesiones de dictado.

    Se usa cuando el docente vuelve a obtener la lista de cursos activos: esa
    lista es la base de todo el flujo, así que al renovarla se empieza de
    cero también aquí (ver 'Obtener Cursos Activos' en el panel web).
    """
    DIR_DATOS.mkdir(parents=True, exist_ok=True)
    RUTA_CONFIGURACION.write_text("{}", encoding="utf-8")


def guardar_configuracion_sesiones(datos: dict) -> dict:
    """Valida y guarda la configuración de sesiones de dictado de un curso.

    'horarios' es un diccionario con una clave por día de la semana (en
    minúsculas, ej. "lunes"), y valor {"hora_inicio": "HH:MM", "hora_fin":
    "HH:MM"} para los días con clase, o None/ausente para los días sin
    clase ese curso.

    Devuelve {"estado": "ok", ...datos guardados} o
    {"estado": "error", "error": "..."}.
    """
    faltantes = [campo for campo in CAMPOS_REQUERIDOS if not datos.get(campo)]
    if faltantes:
        return {"estado": "error", "error": f"Faltan campos: {', '.join(faltantes)}"}

    if not obtener_fechas_curso(datos["curso_codigo"]):
        return {
            "estado": "error",
            "error": 'Primero configura la fecha de inicio y fin de este curso desde "Cursos activos".',
        }

    horarios = datos["horarios"]
    if not isinstance(horarios, dict):
        return {"estado": "error", "error": "El horario semanal no tiene el formato esperado."}

    horarios_limpios = {}
    hay_algun_dia = False
    for dia in DIAS_SEMANA:
        valor = horarios.get(dia)
        if not valor:
            continue
        hora_inicio = valor.get("hora_inicio")
        hora_fin = valor.get("hora_fin")
        if not hora_inicio or not hora_fin:
            continue
        if hora_fin <= hora_inicio:
            return {"estado": "error", "error": f"La hora de fin del {dia} debe ser posterior a la de inicio."}
        horarios_limpios[dia] = {"hora_inicio": hora_inicio, "hora_fin": hora_fin}
        hay_algun_dia = True

    if not hay_algun_dia:
        return {"estado": "error", "error": "Marca al menos un día de la semana con hora de inicio y fin."}

    configuraciones = _cargar_configuraciones()
    configuracion_curso = {
        "curso_codigo": datos["curso_codigo"],
        "curso_nombre": datos["curso_nombre"],
        "horarios": horarios_limpios,
    }
    configuraciones[datos["curso_codigo"]] = configuracion_curso

    DIR_DATOS.mkdir(parents=True, exist_ok=True)
    RUTA_CONFIGURACION.write_text(
        json.dumps(configuraciones, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return {"estado": "ok", **configuracion_curso}
