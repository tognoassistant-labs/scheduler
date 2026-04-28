# Handoff — Estado al 2026-04-28 fin de día

**Lee este archivo PRIMERO.** No releas otros docs salvo que algo concreto te falte.

## Working dir

```
/Users/hector/Projects/handoff_2026-04-26_continuation/scheduler
```

Repo: `github.com/tognoassistant-labs/scheduler` (privado)
Último commit: `cee2590` — "v4.2: course_relationships (Simultaneous merge)"

## Estado actual

| Versión | Fecha | Cobertura | Estado |
|---|---|---|---|
| v3 | 2026-04-26 | 92% | Entregado al cliente (slugs internos) |
| v4 | 2026-04-28 mañana | 94.6% | Canonical PS data + soft penalty |
| v4.1 | 2026-04-28 mediodía | 94.6% | PS import spec compliance |
| **v4.2** | **2026-04-28 tarde** | **94.8%** | **Simultaneous merge — último entregado** |
| v4.3 | PENDIENTE | objetivo 97%+ | Ver "Próximos pasos" abajo |

Bundle entregable: `data/_client_bundle_v4/` (verify_bundle PASS).

## Lo que se hizo en v4.2

1. **Simultaneous course relationships** (6 de 7 del archivo del cliente):
   - Spanish FL: Clara dicta G0902+G1204+G1205+G1206 en 1 sección física (no 4).
   - Sofia: AP 2D+3D Art (1 combo), Drawing I+II (1), Sculpture I+II (1).
   - Clara bajó 9→5 sections, Sofia 8→6.
2. Modelo: `Section.linked_course_ids` + `Course.simul_group`.
3. Ingester lee `reference/course_relationships.csv` (csv local con las 7 relaciones).
4. Exporter emite N filas por sección combinada (1 por curso cubierto, sharing teacher/room/expression).
5. verify_bundle dedupea por `Section_ID_Internal` para no falsa alarma.

## Próximos pasos (v4.3) — orden de impacto

### 1. Term-paired sections (AP Micro/Macro de Ortegon)

**Objetivo:** recuperar las 8 secciones de Ortegon (4 Micro S1 + 4 Macro S2) que están omitidas hoy.

**Estado del código:** preparado pero defer.
- `Section.term_id` model field existe (None=year-long, "3601"=S1, "3602"=S2).
- `Course.term_pair` model field existe.
- Ingester ya tiene la lógica de TERM_CODE_TO_ID y la branch para emitirlas con term_id correcto, pero está comentada.
- Master_solver tiene `_term_partition` helper y partitioning HC1/HC2 ya implementado.

**Bug bloqueante:** cuando se emiten las 8 sections, el master da INFEASIBLE en 2s. Confirmado que NO es HC1, NO es HC2, NO es HC3 (ni con cap 8). El bug está en alguna interacción entre:
- Global `scheme_count` balance constraint (master_solver línea ~257-260)
- HC4 home_room pinning (todas las 9 academic de Ortegon → room 5)
- min_distinct_schemes constraint (línea ~290)

**Pista:** con 1+1 Micro/Macro funciona, con 3+3 funciona, con 4+4 falla. Probable que el balance estricto fuerce Micros y Macros a schemes distintos cuando deberían poder compartir.

**Próximo intento:** contar pair_overlap en sumar global de scheme_count tratando S1+S2 como 1 cell efectiva.

**Archivos a tocar:**
- `src/scheduler/ps_ingest_official.py` líneas ~310-325 (descomentar el branch term_id)
- `src/scheduler/master_solver.py` líneas ~250-265 (refinar scheme balance)

### 2. Coplanning constraint (13 grupos)

**Objetivo:** parejas/tríos de profesores deben compartir un esquema libre simultáneo (regla del doc Reglas Horarios HS 2026-04-22).

**Datos:** `reference/rfi_1._STUDENTS_PER_COURSE_2026-2027.xlsx` hoja `CO PLANNING INFO`. 13 grupos prioritarios + más en orden de importancia.

