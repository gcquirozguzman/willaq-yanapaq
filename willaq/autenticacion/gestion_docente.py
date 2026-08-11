"""
Inicio de sesión en el portal de Gestión Docente de Cibertec
(https://gestiondocente.cibertec.edu.pe/).

Este portal funciona muy distinto a Blackboard, y eso decide todo el diseño
de este archivo:

- Blackboard "recuerda el dispositivo" con cookies que tienen fecha de
  expiración, así que basta con iniciar sesión una vez a mano y guardar el
  perfil del navegador.
- Gestión Docente autentica con cookies DE SESIÓN (ASPAUTHFORM,
  ASPNET_UserId, ASP.NET_SessionId), que el navegador tira al cerrarse, y
  además guarda el estado real en el servidor, que la cierra sola tras un
  rato sin actividad. Se intentó guardar y reinyectar esas cookies y no
  funciona: el portal responde igual que la sesión expiró.

Por eso aquí NO se intenta conservar ninguna sesión. Se guardan el usuario
y la contraseña (cifrados con Windows, ver willaq/autenticacion/credenciales.py)
y la herramienta vuelve a iniciar sesión sola, en el mismo navegador que va
a usar, cada vez que necesita el portal. Así nunca hay una sesión "vieja"
que pueda estar muerta sin que nos enteremos.

Cómo se sabe si se entró: el portal está hecho en ASP.NET WebForms y,
mientras no haya sesión, muestra su formulario de login con los campos
"logUPN_UserName" y "logUPN_Password". Si ese formulario deja de aparecer,
se entró. No se usa la URL para decidirlo, como sí se hace con Blackboard,
porque aquí el login vive en la misma dirección que el portal.
"""

import time
import unicodedata

from playwright.sync_api import sync_playwright

from willaq.autenticacion import credenciales
from willaq.config import (
    DIR_DATOS,
    URL_GESTION_DOCENTE,
    URL_GESTION_DOCENTE_REGISTRO_NOTAS,
)

# Selectores confirmados con el HTML real de la pantalla de login.
SELECTOR_USUARIO = "#logUPN_UserName"
SELECTOR_CLAVE = "#logUPN_Password"
SELECTOR_BOTON_INGRESAR = "#logUPN_LoginButton"

# Dónde avisa el portal de que no aceptó el usuario o la contraseña.
# Comprobado enviando el formulario con un usuario inventado: no usa el
# FailureText clásico de ASP.NET, sino un modal de SweetAlert2 con el texto
# "Usuario no disponible o contraseña incorrecta.". Se deja también el
# selector clásico por si en otra pantalla sí lo usa.
SELECTOR_ERROR_LOGIN = ".swal2-html-container, #logUPN_FailureText"

# Después del login, el portal no muestra las notas: muestra un escritorio
# con los aplicativos del docente, cada uno como un ícono. El que lleva a
# las notas es "Académico", y hay que entrar por ahí: es ese clic el que
# deja la sesión lista para las pantallas de /Academico/Secure/ (entre
# ellas RegNotas.aspx). El enlace abre una pestaña nueva (target="_blank").
SELECTOR_APP_ACADEMICO = 'a.boton-aplicativo[href*="academico/Login.aspx" i]'
SELECTOR_APP_ACADEMICO_RESPALDO = 'a[href*="academico/Login.aspx" i]'

# Cuánto se espera a que aparezca el escritorio de aplicativos después del
# login, y a que la pestaña de Académico termine de abrirse.
SEGUNDOS_MAXIMOS_ESPERA_APLICATIVOS = 60

# Con qué textos se da por rechazado el login. Se compara sin tildes y en
# minúsculas. Hace falta ser específico: el portal usa el mismo tipo de
# modal para otros avisos (por ejemplo, que la clave está por vencer), y
# tomarlos por un rechazo dejaría al docente sin poder entrar.
TEXTOS_LOGIN_RECHAZADO = (
    "usuario no disponible",
    "contrasena incorrecta",
    "clave incorrecta",
    "usuario o contrasena",
)

