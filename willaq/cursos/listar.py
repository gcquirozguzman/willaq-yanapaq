"""
Obtiene la lista de cursos activos (abiertos) del docente en Blackboard.

Reutiliza el mismo perfil de navegador persistente que 'login' (así no hace
falta volver a iniciar sesión si ya hay una sesión guardada): abre el
navegador, entra a la página principal de Blackboard igual que el login, y
desde ahí navega a https://cibertec.blackboard.com/ultra/course, donde
Blackboard muestra una tarjeta por cada curso del docente.

Un curso se considera "activo" si su tarjeta muestra el estado "Abierto"
(en el HTML: bb-translate="base.courses.open"). Los cursos finalizados
muestran bb-translate="base.courses.closed" en su lugar y se descartan.
Todo esto se confirmó con el HTML real de la página.
"""

import json
from datetime import datetime

from playwright.sync_api import sync_playwright

from willaq.autenticacion.login import (
    DIR_PERFIL_NAVEGADOR,
    URL_BLACKBOARD,
    _esperar_carga_de_pagina,
    _hacer_clic_en_boton_ingreso,
    _parece_pantalla_de_login,
)
from willaq.config import MOSTRAR_NAVEGADOR
from willaq.config import DIR_DATOS

URL_CURSOS = URL_BLACKBOARD + "ultra/course"

# Caché del último resultado exitoso de "Obtener Cursos Activos", para que el
# panel web pueda seguir mostrando la lista tras reiniciar el servidor, sin
# obligar al docente a volver a pedirla solo por eso. Se sobrescribe cada vez
# que se vuelve a obtener la lista (por ejemplo, si un curso cambia de estado).
RUTA_CURSOS_GUARDADOS = DIR_DATOS / "cursos_activos.json"

# Qué grupos (períodos) de la página de cursos eligió el docente para
# trabajar. La lista completa de cursos se guarda siempre entera en
# RUTA_CURSOS_GUARDADOS: esto solo dice cuáles de esos grupos mostrar, así
# que cambiar la elección no pierde nada y se puede volver atrás sin tener
# que consultar Blackboard de nuevo.
RUTA_GRUPOS_ELEGIDOS = DIR_DATOS / "grupos_cursos.json"


def guardar_grupos_elegidos(grupos: list) -> dict:
    """Guarda en disco qué grupos de cursos eligió el docente."""
    try:
        DIR_DATOS.mkdir(parents=True, exist_ok=True)
        elegidos = [str(grupo) for grupo in (grupos or [])]
        RUTA_GRUPOS_ELEGIDOS.write_text(
            json.dumps({"grupos": elegidos}, ensure_ascii=False), encoding="utf-8"
        )
        return {"ok": True, "grupos": elegidos}
    except Exception as error:
        return {"ok": False, "error": str(error)}


def cargar_grupos_elegidos():
    """Devuelve los grupos elegidos, o None si el docente nunca eligió.

    None y [] significan cosas distintas: None es "todavía no eligió" (el
    panel propone una selección inicial), y [] es "eligió no incluir
    ninguno".
    """
    try:
        if RUTA_GRUPOS_ELEGIDOS.exists():
            datos = json.loads(RUTA_GRUPOS_ELEGIDOS.read_text(encoding="utf-8"))
            grupos = datos.get("grupos")
            if isinstance(grupos, list):
                return grupos
    except Exception:
        pass
    return None


def _guardar_cursos_obtenidos(cursos: list):
    try:
        DIR_DATOS.mkdir(parents=True, exist_ok=True)
        contenido = {
            "cursos": cursos,
            "obtenido_en": datetime.now().isoformat(timespec="seconds"),
        }
        RUTA_CURSOS_GUARDADOS.write_text(json.dumps(contenido), encoding="utf-8")
    except Exception:
        pass  # esto es solo una comodidad de la interfaz; si falla, no afecta la búsqueda


def reiniciar_configuraciones():
    """Borra la lista de cursos activos guardada y los grupos elegidos.

    A diferencia de las demás 'reiniciar_configuraciones' del proyecto (que
    se llaman cuando SE RENUEVA la lista de cursos), esta se llama cuando se
    borran todos los accesos guardados: sin sesión, la lista de cursos ya no
    sirve de nada, así que se vacía junto con todo lo que depende de ella
    (ver 'Borrar Accesos' en el panel web).
    """
    DIR_DATOS.mkdir(parents=True, exist_ok=True)
    RUTA_CURSOS_GUARDADOS.write_text("{}", encoding="utf-8")
    RUTA_GRUPOS_ELEGIDOS.write_text("{}", encoding="utf-8")


def cargar_cursos_guardados():
    """Lee la última lista de cursos activos guardada en disco, si existe.

    Devuelve {"cursos": [...], "obtenido_en": "YYYY-MM-DDTHH:MM:SS"}, o None
    si nunca se guardó nada (por ejemplo, primera vez que se usa la
    herramienta). Los archivos guardados por una versión anterior de esta
    función (una lista plana, sin fecha) también se leen bien, solo que sin
    "obtenido_en".
    """
    try:
        if RUTA_CURSOS_GUARDADOS.exists():
            datos = json.loads(RUTA_CURSOS_GUARDADOS.read_text(encoding="utf-8"))
            if isinstance(datos, list):
                return {"cursos": datos, "obtenido_en": None}
            return datos
    except Exception:
        pass
    return None

