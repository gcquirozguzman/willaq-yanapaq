"""
Panel web local para docentes.

Este panel es una interfaz más amigable que la terminal para las mismas
funciones del CLI (por ahora: login y generación de la plantilla de
anuncios). Corre en la propia computadora del docente, en
http://127.0.0.1:5000, y no requiere Node.js ni ningún paso de "build":
es un servidor Flask simple sirviendo HTML, CSS y JavaScript planos.

Como Playwright necesita una ventana de navegador visible para que el
profesor complete el login y el SMS a mano, ese paso sigue abriéndose
aparte del panel; el panel solo reemplaza a la terminal para lanzar el
proceso, ver su progreso en vivo y confirmar los pasos manuales con
botones en vez de presionar ENTER.
"""

import threading
import webbrowser

from flask import Flask, jsonify, render_template, request, send_file

from willaq.anuncios.plantilla import generar_plantilla
from willaq.anuncios.semanal import guardar_configuracion_semanal, obtener_configuracion_semanal
from willaq.autenticacion.login import (
    RUTA_AVATAR_DOCENTE,
    cargar_estado_sesion_guardado,
    ejecutar_login,
)
from willaq.cursos.listar import cargar_cursos_guardados, obtener_cursos_activos
from willaq.web.estado import estado_cursos, estado_login


def _detectar_tipo_imagen(ruta) -> str:
    """Adivina el tipo MIME real de la foto de perfil mirando sus primeros bytes.

    Blackboard no siempre entrega el mismo formato de imagen, así que no
    podemos asumir un tipo fijo. Revisamos la "firma" del archivo en vez de
    confiar en el nombre del archivo.
    """
    with open(ruta, "rb") as archivo:
        cabecera = archivo.read(8)
    if cabecera.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if cabecera.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if cabecera.startswith(b"GIF87a") or cabecera.startswith(b"GIF89a"):
        return "image/gif"
    return "image/jpeg"


def crear_app() -> Flask:
    """Arma la aplicación Flask con todas sus rutas."""

    app = Flask(__name__)

    @app.get("/")
    def index():
        return render_template("index.html")

    @app.post("/api/login/iniciar")
    def iniciar_login():
        if estado_login.en_progreso:
            return jsonify({"error": "Ya hay un login en curso."}), 409

        estado_login.iniciar()
        hilo = threading.Thread(target=_ejecutar_login_en_hilo, daemon=True)
        hilo.start()
        return jsonify({"ok": True})

    @app.post("/api/login/confirmar-login-manual")
    def confirmar_login_manual():
        estado_login.evento_login_manual.set()
        return jsonify({"ok": True})

    @app.post("/api/login/confirmar-cierre")
    def confirmar_cierre():
        estado_login.evento_cierre.set()
        return jsonify({"ok": True})

    @app.get("/api/login/estado")
    def consultar_estado_login():
        return jsonify(estado_login.snapshot())

    @app.get("/api/avatar")
    def avatar_docente():
        if not RUTA_AVATAR_DOCENTE.exists():
            return jsonify({"error": "Todavía no hay una foto de perfil guardada."}), 404
        return send_file(RUTA_AVATAR_DOCENTE, mimetype=_detectar_tipo_imagen(RUTA_AVATAR_DOCENTE))

    @app.post("/api/plantilla/generar")
    def generar_plantilla_web():
        datos = request.get_json(silent=True) or {}
        resultado = generar_plantilla(forzar=bool(datos.get("forzar")))
        return jsonify(resultado)

    @app.post("/api/anuncios-semanales/guardar")
    def guardar_anuncios_semanales_web():
        datos = request.get_json(silent=True) or {}
        resultado = guardar_configuracion_semanal(datos)
        return jsonify(resultado)

    @app.get("/api/anuncios-semanales/<codigo_curso>")
    def consultar_anuncios_semanales_web(codigo_curso):
        return jsonify(obtener_configuracion_semanal(codigo_curso) or {})

    @app.post("/api/cursos/obtener")
    def iniciar_obtener_cursos():
        if estado_cursos.en_progreso:
            return jsonify({"error": "Ya se están buscando tus cursos."}), 409

        estado_cursos.iniciar()
        hilo = threading.Thread(target=_obtener_cursos_en_hilo, daemon=True)
        hilo.start()
        return jsonify({"ok": True})

    @app.get("/api/cursos/estado")
    def consultar_estado_cursos():
        return jsonify(estado_cursos.snapshot())

    return app


