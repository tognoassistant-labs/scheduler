# Handoff to next agent — Columbus Scheduler

> **Lee este archivo PRIMERO.** Está diseñado para que un agente nuevo
> pueda continuar el proyecto sin context previo. Todo lo crítico está
> aquí: estado, rutas, decisiones tomadas, recomendaciones.
>
> **Última actualización:** 2026-05-03
> **Versión actual:** v4.28.19
> **Branch git:** `claude/hardcore-lovelace-cb1284`

---

## 1. Resumen ejecutivo en 30 segundos

Motor de horarios académicos para The Columbus School (Medellín, Colombia).
Stack: Python 3.12 + OR-Tools CP-SAT + Streamlit + SQLite.

**Lo que ya funciona:**
- Solve 2-stage (master + student) en <15 min con datos reales (509
  estudiantes, 248 secciones)
- Aplicación local con 10 tabs en español (Inputs, Reglas, Solve,
  Cumplimiento, Explorar, Locks, Corridas, Escenarios, Exportar, Ayuda)
- Persistencia SQLite (44 commits, 3 schema migrations)
- 19 reglas builtin + 6 opcodes Phase 2 custom
- Reportes ejecutivo / por estudiante / por departamento
- Exports compatibles con PowerSchool y con el visor del Colegio
- Program Guide oficial integrado (clasifica required/optative/elective
  desde el PDF del Colegio)

**Lo que NO está terminado:**
- KPIs no llegan a meta v2 §10 con clasificación PDF activa (Required
  97.9%, Electivas 55.6%, Fully scheduled 82.1%) — no por bug, sino por
  **conflictos estructurales reales** del horario del Colegio
- 91 estudiantes (18%) tienen al menos UN curso obligatorio sin asignar
- Cliente aún no ha probado v4.28.19 — esperando feedback

---

## 2. Working directory + rutas críticas

```
WORKTREE:
  /Users/hector/Projects/scheduler_handoff/.claude/worktrees/hardcore-lovelace-cb1284

CARPETA SCHEDULER (todo el código de la app):
  /Users/hector/Projects/scheduler_handoff/.claude/worktrees/hardcore-lovelace-cb1284/scheduler/

VENV (creado por start_local.sh):
  /Users/hector/Projects/scheduler_handoff/.claude/worktrees/hardcore-lovelace-cb1284/scheduler/.venv/

DATOS DEL CLIENTE (no están en git, viven en disco):
  /Users/hector/Downloads/Final_schedule_master_data_hs.xlsx       ← archivo oficial v5
  /Users/hector/Downloads/schedule_master_data_hs.xlsx              ← versión anterior (mismo nombre)
  /Users/hector/Downloads/High School Program Guide 2026-2027 for Students and Parents.pdf
  /Users/hector/Downloads/rfi_1._STUDENTS_PER_COURSE_2026-2027.xlsx ← formato legacy
  /Users/hector/Downloads/rfi_HS_Schedule_25-26.xlsx                ← schedule legacy

ZIPs ENVIADOS AL CLIENTE (en orden cronológico):
  /Users/hector/Downloads/columbus_scheduler_v4.27.zip       ← original (REQ-1..5)
  /Users/hector/Downloads/columbus_scheduler_v4.27.18.zip
  /Users/hector/Downloads/columbus_scheduler_v4.28.0.zip
  /Users/hector/Downloads/columbus_scheduler_v4.28.6.zip
  /Users/hector/Downloads/columbus_scheduler_v4.28.17.zip    ← último zip enviado
  (NO existe zip de v4.28.18/19 — pending, ver §6)

REPORTES GENERADOS:
  /Users/hector/Downloads/REPORTE_EJECUTIVO_final.md         ← último entregable

BACKUPS / SQLITE WORKING (gitignored):
  scheduler/data/columbus.sqlite     ← BD principal del usuario
  scheduler/data/final_solve.sqlite  ← solve sin PDF classification
  scheduler/data/final_v428_19.sqlite ← solve v4.28.19 con PDF classification
```

**Comando para arrancar la app:**

