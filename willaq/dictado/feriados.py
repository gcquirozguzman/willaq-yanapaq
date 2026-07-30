"""
Feriados peruanos, usados para marcar en rojo las sesiones de dictado que
caen en un día no laborable.

Se guardan en datos/feriados.json como {"YYYY-MM-DD": "motivo"}, y el
docente puede agregar o quitar fechas a demanda (por ejemplo, si un feriado
se traslada de fecha, o si su institución no lo considera feriado). La
primera vez que se pide la lista y no existe el archivo, se genera una base
con los feriados nacionales más comunes del año actual (incluyendo Jueves y
Viernes Santo, calculados con la fecha real de Pascua de ese año, y el
motivo de cada uno), para que el docente no tenga que escribirlos todos a
mano. Siempre se devuelven ordenados por fecha ascendente.
"""

import json
from datetime import date, timedelta

from willaq.config import DIR_DATOS

RUTA_FERIADOS = DIR_DATOS / "feriados.json"


def _calcular_domingo_de_pascua(anio: int) -> date:
    """Calcula la fecha del Domingo de Pascua para un año dado.

    Algoritmo estándar (Meeus/Jones/Butcher, calendario gregoriano), el
    mismo que usan los calendarios civiles para ubicar Semana Santa.
    """
    a = anio % 19
    b = anio // 100
    c = anio % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    mes = (h + l - 7 * m + 114) // 31
    dia = ((h + l - 7 * m + 114) % 31) + 1
    return date(anio, mes, dia)


def _feriados_por_defecto(anio: int) -> dict:
    """Feriados nacionales del Perú para un año dado, con su motivo.

    Es una base de referencia (las fechas más reconocidas oficialmente); el
    docente puede corregirla libremente desde el panel si algo no aplica o
    si falta alguna fecha específica de su institución.
    """
    pascua = _calcular_domingo_de_pascua(anio)
    jueves_santo = pascua - timedelta(days=3)
    viernes_santo = pascua - timedelta(days=2)

    return {
        date(anio, 1, 1).isoformat(): "Año Nuevo",
        jueves_santo.isoformat(): "Jueves Santo (Semana Santa)",
        viernes_santo.isoformat(): "Viernes Santo (Semana Santa)",
        date(anio, 5, 1).isoformat(): "Día del Trabajo",
        date(anio, 6, 7).isoformat(): "Batalla de Arica y Día de la Bandera",
        date(anio, 6, 29).isoformat(): "San Pedro y San Pablo",
        date(anio, 7, 23).isoformat(): "Día de la Fuerza Aérea del Perú",
        date(anio, 7, 28).isoformat(): "Fiestas Patrias (Día de la Independencia)",
        date(anio, 7, 29).isoformat(): "Fiestas Patrias (segundo día)",
        date(anio, 8, 6).isoformat(): "Batalla de Junín",
        date(anio, 8, 30).isoformat(): "Santa Rosa de Lima",
        date(anio, 10, 8).isoformat(): "Combate de Angamos",
        date(anio, 11, 1).isoformat(): "Todos los Santos",
        date(anio, 12, 8).isoformat(): "Inmaculada Concepción",
        date(anio, 12, 25).isoformat(): "Navidad",
    }


def _migrar_lista_a_diccionario(fechas: list) -> dict:
    """Convierte el formato anterior (lista de fechas, sin motivo) al actual.

    Para cada fecha, si coincide con un feriado nacional por defecto de su
    año, rescata ese motivo real en vez de dejarlo vacío.
    """
    diccionario = {}
    cache_por_anio = {}
    for fecha in fechas:
        fecha = str(fecha)
        anio = int(fecha[:4]) if fecha[:4].isdigit() else date.today().year
        if anio not in cache_por_anio:
            cache_por_anio[anio] = _feriados_por_defecto(anio)
        diccionario[fecha] = cache_por_anio[anio].get(fecha, "")
    return diccionario


def obtener_feriados() -> dict:
    """Devuelve {fecha: motivo} ordenado por fecha ascendente.

    Si el archivo no existe, genera la base del año actual. Si el archivo
    es del formato anterior (una lista simple, sin motivo), lo migra.
    """
    try:
        if RUTA_FERIADOS.exists():
            datos = json.loads(RUTA_FERIADOS.read_text(encoding="utf-8"))
            if isinstance(datos, list):
                datos = _migrar_lista_a_diccionario(datos)
                guardar_feriados(datos)
            return dict(sorted(datos.items()))
    except Exception:
        pass

    feriados = _feriados_por_defecto(date.today().year)
    guardar_feriados(feriados)
    return dict(sorted(feriados.items()))


def guardar_feriados(feriados: dict) -> dict:
    """Reemplaza el diccionario completo de feriados guardado (agregar/quitar
    se resuelve mandando el diccionario final desde el panel).

    Siempre devuelve las fechas ordenadas ascendentemente.
    """
    feriados_limpios = {
        str(fecha): str(motivo or "").strip() for fecha, motivo in feriados.items() if fecha
    }
    feriados_ordenados = dict(sorted(feriados_limpios.items()))

    DIR_DATOS.mkdir(parents=True, exist_ok=True)
    RUTA_FERIADOS.write_text(json.dumps(feriados_ordenados, ensure_ascii=False), encoding="utf-8")

    return {"estado": "ok", "feriados": feriados_ordenados}
