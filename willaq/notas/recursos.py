"""
Notas que no salen de Blackboard: por ahora, las de un formulario cuyos
resultados viven en un Excel.

El Excel no es público: está en la nube de la institución y solo se abre
con la sesión del docente. Por eso no se descarga con una petición suelta,
sino con el navegador que ya tiene esa sesión iniciada (el mismo perfil de
Blackboard, DIR_PERFIL_NAVEGADOR): se entra a la URL como lo haría una
persona y se aprovecha la descarga que dispara.

Se intentan dos caminos, en este orden:

1. Que la URL descargue el archivo. Es el caso bueno: el .xlsx se lee con
   openpyxl, que da los valores exactos de cada celda.
2. Si no descarga nada, que la página muestre una tabla HTML (una hoja
   publicada, por ejemplo) y se lee de ahí.

Si un día aparece un tercer caso (Excel en línea que dibuja la hoja sin
tablas HTML), el registro técnico dice exactamente qué se encontró, que es
lo que hace falta para resolverlo.
"""

import re
import tempfile
import time
import unicodedata
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from openpyxl import load_workbook
from playwright.sync_api import sync_playwright

from willaq.config import DIR_PERFIL_NAVEGADOR

# Cuánto se espera a que la URL empiece a descargar antes de dar por hecho
# que no va a descargar nada y mirar la página.
SEGUNDOS_ESPERA_DESCARGA = 45

# Cómo se reconoce la columna de los nombres. El docente indica dónde están
# las notas, pero no dónde están los nombres, así que se buscan por el texto
# del encabezado: los formularios de Microsoft traen "Nombre", y es común
# ver también "Apellidos y nombres" o el correo institucional.
ENCABEZADOS_DE_NOMBRE = ("nombre", "apellido", "alumno", "estudiante", "participante")

# Nombres de columna que NO son el alumno, aunque contengan las palabras de
# arriba: los formularios de Microsoft agregan varias de estas.
ENCABEZADOS_A_IGNORAR = ("hora", "id", "puntos", "total", "correo", "email")


def urls_de_descarga(url: str) -> list:
    """Por dónde intentar bajar el archivo, en orden de preferencia.

    La URL que copia el docente es la de Excel en línea: abre el editor, no
    descarga nada, y la hoja se dibuja de una forma que no se puede leer
    desde el HTML. Pero SharePoint expone el archivo original en
    '_layouts/15/download.aspx?UniqueId={GUID}', y ese GUID es el mismo
    'sourcedoc' que ya trae la URL del editor. Comprobado contra el OneDrive
    real: esa es la que descarga; 'download=1' y 'SourceDoc' no.

    Se devuelven varias porque no todas las URLs traen sourcedoc (los
    enlaces cortos para compartir, por ejemplo, no lo tienen) y ahí sí
    suele funcionar 'download=1'.
    """
    candidatas = []
    partes = urlparse(url)
    origen = f"{partes.scheme}://{partes.netloc}"

    sourcedoc = (parse_qs(partes.query).get("sourcedoc") or [""])[0].strip("{}")
    if sourcedoc and "/_layouts/" in partes.path:
        # La ruta del sitio es lo que va antes de /_layouts/, quitándole el
        # prefijo corto que Office mete en sus enlaces (":x:/r", ":x:/g"...).
        sitio = partes.path.split("/_layouts/")[0]
        sitio = re.sub(r"^/:[a-z]:/[a-z]/", "/", sitio)
        candidatas.append(f"{origen}{sitio}/_layouts/15/download.aspx?UniqueId={{{sourcedoc}}}")

    separador = "&" if partes.query else "?"
    candidatas.append(f"{url}{separador}download=1")
    return candidatas


def _sin_tildes(texto) -> str:
    sin_acentos = unicodedata.normalize("NFKD", str(texto or ""))
    return "".join(c for c in sin_acentos if not unicodedata.combining(c)).lower().strip()


def indice_de_columna(letra: str) -> int:
    """Pasa una letra de columna de Excel a su posición (A -> 0, B -> 1...)."""
    letra = (letra or "").strip().upper()
    if not letra or not letra.isalpha():
        return -1
    indice = 0
    for caracter in letra:
        indice = indice * 26 + (ord(caracter) - ord("A") + 1)
    return indice - 1


def _es_columna_de_nombre(encabezado) -> bool:
    texto = _sin_tildes(encabezado)
    if not texto or any(malo in texto for malo in ENCABEZADOS_A_IGNORAR):
        return False
    return any(bueno in texto for bueno in ENCABEZADOS_DE_NOMBRE)


