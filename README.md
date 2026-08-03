# Willaq Yanapaq

Herramienta para ahorrar tiempo en tareas repetitivas del Blackboard de
Cibertec: anuncios semanales y sesiones de dictado en Collaborate,
generados y publicados automáticamente.

Cada profesor la usa en su propia computadora, con su propio login.
**Nadie comparte contraseñas ni sesiones.**

## Requisitos

- **Python 3.10 o superior**. Para verificarlo, abre una terminal y
  escribe `python3 --version` (en Windows puede ser `python --version`).
  Si no lo tienes, descárgalo de https://www.python.org/downloads/ (en
  Windows, marca "Add Python to PATH" al instalar).
- Conexión a internet.
- Tu correo institucional de Cibertec y acceso al celular donde recibes
  el código SMS de verificación.

## Instalación (una sola vez)

Abre una terminal dentro de la carpeta del proyecto y ejecuta:

**Windows:**

```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium
```

**Mac / Linux:**

```
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

No hay que configurar nada más: la herramienta detecta tu nombre y foto
automáticamente de Blackboard la primera vez que inicias sesión.

## Uso diario

1. Abre una terminal en la carpeta del proyecto.
2. Activa el entorno virtual (el mismo comando de "Instalación": `.venv\Scripts\activate` en Windows, o `source .venv/bin/activate` en Mac/Linux).
3. Ejecuta:
   ```
   python -m willaq.cli panel
   ```
4. Se abre una pestaña en tu navegador con el panel. Ahí está todo:
   iniciar sesión, obtener tus cursos, generar anuncios semanales y
   sesiones de dictado. Cada herramienta explica lo que hace antes de
   pedirte confirmación.
5. Para cerrar, vuelve a la terminal y presiona `Ctrl+C`.

La primera vez que inicias sesión se abre una ventana de Blackboard aparte
para que ingreses tu usuario, clave y código SMS a mano. Las siguientes
veces normalmente no te lo vuelve a pedir.

## Problemas comunes

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
