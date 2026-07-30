# Willaq Yanapaq

Herramienta de automatización para el **Blackboard de Cibertec**
(https://cibertec.blackboard.com/), pensada para que los profesores ahorren
tiempo en tareas repetitivas del curso.

No necesitas saber programar para usarla: sigue esta guía paso a paso.
Cada profesor la instala en su propia computadora, hace su propio login y
usa su propia configuración. **Nadie comparte contraseñas ni sesiones.**

## ¿Qué hace por ahora?

Esta primera entrega incluye:

- **Panel web** (`panel`): una página en tu navegador con botones para
  hacer login y generar la plantilla de anuncios, sin escribir comandos.
  Es la forma recomendada de usar la herramienta.
- **`login`**: abre el navegador, va al Blackboard de Cibertec y guarda tu
  sesión iniciada para que no tengas que volver a escribir tu clave ni el
  código SMS cada vez que uses la herramienta. (También disponible desde
  el panel web.)
- **`anuncios plantilla`**: genera un archivo Excel donde puedes redactar
  tranquilamente los anuncios del curso (fecha, título y cuerpo). (También
  disponible desde el panel web.)
- **`cursos`**: muestra la lista de tus cursos activos (abiertos) en
  Blackboard, con su código y nombre. Requiere haber iniciado sesión antes.
  (También disponible desde el panel web.)

Las demás funciones (publicar anuncios automáticamente, consulta al
docente, presentación del curso) están planeadas pero **todavía no
implementadas**. Si las ejecutas, el programa te avisará que están
pendientes.

## Requisitos

- **Python 3.10 o superior** instalado en tu computadora.
  - Para verificarlo, abre una terminal y escribe `python3 --version`
    (en Windows puede ser `python --version`).
  - Si no lo tienes, descárgalo desde https://www.python.org/downloads/
    (en Windows, marca la casilla "Add Python to PATH" durante la instalación).
- Conexión a internet.
- Tu correo institucional de Cibertec y acceso al celular donde recibes el
  código SMS de verificación (MFA).

## Instalación (una sola vez)

Abre una terminal dentro de la carpeta del proyecto (`willaq-yanapaq`) y
sigue estos pasos:

### 1. Crear un entorno virtual

Un entorno virtual es una "carpeta aislada" donde se instalan las
dependencias de este proyecto, sin afectar el resto de tu computadora.

**En Windows (símbolo del sistema o PowerShell):**

```
python -m venv .venv
.venv\Scripts\activate
```

**En Mac o Linux (Terminal):**

```
python3 -m venv .venv
source .venv/bin/activate
```

Si funcionó, deberías ver `(.venv)` al inicio de la línea de tu terminal.
Deberás repetir el comando de activación (`.venv\Scripts\activate` o
`source .venv/bin/activate`) cada vez que abras una terminal nueva para
usar la herramienta.

### 2. Instalar las dependencias

```
pip install -r requirements.txt
```

### 3. Instalar el navegador que usa Playwright

Playwright necesita descargar su propia copia de Chromium (un navegador
tipo Chrome) para poder controlarlo:

```
playwright install chromium
```

> Si tu laptop es de una empresa y tiene instalado software de seguridad
> como **Zscaler**, este paso puede fallar con un error de certificado
> (`SELF_SIGNED_CERT_IN_CHAIN`). Si te pasa eso, revisa la sección
> [Solución de problemas](#solución-de-problemas) más abajo.

No hay que configurar ningún archivo con tus datos: la herramienta
detecta tu nombre y foto automáticamente de Blackboard la primera vez
que inicias sesión.

## Panel web (recomendado)

Con el entorno virtual activado (ver paso 1), ejecuta:

```
python -m willaq.cli panel
```

Esto abre automáticamente una pestaña en tu navegador
(`http://127.0.0.1:5000`) con estas herramientas:

- **Iniciar sesión**: hace lo mismo que el comando `login` (ver abajo),
  pero mostrando el progreso en la propia página, con botones en vez de
  tener que volver a la terminal a presionar ENTER. Una vez que inicias
  sesión, el panel recuerda tu nombre y foto la próxima vez que lo abras
  (no hace falta volver a darle clic solo porque reiniciaste el panel).
- **Obtener Cursos Activos**: lista tus cursos abiertos en Blackboard
  (se habilita después de iniciar sesión). El panel recuerda la última
  lista obtenida entre reinicios, aunque conviene volver a pedirla de vez
  en cuando por si tus cursos cambiaron. Pide confirmación antes de
  lanzarse, ya que renovar la lista reinicia también las fechas de curso,
  Generar Anuncios Semanales y Generar Sesiones Dictado (ver abajo).
  Cada curso obtenido aparece como una tarjeta con un botón para
  **configurar su fecha de inicio y fin**; esa es la fecha que usan
  "Generar Anuncios Semanales" y "Generar Sesiones Dictado", así que hay
  que configurarla una sola vez por curso antes de poder usar esas dos
  herramientas (mientras no la configures, aparecen bloqueadas).
- **Generar Anuncios Semanales**: abre un formulario para elegir un curso
  (solo aparecen los que ya tienen su fecha de inicio/fin configurada
  desde "Cursos activos") y el día/hora de los anuncios de inicio y fin
  de semana. Dentro del mismo formulario:
  - **Ver anuncios**: muestra una grilla editable con un anuncio de inicio
    y uno de fin por cada semana del curso (título, mensaje, fecha y
    hora), con textos de ejemplo listos para editar.
  - **Generar en Blackboard**: toma exactamente lo que ves en esa grilla
    (con cualquier edición que hayas hecho) y crea cada fila como un
    anuncio real dentro de "Anuncios" del curso en Blackboard, programado
    para la fecha y hora indicadas. Pide confirmación antes de publicar,
    ya que crea contenido real visible para tus estudiantes.
- **Generar Sesiones Dictado**: similar al anterior, pero para el horario
  de clases: eliges un curso (con la misma condición de fecha ya
  configurada) y a qué hora dicta cada día de la semana (los días sin
  clase se dejan vacíos). Dentro del mismo formulario:
  - **Ver Sesiones**: genera la grilla de sesiones (una por cada día con
    clase, con el nombre "SESIÓN NN - <curso> (<código>) - <tu nombre>"),
    desde el inicio hasta el fin del curso. Cada sesión se puede
    reprogramar puntualmente (nueva fecha/hora, con motivo obligatorio) sin
    tocar el horario semanal; la fila queda en amarillo y su fecha/hora
    original sigue disponible con el botón "Detalle".
  - **Feriados**: un listado editable de los feriados peruanos del año
    actual (con Semana Santa calculada según la fecha real de Pascua de
    ese año), para agregar o quitar fechas a demanda. Las sesiones que
    caen en un feriado se resaltan en rojo en la grilla.
  - **Generar en Blackboard**: publica, como anuncios reales programados
    (igual que "Generar Anuncios Semanales"), solo las sesiones desde hoy
    en adelante; las que ya pasaron no se publican. Pide confirmación antes
    de publicar, ya que crea contenido real visible para tus estudiantes.

La ventana del navegador de Blackboard (donde completas tu usuario, clave
y el código SMS la primera vez) se sigue abriendo aparte, como una ventana
de Chrome normal — el panel web solo reemplaza la terminal para lanzar el
proceso y ver su estado.

Para detener el panel, vuelve a la terminal donde lo lanzaste y presiona
`Ctrl+C`.

> Si prefieres no usar el panel y trabajar directo desde la terminal,
> puedes hacerlo: más abajo se explican los comandos `login` y
> `anuncios plantilla`, que hacen exactamente lo mismo.

## Primer uso: iniciar sesión (por terminal)

Si prefieres no usar el panel web, con el entorno virtual activado ejecuta:

```
python -m willaq.cli login
```

Esto abrirá una ventana de navegador y te llevará al Blackboard de
Cibertec. La primera vez:

1. La terminal te pedirá que completes el login **a mano** en la ventana
   del navegador: tu correo, tu clave y el código SMS (MFA) que te llega
   al celular.
2. Cuando termines y veas tu panel de Blackboard cargado, **vuelve a la
   terminal y presiona ENTER** para continuar.
3. El programa guardará tu sesión en la carpeta `datos/` (que tampoco se
   sube al repositorio, por seguridad).

En las siguientes veces que ejecutes `login`, normalmente **no te pedirá
el código SMS de nuevo**, porque el navegador ya "recuerda" tu sesión. Si
en algún momento tu sesión expira, el programa te lo indicará y te pedirá
que vuelvas a iniciar sesión a mano, igual que la primera vez.

## Generar la plantilla de anuncios (por terminal)

Si prefieres no usar el panel web, con el entorno virtual activado ejecuta:

```
python -m willaq.cli anuncios plantilla
```

Esto crea el archivo `plantillas_generadas/plantilla_anuncios.xlsx` con
columnas **Fecha**, **Título** y **Cuerpo**, más un par de filas de
ejemplo. Ábrelo con Excel, borra o edita las filas de ejemplo y agrega una
fila por cada anuncio que quieras publicar en tu curso.

Si el archivo ya existe (por ejemplo, porque ya lo habías generado antes),
el programa te preguntará si deseas reemplazarlo, para que no pierdas por
accidente lo que ya habías escrito.

> Por ahora, la publicación de esos anuncios en Blackboard se hace
> manualmente, copiando y pegando desde el Excel. La publicación
> automática es una función futura.

## Ver todos los comandos disponibles

```
python -m willaq.cli --help
```

## Solución de problemas

### `playwright install chromium` falla con `SELF_SIGNED_CERT_IN_CHAIN`

Este error ocurre cuando tu computadora (típicamente una laptop de empresa)
tiene instalado software de seguridad que inspecciona el tráfico de
internet, como **Zscaler**. Ese software intercepta la descarga y la
vuelve a firmar con su propio certificado; tu sistema operativo confía en
ese certificado, pero la herramienta interna que usa Playwright (Node.js)
no lo conoce por defecto, así que rechaza la descarga.

**Solución (Mac):**

1. Exporta el certificado raíz de Zscaler a un archivo, con este comando
   en la terminal:

   ```
   security find-certificate -a -c "Zscaler" -p /Library/Keychains/System.keychain > ~/zscaler-root-ca.pem
   ```

2. Verifica que el archivo no haya quedado vacío:

   ```
   cat ~/zscaler-root-ca.pem
   ```

   Si no muestra nada, es porque el certificado tiene otro nombre en tu
   equipo. Usa este comando de respaldo, que exporta todos los
   certificados del sistema (es más "bruto", pero funciona igual):

   ```
   security find-certificate -a -p /Library/Keychains/System.keychain > ~/zscaler-root-ca.pem
   ```

3. Vuelve a instalar el navegador, indicándole a Node que confíe en ese
   certificado:

   ```
   NODE_EXTRA_CA_CERTS=~/zscaler-root-ca.pem playwright install chromium
   ```

Si usas Windows y tienes este mismo problema (por ejemplo con Zscaler,
Netskope u otro software similar de tu empresa), el enfoque es el mismo:
exportar el certificado raíz desde el "Administrador de certificados" de
Windows (`certmgr.msc`) a un archivo `.pem`, y usar esa misma variable
`NODE_EXTRA_CA_CERTS` apuntando a ese archivo antes de ejecutar
`playwright install chromium`. Si tienes dudas con este paso en Windows,
pide ayuda al área de soporte técnico de tu institución.

## Seguridad y privacidad

- Este repositorio **no contiene credenciales ni datos personales** de
  ningún profesor.
- Tu carpeta `datos/` (sesión de navegador, foto de perfil) es local a tu
  computadora y está excluida del repositorio mediante `.gitignore`. No la
  compartas ni la subas a ningún lado.
- Los archivos Excel que generes en `plantillas_generadas/` tampoco se
  suben al repositorio, ya que pueden contener contenido de tus cursos.

## Estructura del proyecto (para quien quiera revisar el código)

```
willaq/
├── cli.py                  # Define los comandos del programa
├── config.py                # Rutas locales (perfil de navegador, Excel generados)
├── autenticacion/
│   └── login.py             # Login con sesión persistente (implementado)
├── anuncios/
│   ├── plantilla.py         # Genera el Excel de ejemplo (implementado)
│   ├── semanal.py           # Guarda la config. de anuncios semanales (implementado)
│   └── publicar.py          # Publica los anuncios en Blackboard (implementado)
├── cursos/
│   ├── listar.py            # Lista de cursos activos (implementado)
│   └── fechas.py            # Fecha de inicio/fin por curso (implementado)
├── dictado/
│   ├── sesiones.py           # Guarda la config. de sesiones de dictado (implementado)
│   ├── reprogramaciones.py   # Reprogramación puntual de sesiones (implementado)
│   ├── feriados.py           # Feriados peruanos, editables (implementado)
│   └── publicar.py           # Publica las sesiones en Blackboard (implementado)
├── consulta_docente/
│   └── consulta.py          # Consulta al docente (pendiente)
├── presentacion/
│   └── presentacion.py      # Presentación del curso (pendiente)
└── web/
    ├── servidor.py           # Rutas Flask del panel web y su lanzador
    ├── estado.py              # Estado del login en memoria (para el panel)
    ├── templates/index.html   # Página del panel
    └── static/                # CSS y JavaScript del panel (sin frameworks)
```