# Mientras todavía estamos aprendiendo cómo se comporta este portal, la
# comprobación de credenciales se hace con el navegador A LA VISTA, para
# poder mirar qué pasa (pantallas intermedias, avisos, tokens). Cuando el
# flujo esté claro, basta con poner esto en False y la comprobación vuelve
# a hacerse sin ventana, en segundo plano.
MOSTRAR_NAVEGADOR_AL_PROBAR = True

# Cuánto se deja la ventana abierta al terminar la prueba, solo cuando se
# está mirando: si se cerrara al instante no daría tiempo de ver dónde
# terminó. No aplica cuando la prueba corre sin ventana.
SEGUNDOS_PARA_MIRAR_LA_VENTANA = 5

# Cuánto se espera a que el portal conteste al enviar el formulario.
SEGUNDOS_MAXIMOS_ESPERA_LOGIN = 45
SEGUNDOS_ENTRE_SONDEOS = 0.5

# Pausas a propósito entre un paso y el siguiente. Este portal es ASP.NET
# WebForms y, después del login, sigue trabajando un rato aunque la página
# ya se vea: encadena redirecciones y termina de armar la sesión en el
# servidor. Si se le pide la siguiente pantalla antes de que acabe, la
# rechaza como si no hubiera sesión. Por eso no se corre de una pantalla a
# la otra: se le da tiempo.
SEGUNDOS_TRAS_LOGIN = 6
SEGUNDOS_ENTRE_PASOS = 3
# Después de cargar una pantalla, antes de mirar si el portal se quejó:
# el aviso de sesión vencida a veces aparece con la página ya pintada.
SEGUNDOS_ANTES_DE_REVISAR = 2

# A dónde manda el portal cuando la sesión ya no vale. Confirmado entrando
# a RegNotas.aspx sin sesión: redirige a esta ruta.
RUTA_LOGIN_DEL_PORTAL = "/weblogin/login.aspx"

# Texto del aviso de sesión de servidor vencida ("Su sesión de usuario ha
# expirado! Por lo tanto su ultima acción no fue registrada..."). Se busca
# esta frase completa y no solo "ha expirado" a propósito: la pantalla de
# login del portal muestra además un banner de "¡TU CLAVE HA EXPIRADO!"
# que habla de la contraseña, no de la sesión, y confundir los dos daría
# un falso positivo en cada comprobación.
TEXTO_SESION_VENCIDA = "sesion de usuario ha expirado"

# Restos del enfoque anterior (guardar las cookies de sesión del portal en
# un archivo). Ya no se usa y el archivo contenía cookies de sesión, así
# que se borra en cuanto se carga este módulo en vez de dejarlo ahí.
_RUTA_COOKIES_OBSOLETA = DIR_DATOS / "sesion_gestion_docente.json"
try:
    if _RUTA_COOKIES_OBSOLETA.exists():
        _RUTA_COOKIES_OBSOLETA.unlink()
except Exception:
    pass


def _esperar_carga_de_pagina(pagina, timeout: int = 20_000):
    """Espera a que la página termine de cargar, sin colgarse si nunca queda quieta."""
    try:
        pagina.wait_for_load_state("networkidle", timeout=timeout)
    except Exception:
        pass


def _sin_tildes(texto: str) -> str:
    """Pasa a minúsculas y quita tildes, para comparar textos sin sorpresas."""
    sin_acentos = unicodedata.normalize("NFKD", texto or "")
    return "".join(c for c in sin_acentos if not unicodedata.combining(c)).lower()


def _hay_formulario_de_login(pagina) -> bool:
    """True si la página está mostrando el formulario de usuario/contraseña."""
    try:
        return pagina.locator(SELECTOR_USUARIO).count() > 0
    except Exception:
        # Si no se pudo ni consultar el DOM, se asume lo más conservador:
        # que hay que volver a iniciar sesión.
        return True


