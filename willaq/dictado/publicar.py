"""
Publicación automática de las sesiones de dictado en Blackboard.

Usa exactamente el mismo mecanismo que los anuncios semanales: cada sesión
se crea como un anuncio programado, con el panel real "Crear anuncio" del
curso (ver willaq/anuncios/publicar.py para el detalle de cómo funciona
esa automatización, confirmado navegando de verdad con la sesión
guardada). Este módulo solo arma el título y el mensaje de cada sesión
antes de delegar en esa misma función.
"""

from willaq.anuncios.publicar import generar_anuncios_en_blackboard


def _mensaje_sesion(sesion: dict) -> str:
    mensaje = f"Sesión de dictado: {sesion['hora_inicio']} - {sesion['hora_fin']}."
    detalle = (sesion.get("detalle") or "").strip()
    if detalle:
        mensaje += f"\n\nEsta sesión fue reprogramada. Motivo: {detalle}"
    return mensaje


def generar_sesiones_en_blackboard(id_curso: str, sesiones: list, notificar=None) -> dict:
    """Publica una lista de sesiones de dictado como anuncios reales de Blackboard.

    'sesiones' es una lista de diccionarios con "titulo" (el nombre de la
    sesión, ej. "SESIÓN 01 - ..."), "fecha" (YYYY-MM-DD), "hora_inicio" y
    "hora_fin" (HH:MM, 24 horas) y opcionalmente "detalle" (si fue
    reprogramada), tal como se ven en la grilla "Ver Sesiones" del panel.

    Devuelve el mismo formato que generar_anuncios_en_blackboard:
    {"estado": "ok"|"parcial"|"error", "publicados": N, "fallidos": [...]}.
    """
    anuncios = [
        {
            "titulo": sesion["titulo"],
            "mensaje": _mensaje_sesion(sesion),
            "fecha": sesion["fecha"],
            "hora": sesion["hora_inicio"],
        }
        for sesion in sesiones
    ]
    return generar_anuncios_en_blackboard(id_curso, anuncios, notificar=notificar)
