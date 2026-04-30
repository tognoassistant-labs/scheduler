# Guía rápida — Coordinador académico

Pensada para el coordinador del Colegio que NO es desarrollador.
Cubre el flujo completo: subir datos → ajustar reglas → generar
horario → exportar a PowerSchool.

## Qué necesitas para empezar

- URL de la app (te la pasa el equipo de IT)
- Password de acceso (te lo pasa el equipo de IT)
- El archivo `schedule_master_data_hs.xlsx` actualizado del año
- 30-60 minutos la primera vez; 10-15 minutos las siguientes

## Flujo completo (8 pasos)

### 1. Entrar a la app

- Abre la URL en Chrome o Edge
- Ingresa el password
- Verás 10 tabs en la parte de arriba

### 2. Subir los datos (tab `Inputs`)

- En el sidebar (panel izquierdo), elige **"xlsx real de Columbus"**
- **NO subas** el archivo crudo. Antes:
  - Tu IT debe correr el script de limpieza una vez:
    ```
    python scripts/cleanup_master_data.py
      --in <archivo-original>.xlsx
      --out <archivo-limpio>.xlsx
      --report CLEANUP_REPORT.md
    ```
  - El archivo limpio es el que subes
- Click **Ingestar**
- Verifica que dice "Cargado: 509 estudiantes, 248 secciones..."

### 3. Activar persistencia (sidebar)

- Marca el checkbox **"Guardar corridas en SQLite"**
- A partir de aquí cada solve queda guardado en el histórico

### 4. Revisar las reglas (tab `Reglas`)

Las reglas vienen con valores por defecto razonables. Lo más
importante:

| Regla | Default | Cuándo cambiar |
|---|---|---|
| Coplanning | ON | Si el master da infeasible |
| Spread máximo K | 4 | Subir a 5-6 si las electivas están bajas |
| Peso electivas | 20 | Subir a 50 si quieres maximizarlas |

Después de cambiar, click **"✓ Aplicar al próximo solve"**.

### 5. Importar reglas de salas (opcional pero recomendado)

En la sección **"➕ Reglas personalizadas"**:

- Click **"📥 Importar `course_room_type` (STATUS=ACTIVE)"**
- Esto importa las reglas de tipo de sala que IT activó previamente
  en la hoja correspondiente del xlsx (PE → gym, química →
  science_lab, banda → music, etc.)
- Verás la lista de reglas importadas debajo

### 6. Correr el solve (tab `Solve`)

- Deja los presupuestos de tiempo en default (30s master, 180s student)
- Click **"▶️ Solve"**
- Espera 1-3 minutos. Verás:
  - Progress bars
  - Mensaje de éxito con Run #N
  - 6 tarjetas KPI con el resultado

### 7. Revisar cumplimiento (tab `Cumplimiento`)

- La tabla muestra cada regla con su % de cumplimiento
- **Reglas duras (hard) deben estar al 100%** — si no, hay un bug
- **Reglas suaves (soft)** muestran qué tan bien se cumplió cada
  preferencia. 80%+ es bueno
- Si algo está bajo, ve a **Drill-down** y revisa las violaciones
  específicas

### 8. Exportar a PowerSchool (tab `Exportar`)

- Si dejaste la persistencia ON, aquí puedes elegir:
  - **Sesión actual** (default)
  - **Run histórico** — para re-exportar una corrida pasada
- Click **"🎁 Download all as ZIP"**
- El ZIP contiene los 3 CSVs listos para importar a PowerSchool:
  - `ps_sections.csv`
  - `ps_enrollments.csv`
  - `ps_master_schedule.csv`

## Iterar

Si los KPIs no son suficientes:

1. Ve a la tab `Reglas`
2. Ajusta lo que creas conveniente (subir peso electivas, relajar
   balance, etc.)
3. Solve de nuevo (paso 6)
4. Compara las dos corridas en la tab `Corridas` — selecciona
   ambas en el multiselect y verás el diff lado a lado

Cada iteración tarda 1-3 minutos. Lo normal es hacer 3-5 antes de
exportar.

## Cuándo pedir ayuda

- **Master infeasible** después de varios intentos → IT
- **Tabla de cumplimiento muestra una regla dura ≠ 100%** → IT (es un bug)
- **El xlsx no se ingesta** → IT (probablemente falta una hoja)
- **El export a PowerSchool falla en PS** → IT con el log del error de PS

## Lo que la tab `Ayuda` cubre en detalle

- Cada regla explicada en español (qué hace, cuándo usarla)
- Glosario (bundle, run, scheme, etc.)
- Tabla de targets v2 §10 con sus metas
- Recomendaciones para configuraciones comunes

## Recomendación de configuración inicial

Basada en simulación con datos reales de Columbus:

> **`elective_boost`:**
> - Coplanning: ON (por default)
> - Balance K: 4 (default)
> - Peso electivas: **50** (subido desde 20)
>
> **Resultado esperado:** 100% required, ~85% electivas rank-1, balance dev 3.

Esta config logra los 4 targets v2 §10 simultáneamente.