def _texto_de_aviso_de_login(pagina) -> str:
    """Devuelve el aviso que el portal muestra en pantalla, si hay alguno visible."""
    try:
        avisos = pagina.locator(SELECTOR_ERROR_LOGIN)
        for indice in range(avisos.count()):
            aviso = avisos.nth(indice)
            if not aviso.is_visible():
                continue
            texto = (aviso.inner_text(timeout=3_000) or "").strip()
            if texto:
                return texto
        return ""
    except Exception:
        return ""


def _es_rechazo_de_login(texto: str) -> bool:
    """True si ese aviso del portal significa 'usuario o contraseña mal'."""
    sin_tildes = _sin_tildes(texto)
    return any(frase in sin_tildes for frase in TEXTOS_LOGIN_RECHAZADO)


def _sesion_caducada(pagina) -> bool:
    """True si la página muestra que la sesión ya no vale.

    Se comprueban las tres formas en que el portal lo dice, porque no
    siempre usa la misma: te redirige a su pantalla de login, te muestra el
    formulario de usuario/contraseña, o te deja en la página pero con el
    aviso de que la sesión de usuario expiró.
    """
    try:
        if RUTA_LOGIN_DEL_PORTAL in (pagina.url or "").lower():
            return True
        if _hay_formulario_de_login(pagina):
            return True
        texto = pagina.locator("body").inner_text(timeout=5_000)
        return TEXTO_SESION_VENCIDA in _sin_tildes(texto)
    except Exception:
        return True


def _iniciar_sesion_en_pagina(pagina, usuario: str, clave: str, notificar) -> str:
    """Llena el formulario de login del portal y espera el resultado.

    La página ya tiene que estar mostrando el formulario. Devuelve:
    - "ok": se entró al portal.
    - "credenciales": el portal rechazó el usuario o la contraseña.
    - "error": algo falló antes de poder saberlo (red, portal caído...).
    """
    try:
        # Se escribe campo por campo y con una pausa entre medio, como lo
        # haría una persona: el formulario corre validaciones propias al
        # salir de cada campo y llenarlo de golpe puede adelantarlas.
        pagina.fill(SELECTOR_USUARIO, usuario)
        time.sleep(SEGUNDOS_ENTRE_SONDEOS)
        pagina.fill(SELECTOR_CLAVE, clave)
        time.sleep(SEGUNDOS_ENTRE_SONDEOS)
        pagina.click(SELECTOR_BOTON_INGRESAR)
    except Exception as error:
        notificar(f"[ERROR] No se pudo enviar el formulario de inicio de sesión: {error}")
        return "error"

    # El portal responde con una recarga completa (WebForms), así que en vez
    # de esperar un tiempo fijo se sondea hasta que el formulario desaparece
    # —señal de que se entró— o hasta que sale su aviso de rechazo.
    intentos = int(SEGUNDOS_MAXIMOS_ESPERA_LOGIN / SEGUNDOS_ENTRE_SONDEOS)
    for _ in range(intentos):
        if not _hay_formulario_de_login(pagina):
            return _asentar_despues_del_login(pagina, notificar)
        aviso = _texto_de_aviso_de_login(pagina)
        if aviso and _es_rechazo_de_login(aviso):
            notificar(f"[AVISO] El portal respondió: {aviso}")
            return "credenciales"
        time.sleep(SEGUNDOS_ENTRE_SONDEOS)

    notificar("[AVISO] El portal siguió mostrando el formulario de inicio de sesión.")
    return "credenciales"