# Selectores confirmados con el HTML real de la página de cursos.
SELECTOR_TARJETA_CURSO = "article[data-course-id]"
SELECTOR_CODIGO_CURSO = ".course-id span"
SELECTOR_NOMBRE_CURSO = "h4.js-course-title-element"
SELECTOR_ESTADO_ABIERTO = 'span[bb-translate="base.courses.open"]'

# La página de cursos no dibuja todas las tarjetas de golpe: las va
# agregando de a pocas. Por eso el navegador se abre con una ventana
# deliberadamente alta (para que entren todas) y se espera a que la
# cantidad de tarjetas deje de crecer antes de leerlas (ver
# _esperar_lista_de_cursos_completa).
ANCHO_VENTANA = 1600
ALTO_VENTANA = 2400

MS_ENTRE_SONDEOS = 250
SONDEOS_SIN_CAMBIO_PARA_TERMINAR = 8  # ~2 segundos sin tarjetas nuevas
SONDEOS_MAXIMOS = 120  # tope de ~30 segundos

# Blackboard agrupa las tarjetas por período ("202607P", "Cursos de 2025",
# "Otros"...). El encabezado de cada grupo es un <h3> dentro de un
# .course-card-term-name, y manda sobre todas las tarjetas que vienen
# después de él en el orden del documento (confirmado con el HTML real).
# El grupo "Otros" es donde Blackboard pone los cursos que no son de un
# período de dictado (Biblioteca Virtual, capacitaciones internas, etc.).
SELECTOR_ENCABEZADO_GRUPO = ".course-card-term-name h3"

GRUPO_SIN_NOMBRE = "Sin grupo"

# Se lee todo de un tirón dentro del navegador, en vez de con un locator
# por campo y por tarjeta: así el docente espera bastante menos, y además
# es la única forma sencilla de saber a qué grupo pertenece cada tarjeta
# (hace falta recorrer encabezados y tarjetas en el orden del documento).
JS_LEER_TARJETAS = """
({ selectorEncabezado, selectorTarjeta, selectorCodigo, selectorNombre, selectorAbierto, sinNombre }) => {
  const limpiar = (el) => (el ? el.textContent.replace(/\\s+/g, ' ').trim() : null);
  const nodos = document.querySelectorAll(selectorEncabezado + ', ' + selectorTarjeta);
  const cursos = [];
  let grupo = sinNombre;
  for (const nodo of nodos) {
    if (nodo.matches(selectorEncabezado)) {
      grupo = limpiar(nodo) || sinNombre;
      continue;
    }
    cursos.push({
      grupo,
      codigo: limpiar(nodo.querySelector(selectorCodigo)),
      nombre: limpiar(nodo.querySelector(selectorNombre)),
      // El atributo "data-course-id" (ej. "_1460705_1") es el identificador
      // interno que Blackboard usa en las URLs del curso (por ejemplo, para
      // llegar directo a /ultra/courses/<id>/announcements). Confirmado
      // navegando de verdad: el link de la tarjeta no cambia la URL visible
      // (usa ruteo interno de Angular), pero este ID sí sirve para navegar
      // directo con page.goto().
      id: nodo.getAttribute('data-course-id'),
      abierto: !!nodo.querySelector(selectorAbierto),
    });
  }
  return cursos;
}
"""


def _esperar_lista_de_cursos_completa(pagina):
    """Espera a que dejen de aparecer tarjetas nuevas en la lista de cursos.

    Antes se leía la lista apenas aparecía la PRIMERA tarjeta, y como el
    resto todavía se estaba dibujando, se perdían cursos: se confirmó
    contra la cuenta real del docente que así se devolvían 3 de los 7
    cursos abiertos que tenía. Se sondea la cantidad de tarjetas y se
    corta recién cuando se mantiene igual un rato, en vez de usar una
    espera fija que sería lenta cuando hay pocos cursos y corta cuando hay
    muchos.
    """
    tarjetas = pagina.locator(SELECTOR_TARJETA_CURSO)
    conteo_anterior = tarjetas.count()
    sondeos_sin_cambio = 0

    for _ in range(SONDEOS_MAXIMOS):
        pagina.wait_for_timeout(MS_ENTRE_SONDEOS)
        conteo = tarjetas.count()
        if conteo != conteo_anterior:
            conteo_anterior = conteo
            sondeos_sin_cambio = 0
            continue
        sondeos_sin_cambio += 1
        if sondeos_sin_cambio >= SONDEOS_SIN_CAMBIO_PARA_TERMINAR:
            break

    return conteo_anterior