```bash
cd /Users/hector/Projects/scheduler_handoff/.claude/worktrees/hardcore-lovelace-cb1284/scheduler
./start_local.sh
# luego abre http://localhost:8501
```

---

## 3. Cómo se construyó la solución — historia condensada

### 3.1 Origen (v4.0 → v4.26)
Pre-este-proyecto. Era un script + Streamlit en memoria, sin
persistencia. Solo G12, ingest XLSX legacy, exports PowerSchool.
Detalles en `HANDOFF_v4.md`.

### 3.2 v4.27 — De script a aplicación operativa (commits `6261aef` → `aa89e39`)
6 hitos planeados al inicio:
- M1 Persistencia SQLite con 8 tablas
- M2 Registry de 19 reglas builtin
- M3 Tabs Inputs + Reglas
- M4 Tab Cumplimiento + diff de corridas
- M5 Refactor scenarios con persistencia
- M6 Hooks Phase 2 (custom rules placeholder)

Validado con datos reales: 509 estudiantes, 100% required, 88.5%
electivas. Ver `HANDOFF_v5.md`.

### 3.3 v4.27.x — Refinamientos (commits `38449d6` → `aa89e39`)
- v4.27.1: 4 checkers compliance más (13/19 reglas medidas)
- v4.27.2: deploy artifacts (Render, Docker, password gate)
- v4.27.3: cobertura 19/19 + UI español + tab Help + HANDOFF_v5
- v4.27.4: 5 opcodes Phase 2 (forbid_pair, forbid_slot, require_room,
  require_room_type, prefer_teacher, cohort_together)
- v4.27.5: deploy Docker + systemd
- v4.27.x: simulaciones, comparador, matriz de decisión

### 3.4 v4.27.15 → v4.27.18 — UX para cliente
- Multi-grado en UI (no solo G12)
- Banner de archivo cargado con path
- Auto-rutear formato v5 vs legacy
- Generar `student_schedules_friendly.csv` para visor del Colegio

### 3.5 v4.28.0 → v4.28.6 — Sprint de UX (REQ-1..5 + 6 mejoras)
Cliente dijo "qué más le podemos agregar". Implementé Sprint 1 + 2 del
ROADMAP_v4.28.md:
- REQ-1 Selector grados con presets
- REQ-2 Panel permanente de archivos cargados
- REQ-3 Tooltip schema + validador pre-ingest
- REQ-4 Plantillas xlsx descargables
- REQ-5 Errores con solución sugerida
- C2 Micro-sugerencias en KPIs
- F3 Notas y tags por corrida
- C4 Estimación de tiempo
- F2 Auto-comparación
- G1 Reporte ejecutivo 1-página
- J2 Auto-save de session state

### 3.6 v4.28.7 → v4.28.17 — Más backlog
- D3 Auto-rutear formato (legacy/v5 con un solo uploader)
- F4 Lock de corrida
- C3 Diagnóstico narrativo tras Solve
- I3 Notificaciones (toast + beep + browser API)
- G2 Reporte por estudiante
- H1 Banner FERPA
- D2 Auto-inferir año
- I4 Backup automático SQLite
- G3 Reporte por departamento
- HC3b Cap teachers con 7+ secciones (máx 2 días con 5 consecutivos)
- Vista de cursos faltantes × grado (commit `7ce1d76`)

### 3.7 v4.28.18 → v4.28.19 — Program Guide PDF (HOY)
**Aporte clave** — el cliente identificó que el motor no distingía
3 categorías del PDF (Required/Optative/Elective). Solo manejaba
Required vs Elective.

Acciones:
- Codificar PDF como `data/program_guide_2026-2027.yaml`
- Crear `src/scheduler/program_guide.py` (loader + classifier)
- Update `ps_ingest_official.py`: ahora 3,851 cursos HARD required
  (era 1,279) — incluye Optatives reclasificados
- Update `validate.py`: detecta missing_required, missing_optative_area,
  multiple_electives per estudiante
- Refinement: validador ignora cursos que están en optative+elective
  simultáneamente (PDF lista algunos en ambas columnas)