def _buscar_columna_de_nombres(encabezados: list, filas: list, columna_notas: int) -> int:
    """En qué columna están los nombres de los alumnos.

    Primero por el encabezado, que es lo que acierta en los formularios de
    Microsoft. Si ninguno sirve, se elige la columna de texto con más
    valores distintos, saltando la de las notas: los nombres casi no se
    repiten y los números no tienen espacios.
    """
    for indice, encabezado in enumerate(encabezados):
        if indice != columna_notas and _es_columna_de_nombre(encabezado):
            return indice

    mejor, mejor_variedad = -1, 0.0
    for indice in range(max((len(f) for f in filas), default=0)):
        if indice == columna_notas:
            continue
        valores = [
            str(f[indice]).strip()
            for f in filas
            if indice < len(f) and f[indice] is not None and str(f[indice]).strip()
        ]
        con_texto = [v for v in valores if " " in v and re.search(r"[A-Za-zÁÉÍÓÚÑ]", v)]
        if len(con_texto) < max(1, len(filas) * 0.8):
            continue
        variedad = len(set(con_texto)) / len(con_texto)
        if variedad > mejor_variedad:
            mejor, mejor_variedad = indice, variedad
    return mejor


def _letra_de_columna(indice: int) -> str:
    """El nombre de columna de Excel de esa posición (0 -> A, 26 -> AA)."""
    letras = ""
    while indice >= 0:
        letras = chr(ord("A") + indice % 26) + letras
        indice = indice // 26 - 1
    return letras


def _anotar_columnas(encabezados: list, notificar):
    """Deja en el registro qué hay en cada columna, con su letra.

    Cada encabezado se recorta: los formularios usan la pregunta entera
    como nombre de columna y son párrafos de varias líneas, así que sin
    recortar el registro técnico queda ilegible. La letra es lo importante,
    porque es lo que el docente tiene que elegir en el panel.
    """
    notificar("     columnas del archivo:")
    for indice, encabezado in enumerate(encabezados):
        texto = " ".join(str(encabezado or "").split())
        if len(texto) > 60:
            texto = texto[:57] + "..."
        notificar(f"       {_letra_de_columna(indice)}: {texto}")


def _texto_de_nota(valor) -> str:
    """Deja la nota como texto, sin el ".0" que arrastran los números de Excel."""
    if valor is None:
        return ""
    if isinstance(valor, float) and valor.is_integer():
        return str(int(valor))
    return str(valor).strip()


def _leer_excel(ruta: Path, columna_notas: int, notificar) -> dict:
    """Saca de un .xlsx los nombres y las notas de la columna indicada."""
    libro = load_workbook(ruta, data_only=True, read_only=True)
    hoja = libro.active
    filas = [list(fila) for fila in hoja.iter_rows(values_only=True)]
    libro.close()

    if not filas:
        return {"estado": "error", "error": "El archivo no tiene ninguna fila."}

    encabezados = [str(c) if c is not None else "" for c in filas[0]]
    cuerpo = [f for f in filas[1:] if any(c is not None and str(c).strip() for c in f)]
    notificar(f"     hoja '{hoja.title}': {len(cuerpo)} fila(s) con datos")
    _anotar_columnas(encabezados, notificar)

    if columna_notas < 0 or columna_notas >= len(encabezados):
        return {
            "estado": "error",
            "error": f"La columna de notas está fuera del archivo (tiene {len(encabezados)} columnas).",
        }

    columna_nombres = _buscar_columna_de_nombres(encabezados, cuerpo, columna_notas)
    if columna_nombres < 0:
        return {"estado": "error", "error": "No se pudo reconocer la columna de los nombres."}

    notificar(f"     nombres: columna '{encabezados[columna_nombres]}'")
    notificar(f"     notas:   columna '{encabezados[columna_notas]}'")

    alumnos = []
    for fila in cuerpo:
        nombre = str(fila[columna_nombres]).strip() if columna_nombres < len(fila) and fila[columna_nombres] else ""
        if not nombre:
            continue
        nota = _texto_de_nota(fila[columna_notas]) if columna_notas < len(fila) else ""
        alumnos.append({"alumno": nombre, "nota": nota or "--"})

    return {
        "estado": "ok",
        "alumnos": alumnos,
        "columna_nombres": encabezados[columna_nombres],
        "columna_notas": encabezados[columna_notas],
    }


JS_LEER_TABLA_HTML = """
(indiceNotas) => {
  const tablas = Array.from(document.querySelectorAll("table"));
  if (!tablas.length) return null;
  const tabla = tablas.reduce((a, b) =>
    b.querySelectorAll("tr").length > a.querySelectorAll("tr").length ? b : a);
  return Array.from(tabla.querySelectorAll("tr")).map((f) =>
    Array.from(f.cells || []).map((c) => (c.innerText || "").trim()));
}
"""


