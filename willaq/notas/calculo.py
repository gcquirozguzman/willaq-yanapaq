"""
Arma la nota que hay que registrar en Gestión Docente a partir de las notas
descargadas de Blackboard.

Dos problemas que resolver, y ninguno es el aritmético:

1. Los nombres no coinciden. Blackboard y Gestión Docente escriben al mismo
   alumno de formas distintas: cambia el orden (apellidos primero o al
   final), las tildes, las comas y los espacios de más. Por eso no se
   comparan los nombres tal cual, sino una versión normalizada: sin tildes,
   en mayúsculas, sin puntuación y con las palabras ordenadas
   alfabéticamente. Así "GARCIA LOPEZ, ANA" y "Ana García López" quedan
   iguales.

2. Puede haber más de una nota de Blackboard para una sola casilla de
   Gestión Docente (por ejemplo, dos trabajos que van a T1). El docente
   decide si se suman o se promedian; esto solo aplica su decisión.

Nada de esto escribe en ningún portal: devuelve el resultado para que se
pueda revisar antes.
"""

import re
import unicodedata

OPERACIONES = ("suma", "promedio")


def normalizar_nombre(nombre: str) -> str:
    """Deja el nombre en una forma comparable entre los dos sistemas."""
    sin_acentos = unicodedata.normalize("NFKD", nombre or "")
    limpio = "".join(c for c in sin_acentos if not unicodedata.combining(c))
    limpio = re.sub(r"[^A-Za-z0-9\s]", " ", limpio).upper()
    palabras = [p for p in limpio.split() if p]
    # Ordenadas: así da igual si el sistema pone primero los apellidos.
    return " ".join(sorted(palabras))


def _a_numero(valor):
    """Convierte a número la nota tal como viene de Blackboard, o None.

    Blackboard escribe "--" cuando no hay nota puesta, y a veces usa coma
    decimal. Un "--" no es un cero: significa que no rindió o no está
    calificado, y confundirlos inventaría notas que nadie puso.
    """
    if valor is None:
        return None
    texto = str(valor).strip().replace(",", ".")
    if not texto or texto == "--":
        return None
    try:
        return float(texto)
    except ValueError:
        return None


def calcular_notas(alumnos_gd: list, notas_por_elemento: dict, elementos: list, operacion: str) -> dict:
    """Cruza los alumnos del portal con las notas de Blackboard y calcula.

    - 'alumnos_gd': lo leído del portal ([{"nombre", ...}]), que manda: el
      resultado tiene una fila por cada uno de ellos y en su mismo orden,
      porque es el orden en el que hay que registrarlas.
    - 'notas_por_elemento': lo guardado de Blackboard
      ({nombre_elemento: {"alumnos": [{"alumno", "nota"}], "sobre": ...}}).
    - 'elementos': qué elementos de Blackboard entran en esta nota.
    - 'operacion': "suma" o "promedio".

    Devuelve {"filas": [...], "sin_encontrar": [...], "operacion": ...}.
    Cada fila trae la nota final y el detalle de dónde salió, para que se
    pueda revisar antes de registrar nada.
    """
    if operacion not in OPERACIONES:
        operacion = "promedio"

    # Índice de las notas de Blackboard por nombre normalizado.
    por_alumno = {}
    for elemento in elementos:
        guardado = notas_por_elemento.get(elemento) or {}
        for alumno in guardado.get("alumnos") or []:
            clave = normalizar_nombre(alumno.get("alumno"))
            if not clave:
                continue
            por_alumno.setdefault(clave, {})[elemento] = _a_numero(alumno.get("nota"))

    filas = []
    usados = set()
    for alumno in alumnos_gd:
        nombre = alumno.get("nombre") if isinstance(alumno, dict) else str(alumno)
        clave = normalizar_nombre(nombre)
        del_alumno = por_alumno.get(clave)
        usados.add(clave)

        detalle = {e: (del_alumno or {}).get(e) for e in elementos}
        valores = [v for v in detalle.values() if v is not None]

        if not del_alumno:
            nota = None
            estado = "sin_coincidencia"
        elif not valores:
            nota = None
            estado = "sin_nota"
        else:
            nota = sum(valores) if operacion == "suma" else sum(valores) / len(valores)
            nota = round(nota, 2)
            estado = "ok" if len(valores) == len(elementos) else "incompleto"

        filas.append({"nombre": nombre, "nota": nota, "estado": estado, "detalle": detalle})

    # Los de Blackboard que no aparecieron en el portal: casi siempre son
    # alumnos retirados, pero conviene que el docente los vea.
    sin_encontrar = []
    for clave, del_alumno in por_alumno.items():
        if clave in usados:
            continue
        for elemento in elementos:
            guardado = notas_por_elemento.get(elemento) or {}
            for alumno in guardado.get("alumnos") or []:
                if normalizar_nombre(alumno.get("alumno")) == clave:
                    sin_encontrar.append(alumno.get("alumno"))
                    break
            if sin_encontrar and sin_encontrar[-1]:
                break

    return {
        "filas": filas,
        "sin_encontrar": sorted(set(n for n in sin_encontrar if n)),
        "operacion": operacion,
        "elementos": list(elementos),
    }
