"""
Guarda en disco lo que se leyó del Libro de calificaciones, para no tener
que volver a consultar Blackboard cada vez que se abre el panel.

Se guardan dos cosas, ambas por código de curso:

- Los tipos de nota del curso (sus exámenes y actividades), que es lo que
  llena la lista de "Obtener notas".
- Las notas de los alumnos de cada uno de esos tipos.

Todo esto es una copia de lo que había en Blackboard en el momento de
consultarlo, así que se guarda junto con la fecha en que se obtuvo: el
panel la muestra para que el docente sepa qué tan vieja es y decida si
vale la pena volver a pedirla. Nunca se refresca solo; se actualiza
únicamente cuando el docente pulsa el botón correspondiente.
"""

import json
from datetime import datetime

from willaq.config import DIR_DATOS

RUTA_TIPOS_NOTA = DIR_DATOS / "tipos_nota.json"
RUTA_NOTAS = DIR_DATOS / "notas_alumnos.json"

# Los tipos de nota de Gestión Docente van aparte de los de Blackboard: son
# listas distintas y sirven para cosas distintas. En Blackboard son los
# exámenes y actividades tal como los armó el docente; aquí son las casillas
# oficiales donde hay que registrar la nota (T1, T2, EF, RE...). Conseguir
# los de Gestión Docente cuesta bastante más —hay que validar un token a
# mano—, así que guardarlos evita repetir todo ese camino.
RUTA_TIPOS_NOTA_GD = DIR_DATOS / "tipos_nota_gestion_docente.json"


def _cargar(ruta) -> dict:
    try:
        if ruta.exists():
            datos = json.loads(ruta.read_text(encoding="utf-8"))
            if isinstance(datos, dict):
                return datos
    except Exception:
        pass
    return {}


def _guardar(ruta, datos: dict):
    DIR_DATOS.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")


def _ahora() -> str:
    return datetime.now().isoformat(timespec="seconds")


def guardar_tipos_nota(curso_codigo: str, elementos: list):
    """Guarda los tipos de nota (exámenes/actividades) de un curso."""
    if not curso_codigo:
        return
    todos = _cargar(RUTA_TIPOS_NOTA)
    todos[curso_codigo] = {"elementos": elementos or [], "obtenido_en": _ahora()}
    _guardar(RUTA_TIPOS_NOTA, todos)


def obtener_tipos_nota(curso_codigo: str):
    """Devuelve {"elementos": [...], "obtenido_en": "..."} de un curso, o None."""
    return _cargar(RUTA_TIPOS_NOTA).get(curso_codigo)


def guardar_tipos_nota_gd(curso_codigo: str, tipos: list):
    """Guarda los tipos de nota de Gestión Docente de un curso (T1, EF...)."""
    if not curso_codigo:
        return
    todos = _cargar(RUTA_TIPOS_NOTA_GD)
    todos[curso_codigo] = {"tipos": tipos or [], "obtenido_en": _ahora()}
    _guardar(RUTA_TIPOS_NOTA_GD, todos)


def obtener_tipos_nota_gd(curso_codigo: str):
    """Devuelve {"tipos": [...], "obtenido_en": "..."} de un curso, o None."""
    return _cargar(RUTA_TIPOS_NOTA_GD).get(curso_codigo)


def guardar_notas(curso_codigo: str, elemento: str, resultado: dict):
    """Guarda las notas de todos los alumnos de un tipo de nota del curso."""
    if not curso_codigo or not elemento:
        return
    todos = _cargar(RUTA_NOTAS)
    del_curso = todos.get(curso_codigo) or {}
    del_curso[elemento] = {
        "alumnos": resultado.get("alumnos") or [],
        "sobre": resultado.get("sobre"),
        "obtenido_en": _ahora(),
    }
    todos[curso_codigo] = del_curso
    _guardar(RUTA_NOTAS, todos)


def obtener_notas_de_curso(curso_codigo: str) -> dict:
    """Devuelve {nombre_del_tipo: {"alumnos", "sobre", "obtenido_en"}} de un curso."""
    return _cargar(RUTA_NOTAS).get(curso_codigo) or {}


def reiniciar_configuraciones():
    """Borra los tipos de nota y las notas guardadas de todos los cursos.

    Se usa cuando el docente vuelve a obtener la lista de cursos activos:
    esa lista es la base de todo el flujo, así que al renovarla se empieza
    de cero también aquí (ver 'Obtener Cursos Activos' en el panel web).
    """
    _guardar(RUTA_TIPOS_NOTA, {})
    _guardar(RUTA_NOTAS, {})
    _guardar(RUTA_TIPOS_NOTA_GD, {})
