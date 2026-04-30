# Reporte de KPIs — Bundle v4

**Fecha:** 2026-04-28
**Datos:** PowerSchool canónicos (`columbus_official_2026-2027.xlsx`)
**Tiempo total de solve:** 303.7s

## Datos de entrada

| | |
|---|---|
| Estudiantes | 483 |
| Secciones | 248 |
| Profesores | 48 |
| Salones | 38 |
| Cursos | 67 |
| Requests rank-1 | 4398 |

## Resultados del solve

| | |
|---|---|
| Master status | `OPTIMAL` |
| Master assignments | 248 |
| Student status | `FEASIBLE` |
| Estudiantes asignados | 483/483 |
| Requests no satisfechos | 203 |
| **Cobertura** | **95.4%** |

## Rules relaxed in this run

Each row below documents a school rule the engine had to relax to produce a feasible schedule. Machine-readable copy: `applied_relaxations.csv` at the bundle root.

| Rule | Requested | Applied | Severity | Affected | Reason |
|---|---|---|---|---|---|
| `max_consecutive_classes` | 4 | 5 | policy_override | 1 entit(y/ies) | Pigeonhole-infeasible at strict 4: each affected teacher carries ≥7 academic sections × 3 meetings/week vs only 5 blocks/day, so a 5-in-a-row stretch is unavoidable for at least one day. |


## Unmet — distribution by reason

| Reason | Count |
|---|---|
| `grid_clash` | 198 |
| `separation` | 3 |
| `unknown` | 2 |

## KPI breakdown

```
## KPI vs v2 §10 targets

| Metric | Value | Target | Met |
|---|---|---|---|
| Fully scheduled students | 100.0% | ≥98% | ✅ |
| Required course fulfillment | 100.0% | ≥98% | ✅ |
| First-choice electives | 93.5% | ≥80% | ✅ |
| Section balance (max dev from mean) | 14 students | ≤3 | ❌ |
| Unscheduled (missing required) | 0 | 0 | ✅ |
| Time conflicts | 0 | 0 | ✅ (enforced by solver) |
```

## Cambios v4 vs v3

- **Ingester canónico** (`ps_ingest_official.py`) reemplaza al heurístico. Lee 5 hojas del xlsx canónico de PS con IDs reales.
- **Fix:** advisory sections deduplicadas (PS canónico ya las trae).
- **Fix:** cursos semestrales (S1/S2) omitidos para evitar double-count en Ortegon.
- **Soft penalty** en student_solver para required courses — antes era hard `==1`, ahora con slack penalizado. Permite cobertura parcial cuando el grid no alcanza (estudiante 29096: 10 requests vs 9 slots).
- **Per-unmet diagnostic** (Principle 5): `unmet_requests.csv` ahora incluye una columna `reason` clasificando cada caso (capacity / grid_clash / separation / restriction / no_section). Resumen en `unmet_diagnosis.md`.
- **Audit trail de relajaciones** (Principle 7): cada vez que el engine relaja una regla del colegio, queda registrado en `applied_relaxations.csv` y en la sección "Rules relaxed in this run" arriba.

## Problemas de datos del cliente

Ver `PROBLEMAS_DATOS_CLIENTE.md` en la raíz del repo. ~3 días perdidos en limpieza.

## Decisiones del cliente pendientes

1. **Cursos semestrales** (Ortegon): ¿OK omitir para demo, modelar properly post-MVP?
2. **Estudiantes sobreasignados** (29096 con 10 requests): ¿soft penalty es aceptable o hay que reducir requests en origen?
