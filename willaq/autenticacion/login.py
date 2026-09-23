"""
Inicio de sesión en el Blackboard de Cibertec, con sesión persistente.

Cómo funciona (en palabras simples):

1. Playwright abre una ventana de navegador, pero usando una "carpeta de
   perfil" guardada en disco (datos/perfil_navegador/). Esa carpeta funciona
   como el perfil de un Chrome normal: ahí quedan guardadas las cookies, la
   sesión iniciada, y el "recuerdo de este dispositivo" que usa Microsoft
   para no pedir el código SMS en cada inicio de sesión.

2. La PRIMERA vez que se usa, esa carpeta está vacía, así que Blackboard
   redirige al login de Microsoft/Outlook y pide usuario, clave y el código
   de verificación (SMS o correo). Como eso solo lo puede completar el
   profesor a mano, el script no bloquea esperando una confirmación: sondea
   sola la URL cada pocos segundos hasta detectar que ya salió de esa
   pantalla (ver _esperar_fin_de_pantalla_de_login).

3. La página principal de Blackboard muestra un botón "Estudiante | Docente"
   que siempre hay que presionar para continuar (con sesión activa te lleva
   directo al panel; sin sesión, te lleva al login de Microsoft). Aparte de
   ese botón, no completamos ningún formulario por el profesor (todo el
   login es manual), así que para saber si terminamos en una pantalla de
   login o no, nos basta con mirar el dominio de la URL actual.

4. En corridas siguientes, como la carpeta de perfil ya no está vacía,
   normalmente Blackboard/Microsoft reconocen el navegador y no vuelven a
   pedir el código SMS, a menos que la sesión haya expirado.

Este módulo se puede usar tanto desde la terminal (CLI) como desde el panel
web, por eso los momentos donde se avisa algo al profesor o se espera su
confirmación están separados en funciones intercambiables ("notificar",
"marcar_esperando_login_manual", "esperar_orden_de_cierre"). Por defecto
usan la terminal (print/input); el panel web les pasa sus propias versiones
basadas en su estado en memoria.
"""

import json
import shutil

from playwright.sync_api import TimeoutError as ErrorDeTiempoDeEspera
from playwright.sync_api import sync_playwright

from willaq.config import DIR_DATOS, DIR_PERFIL_NAVEGADOR, URL_BLACKBOARD

# Fragmentos de dominio típicos del login de Microsoft/Outlook. Si la URL
# actual contiene alguno de estos, asumimos que todavía estamos en una
# pantalla de inicio de sesión y no dentro de Blackboard. Esto es solo el
# nombre del dominio (no un selector de HTML), así que es seguro de asumir
# sin haber visto la página.
DOMINIOS_DE_LOGIN = (
    "login.microsoftonline.com",
    "login.live.com",
    "login.microsoft.com",
)

# Botón "Estudiante | Docente" de la página principal de Blackboard.
# Siempre hay que hacer clic en él para continuar, tanto si ya tienes
# sesión iniciada (te lleva directo a tu panel) como si no (te lleva al
# login de Microsoft). Confirmado con el HTML real de la página.
SELECTOR_BOTON_INGRESO = "#btn-login"

# Botón de perfil (foto + nombre) que aparece en el menú de Blackboard una
# vez logueado, en https://cibertec.blackboard.com/ultra/institution-page.
# Usamos el atributo 'data-analytics-id', que es estable, en vez de las
# clases con hash que genera Material-UI (esas sí cambian). Confirmado con
# el HTML real de la página.
SELECTOR_BOTON_PERFIL = 'a[data-analytics-id="base.nav.navigation.profile"]'

# Dónde se guarda localmente la foto de perfil descargada (no se sube al
# repositorio: está dentro de datos/, que ya está en .gitignore).
RUTA_AVATAR_DOCENTE = DIR_DATOS / "avatar_docente.jpg"

# Caché mínimo del último login exitoso (solo nombre + si hay foto), para
# que el panel web pueda mostrar tu identidad de inmediato la próxima vez
# que se inicie, sin obligarte a hacer clic en "Iniciar sesión" de nuevo.
# La sesión real (cookies) sigue viviendo en DIR_PERFIL_NAVEGADOR; esto es
# solo para no perder la identidad mostrada en pantalla entre reinicios.
RUTA_ESTADO_SESION = DIR_DATOS / "estado_sesion.json"