def _asentar_despues_del_login(pagina, notificar) -> str:
    """Le da tiempo al portal a terminar de entrar antes de seguir.

    Que el formulario desaparezca no significa que ya se esté dentro: el
    portal encadena redirecciones y arma la sesión en el servidor después.
    Si se le pide la siguiente pantalla en ese momento, contesta como si no
    hubiera sesión. Aquí se espera a que la página quede quieta, se hace una
    pausa y recién entonces se comprueba que el login se sostiene.
    """
    _esperar_carga_de_pagina(pagina)
    time.sleep(SEGUNDOS_TRAS_LOGIN)
    _esperar_carga_de_pagina(pagina)

    if _hay_formulario_de_login(pagina):
        # Volvió al login por su cuenta: no llegó a quedar dentro.
        notificar("[AVISO] El portal volvió a la pantalla de inicio de sesión.")
        return "credenciales"

    notificar("[OK] Se entró al portal.")
    return "ok"


def _entrar_al_portal(pagina, usuario: str, clave: str, notificar) -> str:
    """Abre el portal y, si pide login, lo hace con las credenciales dadas.

    Devuelve "ok", "credenciales" o "error", igual que _iniciar_sesion_en_pagina.
    """
    try:
        pagina.goto(URL_GESTION_DOCENTE, wait_until="domcontentloaded", timeout=60_000)
    except Exception as error:
        notificar(f"[ERROR] No se pudo abrir Gestión Docente: {error}")
        return "error"
    _esperar_carga_de_pagina(pagina)

    if not _hay_formulario_de_login(pagina):
        return "ok"

    notificar("Iniciando sesión en Gestión Docente...")
    return _iniciar_sesion_en_pagina(pagina, usuario, clave, notificar)


def _abrir_aplicativo_academico(pagina, notificar):
    """Hace clic en el ícono "Académico" del escritorio y devuelve su página.

    Es el paso que faltaba: entrar al portal deja al docente en un
    escritorio con sus aplicativos, y la sesión de las pantallas de notas
    recién queda lista cuando se entra por el ícono de Académico. Ese
    enlace abre una pestaña nueva, así que se devuelve esa pestaña (o la
    misma, si algún día dejara de abrirla).

    Devuelve la página donde quedó Académico, o None si no se pudo.
    """
    time.sleep(SEGUNDOS_ENTRE_PASOS)

    enlace = pagina.locator(SELECTOR_APP_ACADEMICO)
    try:
        enlace.first.wait_for(
            state="visible", timeout=SEGUNDOS_MAXIMOS_ESPERA_APLICATIVOS * 1_000
        )
    except Exception:
        enlace = pagina.locator(SELECTOR_APP_ACADEMICO_RESPALDO)
        if enlace.count() == 0:
            notificar('[AVISO] No se encontró el ícono "Académico" en el portal.')
            return None

    notificar('Entrando al aplicativo "Académico"...')
    contexto = pagina.context
    try:
        with contexto.expect_page(
            timeout=SEGUNDOS_MAXIMOS_ESPERA_APLICATIVOS * 1_000
        ) as pestaña_nueva:
            enlace.first.click()
        pagina_academico = pestaña_nueva.value
    except Exception:
        # Si no abrió pestaña nueva, puede haber navegado en la misma.
        notificar('[AVISO] "Académico" no abrió una pestaña nueva; se sigue en la actual.')
        pagina_academico = pagina

    try:
        pagina_academico.wait_for_load_state("domcontentloaded", timeout=60_000)
    except Exception:
        pass
    _esperar_carga_de_pagina(pagina_academico)
    time.sleep(SEGUNDOS_ANTES_DE_REVISAR)

    if _sesion_caducada(pagina_academico):
        notificar('[AVISO] "Académico" no llegó a cargar con la sesión puesta.')
        return None

    notificar('[OK] "Académico" cargó correctamente.')
    return pagina_academico


