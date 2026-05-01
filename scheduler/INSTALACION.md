# Instalación local — Columbus Scheduler v4.27

Guía de instalación del paquete para el Colegio. Funciona en macOS y Linux.
Para Windows, recomendamos WSL2 o Docker (ver `DEPLOY.md`).

---

## Lo que necesitas antes de empezar

- Un computador con macOS o Linux
- 2 GB de espacio libre
- Conexión a internet (solo para la primera instalación, descarga ~500MB
  de dependencias Python)
- **Python 3.12** instalado
- Privilegios de usuario normal (no necesitas sudo si Python ya está)

### Verificar Python 3.12

Abre Terminal y ejecuta:

```bash
python3.12 --version
```

Debe imprimir algo como `Python 3.12.7`. Si no lo tienes:

**macOS:**
```bash
brew install python@3.12
```

**Linux (Ubuntu/Debian):**
```bash
sudo apt update
sudo apt install python3.12 python3.12-venv
```

---

## Paso 1 — Descomprimir el paquete

Asume que recibiste `columbus_scheduler_v4.27.zip`. En Terminal:

```bash
cd ~/Downloads     # o donde lo hayas guardado
unzip columbus_scheduler_v4.27.zip
cd columbus_scheduler_v4.27
ls
```

Deberías ver carpetas como `src/`, `tests/`, `data/`, `scripts/`, y
archivos como `app.py`, `start_local.sh`, `Dockerfile`, etc.

---

## Paso 2 — Primera ejecución (instala dependencias)

```bash
chmod +x start_local.sh
./start_local.sh
```

La primera vez verás:

```
→ Creando virtual environment (.venv) ...
→ Instalando dependencias ...
```

Esto demora **1-3 minutos** (descarga ortools, pandas, streamlit, etc.).

Cuando termine, verás:

```
═══════════════════════════════════════════════════════
  Columbus Scheduler — modo local
═══════════════════════════════════════════════════════
  URL:   http://localhost:8501
  ...
═══════════════════════════════════════════════════════

  You can now view your Streamlit app in your browser.
  URL: http://localhost:8501
```

**Deja esa Terminal abierta.** Cerrarla detiene la app.

---

## Paso 3 — Abrir la app

En Chrome, Safari o Edge:

```
http://localhost:8501
```

La app debe cargar y mostrar el sidebar a la izquierda con la opción
"Fuente de datos" y 10 tabs arriba.

---

## Paso 4 — Cargar datos del Colegio

En el sidebar:

1. Selecciona **"xlsx real de Columbus"**
2. Click **"Browse files"** y selecciona tu archivo
   `schedule_master_data_hs.xlsx` (el original o el limpio)
3. Deja "Workbook de schedule" vacío
4. Grado: `12` (o el que corresponda)
5. Click **"📥 Ingestar"**

Espera ~10 segundos. Verás *"Ingestado: 509 estudiantes, 248 secciones..."*

---

## Paso 5 — Activar persistencia

En el sidebar, marca el checkbox **"Guardar corridas en SQLite"**.

A partir de aquí cada solve queda guardado en una BD local (en
`data/columbus.sqlite`). Esto te permite:
- Comparar corridas
- Re-exportar corridas pasadas
- No perder trabajo si cierras la app

---

## Paso 6 — Tu primera corrida

1. Click tab **"2️⃣ Solve"**
2. Deja todo en default
3. Click **"▶️ Solve"**
4. Espera 1-3 minutos
5. Revisa los KPIs en pantalla

Si los KPIs no son los esperados, **lee** `CASO_DEMO_Y_AJUSTE.md` —
explica cómo subir el peso de electivas y qué iteraciones hacer.

---

## Paso 7 — Detener la app

En la Terminal donde corre, presiona `Ctrl + C`.

---

## Re-arrancar después (días siguientes)

Solo necesitas:

```bash
cd ~/Downloads/columbus_scheduler_v4.27
./start_local.sh
```

La instalación de dependencias **no se repite** — usa el venv ya creado.

---

## Resolver problemas comunes

### "command not found: python3.12"

Instala Python 3.12 (ver sección "Verificar Python 3.12" arriba).

### "Permission denied" al correr ./start_local.sh

```bash
chmod +x start_local.sh
```

### "Port 8501 already in use"

Usa otro puerto:

```bash
./start_local.sh --port 8502
```

Y abre `http://localhost:8502`.

### La app se queda colgada

```bash
pkill -f "streamlit run"
```

Vuelve a ejecutar `./start_local.sh`.

### Quiero borrar todo y empezar de cero

```bash
rm -rf .venv data/columbus.sqlite
./start_local.sh
```

### Quiero ver qué hay en la BD

```bash
sqlite3 data/columbus.sqlite "SELECT id, label, status FROM run"
```

---

## Documentos incluidos en el paquete

- **`INSTALACION.md`** — este archivo (instalación)
- **`COORDINATOR_QUICKSTART.md`** — guía de 8 pasos para el coordinador
- **`CASO_DEMO_Y_AJUSTE.md`** — caso de ejemplo + cómo iterar pesos
- **`HANDOFF_v5.md`** — documentación técnica completa (para IT)
- **`DEPLOY.md`** — opciones de despliegue (Docker / systemd / Render)

Lee primero `INSTALACION.md`, después `COORDINATOR_QUICKSTART.md` para
el flujo diario, y `CASO_DEMO_Y_AJUSTE.md` cuando los KPIs no estén al
nivel esperado.

---

## Datos NO incluidos en el paquete

Por privacidad (FERPA), el paquete **no incluye** archivos con datos
reales de estudiantes. El Colegio debe usar su propio xlsx
(`schedule_master_data_hs.xlsx`).

El paquete sí incluye un generador de datos sintéticos (`scripts/` y
sample en `data/sample/`) para hacer pruebas sin tocar datos reales.

Para generar un sample:

```bash
.venv/bin/python -m src.scheduler.cli generate-sample --out data/test_sample
```

Después en la app: sidebar → "Carpeta canónica de CSVs" → ruta
`data/test_sample`.

---

## Soporte

Si algo no funciona:

1. Revisa esta guía
2. Revisa `CASO_DEMO_Y_AJUSTE.md` para problemas con KPIs
3. Si el problema es técnico, contacta al equipo de IT con:
   - El mensaje de error completo
   - El archivo `data/columbus.sqlite` (si existe)
   - La versión del motor: `v4.27`

---

## Verificar que la instalación funciona

Después del Paso 2, antes de cargar datos reales, puedes correr el
test suite para verificar que todo está bien:

```bash
.venv/bin/python -m pytest tests/test_persistence.py tests/test_compliance.py tests/test_runner.py tests/test_rule_registry.py -q
```

Esperado: **60 passed** en ~2 minutos.

Si algún test falla, NO uses la app con datos reales hasta resolver
el problema con IT.
