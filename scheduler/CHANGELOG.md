# Changelog

## v4.27 — Aplicación local con persistencia (2026-04-30 → 2026-05-01)

Convierte el motor v4.26 (script + Streamlit en memoria) en una
aplicación local completa con histórico versionado, reglas
configurables desde la UI, y compliance por regla. **Sin tocar el
solver, los modelos, o los exports — extiende por los bordes.**

### Nuevas capacidades para el coordinador

- **App local con auth opcional** — Streamlit con 10 tabs, gate de
  password via `APP_PASSWORD` env var
- **Persistencia SQLite** — cada solve queda guardado con sus inputs,
  config de reglas, resultados, KPIs y compliance. Comparable después
- **Editor de reglas en UI** — toggles para reglas duras + sliders
  para pesos suaves, generados desde el registry
- **Compliance por regla** — 19 reglas medidas, drill-down a violaciones
- **Diff lado a lado de N corridas** — selecciona varias en la tab
  Corridas y ve el efecto de cambios
- **Restore de corridas históricas** — re-exporta cualquier corrida
  pasada sin re-correr el solver
- **UI 100% en español** — flujos, mensajes, errores
- **Tab Ayuda** — explicación de cada regla y KPI para no-técnicos

### Nuevas capacidades para IT

- **CLI extendido** — flag `--persist` en `solve` para uso programático
- **Deploy artifacts**:
  - `Dockerfile` multi-stage + `docker-compose.yml`
  - `render.yaml` blueprint
  - systemd unit doc en `DEPLOY.md`
  - `.streamlit/config.toml` para branding
- **Cleanup script** — `scripts/cleanup_master_data.py` toma un xlsx
  del Colegio y produce versión limpia + reporte de diff
- **Sweep de simulación** — `scripts/simulate_success.py` corre N
  configuraciones y reporta probabilidad de éxito
- **Comparación de corridas CLI** — `scripts/compare_runs.py` genera
  markdown diff entre N runs persistidos

### Nuevas capacidades para desarrolladores

- **Registry de reglas** — `src/scheduler/rules/` con 19 reglas
  builtin, cada una con metadata (label, kind, default, bounds)
- **Phase 2 DSL — 6 opcodes implementados:**
  - `forbid_pair` — pares de estudiantes nunca juntos
  - `forbid_slot` — teacher no puede dictar en cierto bloque
  - `require_room` — curso solo en sala específica
  - `require_room_type` — curso solo en salas tipo X (gym, lab, etc.)
  - `prefer_teacher` — estudiante con teacher específico para un curso
  - `cohort_together` — lista de estudiantes comparte secciones
- **Compliance dispatch** — 19 checkers por regla con dispatch automático
- **Runner unificado** — `runner.py` es el seam único solve+persist
  usado por CLI y app

### Schema SQLite (8 tablas)

```
input_bundle, input_file, rule_config, run, run_result,
run_kpi, rule_compliance, schema_meta
```

### Documentación nueva

| Archivo | Audiencia |
|---|---|
| `LEEME_PRIMERO.md` | Primera lectura |
| `INSTALACION.md` | Cómo instalar |
| `COORDINATOR_QUICKSTART.md` | Coordinador, 8 pasos |
| `CASO_DEMO_Y_AJUSTE.md` | Cuando KPIs están bajos |
| `MATRIZ_DECISION.md` | Cuál config escoger |
| `HANDOFF_v5.md` | Doc técnica completa |
| `DEPLOY.md` | Despliegue (Docker/systemd/Render) |
| `CHANGELOG.md` | Este archivo |

### Tests nuevos

- `tests/test_persistence.py` — 19 tests
- `tests/test_rule_registry.py` — 12 tests
- `tests/test_runner.py` — 5 tests
- `tests/test_compliance.py` — 24 tests
- `tests/test_compare_runs.py` — 4 tests

**Total v4.27 tests: 64 verdes.**

### Compatibilidad — qué NO cambió

- `master_solver.py`, `student_solver.py` — sin cambios
- `models.py` — sin cambios (Pydantic schemas estables)
- `io_csv.py`, `ps_ingest.py`, `ps_ingest_official.py` — sin cambios
- `exporter.py` — sin cambios (PowerSchool exports byte-idénticos)
- `validate.py`, `reports.py` — sin cambios
- CLI sin `--persist` se comporta idéntico a v4.26
- Streamlit sin `APP_PASSWORD` se comporta idéntico (sin gate)
- Tests existentes siguen pasando (los 2 fallos en `test_models.py` y
  `test_reports_exporter.py` son pre-existentes desde v4.16)

### Validación con datos reales del Colegio

Smoke test con `schedule_master_data_hs.xlsx`:
- 509 estudiantes, 248 secciones, 67 cursos
- Solve OPTIMAL/FEASIBLE en 124s (config baseline)
- Cumplimiento: 100% required, 83.9% electivas rank-1, balance dev 3

Simulación de 9 configuraciones (`scripts/simulate_success.py`):
- Probabilidad de éxito (4 targets v2 §10): 50% (3/6) en sweep básico
- Mejor configuración: **`elective_boost`** (peso electivas=50)
- Anti-patrón confirmado: **`lexmin` colapsa required a 25%** — NO usar

### Roadmap pendiente (no implementado en v4.27)

- **Reglas condicionales** (Phase 3) — "cuando teacher X libre,
  asignar Y a Z". Requiere DSL más rico
- **Solve multi-grado simultáneo** — actualmente cada grado se
  resuelve por separado
- **Auth con cuentas SSO** — actualmente solo password compartido
- **Backup automático de SQLite a S3/NAS** — manual via cron
- **PowerSchool API directo** — actualmente vía export xlsx
- **Sugerencias automáticas** — *"el solver no pudo X, prueba Y"*

---

## v4.26 — baseline (2026-04-29)

Ver `HANDOFF_v4.md` para el motor solver original. Sin cambios.

---

## Cómo migrar de v4.26 a v4.27

**No hay migración rota.** Si tu instalación es v4.26:

1. Reemplaza el directorio `scheduler/` con la versión v4.27
2. Re-instala dependencias: `.venv/bin/pip install -r requirements.txt`
   (agrega solo `streamlit-authenticator` opcional, todo lo demás ya
   estaba)
3. (Opcional) Activa persistencia añadiendo `--persist` al CLI o
   marcando "Guardar corridas en SQLite" en la app
4. (Opcional) Pon `APP_PASSWORD=...` para activar gate

Datos viejos (CSVs, exports antiguos) siguen funcionando intactos. La
SQLite arranca vacía y se llena con corridas nuevas.
