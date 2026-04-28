# Problemas de calidad de datos en archivos del cliente

**Fecha:** 2026-04-28
**Versión bundle afectada:** v4 (datos canónicos PS)
**Impacto:** retrasos en build, varias rondas de diagnóstico, fixes ad-hoc en el ingester

Este registro existe para que el cliente entienda dónde se pierde tiempo y pueda decidir si corregir el origen (PowerSchool / hojas oficiales) o si aceptamos los workarounds actuales.

---

## 1. Cursos semestrales sin distinción de término

**Archivo:** `columbus_official_2026-2027.xlsx`, hoja de asignaciones (`SCHEDULETERMCODE`)

**Problema:** Cursos como AP Microeconomics (S1) y AP Macroeconomics (S2) aparecen como **secciones distintas que comparten profesor y horario**. PowerSchool exporta:

- 4 secciones AP Micro con `SCHEDULETERMCODE='S1'`
- 4 secciones AP Macro con `SCHEDULETERMCODE='S2'`

Son **los mismos 4 time slots** (Ortegon Valle dicta Micro en agosto-diciembre, Macro en enero-junio, en las mismas horas). El motor de horarios los leía como 8 secciones simultáneas y declaraba **INFEASIBLE** en el master solve (Ortegon necesitaría 8 × 3 = 24 celdas + advisory = 25; cabría justo, pero sumado a los demás conflictos rompe).

**Síntoma:** `master INFEASIBLE in 0.9s, 0 assignments` en el solve inicial v4.

**Workaround actual (línea 303 de `ps_ingest_official.py`):** se omiten las secciones con `SCHEDULETERMCODE` que no sea `26-27` o vacío. Resultado: ~8 secciones perdidas (todas de Ortegon).

**Solución correcta:** PowerSchool debería exportar dos campos separables — uno por `term_id` (S1, S2, año completo) y otro por `period` real. El motor podría modelar `Course.term` + `Section.semester_id` y compartir slots entre S1/S2. Esto es trabajo de Track B post-MVP.

**Decisión pendiente del cliente:** ¿OK ignorar las semestrales para la demo del 1-mayo? Si no, hay que modelar semester antes — varios días de trabajo.

---

## 2. Advisory secciones presentes en datos canónicos

**Archivo:** misma hoja de asignaciones

**Problema:** PS canónico ya viene con advisory sections asignadas a profesores específicos (`ADVHS01.1`, `ADVHS01.2`, …, `ADVHS01.16`). Nuestro ingester antiguo asumía que advisory NO venía y las creaba sintéticamente — resultado: las advisory aparecían **dos veces** con IDs colisionando, sumando carga ficticia.

**Síntoma:** Clara Martinez aparecía con 10 secciones (8 académicas + advisory duplicada × 2 = 10). 10 × 3 = 30 celdas > 25 grid → master INFEASIBLE.

**Workaround actual:** el ingester ahora prefiere las advisories del PS canónico y solo sintetiza si PS no las da (líneas 410-429 de `ps_ingest_official.py`).

**Esto es bug nuestro originado por inconsistencia entre fuentes** — los archivos heurísticos (xlsx anteriores) NO traían advisory, los canónicos SÍ. Ya está arreglado.

---

## 3. Estudiante 29096 con 10 requests vs 9 slots

**Archivo:** hoja de course requests

**Problema:** El estudiante 29096 tiene 10 cursos solicitados marcados como obligatorios. El grid HS solo tiene 9 slots académicos por estudiante (5 días × ~2 períodos académicos = 9 después de quitar advisory). **Físicamente imposible** asignarle todos.

**Síntoma:** Si todos los requests son hard mandatory → solver INFEASIBLE.
Si son soft → cobertura baja para 29096 (y otros estudiantes sobreasignados).

**Workaround actual:** ALL requests están marcadas `is_required=True` (B6 directiva del cliente). Esto fuerza fulfillment total que es matemáticamente imposible.

**Decisión pendiente:**
- (a) **Soft penalty:** permitir cumplir 9/10 con penalización grande. Cobertura sube a >95% pero algunos estudiantes pierden 1 curso.
- (b) **Hard fix en datos:** cliente revisa estudiantes sobreasignados y reduce a ≤9 requests.
- (c) **Expandir grid:** agregar período (no se puede sin reabrir negociación de horarios).

Sin decisión, no podemos pasar de 92% cobertura.

---

## 4. Profesores con carga académica pigeonhole-imposible

