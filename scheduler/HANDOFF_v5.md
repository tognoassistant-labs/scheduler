# Handoff — v4.27 (App de motor de horarios) — 2026-04-30

**Lee este archivo PRIMERO** si vas a continuar el trabajo de la app. Para el motor solver puro (CP-SAT, ingest PS, exports), `HANDOFF_v4.md` sigue siendo la referencia.

## Working dir

```
/Users/hector/Projects/scheduler_handoff/.claude/worktrees/hardcore-lovelace-cb1284
```

Branch: `claude/hardcore-lovelace-cb1284`
Último commit: `v4.27.2: deploy artifacts + password gate` (más extensiones en commits siguientes)

## Qué cambió en v4.27 (resumen ejecutivo)

El motor v4.26 era un script + Streamlit en memoria. v4.27 lo convierte en una **aplicación local completa** con:

1. **BD SQLite versionada** — cada solve guarda bundle, rule_config, resultados, KPIs, compliance
2. **Registry de reglas** — 19 reglas builtin (toggles + sliders) generadas desde la UI
3. **Compliance por regla** — % cumplimiento + drill-down a violaciones (19/19 cubiertas)
4. **Tab Runs** — comparación lado-a-lado de N corridas históricas
5. **Tab Help** — explicación en español de cada regla y KPI para no-técnicos
6. **UI completa en español** — workflows, mensajes, errores, todo localizado
7. **Phase 2 hooks** — `CustomRuleSpec` con applier funcional para `forbid_pair`; otros opcodes (forbid_slot, require_room, prefer_teacher, cap_per_grade, cohort_together) están como no-op listos para implementar
8. **Deploy artifacts** — `render.yaml`, `Procfile`, `DEPLOY.md`, password gate opcional

## Arquitectura — qué se agregó

```
scheduler/
├── app.py                              # Streamlit — 10 tabs (era 6); UI 100% español
├── render.yaml + Procfile + DEPLOY.md  # Deploy a Render con disco persistente
├── .streamlit/config.toml              # Branding y server config
├── src/scheduler/
│   ├── persistence/                    # NUEVO — capa SQLite
│   │   ├── db.py                       #   connection + bootstrap + migraciones
│   │   ├── repo.py                     #   InputBundleRepo, RuleConfigRepo, RunRepo
│   │   └── serialize.py                #   Pydantic ↔ JSON + hashing
│   ├── rules/                          # NUEVO — registry de reglas
│   │   ├── registry.py                 #   Rule dataclass + RULE_REGISTRY
│   │   ├── builtins.py                 #   19 reglas builtin
│   │   ├── compliance.py               #   19 checkers + dispatch
│   │   └── custom.py                   #   CustomRuleSpec + applier Phase 2
│   ├── runner.py                       # NUEVO — orquestador único solve+persist
│   └── cli.py                          # MODIFICADO — flag --persist
└── tests/
    ├── test_persistence.py             # 19 tests
    ├── test_rule_registry.py           # 12 tests
    ├── test_runner.py                  # 5 tests
    └── test_compliance.py              # 11 tests
```

**Sin cambios:** `master_solver.py`, `student_solver.py`, `models.py`, `io_csv.py`, `ps_ingest.py`, `ps_ingest_official.py`, `exporter.py`, `validate.py`, `reports.py`. La filosofía es extender por los bordes, no reescribir.

## Schema SQLite (8 tablas)

```sql
schema_meta(version, applied_at)
input_bundle(id, label, source_kind, created_at, dataset_json, hash)
input_file(id, bundle_id FK, role, filename, content, sha256)
rule_config(id, label, created_at, hard_json, soft_json, registry_overrides_json, hash)
run(id, label, created_at, bundle_id FK, rule_config_id FK, status, master_seconds,
    student_seconds, objective, git_sha, app_version, error_message)
run_result(run_id PK FK, master_json, students_json, unmet_json)
run_kpi(run_id FK, metric, scope, key, value)  -- scope ∈ {global, rule, student, course, section, teacher}
rule_compliance(run_id FK, rule_id, satisfied, violated, pct, sample_violations_json)
```

Hashes en `input_bundle` y `rule_config` permiten dedup de contenido idéntico.

## Cómo correr

### Local (default)

```bash
cd scheduler
.venv/bin/streamlit run app.py
```

### Local con persistencia explícita

```bash
COLUMBUS_DB=/path/to/columbus.sqlite .venv/bin/streamlit run app.py
```

### CLI con persistencia

```bash
.venv/bin/python -m src.scheduler.cli solve \
  --in data/sample --out /tmp/exp \
  --persist --run-label "mi-corrida"

sqlite3 data/columbus.sqlite "SELECT id,label,objective FROM run"
```

### Deploy a Render

Ver `DEPLOY.md` — paso a paso. Recomendado: plan Starter ($7/mes) con disco persistente 1GB.

## Resultados con datos reales (Columbus xlsx v5)

Smoke test ejecutado con `/Users/hector/Downloads/schedule_master_data_hs.xlsx`:
- 509 estudiantes, 248 secciones, 67 cursos, 79 separaciones, 18 coplanning groups
- Coplanning OFF (default ON da master infeasible — comportamiento conocido v4.16)
- **Resultado:** 100% fully scheduled, 100% required, 88.5% first-choice electivas, balance dev 3
- Compliance 19/19: todas las reglas duras al 100%, soft variando entre 83.3% y 100%

### Simulación de probabilidad de éxito (2026-05-01)

