"""
Feriados peruanos, usados para marcar en rojo las sesiones de dictado que
caen en un día no laborable.

La lista se guarda en datos/feriados.json y el docente puede agregar o
quitar fechas a demanda (por ejemplo, si un feriado se traslada de fecha,
o si su institución no lo considera feriado). La primera vez que se pide
la lista y no existe el archivo, se genera una lista base con los
feriados nacionales más comunes del año actual (incluyendo Jueves y
Viernes Santo, calculados con la fecha real de Pascua de ese año), para
que el docente no tenga que escribirlos todos a mano.
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


def _feriados_por_defecto(anio: int) -> list:
    """Lista base de feriados nacionales del Perú para un año dado.

    Es una lista de referencia (las más reconocidas oficialmente); el
    docente puede corregirla libremente desde el panel si algo no aplica
    o si falta alguna fecha específica de su institución.
    """
    pascua = _calcular_domingo_de_pascua(anio)
    jueves_santo = pascua - timedelta(days=3)
    viernes_santo = pascua - timedelta(days=2)

    fechas = [
        date(anio, 1, 1),  # Año Nuevo
        jueves_santo,
        viernes_santo,
        date(anio, 5, 1),  # Día del Trabajo
        date(anio, 6, 29),  # San Pedro y San Pablo
        date(anio, 7, 28),  # Día de la Independencia
        date(anio, 7, 29),  # Fiestas Patrias (segundo día)
        date(anio, 8, 30),  # Santa Rosa de Lima
        date(anio, 10, 8),  # Combate de Angamos
        date(anio, 11, 1),  # Todos los Santos
        date(anio, 12, 8),  # Inmaculada Concepción
        date(anio, 12, 25),  # Navidad
    ]
    return sorted(fecha.isoformat() for fecha in fechas)


def obtener_feriados() -> list:
    """Devuelve la lista de feriados guardada (o genera la base del año actual)."""
    try:
        if RUTA_FERIADOS.exists():
            return json.loads(RUTA_FERIADOS.read_text(encoding="utf-8"))
    except Exception:
        pass

    feriados = _feriados_por_defecto(date.today().year)
    guardar_feriados(feriados)
    return feriados


def guardar_feriados(feriados: list) -> dict:
    """Reemplaza la lista completa de feriados guardada (agregar/quitar se
    resuelve mandando la lista final desde el panel)."""
    feriados_limpios = sorted({str(fecha) for fecha in feriados if fecha})

    DIR_DATOS.mkdir(parents=True, exist_ok=True)
    RUTA_FERIADOS.write_text(json.dumps(feriados_limpios), encoding="utf-8")

    return {"estado": "ok", "feriados": feriados_limpios}