**Plan:**
1. Crear helper `_read_coplanning_groups(xlsx_path)` en ingester que devuelva `list[list[str]]` de teacher_dcid_groups.
2. Agregar `Dataset.coplanning_groups` o pasar como parámetro al solver.
3. En `master_solver.py`, agregar constraint: para cada grupo, ∃ scheme tal que TODOS los teachers están libres en ese scheme.
4. Empezar con HARD constraint; si causa INFEASIBLE, downgrade a SOFT con penalty.

**Profesores "New X Teacher" en la hoja**: son placeholders del cliente (no contratados aún). Filtrarlos del grupo si no están en `ds.teachers`.

### 3. Archivo nuevo de Juan (cursos por estudiante)

**Sheet ID:** `1k_6BUOOAL2UEOjjfznYXVw9LY5NXFlABu8KxPFkr3h0`
**Tamaño:** 60kb (≈ 60,000 chars de output) — leer por chunks con offset/limit.

**Hipótesis:** sustituye o complementa la hoja `requests` del canónico con la lista autoritativa "qué debe ver cada estudiante". Confirmar primero contenido leyendo primeras filas.

**Ruta sugerida:**
```python
mcp__bfd7cab6-..__read_file_content(fileId="1k_6BUOOAL2UEOjjfznYXVw9LY5NXFlABu8KxPFkr3h0")
# → output too large, persistido en file
# Read with offset+limit to scan structure
```

## Decisiones del cliente que están pegadas

1. **Estudiante 29096 con 10 requests**: ¿bajan a ≤9 en origen o aceptan cobertura parcial 94.8%?
2. **Sofía/Gloria/Clara override max_consec**: ¿reducen carga en origen o mantienen override?
3. **Demo 1-mayo**: ¿se muestra v4.2 actual o esperan v4.3 con term/coplanning?

## Reglas activas (no cambies sin pensarlo)

- HC1 — teacher conflict (term-aware partition implementado pero no activado)
- HC2 — room conflict (idem)
- HC2b — advisory rooms distinct
- HC3 — max consecutive 4, override 5 per-teacher si ≥7 secciones
- HC4 — home_room por profesor (LISTADO MAESTRO)

## Reglas que NO existen aún (pendientes)

- **Coplanning** (13 grupos) — datos disponibles, falta código.
- **Term sharing** (Micro/Macro) — código preparado, falta arreglar scheme balance.

## Lo que NO hay que hacer

- No agregar Hall-matching constraint en master. Lo intentamos antes; arregla MS pero rompe HS.
- No re-añadir auto-relax de max_consecutive a 5 global.
- No commitear `.venv/`, intermedios grandes, ni el archivo `course_relationships.csv` con datos sensibles del cliente.
- No borrar `ps_ingest.py` (el heurístico) — los tests legacy lo usan.

## Files de referencia rápida

- `reference/columbus_official_2026-2027.xlsx` — canonical PS export (5 sheets)
- `reference/course_relationships.csv` — 7 relaciones (Simultaneous + Term)
- `reference/rfi_1._STUDENTS_PER_COURSE_2026-2027.xlsx` — tiene `CO PLANNING INFO` sheet
- `PROBLEMAS_DATOS_CLIENTE.md` — registro detallado de los issues acumulados

## Comandos útiles

```bash
# Re-build bundle v4.2 desde scratch (4-5 min):
cd /Users/hector/Projects/handoff_2026-04-26_continuation/scheduler
.venv/bin/python build_v4_bundle.py

# Verify bundle:
cd data/_client_bundle_v4 && python3 verify_bundle.py .

# Quick ingest test sin solve:
.venv/bin/python -c "
from pathlib import Path
from src.scheduler.ps_ingest_official import build_dataset_from_official_xlsx
ds = build_dataset_from_official_xlsx(Path('../reference/columbus_official_2026-2027.xlsx'))
print(f'students={len(ds.students)} sections={len(ds.sections)}')
"
```

## Cómo arrancar la próxima sesión

```
cd /Users/hector/Projects/handoff_2026-04-26_continuation/scheduler
lee HANDOFF_v4.md

continúa con v4.3 — primero arregla bug Term en master_solver:
debug por qué con 4 Micro + 4 Macro de Ortegon el master da INFEASIBLE.
Pista: probablemente scheme_count balance fuerza spread entre Micro/Macro.
```
