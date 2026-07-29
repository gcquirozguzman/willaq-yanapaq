"""
Punto de entrada de la línea de comandos (CLI) de Willaq Yanapaq.

Cómo usarlo, desde la carpeta del proyecto y con el entorno virtual activado:

    python -m willaq.cli panel
    python -m willaq.cli login
    python -m willaq.cli anuncios plantilla

Para la mayoría de los docentes, el comando más cómodo es 'panel': abre un
panel web local (en el navegador) con botones para hacer login y generar
la plantilla de anuncios, sin escribir comandos. Los demás comandos hacen
lo mismo pero por terminal.

Para ver todos los comandos disponibles y su descripción:

    python -m willaq.cli --help
"""

import argparse
import sys

from willaq.anuncios import publicar as anuncios_publicar
from willaq.anuncios.plantilla import generar_plantilla_cli
from willaq.autenticacion.login import ejecutar_login
from willaq.consulta_docente import consulta as consulta_docente
from willaq.cursos.listar import obtener_cursos_activos_cli
from willaq.presentacion import presentacion as presentacion_curso
from willaq.web.servidor import iniciar_panel


def _construir_parser() -> argparse.ArgumentParser:
    """Define todos los subcomandos disponibles del CLI."""

    parser = argparse.ArgumentParser(
        prog="willaq",
        description="Herramienta de automatización para el Blackboard de Cibertec.",
    )
    subcomandos = parser.add_subparsers(dest="comando", required=True)

    # --- panel web (recomendado para la mayoría de los docentes) ---
    subcomandos.add_parser(
        "panel",
        help="Abre un panel web local (más amigable que la terminal) para login y anuncios.",
    )

    # --- login ---
    subcomandos.add_parser(
        "login",
        help="Inicia sesión en Blackboard (la primera vez, completa el login y el SMS a mano).",
    )

    # --- cursos ---
    subcomandos.add_parser(
        "cursos",
        help="Muestra la lista de cursos activos (abiertos) del docente.",
    )

    # --- anuncios (con sus propios subcomandos) ---
    parser_anuncios = subcomandos.add_parser(
        "anuncios", help="Funciones relacionadas a los anuncios del curso."
    )
    subcomandos_anuncios = parser_anuncios.add_subparsers(dest="subcomando", required=True)

    subcomandos_anuncios.add_parser(
        "plantilla",
        help="Genera un archivo Excel con la plantilla para redactar anuncios.",
    )
    subcomandos_anuncios.add_parser(
        "publicar",
        help="[Pendiente] Publica en Blackboard los anuncios escritos en el Excel.",
    )

    # --- consulta al docente (única vez, al inicio del curso) ---
    subcomandos.add_parser(
        "consulta",
        help="[Pendiente] Completa la consulta al docente al inicio del curso.",
    )

    # --- presentación del curso (única vez, al inicio del ciclo) ---
    subcomandos.add_parser(
        "presentacion",
        help="[Pendiente] Completa la presentación del curso al inicio del ciclo.",
    )

    return parser


def main():
    parser = _construir_parser()
    args = parser.parse_args()

    if args.comando == "panel":
        iniciar_panel()
    elif args.comando == "login":
        ejecutar_login()
    elif args.comando == "cursos":
        obtener_cursos_activos_cli()
    elif args.comando == "anuncios":
        if args.subcomando == "plantilla":
            generar_plantilla_cli()
        elif args.subcomando == "publicar":
            anuncios_publicar.ejecutar()
    elif args.comando == "consulta":
        consulta_docente.ejecutar()
    elif args.comando == "presentacion":
        presentacion_curso.ejecutar()
    else:
        # No debería llegar aquí porque los subcomandos son "required",
        # pero se deja como respaldo por si se agregan nuevos comandos.
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