**Archivo:** asignaciones + LISTADO MAESTRO

**Problema:** 3 profesores con ≥7 secciones académicas:
- Sofia Arcila (8 sec)
- Gloria Velez (8 sec)
- Clara Martinez (9 sec)

Con el cap HC3 global de 4 bloques consecutivos, **pigeonhole les hace imposible** caber en el grid:
- 7 secciones × 3 cells = 21 cells repartidas en 5 días → al menos un día con 5 cells consecutivas
- Con cap=4, el solver se bloquea

**Workaround actual:** override per-teacher `max_consecutive_classes=5` solo para esos 3 (línea 339 de `ps_ingest_official.py`). El resto del cuerpo docente sigue con cap global=4.

**Esto refleja una sobrecarga real de RR.HH.** Los demás profesores ya tienen carga balanceada; estos 3 están al máximo del calendario físico. El cliente debería evaluar si la carga es sostenible pedagógicamente — el motor lo permite pero el riesgo de burnout es alto.

---

## 5. Profesores con 5 bloques seguidos en horario actual (reportado por cliente)

**Reportado por cliente vía screenshot:** Castañeda con 5 bloques en Día C.

**Implicación:** el horario que actualmente corre Columbus **ya viola HC3=4 consecutivos** para algunos profesores. El motor con cap estricto rechaza esa configuración. Por eso usamos el override per-teacher en (4) en vez de relajar el cap global.

**Decisión del cliente (2026-04-28):** mantener cap global = 4, override solo para los 3 profesores estructuralmente imposibles. NO bajar el cap general a 5 porque más profesores podrían terminar con 5 bloques.

---

## 6. IDs inconsistentes (formato float)

**Archivos heurísticos (v3 y antes):** Student IDs llegaban como `28025.0` (float) en algunas columnas y `28025` (string) en otras. Esto rompía el matching entre requests y grouping rules.

**Workaround:** función `_id_str()` normaliza float → int → string en el ingester (`ps_ingest.py`).

**Síntoma original:** request IDs no overlapaban con grouping IDs → groupings ignorados.

**En el archivo canónico:** menos problema porque PS exporta con tipos consistentes, pero el normalizador se mantiene como defensa.

---

## 7. Cursos en LISTADO MAESTRO sin demanda real

**Síntoma:** algunos cursos del catálogo no tienen estudiantes que los pidan en course requests.

**Workaround actual:** se filtran cursos sin demanda al final del ingester (línea 348 de `ps_ingest_official.py`):

```python
courses = [c for c in courses if c.is_advisory or any(s.course_id == c.course_id for s in sections)]
```

**No es bloqueante**, pero indica que el catálogo está desactualizado o que falta data de inscripciones.

---

## Resumen de impacto en el cronograma

| Problema | Impacto | Estado |
|---|---|---|
| 1. Semester course duplication | 1 día de diagnóstico + workaround | Workaround OK para demo |
| 2. Advisory duplicado | 0.5 día | **Resuelto** |
| 3. Estudiante 29096 sobreasignado | Bloquea cobertura >92% | **Decisión cliente pendiente** |
| 4. Profesores estructuralmente sobrecargados | 0.5 día + override | Workaround OK |
| 5. Cap consecutivo realista | 0.5 día (override per-teacher) | Resuelto con override |
| 6. IDs como float | 0.25 día | Resuelto |
| 7. Cursos sin demanda | Cosmético | Filtrado |

**Total tiempo perdido en limpieza de datos: ~3 días.** Si los archivos vinieran limpios desde PowerSchool, este tiempo se habría usado en el solver mismo (cobertura >95%, mejor balance, soporte de semester).

## Recomendaciones al cliente

1. **Para la demo del 1-mayo:** seguir con los workarounds actuales. v4 sale con todos los fixes documentados aquí.
2. **Post-demo (Track B):**
   - Decidir política para estudiantes sobreasignados (problema 3) → desbloquea cobertura >95%.
   - Modelar cursos semestrales properly (problema 1) → recupera ~8 secciones de Ortegon.
   - Auditar carga real de Sofia/Gloria/Clara (problema 4) → posible redistribución pedagógica.
3. **Para la próxima exportación de PS:**
   - Verificar que `SCHEDULETERMCODE` sea consistente.
   - Confirmar si advisory debe venir en el export (nuestro motor ya lo soporta, ahora).
   - Revisar enrollments de estudiantes >9 requests.
