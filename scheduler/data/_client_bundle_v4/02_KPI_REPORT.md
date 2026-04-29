# Reporte de KPIs — Bundle v4

**Fecha:** 2026-04-28
**Datos:** PowerSchool canónicos (`columbus_official_2026-2027.xlsx`)
**Tiempo total de solve:** 304.0s

## Datos de entrada

| | |
|---|---|
| Estudiantes | 509 |
| Secciones | 248 |
| Profesores | 48 |
| Salones | 38 |
| Cursos | 67 |
| Requests rank-1 | 4636 |

## Resultados del solve

| | |
|---|---|
| Master status | `OPTIMAL` |
| Master assignments | 248 |
| Student status | `FEASIBLE` |
| Estudiantes asignados | 509/509 |
| Requests no satisfechos | 351 |
| **Cobertura** | **92.4%** |

## KPI breakdown

```
## KPI vs v2 §10 targets

| Metric | Value | Target | Met |
|---|---|---|---|
| Fully scheduled students | 41.5% | ≥98% | ❌ |
| Required course fulfillment | 92.4% | ≥98% | ❌ |
| First-choice electives | 0.0% | ≥80% | ❌ |
| Section balance (max dev from mean) | 4 students | ≤3 | ❌ |
| Unscheduled (missing required) | 298 | 0 | ❌ |
| Time conflicts | 0 | 0 | ✅ (enforced by solver) |
```

## Cambios v4 vs v3

- **Ingester canónico** (`ps_ingest_official.py`) reemplaza al heurístico. Lee 5 hojas del xlsx canónico de PS con IDs reales.
- **Fix:** advisory sections deduplicadas (PS canónico ya las trae).
- **Fix:** cursos semestrales (S1/S2) omitidos para evitar double-count en Ortegon.
- **Soft penalty** en student_solver para required courses — antes era hard `==1`, ahora con slack penalizado. Permite cobertura parcial cuando el grid no alcanza (estudiante 29096: 10 requests vs 9 slots).

## Problemas de datos del cliente

Ver `PROBLEMAS_DATOS_CLIENTE.md` en la raíz del repo. ~3 días perdidos en limpieza.

## Decisiones del cliente pendientes

1. **Cursos semestrales** (Ortegon): ¿OK omitir para demo, modelar properly post-MVP?
2. **Estudiantes sobreasignados** (29096 con 10 requests): ¿soft penalty es aceptable o hay que reducir requests en origen?