def _guardar_estado_sesion(datos_docente: dict):
    try:
        DIR_DATOS.mkdir(parents=True, exist_ok=True)
        RUTA_ESTADO_SESION.write_text(
            json.dumps(
                {
                    "nombre": datos_docente.get("nombre"),
                    "tiene_avatar": bool(datos_docente.get("ruta_avatar")),
                }
            ),
            encoding="utf-8",
        )
    except Exception:
        pass  # esto es solo una comodidad de la interfaz; si falla, no afecta el login


def cargar_estado_sesion_guardado():
    """Lee el último login exitoso guardado en disco, si existe.

    Devuelve None si nunca se guardó nada (por ejemplo, primera vez que se
    usa la herramienta).
    """
    try:
        if RUTA_ESTADO_SESION.exists():
            return json.loads(RUTA_ESTADO_SESION.read_text(encoding="utf-8"))
    except Exception:
        pass
    return None


def borrar_sesion_guardada():
    """Borra la sesión de Blackboard guardada en disco (perfil de navegador,
    identidad en caché y foto de perfil), para forzar un login desde cero.

    No toca Gestión Docente: esa sesión se olvida aparte, con
    willaq.autenticacion.credenciales.olvidar().

    Lanza OSError si la carpeta del perfil no se pudo borrar (por ejemplo,
    si un navegador todavía la tiene abierta), para que quien llama pueda
    avisarle al docente en vez de fallar en silencio.
    """
    if DIR_PERFIL_NAVEGADOR.exists():
        try:
            shutil.rmtree(DIR_PERFIL_NAVEGADOR)
        except OSError as error:
            raise OSError(
                "No se pudo borrar la sesión de Blackboard guardada: cierra "
                "cualquier ventana del navegador que haya quedado abierta e "
                "inténtalo de nuevo."
            ) from error

    for ruta in (RUTA_ESTADO_SESION, RUTA_AVATAR_DOCENTE):
        try:
            ruta.unlink(missing_ok=True)
        except Exception:
            pass  # esto es solo una comodidad de la interfaz; si falla, no es grave


def _parece_pantalla_de_login(url: str) -> bool:
    """Indica si la URL actual parece ser una pantalla de login de Microsoft."""
    return any(dominio in url for dominio in DOMINIOS_DE_LOGIN)


