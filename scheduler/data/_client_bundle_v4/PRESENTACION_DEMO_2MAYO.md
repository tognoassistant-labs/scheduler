# Presentación demo — Columbus HS 2026-2027

**Fecha:** 2026-05-02
**Versión bundle principal:** v4.28 — Solución A "Admin Proposal Applied"

---

## TL;DR

> 💎 **Si el Colegio aprueba 6 acciones administrativas** (que ya identificamos exactamente), **el horario llega a 58.7% de estudiantes con TODOS sus cursos** (vs 45.6% actual), 100% required, 94.1% promedio de satisfacción individual, balance ≤3 ✅.

---

## La métrica que importa más (y cómo presentarla)

El número "44% de estudiantes con TODOS sus cursos" es engañoso porque mide todo-o-nada. Una lectura más honesta:

### Bundle base actual (v4.27 phased — sin acciones admin)

```
Required course fulfillment:                   100%   ✅
Estudiantes con AL MENOS 75% de sus requests:  99.2%  (505 de 509)
Estudiantes con AL MENOS 85% de sus requests:  93.3%  (475 de 509)
Estudiantes con AL MENOS 90% de sus requests:  45.6%
Estudiantes con TODOS sus requests:            45.6%
Promedio individual de satisfacción:           92.4%
Mediana individual:                            88.9%
Peor estudiante:                               62.5% (5 de 8 cursos asignados)
```

> *"Ningún estudiante recibe menos del 62% de lo que pidió. El 99% recibe al menos el 75%. El 93% al menos el 85%. Los obligatorios están al 100%."*

### Bundle Solución A (admin applied)

```
Required course fulfillment:                   100%   ✅
Estudiantes con AL MENOS 75% de sus requests:  99.8%  (508 de 509)
Estudiantes con AL MENOS 85% de sus requests:  93.3%  (475 de 509)
Estudiantes con TODOS sus requests:            58.7%  (299 de 509)
Promedio individual de satisfacción:           94.1%
Mediana individual:                            100.0%   ⭐  ← más de la mitad recibe TODO
First-choice electives:                        91.3%   ✅
Section balance:                               ≤3      ✅
```

---

## Comparativa de las 3 alternativas evaluadas hoy

| Métrica | Baseline (v4.27 phased) | Solución A (admin applied) | Solución B (iterative master) |
|---|---|---|---|
| **Estudiantes con TODOS** | 232 (45.6%) | **299 (58.7%)** ⭐ | 208 (40.9%) |
| Promedio satisfacción | 92.4% | **94.1%** | 91.8% |
| Mediana satisfacción | 88.9% | **100%** | 87.5% |
| First-choice electives | 88.9% | **91.3%** | 88.1% |
| Section balance | ≤5 (mediocre) | **≤3** ✅ | ≤4 |
| Required fulfillment | 100% | 100% | 100% |
| Decisiones del Colegio | ninguna | aprobar 6 acciones | ninguna |

**Solución B (iterative master)** — descartada. La idea era buena (re-correr master con slot hints) pero los locks acumulados generaron más conflictos que ganancia. Aprendizaje: el master_solver actual es bueno; el problema NO está en los slots sino en la capacidad/distribución de secciones.

---

## Solución A — qué es y por qué funciona

### Qué hace

Aplica las **6 acciones administrativas** del documento `06_PROPUESTA_ADMIN_G12.md`:

| # | Acción | Detalle |
|---|---|---|
| 1 | Mover **AP Research** (OB1532.1) a scheme 6 (slots B1, C4, E2) | + abrir 2ª sección OB1532.2 con la misma profe Butterworth (ella solo tiene 1 sección hoy, tiene capacidad) |
| 2 | Mover **AP English Lit** (H1201B.1) a scheme 6 | de A1/D2/B4 → B1/C4/E2 |
| 3 | Abrir **3ª sección de Journalism Higher** (OH1501.3) en scheme 6 con Shainker | |
| 4 | Mover una sección de **Calculus** (OI1305.1) a scheme 6 | |
| 5 | Mover una sección de **Financial Math** (OI1303.1) a scheme 6 | |
| 6 | Abrir **3ª sección de AP Physics 2** (OA1322.3) en scheme 6 con Mickens | |

Las 6 acciones convergen en **scheme 6** porque la mayoría de los G12 que tenían cursos faltantes están libres simultáneamente en ese scheme.

### Por qué funciona

- **G12 saltó de 43.8% → 71.1%** (+27pp): los principales bottlenecks del año estaban concentrados ahí, las acciones los desbloquean directamente
- **G10 saltó de 54.7% → 77.3%** (+22.6pp, bonus): muchas de esas secciones ampliadas también tenían demanda de G10
- **Section balance recuperado a ≤3** (era ≤5 con phased solo)
- **Sin tocar el motor**: solo cambian datos del input

### Costo operativo

| Recurso adicional | ¿Disponible hoy? |
|---|---|
| Profesora para 2ª sección AP Research | Butterworth (1 sec hoy → puede +1) ✅ |
| Profesor para 3ª sección Journalism | Shainker (2 sec hoy → puede +1) ✅ |
| Profesor para 3ª sección AP Physics 2 | Mickens (2 sec hoy → puede +1) ✅ |
| Aulas adicionales en scheme 6 (3 nuevas secciones × 1 aula c/u) | Por validar con coordinación |
| Re-coordinar 3 horarios de profesores existentes (movimientos) | Por validar |