`scripts/simulate_success.py` corre 6 configuraciones contra el dataset
limpio (`master_data_hs_CLEANED.xlsx`) y reporta cuántas cumplen los 4
targets v2 §10 simultáneamente.

**Probabilidad global: 50% (3/6 escenarios cumplen todos los targets).**

| Escenario | Required | Electivas | Balance | Total |
|---|---|---|---|---|
| baseline | 100% | 83.6% | 3 | ✅ |
| coplanning_hard | 100% | 82.7% | 3 | ✅ |
| **elective_boost** | 100% | 85.1% | 3 | ✅ ← recomendado |
| balance_strict | 99.8% | 77.9% | 2 | ❌ electivas |
| balance_loose | 100% | 85.7% | 4 | ❌ balance |
| lexmin | 25.2% | 98.3% | 4 | ❌ ❌ |

**Conclusiones:**
1. Coplanning ON ya NO causa infeasible con el archivo limpio — antes fallaba el master, ahora corre perfecto
2. `lexmin` colapsa required a 25% — la prioridad estricta de electivas saca a estudiantes de cursos requeridos. **No usar lexmin con datos del Colegio**
3. `balance_strict` (K=3) sacrifica electivas — el coordinador debe elegir
4. `elective_boost` (peso 50) es la mejor configuración: maximiza electivas sin romper otros targets

Hit rate por target:
- fully_scheduled ≥ 98%: **83% de los escenarios cumplen**
- required ≥ 98%: **83%**
- first_choice ≥ 80%: **83%**
- balance ≤ 3: **67%**

Reporte completo: `data/SIMULATION_REPORT.md` — runs persistidas en `data/sim.sqlite`.

## Reglas builtin (19) — agrupadas

### Hard — toggles
- `R_enforce_separations` — pares NUNCA juntos
- `R_enforce_restricted_teachers` — teachers prohibidos por estudiante
- `R_enforce_coplanning_groups` — grupos de teachers con scheme libre común

### Hard — caps numéricos
- `R_max_class_size` (default 25)
- `R_ap_research_max_size` (default 26)
- `R_max_consecutive_classes` (default 4)
- `R_max_section_spread_per_course` (default 4)
- `R_min_sections_for_balance` (default 2)

### Soft — pesos
- `R_w_first_choice_electives` (20)
- `R_w_balance_class_sizes` (8)
- `R_w_co_planning` (0)
- `R_w_grouping_codes` (4)
- `R_w_teacher_load_balance` (5)
- `R_w_teacher_preferred_courses` (3)
- `R_w_teacher_avoid_courses` (5)
- `R_w_teacher_preferred_blocks` (2)
- `R_w_teacher_avoid_blocks` (3)
- `R_w_singleton_separation` (0)
- `R_w_separation_violation` (1000)

## Pendientes / próximos pasos

### Phase 2 DSL — opcodes pendientes

`apply_custom_rules_to_dataset()` en `custom.py` solo aplica `forbid_pair` hoy. Pendientes:
- `forbid_slot` — curso X no puede dictarse en día Y bloque Z
- `require_room` — curso X solo en sala Y
- `prefer_teacher` — curso X prefiere teacher T
- `cap_per_grade` — máx N estudiantes de grado G en una sección
- `cohort_together` — lista L comparte cierto curso

Cada uno = una rama del `if/elif` en `apply_custom_rules_to_dataset` + traducción a entradas en el dataset (typically Section, behavior, locked_room, etc.). Un día de trabajo cada uno con tests.

### Datos del cliente — limpieza pendiente

Detectado en el ingest de `schedule_master_data_hs.xlsx`:
- **OZ1333**: 19 secciones planeadas, 0 generadas (no tiene teacher_assignments)
- **conselours_recommendations**: 1 student ID huérfano (no aparece en student_requests)
- **6 reglas en texto libre** en CONSTRAINTS — el ingester no las puede traducir (lógica condicional en español sobre swaps de teachers)
- **Coplanning hard hace master infeasible** — revisar si los 18 grupos son viables o si debe pasar a soft

Ver más detalle en el dialogo del 2026-04-30.

### Hardening de deploy (cuando vaya a producción)

- Backup automático de la SQLite a S3/R2 (cron en Render)
- Rate limiting con Cloudflare frente del Render
- Auth con cuentas en lugar de password único (`streamlit-authenticator`)
- Encriptación de la BD (SQLCipher) antes de FERPA review

## Cosas que NO cambiaron

- El solver CP-SAT (master + student) es idéntico a v4.26
- Los exports PowerSchool son byte-idénticos
- Los Pydantic models no se tocaron
- Los tests existentes siguen pasando (los 2 fallos en `test_models.py` y `test_reports_exporter.py` son pre-existentes desde v4.16, no causados por v4.27)

## Compatibilidad

- **CLI sin `--persist`:** comportamiento idéntico a v4.26
- **Streamlit sin `APP_PASSWORD` env var:** sin gate, igual que antes
- **Streamlit sin "Save runs to SQLite" activado:** session_state in-memory, igual que antes
- **CSVs / xlsx ingest:** sin cambios
- **PowerSchool export:** sin cambios

## Tests

```bash
.venv/bin/python -m pytest tests/test_persistence.py tests/test_rule_registry.py tests/test_runner.py tests/test_compliance.py -q
```

Esperado: 47 pass.

Suite completa (excluyendo 2 fallos pre-existentes):

```bash
.venv/bin/python -m pytest --ignore=tests/test_models.py --ignore=tests/test_reports_exporter.py -q
```

Esperado: 131 pass.
