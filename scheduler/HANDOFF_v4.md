# Handoff v4 — 2026-04-28

Continuación tras llenar contexto. Lee este archivo PRIMERO. No releas otros docs ni el `.jsonl` previo salvo que algo concreto te falte.

## Working dir

```
/Users/hector/Projects/handoff_2026-04-26_continuation/scheduler
```

Repo: `github.com/tognoassistant-labs/scheduler` (privado)
Último commit en `main`: `d147214` (Initial clean commit: scheduler engine + v3 bundle)

## Estado: v3 entregado, v4 en construcción

**v3 (entregado al cliente)**: `data/_client_bundle_v3/` — HC4 ok, 92% estudiantes con ≥8 cursos, datos de PS heurísticos (no canónicos).

**v4 (objetivo)**: usar el archivo oficial de PowerSchool del cliente. Este es el cambio clave. Sustituye el heurístico por el ingester canónico que lee 5 hojas reales de PS.

## Lo que está hecho en esta rama (sin commit)

```
M src/scheduler/master_solver.py     ← HC4 + home_room dentro de course_rooms
M src/scheduler/models.py            ← Teacher.max_consecutive_classes: int|None
M src/scheduler/ps_ingest.py         ← warning + per-teacher override (heurístico)
M tests/test_ps_ingest.py            ← tests para per-teacher override + HC4
?? src/scheduler/ps_ingest_official.py  ← NUEVO ingester canónico (452 líneas)
?? ../reference/columbus_official_2026-2027.xlsx  ← data canónica del cliente
?? data/columbus_full_hs_v5/, v6/    ← experimentos intermedios (puedes ignorar)
```

## El bug que se acaba de arreglar (semester double-count)

`ps_ingest_official.py` leía las asignaciones y las contaba todas, incluyendo cursos semestrales. Ortegon Valle tiene 4 AP Microeconomics (S1) + 4 AP Macroeconomics (S2) — esos son **los mismos 4 time slots** con contenido distinto por semestre, pero el modelo los trataba como 8 secciones simultáneas. Resultado: master INFEASIBLE en 0.9s.

**Fix aplicado** (línea 298 en `ps_ingest_official.py`):

```python
# Semester courses (SCHEDULETERMCODE='S1' or 'S2') are not yet modeled.
# Skip them so the semester sections don't double-count against teachers'
# max_load / HC4 / HC2.
term_code = _safe_str(a.get("SCHEDULETERMCODE"))
if term_code and term_code not in ("26-27", "2026-2027", ""):
    continue
```

**TODO real**: modelar semester properly via `Course.term` + `Section semester field`. Por ahora se omiten esas secciones — ~8 secciones perdidas en total, todas de Ortegon. El cliente está al tanto.

## Siguiente paso concreto

### 1. Verificar que master ya no es INFEASIBLE

```python
from pathlib import Path
from src.scheduler.ps_ingest_official import build_dataset_from_official_xlsx
from src.scheduler.master_solver import solve_master

ds = build_dataset_from_official_xlsx(
    Path('/Users/hector/Projects/handoff_2026-04-26_continuation/reference/columbus_official_2026-2027.xlsx')
)
print(f"{len(ds.students)} students, {len(ds.sections)} sections")
master, _, m = solve_master(ds, time_limit_s=300.0)
print(f"status: {m['status']}, assignments: {len(master)}")
```

Esperado tras el fix: `status: OPTIMAL`, ~250 assignments.

### 2. Ejecutar student solver

`from src.scheduler.student_solver import solve_students`

### 3. Empaquetar v4

Mismo formato que v3. Usar `scripts/build_client_bundle.py` (o el script que se haya usado para v3 — revisar `data/_client_bundle_v3/00_LEEME_PRIMERO.md`).

### 4. Verificar bundle

```bash
python verify_bundle.py data/_client_bundle_v4/
```

### 5. Commit + push

```bash
git add src/scheduler/ps_ingest_official.py src/scheduler/master_solver.py \
        src/scheduler/models.py src/scheduler/ps_ingest.py tests/test_ps_ingest.py
git commit -m "v4: canonical PS ingester + semester skip + HC4 + per-teacher max_consec"
git push origin main
```

## Decisiones del cliente que están pegadas

1. **Estudiante 29096 tiene 10 requests vs 9 slots**: necesita decisión sobre soft penalty para fulfillment parcial. Bloqueante para subir cobertura del 92% a >95%.

2. **Cursos semestrales**: confirmar con cliente que omitir Ortegon S1/S2 está bien para la demo del 1-mayo. Modelar properly va a Track B post-MVP.

## Reglas activas (no cambies sin pensarlo)

- HC1 — teacher conflict
- HC2 — room conflict (incluye home_room: ver fix en `master_solver.py`)
- HC2b — advisory rooms distinct (`AddAllDifferent`)
- HC3 — max consecutive classes = 4 (global)
  - Per-teacher override = 5 para 3 docentes con ≥7 secciones académicas: Sofia, Gloria, Clara
  - Modelado en `Teacher.max_consecutive_classes: int | None` (None = usar default)
- HC4 — home_room por docente (LISTADO MAESTRO single-room ⇒ home_room_id)

## Lo que NO hay que hacer

- No agregar Hall-matching constraint en master_solver. Lo intentamos, arregla MS pero rompe HS. Ver `~/.claude/.../feedback_cohort_matching_caveat.md`.
- No re-añadir auto-relax de max_consecutive a 5 global. El cliente reportó docentes con 5 bloques seguidos (Castañeda Día C). Override per-teacher es la solución correcta.
- No commitear `.venv/` ni intermedios grandes. Está en `.gitignore`.

## Ortools

Pinneado en `requirements.txt`: `ortools>=9.10,<9.13`. La 9.15 está rota en Apple Silicon (devuelve `MODEL_INVALID` en LP triviales).

## Dependencias del flujo

```
ps_ingest_official.py
  └─ build_dataset_from_official_xlsx()
       └─ master_solver.solve_master(ds)        ← HC1, HC2, HC2b, HC3, HC4
            └─ student_solver.solve_students()  ← cobertura de requests
                 └─ build_client_bundle()       ← v4 .zip
                      └─ verify_bundle.py       ← integridad SHA256
```

## Archivos canónicos vs heurísticos

- **Canónico (v4 en adelante)**: `ps_ingest_official.py` lee `reference/columbus_official_2026-2027.xlsx` (5 hojas, IDs reales de PS).
- **Heurístico (v3 y antes)**: `ps_ingest.py` lee 2 .xlsx del cliente con regex sobre nombres. Mantenido para tests legacy (`tests/test_ps_ingest.py`).

No borres `ps_ingest.py` aún. Los tests reales lo usan y nos dan una baseline de regresión.
