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

# Cómo se arma cada nota de Gestión Docente a partir de las de Blackboard:
# qué exámenes entran y si se suman o se promedian. Lo decide el docente en
# el modal de "Procesar" y no se puede deducir solo, así que se guarda.
RUTA_CALCULOS_GD = DIR_DATOS / "calculos_notas_gestion_docente.json"

# Notas que no vienen de Blackboard sino de otra parte: por ahora, los
# formularios cuyos resultados el docente lleva en un Excel. Se guardan
# aparte de los tipos de Blackboard porque no se descubren solos —los
# escribe el docente, con su URL y su columna— pero después se comportan
# igual: aparecen en la misma lista y sus notas van al mismo archivo, así
# que se pueden usar para armar una nota de Gestión Docente.
RUTA_RECURSOS_NOTA = DIR_DATOS / "recursos_nota.json"


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


def guardar_recurso_nota(curso_codigo: str, recurso: dict):
    """Guarda (o actualiza) un recurso de notas del curso, por su nombre."""
    if not curso_codigo or not recurso.get("nombre"):
        return
    todos = _cargar(RUTA_RECURSOS_NOTA)
    del_curso = [r for r in (todos.get(curso_codigo) or []) if r.get("nombre") != recurso["nombre"]]
    del_curso.append({**recurso, "guardado_en": _ahora()})
    todos[curso_codigo] = del_curso
    _guardar(RUTA_RECURSOS_NOTA, todos)


def obtener_recursos_nota(curso_codigo: str) -> list:
    """Los recursos de notas configurados para un curso."""
    return _cargar(RUTA_RECURSOS_NOTA).get(curso_codigo) or []


def olvidar_recurso_nota(curso_codigo: str, nombre: str):
    """Quita un recurso y las notas que había traído."""
    todos = _cargar(RUTA_RECURSOS_NOTA)
    todos[curso_codigo] = [r for r in (todos.get(curso_codigo) or []) if r.get("nombre") != nombre]
    _guardar(RUTA_RECURSOS_NOTA, todos)

    notas = _cargar(RUTA_NOTAS)
    del_curso = notas.get(curso_codigo) or {}
    if del_curso.pop(nombre, None) is not None:
        notas[curso_codigo] = del_curso
        _guardar(RUTA_NOTAS, notas)


def guardar_datos_gd(curso_codigo: str, tipos: list, alumnos: list):
    """Guarda lo que se trajo de Gestión Docente de un curso.

    Son dos cosas de un mismo viaje: los tipos de nota (T1, EF...) y la
    lista de alumnos tal como la nombra el portal. Los nombres importan
    porque son con los que hay que cruzar las notas de Blackboard, que
    escribe los nombres a su manera.
    """
    if not curso_codigo:
        return
    todos = _cargar(RUTA_TIPOS_NOTA_GD)
    todos[curso_codigo] = {
        "tipos": tipos or [],
        "alumnos": alumnos or [],
        "obtenido_en": _ahora(),
    }
    _guardar(RUTA_TIPOS_NOTA_GD, todos)


def obtener_datos_gd(curso_codigo: str):
    """Devuelve {"tipos", "alumnos", "obtenido_en"} de un curso, o None."""
    return _cargar(RUTA_TIPOS_NOTA_GD).get(curso_codigo)


def guardar_calculo_gd(curso_codigo: str, tipo_gd: str, configuracion: dict):
    """Guarda cómo se arma la nota de un tipo de Gestión Docente.

    Es la elección del docente en el modal de "Procesar": qué notas de
    Blackboard entran y si se suman o se promedian. Se guarda para no tener
    que volver a armarlo cada vez.
    """
    if not curso_codigo or not tipo_gd:
        return
    todos = _cargar(RUTA_CALCULOS_GD)
    del_curso = todos.get(curso_codigo) or {}
    del_curso[tipo_gd] = {
        "elementos": configuracion.get("elementos") or [],
        "operacion": configuracion.get("operacion") or "promedio",
        "guardado_en": _ahora(),
    }
    todos[curso_codigo] = del_curso
    _guardar(RUTA_CALCULOS_GD, todos)


def obtener_calculos_gd(curso_codigo: str) -> dict:
    """Devuelve {tipo_gd: {"elementos", "operacion", "guardado_en"}} del curso."""
    return _cargar(RUTA_CALCULOS_GD).get(curso_codigo) or {}


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
    _guardar(RUTA_CALCULOS_GD, {})
    _guardar(RUTA_RECURSOS_NOTA, {})
