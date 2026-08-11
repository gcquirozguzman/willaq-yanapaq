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
from difflib import SequenceMatcher

OPERACIONES = ("suma", "promedio")

# A partir de qué parecido se acepta que dos nombres son la misma persona
# cuando no son idénticos. Los casos reales son cosas como un apellido
# compuesto que en un sistema va junto y en el otro separado, o un segundo
# nombre que falta: eso queda muy por encima de 75. Por debajo, es más
# probable que sean dos personas distintas, y ahí se prefiere no emparejar
# y avisar, porque una nota puesta al alumno equivocado es peor que una
# nota que falta.
PARECIDO_MINIMO = 75

# Desde qué parecido vale la pena siquiera mencionar al candidato como
# "lo más parecido". Por debajo son nombres que no tienen nada que ver y
# nombrarlos solo ensucia la observación.
PARECIDO_PARA_SUGERIR = 50


def parecido_entre_nombres(uno: str, otro: str) -> int:
    """Cuánto se parecen dos nombres, de 0 a 100.

    Se mezclan dos miradas porque cada una falla sola: cuántas palabras
    tienen en común (buena para el orden y para nombres partidos, ciega a
    las erratas) y el parecido letra a letra (bueno para las erratas, ciego
    al orden). El peso se carga a las palabras, que es como se diferencian
    de verdad los nombres.
    """
    a, b = normalizar_nombre(uno), normalizar_nombre(otro)
    if not a or not b:
        return 0
    if a == b:
        return 100

    palabras_a, palabras_b = set(a.split()), set(b.split())
    comunes = len(palabras_a & palabras_b) / max(len(palabras_a), len(palabras_b))
    letras = SequenceMatcher(None, a, b).ratio()
    return round(100 * (0.6 * comunes + 0.4 * letras))


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


def _mas_parecido(nombre: str, por_alumno: dict, ya_usados: set):
    """El alumno de Blackboard más parecido a ese nombre, entre los libres.

    Se saltan los ya emparejados para que dos alumnos del portal no
    terminen apuntando al mismo alumno de Blackboard.
    """
    mejor_clave = None
    mejor = {"parecido": 0, "entrada": None}
    for clave, entrada in por_alumno.items():
        if clave in ya_usados:
            continue
        parecido = parecido_entre_nombres(nombre, entrada["nombre"])
        if parecido > mejor["parecido"]:
            mejor_clave = clave
            mejor = {"parecido": parecido, "entrada": entrada}
    return (mejor_clave, mejor) if mejor["entrada"] else (None, mejor)


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

    # Índice de Blackboard por nombre normalizado. Se guarda también el
    # nombre TAL COMO lo escribe Blackboard, porque el panel muestra las dos
    # versiones lado a lado para que se pueda revisar de un vistazo que el
    # cruce emparejó a la persona correcta.
    por_alumno = {}
    for elemento in elementos:
        guardado = notas_por_elemento.get(elemento) or {}
        for alumno in guardado.get("alumnos") or []:
            original = alumno.get("alumno")
            clave = normalizar_nombre(original)
            if not clave:
                continue
            entrada = por_alumno.setdefault(clave, {"nombre": original, "notas": {}})
            entrada["notas"][elemento] = _a_numero(alumno.get("nota"))

    filas = []
    usados = set()
    for alumno in alumnos_gd:
        nombre_gd = alumno.get("nombre") if isinstance(alumno, dict) else str(alumno)
        clave = normalizar_nombre(nombre_gd)

        encontrado = por_alumno.get(clave)
        parecido = 100 if encontrado else 0
        sugerencia = ""

        # Sin coincidencia exacta se busca el más parecido: los dos sistemas
        # no siempre escriben igual al mismo alumno.
        if not encontrado:
            mejor_clave, mejor = _mas_parecido(nombre_gd, por_alumno, usados)
            if mejor_clave:
                parecido = mejor["parecido"]
                if parecido >= PARECIDO_MINIMO:
                    encontrado = mejor["entrada"]
                    clave = mejor_clave
                elif parecido >= PARECIDO_PARA_SUGERIR:
                    sugerencia = mejor["entrada"]["nombre"]

        usados.add(clave)
        notas = (encontrado or {}).get("notas") or {}
        detalle = {e: notas.get(e) for e in elementos}
        valores = [v for v in detalle.values() if v is not None]

        if not encontrado:
            # Al alumno que no aparece en Blackboard se le pone 0: no entregó
            # nada, así que esa es su nota. Se deja el estado y la
            # observación para que igual se vea de dónde salió ese 0 y se
            # pueda corregir a mano si en realidad era un nombre mal escrito.
            nota = 0
            estado = "sin_coincidencia"
        elif not valores:
            nota = None
            estado = "sin_nota"
        else:
            nota = sum(valores) if operacion == "suma" else sum(valores) / len(valores)
            nota = round(nota, 2)
            estado = "ok" if len(valores) == len(elementos) else "incompleto"

        filas.append(
            {
                "nombre": nombre_gd,
                "nombre_gd": nombre_gd,
                "nombre_bb": (encontrado or {}).get("nombre", ""),
                "codigo": alumno.get("codigo", "") if isinstance(alumno, dict) else "",
                "coincidencia": parecido if encontrado else 0,
                "sugerencia": sugerencia,
                "parecido_sugerencia": parecido if sugerencia else 0,
                "nota": nota,
                "estado": estado,
                "detalle": detalle,
            }
        )

    # Los de Blackboard que no aparecieron en el portal: casi siempre son
    # alumnos retirados, pero conviene que el docente los vea.
    sin_encontrar = sorted(
        entrada["nombre"]
        for clave, entrada in por_alumno.items()
        if clave not in usados and entrada.get("nombre")
    )

    return {
        "filas": filas,
        "sin_encontrar": sin_encontrar,
        "operacion": operacion,
        "elementos": list(elementos),
    }