def _abrir_registro_de_notas_en_pagina(pagina, notificar) -> bool:
    """Navega a la pantalla de registro de notas. False si el portal la rechaza."""
    # Pausa antes de pedir la siguiente pantalla: ir seguido de una a otra
    # es justo lo que hace que el portal responda que no hay sesión.
    time.sleep(SEGUNDOS_ENTRE_PASOS)
    try:
        pagina.goto(
            URL_GESTION_DOCENTE_REGISTRO_NOTAS,
            wait_until="domcontentloaded",
            timeout=60_000,
        )
    except Exception as error:
        notificar(f"[ERROR] No se pudo abrir la pantalla de notas: {error}")
        return False
    _esperar_carga_de_pagina(pagina)
    # Y otra antes de juzgar el resultado: el aviso de sesión vencida a
    # veces llega con la pantalla ya dibujada.
    time.sleep(SEGUNDOS_ANTES_DE_REVISAR)
    return not _sesion_caducada(pagina)


def probar_credenciales(usuario: str, clave: str, notificar=None) -> dict:
    """Comprueba que ese usuario y esa contraseña sirven para entrar al portal.

    Se da por buena la prueba cuando, después del login, carga el
    aplicativo "Académico": entrar a la raíz del portal no garantiza nada
    (esa diferencia ya nos engañó antes, con el panel diciendo "sesión
    activa" y la herramienta diciendo que había expirado), y Académico es
    justamente por donde se llega a las notas.

    La ventana se ve o no según MOSTRAR_NAVEGADOR_AL_PROBAR; por ahora se
    ve, para poder seguir con la vista lo que hace el portal.

    Devuelve {"estado": "activa"|"credenciales"|"error", "error": "..."}.
    """
    notificar = notificar or print

    if not usuario or not clave:
        return {"estado": "credenciales", "error": "Falta el usuario o la contraseña."}

    with sync_playwright() as playwright:
        navegador = playwright.chromium.launch(headless=not MOSTRAR_NAVEGADOR_AL_PROBAR)
        try:
            pagina = navegador.new_page(no_viewport=MOSTRAR_NAVEGADOR_AL_PROBAR)

            resultado = _entrar_al_portal(pagina, usuario, clave, notificar)
            if resultado == "credenciales":
                notificar("[AVISO] El portal no aceptó ese usuario o esa contraseña.")
                return {"estado": "credenciales"}
            if resultado != "ok":
                return {"estado": "error", "error": "No se pudo abrir Gestión Docente."}

            if _abrir_aplicativo_academico(pagina, notificar) is None:
                notificar('[AVISO] Se entró al portal, pero no cargó "Académico".')
                return {"estado": "error", "error": 'El portal no dejó abrir "Académico".'}

            notificar("[OK] El usuario y la contraseña de Gestión Docente funcionan.")
            if MOSTRAR_NAVEGADOR_AL_PROBAR:
                # Un momento para alcanzar a ver en qué pantalla terminó,
                # ya que la ventana se cierra apenas termina la prueba.
                time.sleep(SEGUNDOS_PARA_MIRAR_LA_VENTANA)
            return {"estado": "activa"}
        except Exception as error:
            notificar(f"[ERROR] No se pudo comprobar el acceso a Gestión Docente: {error}")
            return {"estado": "error", "error": str(error)}
        finally:
            try:
                navegador.close()
            except Exception:
                pass


def guardar_y_probar_credenciales(usuario: str, clave: str, notificar=None) -> dict:
    """Prueba el usuario y la contraseña y, si sirven, los guarda para reusarlos.

    Solo se guardan cuando el portal ya los aceptó, para no dejar guardada
    una contraseña equivocada con la que después todo falle en silencio.
    """
    notificar = notificar or print

    usuario = (usuario or "").strip()
    clave = clave or ""

    resultado = probar_credenciales(usuario, clave, notificar=notificar)
    if resultado.get("estado") != "activa":
        return resultado

    credenciales.guardar(usuario, clave)
    notificar("     Quedaron guardados en esta computadora, cifrados por Windows.")
    notificar("     La herramienta los usará para entrar sola cuando los necesite.")
    return resultado
