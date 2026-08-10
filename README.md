# Willaq Yanapaq

Herramienta para ahorrar tiempo en tareas repetitivas del Blackboard de
Cibertec: anuncios semanales y sesiones de dictado en Collaborate,
generados y publicados automáticamente, y las notas de tus alumnos
consultadas de una sola vez.

Cada profesor la usa en su propia computadora, con su propio login.
**Nadie comparte contraseñas ni sesiones.**

## Requisitos

- **Python 3.10 o superior**. Para verificarlo, abre una terminal y
  escribe `python --version` (en Mac/Linux suele ser `python3 --version`).
  Si no lo tienes, descárgalo de https://www.python.org/downloads/ (en
  Windows, marca "Add Python to PATH" al instalar).
- Conexión a internet.
- Tu correo institucional de Cibertec y acceso al celular donde recibes
  el código SMS de verificación.

## Instalación (una sola vez)

Abre una terminal **dentro de la carpeta del proyecto** (la que contiene
este archivo `README.md`) y ejecuta las cuatro líneas, una por una:

**Windows:**

```
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python -m playwright install chromium
```

**Mac / Linux:**

```
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m playwright install chromium
```

La última línea descarga un navegador (~150 MB), así que puede demorar
unos minutos. Al terminar, en la carpeta del proyecto debe existir una
carpeta nueva llamada `.venv`.

No hay que configurar nada más: la herramienta detecta tu nombre y foto
automáticamente de Blackboard la primera vez que inicias sesión.

## Uso diario

1. Abre una terminal en la carpeta del proyecto.
2. Ejecuta:

   **Windows:**

   ```
   .\.venv\Scripts\python -m willaq.cli panel
   ```

   **Mac / Linux:**

   ```
   .venv/bin/python -m willaq.cli panel
   ```

3. Se abre una pestaña en tu navegador con el panel. Ahí está todo:
   iniciar sesión, obtener tus cursos, generar anuncios semanales y
   sesiones de dictado, y obtener las notas de un examen o actividad para
   todos tus alumnos. Cada herramienta explica lo que hace antes de
   pedirte confirmación.
4. Para cerrar, vuelve a la terminal y presiona `Ctrl+C`.

La primera vez que inicias sesión se abre una ventana de Blackboard aparte
para que ingreses tu usuario, clave y código SMS a mano. Las siguientes
veces normalmente no te lo vuelve a pedir.

El panel usa dos sistemas de Cibertec, cada uno con su propia sesión, y te
muestra el estado de ambas:

- **Blackboard**, para los cursos, anuncios, sesiones de dictado y notas.
- **Gestión Docente**, para pasar las notas. Aquí "Iniciar sesión" te pide
  tu usuario y contraseña en el propio panel: se comprueban entrando al
  portal y, si funcionan, quedan guardados en tu computadora (cifrados por
  Windows, en `datos/`, que nunca se sube a ningún lado). Hace falta
  guardarlos porque ese portal no permite conservar la sesión, así que la
  herramienta vuelve a entrar sola cada vez que la necesita. Si alguna vez
  cambias tu contraseña, el panel te avisa y la vuelves a escribir ahí
  mismo; con "Olvidar credenciales" puedes borrarla cuando quieras.

> **Nota:** el comando usa el Python de la carpeta `.venv` (y no solo
> `python`) para que funcione siempre, sin tener que "activar" nada. En
> Windows el `.\` del inicio es obligatorio: PowerShell no ejecuta rutas
> relativas sin él. Si prefieres activar el entorno
> (`.\.venv\Scripts\activate` en Windows, `source .venv/bin/activate` en
> Mac/Linux), a partir de ahí puedes usar el comando corto
> `python -m willaq.cli panel`.

## Problemas comunes

- **`El módulo '.venv' no pudo cargarse`** o
  **`CommandNotFoundException`** (en Windows): te faltó el `.\` al inicio.
  El comando empieza con `.\.venv\Scripts\python`, con punto y barra
  invertida, no con `.venv\...`.
- **`ModuleNotFoundError: No module named 'playwright'`** (o `'flask'`, o
  `'openpyxl'`): falta hacer la instalación, o la estás ejecutando con el
  Python equivocado. Vuelve a la sección "Instalación" y ejecútala
  completa; luego usa el comando de "Uso diario" tal cual está escrito,
  empezando con `.\.venv\Scripts\python`.
- **`python` no se reconoce como un comando**: Python no está instalado o
  no se marcó "Add Python to PATH" al instalarlo. Reinstálalo desde
  https://www.python.org/downloads/ marcando esa casilla, y luego cierra y
  vuelve a abrir la terminal.
- **El comando no encuentra `.venv\Scripts\python`**: estás en otra
  carpeta, o la instalación no llegó a crear el entorno. Asegúrate de que
  la terminal esté abierta en la carpeta del proyecto (donde está este
  `README.md`) y repite la instalación.
- **`No se puede cargar el archivo ...\Activate.ps1 porque la ejecución de
  scripts está deshabilitada`**: solo aparece si intentas activar el
  entorno en PowerShell. No hace falta activarlo: usa el comando de "Uso
  diario" que empieza con `.\.venv\Scripts\python`.
- **`playwright install chromium` falla con un error de certificado**:
  suele pasar en laptops de empresa con software de seguridad (Zscaler,
  Netskope y similares). Pide ayuda al soporte técnico de tu institución,
  o contacta a quien te compartió esta herramienta.
- **Te vuelve a pedir el login**: es normal de vez en cuando (la sesión
  expira); complétalo otra vez como la primera vez.

## Privacidad

- Tu contraseña y tu sesión nunca se comparten con nadie: quedan
  guardadas solo en tu computadora, en la carpeta `datos/`.
- No subas esa carpeta ni la compartas con nadie.