def _esperar_fin_de_pantalla_de_login(pagina, tiempo_maximo_segundos: int = 600, intervalo_segundos: int = 2):
    """Sondea la URL actual hasta que deja de verse como pantalla de login de Microsoft.

    El profesor completa su usuario, clave y el código de verificación (SMS
    o correo) él mismo, directamente en la ventana del navegador; en vez de
    bloquear esperando que alguien lo confirme a mano desde afuera, esto
    detecta solo cuándo ya salió de esa pantalla, revisando la URL cada
    'intervalo_segundos'. 10 minutos de tiempo máximo por defecto alcanza de
    sobra para cualquier código de verificación; si se agota, quien llama lo
    nota igual porque vuelve a comprobar la URL después de esta función.
    """
    intentos_maximos = max(1, tiempo_maximo_segundos // intervalo_segundos)
    for _ in range(intentos_maximos):
        if not _parece_pantalla_de_login(pagina.url):
            return
        pagina.wait_for_timeout(intervalo_segundos * 1000)


def _esperar_carga_de_pagina(pagina):
    """Espera a que la página termine de cargar, sin colgarse si nunca queda 100% quieta.

    Algunas páginas modernas (como Blackboard) mantienen conexiones de red
    abiertas en segundo plano y nunca llegan al estado "networkidle". Por eso
    ponemos un límite de tiempo y seguimos adelante si se cumple, en vez de
    tratarlo como un error.
    """
    try:
        pagina.wait_for_load_state("networkidle", timeout=15_000)
    except Exception:
        pass


def _hacer_clic_en_boton_ingreso(pagina, notificar):
    """Hace clic en el botón 'Estudiante | Docente' de la página principal.

    Este botón siempre debe presionarse para continuar, sin importar si ya
    tienes sesión iniciada o no: con sesión activa te lleva directo al
    panel de Blackboard; sin sesión, te lleva al login de Microsoft.
    """
    try:
        pagina.click(SELECTOR_BOTON_INGRESO, timeout=10_000)
    except ErrorDeTiempoDeEspera:
        notificar("[AVISO] No se encontró el botón 'Estudiante | Docente' en la página principal.")
        notificar("        Puede que Blackboard haya cambiado su página de inicio; continuamos igual.")


def _esperar_por_terminal(mensaje: str):
    input(mensaje)


def _extraer_datos_docente(pagina, contexto, notificar) -> dict:
    """Intenta leer el nombre y la foto de perfil del docente ya logueado.

    Es un intento "best effort": el botón de perfil solo aparece cuando el
    login funcionó. Si algo falla (Blackboard cambió su interfaz, tardó más
    de lo esperado, etc.), no mostramos nombre/foto, pero SÍ avisamos por
    qué (en vez de fallar en silencio), para poder diagnosticarlo.
    """
    datos = {"nombre": None, "ruta_avatar": None}

    boton_perfil = pagina.locator(SELECTOR_BOTON_PERFIL)
    try:
        boton_perfil.wait_for(timeout=8_000)
        datos["nombre"] = boton_perfil.locator("bdi").inner_text(timeout=3_000).strip()
    except Exception as error:
        notificar(f"[AVISO] No se pudo leer tu nombre de perfil (no es grave): {error}")
        return datos

    # No todos los docentes tienen una foto configurada en Blackboard: eso
    # es normal, no un error. Por eso este bloque no usa "[AVISO]" (que
    # suena a problema); si no hay foto, simplemente no se muestra ninguna.
    try:
        url_avatar = boton_perfil.locator("img").get_attribute("src", timeout=3_000)
    except Exception:
        url_avatar = None

    if not url_avatar:
        notificar("     No se detectó una foto de perfil (es normal si no tienes una configurada en Blackboard).")
    else:
        try:
            # Descargamos la foto navegando con el propio navegador (una
            # pestaña nueva), en vez de usar 'contexto.request' (un cliente
            # HTTP aparte). Esto evita problemas con proxys corporativos que
            # inspeccionan HTTPS (como Zscaler): el navegador confía en su
            # certificado porque usa el almacén del sistema operativo, pero
            # el cliente HTTP interno de Playwright no.
            #
            # Blackboard sirve esta URL como una descarga de archivo (no
            # como una página normal), así que hay que capturarla con
            # 'expect_download' en vez de tratarla como una navegación común.
            pagina_avatar = contexto.new_page()
            try:
                with pagina_avatar.expect_download(timeout=6_000) as info_descarga:
                    try:
                        pagina_avatar.goto(url_avatar)
                    except Exception:
                        pass  # goto() corta la navegación apenas empieza la descarga; es lo esperado
                descarga = info_descarga.value
                DIR_DATOS.mkdir(parents=True, exist_ok=True)
                descarga.save_as(str(RUTA_AVATAR_DOCENTE))
                datos["ruta_avatar"] = str(RUTA_AVATAR_DOCENTE)
            finally:
                pagina_avatar.close()
        except Exception:
            notificar("     No se pudo obtener tu foto de perfil (puede que no tengas una configurada en Blackboard).")

    if datos["nombre"]:
        notificar(f"     Docente detectado: {datos['nombre']}")

    return datos


def ejecutar_login(
    notificar=None,
    marcar_esperando_login_manual=None,
    esperar_orden_de_cierre=None,
    al_confirmar_sesion=None,
):
    """Ejecuta el flujo completo de login y devuelve el resultado.

    Parámetros (todos opcionales; si no se pasan, se usa la terminal):
    - notificar(mensaje): muestra un mensaje al profesor. Por defecto, print.
    - marcar_esperando_login_manual(): se llama una vez, apenas se detecta la
      pantalla de login de Microsoft, solo para avisar que se está
      esperando (por ejemplo, para que el panel web cambie de fase). No
      bloquea nada: el profesor completa usuario, clave y el código de
      verificación (SMS o correo) él mismo en la ventana del navegador, y
      esta función sondea sola la URL hasta detectar que ya salió de esa
      pantalla (ver _esperar_fin_de_pantalla_de_login). Por defecto no hace
      nada.
    - esperar_orden_de_cierre(): bloquea hasta que el profesor pide cerrar
      el navegador. Por defecto, espera ENTER. Solo se usa si el login
      terminó en "aviso" (no se pudo confirmar); si terminó en "ok" o
      "activa", el navegador se cierra solo, sin pedir confirmación.
    - al_confirmar_sesion(resultado, datos_docente): se llama apenas se
      confirma que la sesión quedó activa ("ok" o "activa"), ANTES de
      intentar cerrar el navegador. Existe porque cerrar un
      launch_persistent_context a veces tarda mucho o se queda colgado
      (visto en Windows), y sin este aviso temprano quien llama (el panel
      web) nunca se enteraría de que el login sí funcionó, dejando las
      herramientas bloqueadas indefinidamente. Por defecto no hace nada.

    Devuelve una tupla (resultado, datos_docente):
    - resultado es uno de "activa" (ya había sesión vigente), "ok" (se
      completó el login manual ahora) o "aviso" (no se pudo confirmar).
    - datos_docente es un diccionario {"nombre": ..., "ruta_avatar": ...},
      con valores en None si no se pudo leer el nombre/foto del perfil.
    """
    notificar = notificar or print
    marcar_esperando_login_manual = marcar_esperando_login_manual or (lambda: None)
    esperar_orden_de_cierre = esperar_orden_de_cierre or (
        lambda: _esperar_por_terminal(">> Presiona ENTER para cerrar el navegador...")
    )
    al_confirmar_sesion = al_confirmar_sesion or (lambda resultado, datos_docente: None)

    DIR_PERFIL_NAVEGADOR.mkdir(parents=True, exist_ok=True)

    notificar("=" * 70)
    notificar("WILLAQ YANAPAQ - Inicio de sesión en Blackboard Cibertec")
    notificar("=" * 70)
    notificar(f"Se abrirá una ventana de navegador y se navegará a: {URL_BLACKBOARD}")

    with sync_playwright() as playwright:
        # launch_persistent_context guarda todo (cookies, sesión) en
        # DIR_PERFIL_NAVEGADOR, para poder reutilizarlo en la próxima corrida.
        # headless=False es obligatorio aquí: el profesor necesita ver la
        # ventana para completar el login y el código SMS a mano.
        contexto = playwright.chromium.launch_persistent_context(
            user_data_dir=str(DIR_PERFIL_NAVEGADOR),
            headless=False,
        )

        pagina = contexto.pages[0] if contexto.pages else contexto.new_page()
        pagina.goto(URL_BLACKBOARD)
        _esperar_carga_de_pagina(pagina)

        _hacer_clic_en_boton_ingreso(pagina, notificar)
        _esperar_carga_de_pagina(pagina)

        if _parece_pantalla_de_login(pagina.url):
            notificar("Se detectó la pantalla de inicio de sesión de Microsoft/Outlook.")
            notificar("Por favor, en la ventana del navegador que se abrió:")
            notificar("  1. Ingresa tu correo y contraseña institucional de Cibertec.")
            notificar("  2. Completa la verificación por SMS o correo (MFA) cuando te la pidan.")
            notificar("  3. Esto seguirá solo apenas termine de cargar tu panel de Blackboard.")
            marcar_esperando_login_manual()
            _esperar_fin_de_pantalla_de_login(pagina)

            _esperar_carga_de_pagina(pagina)

            if _parece_pantalla_de_login(pagina.url):
                notificar("[AVISO] Todavía parece que sigues en una pantalla de inicio de sesión.")
                notificar("        Revisa la ventana del navegador: si el login no se completó,")
                notificar("        termínalo ahí y vuelve a intentarlo.")
                resultado = "aviso"
                datos_docente = {"nombre": None, "ruta_avatar": None}
            else:
                notificar("[OK] Sesión iniciada correctamente.")
                notificar(f"     Tu sesión quedó guardada en: {DIR_PERFIL_NAVEGADOR}")
                notificar(
                    "     La próxima vez no debería pedirte el SMS de nuevo, mientras esa sesión siga vigente."
                )
                resultado = "ok"
                datos_docente = _extraer_datos_docente(pagina, contexto, notificar)
                _guardar_estado_sesion(datos_docente)
                al_confirmar_sesion(resultado, datos_docente)
        else:
            notificar("[OK] Ya tenías una sesión guardada y sigue activa.")
            notificar("     No fue necesario volver a iniciar sesión.")
            resultado = "activa"
            datos_docente = _extraer_datos_docente(pagina, contexto, notificar)
            _guardar_estado_sesion(datos_docente)
            al_confirmar_sesion(resultado, datos_docente)

        if resultado == "aviso":
            # Algo no se pudo confirmar: dejamos que el profesor revise la
            # ventana antes de cerrarla.
            esperar_orden_de_cierre()
        else:
            notificar("Cerrando el navegador automáticamente...")

        contexto.close()

    return resultado, datos_docente