def _leer_tabla_de_la_pagina(pagina, columna_notas: int, notificar) -> dict:
    """Plan B: leer la hoja desde una tabla HTML de la propia página."""
    try:
        filas = pagina.evaluate(JS_LEER_TABLA_HTML, columna_notas)
    except Exception as error:
        return {"estado": "error", "error": f"No se pudo leer la página: {error}"}

    if not filas or len(filas) < 2:
        return {
            "estado": "error",
            "error": "La URL no descargó ningún archivo y la página no tiene una tabla legible.",
        }

    encabezados = filas[0]
    cuerpo = [f for f in filas[1:] if any(c.strip() for c in f)]
    notificar(f"     tabla de la página: {len(cuerpo)} fila(s)")
    _anotar_columnas(encabezados, notificar)

    if columna_notas < 0 or columna_notas >= len(encabezados):
        return {"estado": "error", "error": "La columna de notas está fuera de la tabla."}

    columna_nombres = _buscar_columna_de_nombres(encabezados, cuerpo, columna_notas)
    if columna_nombres < 0:
        return {"estado": "error", "error": "No se pudo reconocer la columna de los nombres."}

    alumnos = []
    for fila in cuerpo:
        nombre = fila[columna_nombres].strip() if columna_nombres < len(fila) else ""
        if not nombre:
            continue
        nota = fila[columna_notas].strip() if columna_notas < len(fila) else ""
        alumnos.append({"alumno": nombre, "nota": nota or "--"})

    return {
        "estado": "ok",
        "alumnos": alumnos,
        "columna_nombres": encabezados[columna_nombres],
        "columna_notas": encabezados[columna_notas],
    }


def cargar_formulario(url: str, columna: str, notificar=None) -> dict:
    """Abre el Excel del formulario con la sesión del docente y lee sus notas.

    'columna' es la letra donde están las notas (A, B, C...), que el docente
    indica porque solo él sabe qué pregunta del formulario es la calificada.

    Devuelve {"estado": "ok"|"error", "alumnos": [{"alumno", "nota"}],
    "error": "..."}.
    """
    notificar = notificar or print

    columna_notas = indice_de_columna(columna)
    if columna_notas < 0:
        return {"estado": "error", "error": "La columna de notas no es una letra válida."}

    DIR_PERFIL_NAVEGADOR.mkdir(parents=True, exist_ok=True)
    carpeta = Path(tempfile.mkdtemp(prefix="willaq_formulario_"))

    with sync_playwright() as playwright:
        # Se usa el perfil de Blackboard porque es el que tiene iniciada la
        # sesión institucional con la que ese Excel se deja abrir. Y con
        # ventana a la vista: si la nube pide confirmar algo, el docente lo
        # ve y puede resolverlo.
        contexto = playwright.chromium.launch_persistent_context(
            user_data_dir=str(DIR_PERFIL_NAVEGADOR),
            headless=False,
            accept_downloads=True,
        )
        try:
            pagina = contexto.pages[0] if contexto.pages else contexto.new_page()

            descargado = None
            for candidata in urls_de_descarga(url):
                notificar(f"Intentando descargar desde {candidata[:110]}...")
                try:
                    with pagina.expect_download(timeout=SEGUNDOS_ESPERA_DESCARGA * 1_000) as espera:
                        try:
                            pagina.goto(candidata, wait_until="domcontentloaded", timeout=60_000)
                        except Exception:
                            # Cuando la URL es una descarga directa, navegar
                            # "falla" porque no hay página que cargar: es
                            # normal y significa que sí está descargando.
                            pass
                    descarga = espera.value
                    descargado = carpeta / (descarga.suggested_filename or "formulario.xlsx")
                    descarga.save_as(str(descargado))
                    notificar(f"[OK] Se descargó {descargado.name}")
                    break
                except Exception:
                    notificar("     por ahí no descargó.")

            if descargado is None:
                notificar("Ninguna URL descargó el archivo; se mirará la página.")
                try:
                    pagina.goto(url, wait_until="domcontentloaded", timeout=60_000)
                except Exception:
                    pass

            if descargado and descargado.suffix.lower() in (".xlsx", ".xlsm"):
                return _leer_excel(descargado, columna_notas, notificar)

            if descargado:
                return {
                    "estado": "error",
                    "error": f"Se descargó {descargado.name}, pero no es un Excel (.xlsx).",
                }

            time.sleep(2)
            return _leer_tabla_de_la_pagina(pagina, columna_notas, notificar)
        except Exception as error:
            notificar(f"[ERROR] No se pudo leer el formulario: {error}")
            return {"estado": "error", "error": str(error)}
        finally:
            try:
                contexto.close()
            except Exception:
                pass