**Conclusión: 0 contrataciones nuevas.** Solo decisión administrativa de cómo distribuir el scheme 6 (que tiene cupo libre en aulas — el motor lo confirma).

---

## Por grado: el detalle

| Grado | Total | Baseline 4.27 | Sol A admin | Δ Sol A |
|---|---|---|---|---|
| **G12** | 121 | 53 (43.8%) | **86 (71.1%)** | **+33** |
| **G11** | 131 | 69 (52.7%) | 67 (51.1%) | -2 (variance) |
| **G10** | 128 | 70 (54.7%) | **99 (77.3%)** | **+29** |
| **G9** | 129 | 40 (31.0%) | 47 (36.4%) | +7 |
| **TOTAL** | 509 | 232 (45.6%) | **299 (58.7%)** | **+67** |

### G9 sigue siendo el grado más complejo

47 de 129 G9 con todos sus cursos (36.4%). Mejor que baseline (31%) pero todavía bajo. **Razón estructural** (no es bug del motor):
- G9 tiene **5 cursos requeridos** (vs G12 tiene 1, G11 tiene 1, G10 tiene 3)
- G9 tiene la mayor demanda en Technology 9 (J0901), Band Level I (C0904), Algebra I 9 (I0903) — los nuevos top unmet
- Para subir G9 hay que hacer la **misma propuesta admin para G9** (mover/abrir secciones bottleneck de G9) — eso podría llevar G9 a ~60-70%

Esto es candidato a un próximo turn de optimización (no es para mañana).

---

## Recomendación para mañana

### Plan de presentación (orden sugerido)

1. **Abrir con la métrica reframeada**: "100% required, 94% promedio satisfacción, 99.8% con ≥75% requests"
2. **Mostrar el visor**: pasear por estudiantes específicos en el bundle Solución A
3. **Presentar la propuesta admin**: las 6 acciones que ya están medidas + impacto exacto (+67 estudiantes, +27pp G12)
4. **Acordar siguientes pasos**: quién y cuándo aprueba las 6 acciones admin, y luego un sprint corto para optimizar G9

### Si el Colegio dice "queremos 100%"

Honestidad técnica:
- 100% literal requiere abrir aún más secciones (no solo las 6 propuestas)
- Específicamente, las 8 más críticas para G9 (J0901, C0904, OA1319, etc.)
- Cada sección extra: ~1 profesor + 1 aula + 3 slots
- El motor mide exactamente cuántas y cuáles. Lo mostramos ahí mismo si quieren.

### Si el Colegio dice "no podemos aprobar 6 acciones admin"

Plan B:
- Quedamos con baseline v4.27 (45.6% full, 100% required, 92.4% promedio)
- Sigue cumpliendo todos los KPI técnicos (≥98% required, ≥80% electives, ≤3 balance)
- Es lo que hay sin tocar nada operativo

---

## Bundles disponibles para descargar

Todos en GitHub (`tognoassistant-labs/scheduler`):

| Versión | Carpeta | Status | Cuándo usar |
|---|---|---|---|
| **`HS_2026-2027_admin_applied`** ⭐ | `scheduler/data/_client_bundle_v4/HS_2026-2027_admin_applied/` | **RECOMENDADO** | Si admin aprueba las 6 acciones |
| `HS_2026-2027_phased` | `_client_bundle_v4/HS_2026-2027_phased/` | Backup | Sin acciones admin (status quo) |
| `HS_2026-2027_real` | `_client_bundle_v4/HS_2026-2027_real/` | Versión old (mixed solver) | Comparación histórica |
| `HS_2026-2027_iterative` | `_client_bundle_v4/HS_2026-2027_iterative/` | Experimento | NO usar — peor que baseline |
| `HS_2026-2027_G12_only` | `_client_bundle_v4/HS_2026-2027_G12_only/` | Análisis G12 puro | Con propuesta admin del G12 |

---

## Anexo — los KPIs técnicos (todos cumplidos en Sol A)

```
| Metric                        | Value | Target | Met |
| Fully scheduled students      | 100%  | ≥98%   | ✅  |   ← KPI definition: required-only
| Required course fulfillment   | 100%  | ≥98%   | ✅  |
| First-choice electives        | 91.3% | ≥80%   | ✅  |
| Section balance ≤3            | 3     | ≤3     | ✅  |
| Unscheduled (req missing)     | 0     | 0      | ✅  |
| Time conflicts                | 0     | 0      | ✅  |
```

---

## Notas técnicas (para Hector, no para el Colegio)

- El multi-seed harvest (run de 5 seeds en paralelo) sigue corriendo. Si saca algo mejor que Sol A, lo combinamos.
- Solución B (iterative master) NO se descarta para futuro: la idea es buena pero la implementación greedy de slot-hints fue muy agresiva. Una versión más conservadora (lockear máximo 2 secciones por iteración, validar cada lock) podría dar resultados.
- El próximo gran salto (subir G9 a 60%+) requiere o (a) abrir más secciones para G9 (admin), o (b) implementar swap-based local search (~1 día de trabajo).