def _extraer_cursos_activos(pagina, notificar):
    """Lee las tarjetas de curso de la página y devuelve solo los activos.

    Cada curso devuelto incluye a qué grupo (período) pertenece, para que
    el panel pueda preguntarle al docente qué grupos quiere usar sin tener
    que volver a consultar Blackboard.

    Devuelve None (no una lista vacía) si la página de cursos no llegó a
    cargar a tiempo. Esta distinción importa: una lista vacía "de verdad"
    significa que el docente no tiene cursos activos, mientras que None es
    un fallo transitorio (timeout, red lenta) que NO debe sobrescribir la
    última lista buena guardada en disco.
    """
    try:
        pagina.locator(SELECTOR_TARJETA_CURSO).first.wait_for(timeout=15_000)
    except Exception as error:
        notificar(f"[AVISO] No se pudo cargar la lista de cursos: {error}")
        return None

    _esperar_lista_de_cursos_completa(pagina)

    tarjetas = pagina.evaluate(
        JS_LEER_TARJETAS,
        {
            "selectorEncabezado": SELECTOR_ENCABEZADO_GRUPO,
            "selectorTarjeta": SELECTOR_TARJETA_CURSO,
            "selectorCodigo": SELECTOR_CODIGO_CURSO,
            "selectorNombre": SELECTOR_NOMBRE_CURSO,
            "selectorAbierto": SELECTOR_ESTADO_ABIERTO,
            "sinNombre": GRUPO_SIN_NOMBRE,
        },
    )

    cursos = []
    for tarjeta in tarjetas:
        # Sin "Abierto" (está finalizado, etc.): se descarta.
        if not tarjeta.get("abierto") or not tarjeta.get("id"):
            continue
        cursos.append(
            {
                "codigo": tarjeta.get("codigo") or "",
                "nombre": tarjeta.get("nombre") or "",
                "id": tarjeta["id"],
                "grupo": tarjeta.get("grupo") or GRUPO_SIN_NOMBRE,
            }
        )

    return cursos


def obtener_cursos_activos(notificar=None, info_actualizacion=None) -> list:
    """Abre el navegador, va a la lista de cursos y devuelve los activos.

    Requiere que ya exista una sesión guardada (ejecutar 'login' antes). Si
    no hay sesión activa, avisa por qué y devuelve una lista vacía.

    Si se pasa 'info_actualizacion' (un diccionario), se le agrega la clave
    "actualizado": True solo cuando se obtuvo y guardó una lista nueva de
    verdad (no cuando se devolvió la lista guardada previamente por un fallo
    o por falta de sesión). El panel web usa esto para decidir si debe
    reiniciar la configuración de Anuncios Semanales y Sesiones Dictado, ya
    que ambas dependen de la lista de cursos vigente.
    """
    notificar = notificar or print
    if info_actualizacion is not None:
        info_actualizacion["actualizado"] = False

    notificar("Buscando tus cursos activos en Blackboard...")

    with sync_playwright() as playwright:
        # Mismo perfil persistente que el login, pero sin ventana visible
        # por defecto: esto no necesita ninguna acción manual del docente.
        # MOSTRAR_NAVEGADOR (ver willaq/config.py, variable de .env) la
        # muestra igual, para depurar.
        contexto = playwright.chromium.launch_persistent_context(
            user_data_dir=str(DIR_PERFIL_NAVEGADOR),
            headless=not MOSTRAR_NAVEGADOR,
        )

        pagina = contexto.pages[0] if contexto.pages else contexto.new_page()
        pagina.set_viewport_size({"width": ANCHO_VENTANA, "height": ALTO_VENTANA})
        pagina.goto(URL_BLACKBOARD)
        _esperar_carga_de_pagina(pagina)

        _hacer_clic_en_boton_ingreso(pagina, notificar)
        _esperar_carga_de_pagina(pagina)

        if _parece_pantalla_de_login(pagina.url):
            notificar("[AVISO] No hay una sesión activa. Primero inicia sesión con 'Iniciar sesión'.")
            contexto.close()
            return []

        pagina.goto(URL_CURSOS)
        _esperar_carga_de_pagina(pagina)

        cursos = _extraer_cursos_activos(pagina, notificar)
        if cursos is None:
            # Fallo transitorio al cargar la página: se mantiene la última
            # lista buena guardada en vez de reemplazarla por una vacía, para
            # no bloquear en el panel herramientas que ya estaban disponibles
            # (Generar Anuncios Semanales, Generar Sesiones Dictado, etc.).
            notificar("[AVISO] Se mantiene la última lista de cursos guardada; no se pudo actualizar.")
            guardado = cargar_cursos_guardados()
            cursos = guardado["cursos"] if guardado else []
        else:
            notificar(f"Se encontraron {len(cursos)} curso(s) activo(s).")
            _guardar_cursos_obtenidos(cursos)
            if info_actualizacion is not None:
                info_actualizacion["actualizado"] = True

        contexto.close()

    return cursos


def obtener_cursos_activos_cli():
    """Versión para la terminal: imprime la lista de cursos encontrados."""
    cursos = obtener_cursos_activos()

    if not cursos:
        return

    print("=" * 70)
    print(f"[OK] {len(cursos)} curso(s) activo(s):")
    for curso in cursos:
        print(f"  - {curso['codigo']}: {curso['nombre']}")
    print("=" * 70)