**Resultado real (Run #2 de `data/final_v428_19.sqlite`, A+C config):**
```
Fully scheduled:    82.1%  (meta ≥98%)  ❌
Required:           97.9%  (meta ≥98%)  ❌
Electivas rank-1:   55.6%  (meta ≥80%)  ❌
Balance dev:        3      (meta ≤3)    ✅
Unscheduled:        91 estudiantes
Unmet rank-1:       203
```

**Esto es información honesta que estaba enmascarada antes.** El "100%
required" anterior solo medía PE.

---

## 4. Site map — qué hay y dónde

### 4.1 Documentación maestra (raíz scheduler/)

| Archivo | Audiencia | Estado |
|---|---|---|
| `HANDOFF_NEXT_AGENT.md` | **Tú (próximo agente)** | Este archivo |
| `HANDOFF_v5.md` | Desarrollador continuando | Vigente, no incluye v4.28.x |
| `HANDOFF_v4.md` | Histórico (motor solver) | Sin actualizar |
| `MAINTENANCE_GUIDE.md` | Walkthrough del código | Sin actualizar |
| `CHANGELOG.md` | Migración v4.26 → v4.27 | Vigente, no incluye v4.28.x |
| `MANUAL_REGLAS.md` | **Coordinador del Colegio** | 13 secciones, vigente |
| `MATRIZ_DECISION.md` | **Coordinador (escoger config)** | Vigente |
| `CASO_DEMO_Y_AJUSTE.md` | **Coordinador (iterar pesos)** | Vigente |
| `COORDINATOR_QUICKSTART.md` | **Coordinador (8 pasos)** | Vigente |
| `INSTALACION.md` | IT del Colegio | Vigente |
| `DEPLOY.md` | IT (Docker/systemd/Render) | Vigente |
| `ROADMAP_v4.28.md` | Histórico (REQ-1..5) | Completado |
| `PRODUCTION_GAPS.md` | Limitaciones conocidas | Sin actualizar |
| `PROBLEMAS_DATOS_CLIENTE.md` | Issues con xlsx del cliente | Vigente |
| `DEVELOPMENT_PROPOSAL.md` | Propuesta original | Histórico |
| `README.md` | Punto de entrada | Vigente |

### 4.2 Código fuente

```
src/scheduler/
├── __init__.py
├── models.py                    Pydantic schemas (Course, Teacher, ...)
├── master_solver.py             Stage 1 (CP-SAT) — INCLUYE HC3b
├── student_solver.py            Stage 2 (CP-SAT)
├── io_csv.py                    Round-trip de los 8 CSVs canónicos
├── io_oneroster.py              Export OneRoster (legacy, no se usa)
├── ps_ingest.py                 Ingester legacy (1._STUDENTS_PER_COURSE)
├── ps_ingest_official.py        Ingester v5 — INCLUYE program_guide
├── exporter.py                  Export PowerSchool
├── reports.py                   KPIs + student_schedules_friendly.csv
├── validate.py                  Pre-solve readiness — INCLUYE PDF coverage check
├── scenarios.py                 Multi-scenario comparison
├── runner.py                    Orquestador único solve+persist
├── sample_data.py               Generador G12 sintético
├── cli.py                       CLI entry point — flag --persist
├── program_guide.py             ⭐ NUEVO v4.28.18 — loader del PDF YAML
├── persistence/
│   ├── __init__.py
│   ├── db.py                    Bootstrap + 3 schema migrations
│   ├── repo.py                  InputBundleRepo, RuleConfigRepo, RunRepo
│   └── serialize.py             Pydantic ↔ JSON + hashing
└── rules/
    ├── __init__.py
    ├── registry.py              Rule dataclass + RULE_REGISTRY
    ├── builtins.py              19 reglas builtin
    ├── compliance.py            19 checkers + dispatch
    └── custom.py                6 opcodes Phase 2 (forbid_pair, etc.)
```

### 4.3 Aplicación Streamlit

```
app.py                           ← Entry point — 10 tabs en español
.streamlit/config.toml           ← Branding y server config
start_local.sh                   ← Launcher (crea venv + arranca)
```

### 4.4 Scripts CLI

```
scripts/
├── cleanup_master_data.py       Limpia xlsx del Colegio + reporte
├── compare_runs.py              Markdown diff entre N corridas
├── simulate_success.py          Sweep de N escenarios → reporte
├── generate_executive_report.py Reporte ejecutivo 1-página
├── generate_student_reports.py  Reportes individuales por estudiante
├── generate_department_report.py Reporte por departamento
├── generate_template_xlsx.py    Plantillas xlsx descargables
├── backup_db.py                 Backup SQLite + restore
├── generate_demo_posters.py     ⚠️ legacy (no se usa)
└── section_expansion_advisor.py ⚠️ legacy (no se usa)
```

### 4.5 Datos y configuración

```
data/
├── program_guide_2026-2027.yaml ⭐ El PDF del Colegio codificado (v4.28.18)
├── templates/
│   ├── plantilla_legacy.xlsx    Plantilla formato legacy
│   └── plantilla_v5.xlsx        Plantilla formato v5
├── sample/                      Sample G12 sintético (130 estudiantes)
└── (gitignored: cleanup/, columbus*.sqlite, columbus_*.xlsx, etc.)
```

### 4.6 Tests

```
tests/                           161 tests verdes (160 + program_guide)
├── conftest.py
├── test_persistence.py          19 tests (incluye F3, F4)
├── test_rule_registry.py        12 tests
├── test_compliance.py           24 tests (incluye 6 opcodes)
├── test_runner.py                5 tests
├── test_compare_runs.py          4 tests
├── test_program_guide.py        10 tests ⭐ NUEVO v4.28.18
├── test_io_csv.py
├── test_master_solver.py
├── test_models.py               ⚠️ 1 fallo pre-existente (v4.16+)
├── test_oneroster.py
├── test_ps_ingest.py
├── test_reports_exporter.py     ⚠️ 1 fallo pre-existente (v4.16+)
├── test_sample_data.py
├── test_scenarios.py
├── test_student_solver.py
├── test_validate.py
└── test_hypothesis.py
```

### 4.7 Deploy

```
Dockerfile                       Multi-stage Python 3.12
docker-compose.yml               Compose con volumen persistente
Procfile                         Heroku-compatible
render.yaml                      Render Blueprint
.env.example                     Template env vars
```

---

## 5. Estado actual al cierre — datos clave

### 5.1 Git

```
HEAD:   f346598 v4.28.19: validador refinado — multi_electives ignora cursos
        que también son optative
Branch: claude/hardcore-lovelace-cb1284
Commits desde v4.26: 44

Working tree: clean (todo committeado)
```

### 5.2 KPIs actuales (Run #2 — config A+C)

```
Dataset: Final_schedule_master_data_hs.xlsx (509 estudiantes, 248 secciones)
Config:  coplanning OFF, peso electivas=50, balance K=5, student_time=1200s

Fully scheduled:    82.1%  (meta ≥98%)  ❌
Required:           97.9%  (meta ≥98%)  ❌  (fail por 0.1pp)
Electivas rank-1:   55.6%  (meta ≥80%)  ❌
Balance dev:        3       (meta ≤3)   ✅
Unscheduled:        91 estudiantes
Unmet rank-1:       203
```

### 5.3 Diagnóstico del estado actual

**Gap principal:** 91 estudiantes (18%) tienen al menos un curso obligatorio
sin asignar. La causa NO es capacidad insuficiente:

```
Cursos top-saturados con cap > demanda pero unmet > 0:
  Entrepreneurship  41 demanda → 50 cap   pero 28 unmet (conflictos)
  FRC 9             64 demanda → 75 cap   pero 21 unmet
  Painting II       61 demanda → 75 cap   pero 19 unmet
  Algebra I 9       57 demanda → 75 cap   pero 12 unmet
  Technology 9      65 demanda → 75 cap   pero 13 unmet
```

**Causa:** conflictos de horario entre cursos populares. Con 4,360
cursos required y solo 8 schemes posibles, ciertas combinaciones
matemáticamente no caben.

---

## 6. Pendientes

### 6.1 Pendientes inmediatos (ordenados por urgencia)

| # | Tarea | Tiempo | Por qué |
|---|---|---|---|
| 1 | **Generar zip v4.28.19** | 5 min | Cliente está esperando — no se ha enviado el último |
| 2 | **Comunicar al cliente que los KPIs cayeron** y qué significa | 0 | Decisión de comunicación: la caída de 100% → 97.9% no es un bug, es honestidad |
| 3 | Que el cliente confirme si los 20 GUIDE_warnings son data reales o errores | 0 | Bloquea iteraciones futuras |
| 4 | Que el cliente decida: ¿abrir secciones nuevas para los 5 cursos saturados? | 0 | Decisión académica, no técnica |

### 6.2 Pendientes técnicos (si el cliente sigue iterando)

| # | Tarea | Tiempo |
|---|---|---|
| A | Probar config D (coplanning ON) | 20 min |
| B | Probar config E (peso electivas 80) | 20 min |
| C | Análisis profundo de qué combinaciones de cursos generan los conflictos | 1 h |
| D | Refinar `program_guide.yaml` con los 20 warnings (¿son del YAML o del data?) | 1 h |
| E | Implementar opcodes Phase 2 restantes (cap_per_grade) | 1 día |

### 6.3 Pendientes documentación

- `HANDOFF_v5.md` está desactualizado (no incluye v4.28.x)
- `CHANGELOG.md` está desactualizado (frenó en v4.27)
- `MAINTENANCE_GUIDE.md` no menciona `program_guide.py`, `runner.py`,
  `persistence/`, `rules/`

---

## 7. Recomendaciones para el próximo agente

### 7.1 Antes de hacer cualquier cosa nueva

1. **Confirma con el usuario qué quiere hacer** antes de añadir features.
   Llevamos 44 commits sin que el cliente pruebe muchos. Cada feature
   nueva tiene rendimiento marginal decreciente.

2. **No te apures a sacar zip nuevo.** El usuario explícitamente pidió
   "no saques más paquetes, espera hasta el final o hasta que te diga".
   Espera la señal.

3. **Si el cliente reporta un bug, primero reproduce localmente.**
   El cliente reportó "se cae y se limpia todo" en una sesión —
   resultó ser memoria/timeout en su PC, no bug del motor.
   Implementé J2 (auto-save) preventivamente.

### 7.2 Reglas implícitas que descubrí trabajando con este usuario

- **Comunicación en español al cliente** (memoria persistente lo dice
  explícitamente). Internal docs/code en inglés OK.
- **Tono técnico pero claro** — no pretender ser PM ni recortar detalle
  cuando es relevante.
- **Respuestas concisas** — el usuario no quiere paseos largos.
- **Cuando le diga "sigue", no preguntes** — implementa el siguiente
  item del backlog y avanza.
- **Cuando le diga "saca zip", no negocies** — construye y entrega path.
- **Cuando termine un solve largo, espera con TaskOutput o background**
  — no chequees con polls cortos.
- **Al final de cada feature, commit explícito** con mensaje detallado.

### 7.3 Errores que cometí — no los repitas

1. **Asumí que el cliente tenía formato legacy** cuando subió v5.
   Ahora el ingester auto-detecta (D3) — no preguntar primero.

2. **Generé zip cada feature** al inicio. El usuario me dijo que parara.
   Sigue commiteando, espera para zips.

3. **Tomé "sí, has solve" literal** y corrí UN solve. La próxima vez
   que el cliente diga "haz solve" probablemente quiera ver más
   variantes — pregunta o corre con la config recomendada.

4. **No actualicé HANDOFF_v5.md ni CHANGELOG.md** durante esta sesión.
   Cuando el cliente diga "ya termina" se notará el gap.

5. **Modifiqué master_solver.py para HC3b** — riesgoso. Tests existentes
   pasaron pero no es trivial. La próxima cosa que toques en
   `master_solver.py` o `student_solver.py` requiere extra cuidado.

### 7.4 Si el cliente pide algo que parece grande

- **Phase 2 DSL completo** — 5 días, requiere extender CP-SAT
- **PowerSchool API integration** — 3-5 días con credenciales
- **Reglas condicionales (si X libre → asignar Y)** — necesita lógica
  if-then-else en el solver, refactor grande
- **Multi-school support** — actualmente está cableado a Columbus

Estas son inversiones grandes. Confirma con el usuario antes de meterte.

### 7.5 Si el cliente dice "no funciona X"

Patrón que vi múltiples veces:
1. Reproduce localmente con CLI primero (`build_dataset_from_official_xlsx`)
2. Si funciona ahí, el problema es Streamlit/UI/browser/timeout
3. Si no funciona, mira los logs `[INFO]` y `[WARN]` del ingester
4. La mayoría de "no funciona" eran formato legacy vs v5 — ahora resuelto por D3

### 7.6 Datos del Colegio — privacidad

- **NUNCA commitees xlsx con datos reales** al repo.
- `.gitignore` ya excluye `data/cleanup/`, `data/*.xlsx`, `data/*.sqlite`.
- Las plantillas en `data/templates/` SÍ están commiteadas (solo dummy data).
- Si el cliente comparte un nuevo xlsx, déjalo en `~/Downloads/` y
  trabaja con copia en `/tmp/scheduler_uploads/`.
- El reportes generados (`REPORTE_EJECUTIVO_*.md`, etc.) tienen datos
  agregados pero NO PII directa — OK para Downloads.

---

## 8. Cómo verificar que todo está OK al arrancar

```bash
cd /Users/hector/Projects/scheduler_handoff/.claude/worktrees/hardcore-lovelace-cb1284/scheduler

# 1. Tests pasan (excluyendo 2 pre-existentes)
.venv/bin/python -m pytest tests/ -q --tb=line \
  --ignore=tests/test_models.py \
  --ignore=tests/test_reports_exporter.py
# Esperado: 161 passed

# 2. App arranca
./start_local.sh
# luego abre http://localhost:8501 — deberías ver 10 tabs

# 3. Solve E2E con sample sintético (no requiere xlsx del Colegio)
.venv/bin/python -m src.scheduler.cli solve \
  --in data/sample --out /tmp/exp_test --persist \
  --master-time 15 --student-time 30
# Esperado: OPTIMAL/FEASIBLE en <2 min, exporta CSVs a /tmp/exp_test/

# 4. Solve con datos reales (si tienes el xlsx)
.venv/bin/python -c "
from pathlib import Path
from src.scheduler.ps_ingest_official import build_dataset_from_official_xlsx
ds = build_dataset_from_official_xlsx(Path('/Users/hector/Downloads/Final_schedule_master_data_hs.xlsx'))
print(f'OK: {len(ds.students)} estudiantes, {len(ds.sections)} secciones')
"
# Esperado: 'OK: 509 estudiantes, 248 secciones'
```

---

## 9. Contactos / referencias

- **Cliente:** Coordinador académico de The Columbus School (vía hekticor)
- **Usuario actual:** hector — `hekticor@gmail.com`
- **Visor estático del Colegio:** https://publicaciones.columbus.edu.co/web_resources/visor_schedules/
- **Repo:** privado, no hay GitHub remote configurado en este worktree

---

## 10. TL;DR — primeras 3 acciones del próximo agente

1. **Lee este archivo.** Después lee `HANDOFF_v5.md` para detalles
   técnicos de v4.27.x. Tiempo: 30 min.
2. **Verifica el setup** ejecutando los 4 comandos del §8.
3. **Pregúntale al usuario qué quiere hacer.** Lo más probable:
   - Generar zip v4.28.19 (5 min)
   - Comunicar resultado del solve al cliente (decisión)
   - Esperar feedback del cliente

**No empieces a programar features hasta que el usuario lo pida
explícitamente.** Llevamos 44 commits y rendimiento marginal
decreciente. Es momento de stop, ship, observe.

---

_Documento generado el 2026-05-03 por el agente saliente._
_Si encuentras algo desactualizado, actualízalo en este mismo archivo._