def _ejecutar_login_en_hilo():
    """Corre el flujo de login en un hilo aparte, reportando todo al estado compartido.

    Le pasamos a 'ejecutar_login' nuestras propias versiones de notificar/esperar,
    basadas en el estado en memoria y en eventos, en vez de print()/input().
    """

    def notificar(mensaje):
        estado_login.agregar_log(mensaje)

    def esperar_login_manual():
        estado_login.marcar_fase("esperando_login_manual")
        estado_login.evento_login_manual.wait()
        estado_login.evento_login_manual.clear()
        estado_login.marcar_fase("ejecutando")

    def esperar_orden_de_cierre():
        estado_login.marcar_fase("esperando_cierre")
        estado_login.evento_cierre.wait()
        estado_login.evento_cierre.clear()

    try:
        resultado, datos_docente = ejecutar_login(
            notificar=notificar,
            esperar_login_manual=esperar_login_manual,
            esperar_orden_de_cierre=esperar_orden_de_cierre,
        )
        estado_login.marcar_terminado(
            resultado,
            nombre_docente=datos_docente.get("nombre"),
            tiene_avatar=bool(datos_docente.get("ruta_avatar")),
        )
    except Exception as error:
        # Capturamos cualquier falla inesperada para mostrarla en el panel
        # en vez de que el hilo muera en silencio y el navegador se quede
        # esperando para siempre.
        estado_login.agregar_log(f"[ERROR] Ocurrió un problema inesperado: {error}")
        estado_login.marcar_terminado("error", error=str(error))


def _obtener_cursos_en_hilo():
    """Corre la búsqueda de cursos en un hilo aparte, igual que el login."""

    def notificar(mensaje):
        estado_cursos.agregar_log(mensaje)

    try:
        cursos = obtener_cursos_activos(notificar=notificar)
        estado_cursos.marcar_terminado("ok", cursos=cursos)
    except Exception as error:
        estado_cursos.agregar_log(f"[ERROR] Ocurrió un problema inesperado: {error}")
        estado_cursos.marcar_terminado("error", error=str(error))


def _restaurar_sesion_guardada():
    """Si ya se había hecho login antes, precarga esa identidad en el estado.

    Así el panel muestra tu nombre/foto y desbloquea las herramientas de
    inmediato al arrancar, sin obligarte a hacer clic en "Iniciar sesión"
    otra vez solo porque reiniciaste el panel. La sesión real (cookies)
    vive en el perfil de navegador y no se toca aquí; si en verdad expiró,
    el próximo intento real de usar Blackboard lo detectará igual.
    """
    guardado = cargar_estado_sesion_guardado()
    if guardado:
        estado_login.marcar_terminado(
            "activa",
            nombre_docente=guardado.get("nombre"),
            tiene_avatar=guardado.get("tiene_avatar", False),
        )


def _restaurar_cursos_guardados():
    """Si ya se había obtenido la lista de cursos antes, precárgala en el estado.

    Igual que con la sesión: la búsqueda real solo ocurre cuando el docente
    presiona "Obtener" otra vez, pero así no se pierde la última lista
    encontrada solo por haber reiniciado el panel.
    """
    cursos_guardados = cargar_cursos_guardados()
    if cursos_guardados is not None:
        estado_cursos.marcar_terminado("ok", cursos=cursos_guardados)


def iniciar_panel(host: str = "127.0.0.1", puerto: int = 5000):
    """Levanta el panel web y abre el navegador automáticamente."""

    app = crear_app()
    _restaurar_sesion_guardada()
    _restaurar_cursos_guardados()
    url = f"http://{host}:{puerto}"

    print("=" * 70)
    print("WILLAQ YANAPAQ - Panel web del docente")
    print("=" * 70)
    print(f"Abriendo el panel en: {url}")
    print("Para detenerlo, vuelve a esta terminal y presiona Ctrl+C.")
    print()

    threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    app.run(host=host, port=puerto, debug=False, threaded=True)
