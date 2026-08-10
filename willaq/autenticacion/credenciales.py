"""
Guardado local del usuario y la contraseña de Gestión Docente.

Por qué hay que guardar la contraseña (y no solo la sesión, como con
Blackboard): el portal de Gestión Docente autentica con cookies DE SESIÓN
más estado en el servidor, así que su sesión no sobrevive a cerrar el
navegador ni se puede copiar de una ventana a otra. La única forma de que
la herramienta pueda entrar sola cada vez que la necesita es volver a
iniciar sesión, y para eso necesita las credenciales.

Cómo se guardan: cifradas con DPAPI, el cifrado que trae Windows. La clave
la maneja el propio Windows y está atada a la cuenta de usuario y a la
máquina, así que el archivo no sirve de nada si alguien se lo lleva a otra
computadora o lo abre desde otra cuenta de Windows. Aun así vive dentro de
datos/, que está en .gitignore y nunca se sube al repositorio.

Si DPAPI no estuviera disponible (por ejemplo, corriendo esto fuera de
Windows), se guarda sin cifrar antes que romper la herramienta, pero se
deja constancia en el propio archivo ('protegido': false) para que se sepa.
"""

import base64
import ctypes
import json
from ctypes import wintypes

from willaq.config import DIR_DATOS

RUTA_CREDENCIALES = DIR_DATOS / "credenciales_gestion_docente.json"


class _Blob(ctypes.Structure):
    """DATA_BLOB de la API de Windows: un puntero a bytes y su tamaño."""

    _fields_ = [
        ("cbData", wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_char)),
    ]

    @classmethod
    def desde_bytes(cls, datos: bytes) -> "_Blob":
        bufer = ctypes.create_string_buffer(datos, len(datos))
        return cls(len(datos), ctypes.cast(bufer, ctypes.POINTER(ctypes.c_char)))

    def a_bytes(self) -> bytes:
        return ctypes.string_at(self.pbData, self.cbData)

    def liberar(self):
        ctypes.windll.kernel32.LocalFree(self.pbData)


def _cifrar(texto: str) -> str:
    """Cifra con DPAPI y devuelve el resultado en base64 (texto para JSON)."""
    entrada = _Blob.desde_bytes(texto.encode("utf-8"))
    salida = _Blob()
    ok = ctypes.windll.crypt32.CryptProtectData(
        ctypes.byref(entrada), None, None, None, None, 0, ctypes.byref(salida)
    )
    if not ok:
        raise OSError("Windows no pudo cifrar la contraseña (CryptProtectData).")
    try:
        return base64.b64encode(salida.a_bytes()).decode("ascii")
    finally:
        salida.liberar()


def _descifrar(texto_base64: str) -> str:
    """Deshace lo que hizo _cifrar. Solo funciona en la misma cuenta y máquina."""
    entrada = _Blob.desde_bytes(base64.b64decode(texto_base64))
    salida = _Blob()
    ok = ctypes.windll.crypt32.CryptUnprotectData(
        ctypes.byref(entrada), None, None, None, None, 0, ctypes.byref(salida)
    )
    if not ok:
        raise OSError("Windows no pudo descifrar la contraseña (CryptUnprotectData).")
    try:
        return salida.a_bytes().decode("utf-8")
    finally:
        salida.liberar()


def guardar(usuario: str, clave: str):
    """Guarda las credenciales, cifradas si el sistema lo permite."""
    DIR_DATOS.mkdir(parents=True, exist_ok=True)
    try:
        contenido = {"usuario": usuario, "clave": _cifrar(clave), "protegido": True}
    except Exception:
        contenido = {"usuario": usuario, "clave": clave, "protegido": False}
    RUTA_CREDENCIALES.write_text(
        json.dumps(contenido, ensure_ascii=False), encoding="utf-8"
    )


def cargar() -> dict | None:
    """Devuelve {"usuario", "clave"} o None si no hay nada guardado o no se pudo leer."""
    try:
        if not RUTA_CREDENCIALES.exists():
            return None
        datos = json.loads(RUTA_CREDENCIALES.read_text(encoding="utf-8"))
        usuario = datos.get("usuario")
        clave = datos.get("clave")
        if not usuario or not clave:
            return None
        if datos.get("protegido"):
            clave = _descifrar(clave)
        return {"usuario": usuario, "clave": clave}
    except Exception:
        # Un archivo ilegible (cifrado en otra cuenta de Windows, corrupto)
        # equivale a no tener credenciales: se vuelven a pedir.
        return None


def hay_guardadas() -> bool:
    return cargar() is not None


def olvidar():
    """Borra las credenciales guardadas."""
    try:
        if RUTA_CREDENCIALES.exists():
            RUTA_CREDENCIALES.unlink()
    except Exception:
        pass
