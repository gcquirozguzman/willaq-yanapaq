"""
Estado compartido del panel web, guardado en memoria.

El panel web es para un solo docente ejecutándose en su propia máquina (no
hay múltiples usuarios ni base de datos), así que basta con guardar el
progreso del login en un objeto en memoria. Se usa un candado
(threading.Lock) porque dos hilos lo tocan al mismo tiempo: el hilo de
Flask que atiende las peticiones del navegador, y el hilo en segundo plano
que corre Playwright.
"""

import threading


class EstadoLogin:
    """Guarda el progreso del login mientras corre en un hilo aparte."""

    def __init__(self):
        self._candado = threading.Lock()
        self.evento_login_manual = threading.Event()
        self.evento_cierre = threading.Event()
        self.nombre_docente = None
        self.tiene_avatar = False
        self._reiniciar_sin_candado()

    def _reiniciar_sin_candado(self):
        self.en_progreso = False
        self.logs = []
        # Fases posibles: inactivo, ejecutando, esperando_login_manual,
        # esperando_cierre, terminado.
        self.fase = "inactivo"
        self.resultado = None  # None | "ok" | "activa" | "aviso" | "error"
        self.error = None
        # Nota: 'nombre_docente' y 'tiene_avatar' NO se reinician aquí a
        # propósito, para que el header del panel no "parpadee" perdiendo
        # el nombre/foto mientras corre un nuevo intento de login.

    def iniciar(self):
        """Reinicia el estado para arrancar un nuevo intento de login."""
        with self._candado:
            self._reiniciar_sin_candado()
            self.en_progreso = True
            self.fase = "ejecutando"
        self.evento_login_manual.clear()
        self.evento_cierre.clear()

    def agregar_log(self, mensaje: str):
        with self._candado:
            self.logs.append(mensaje)

    def marcar_fase(self, fase: str):
        with self._candado:
            self.fase = fase

    def marcar_terminado(
        self,
        resultado: str,
        error: str = None,
        nombre_docente: str = None,
        tiene_avatar: bool = False,
    ):
        with self._candado:
            self.en_progreso = False
            self.fase = "terminado"
            self.resultado = resultado
            self.error = error
            if nombre_docente:
                self.nombre_docente = nombre_docente
            if tiene_avatar:
                self.tiene_avatar = tiene_avatar

    def snapshot(self) -> dict:
        """Foto del estado actual, lista para convertir a JSON."""
        with self._candado:
            return {
                "en_progreso": self.en_progreso,
                "logs": list(self.logs),
                "fase": self.fase,
                "resultado": self.resultado,
                "error": self.error,
                "nombre_docente": self.nombre_docente,
                "tiene_avatar": self.tiene_avatar,
            }


class EstadoCursos:
    """Guarda el progreso de la búsqueda de cursos activos."""

    def __init__(self):
        self._candado = threading.Lock()
        self.obtenido_en = None
        self._reiniciar_sin_candado()

    def _reiniciar_sin_candado(self):
        self.en_progreso = False
        self.logs = []
        self.fase = "inactivo"  # inactivo | ejecutando | terminado
        self.resultado = None  # None | "ok" | "error"
        self.cursos = []
        self.error = None
        # Nota: 'obtenido_en' NO se reinicia aquí a propósito, para que la
        # fecha mostrada en el panel no desaparezca mientras corre una nueva
        # búsqueda (se actualiza recién cuando esa búsqueda termina bien).

    def iniciar(self):
        with self._candado:
            self._reiniciar_sin_candado()
            self.en_progreso = True
            self.fase = "ejecutando"

    def agregar_log(self, mensaje: str):
        with self._candado:
            self.logs.append(mensaje)

    def marcar_terminado(self, resultado: str, cursos: list = None, error: str = None, obtenido_en: str = None):
        with self._candado:
            self.en_progreso = False
            self.fase = "terminado"
            self.resultado = resultado
            self.cursos = cursos or []
            self.error = error
            if obtenido_en is not None:
                self.obtenido_en = obtenido_en

    def snapshot(self) -> dict:
        with self._candado:
            return {
                "en_progreso": self.en_progreso,
                "logs": list(self.logs),
                "fase": self.fase,
                "resultado": self.resultado,
                "cursos": list(self.cursos),
                "error": self.error,
                "obtenido_en": self.obtenido_en,
            }


class EstadoTarea:
    """Estado genérico para una tarea de fondo que abre el navegador.

    A diferencia de EstadoLogin/EstadoCursos (que llevan campos propios
    como 'nombre_docente' o 'cursos'), esta clase sirve para cualquier
    acción que simplemente corre en un hilo aparte y al final entrega un
    resultado en forma de diccionario (por ejemplo, {"publicados": N,
    "fallidos": [...]})); se usa para las acciones que publican o eliminan
    cosas reales en Blackboard (anuncios semanales, sesiones de dictado),
    que antes bloqueaban la petición HTTP mientras Playwright corría, sin
    poder mostrar ninguna señal de progreso en el panel mientras tanto.
    """

    def __init__(self):
        self._candado = threading.Lock()
        self._reiniciar_sin_candado()

    def _reiniciar_sin_candado(self):
        self.en_progreso = False
        self.logs = []
        self.fase = "inactivo"  # inactivo | ejecutando | terminado
        self.resultado = None
        self.error = None
        # 'total' es cuántos elementos hay que procesar (se sabe de
        # antemano cuando se publica una lista concreta de anuncios o
        # sesiones); queda en None cuando no se sabe (el barrido de
        # "eliminar sesiones no iniciadas" no tiene un total fijo, va
        # descubriendo qué eliminar sobre la marcha). 'procesados' cuenta
        # cuántos elementos ya se empezaron a procesar, sin importar si
        # terminaron bien o mal.
        self.total = None
        self.procesados = 0

    def iniciar(self, total: int = None):
        with self._candado:
            self._reiniciar_sin_candado()
            self.en_progreso = True
            self.fase = "ejecutando"
            self.total = total

    def agregar_log(self, mensaje: str):
        with self._candado:
            self.logs.append(mensaje)

    def incrementar_procesados(self):
        with self._candado:
            self.procesados += 1

    def marcar_terminado(self, resultado: dict = None, error: str = None):
        with self._candado:
            self.en_progreso = False
            self.fase = "terminado"
            self.resultado = resultado
            self.error = error

    def snapshot(self) -> dict:
        with self._candado:
            return {
                "en_progreso": self.en_progreso,
                "logs": list(self.logs),
                "fase": self.fase,
                "resultado": self.resultado,
                "error": self.error,
                "total": self.total,
                "procesados": self.procesados,
            }


# Una sola instancia compartida por todo el panel web
# (un solo docente, un solo proceso corriendo en su máquina).
estado_login = EstadoLogin()
estado_cursos = EstadoCursos()
estado_generar_anuncios = EstadoTarea()
estado_generar_sesiones = EstadoTarea()
estado_eliminar_sesiones = EstadoTarea()
