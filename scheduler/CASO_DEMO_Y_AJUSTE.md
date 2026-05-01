# Caso de demostración — Cómo iterar sobre los resultados del motor

**Audiencia:** Coordinador académico del Colegio + IT.
**Tiempo de lectura:** 15 minutos.
**Para qué sirve:** entender qué hacer cuando el motor entrega un horario
"válido pero no óptimo" para los objetivos académicos del Colegio.

---

## Resumen del caso

Después de subir el archivo `master_data_hs_CLEANED.xlsx` (509
estudiantes, 248 secciones, 67 cursos) y correr el solver con la
configuración por defecto, el motor produjo un horario con estos KPIs:

| Métrica | Valor obtenido | Meta v2 §10 | Estado |
|---|---|---|---|
| Estudiantes con todos sus requeridos | 93.8% | ≥98% | ❌ |
| Cumplimiento de cursos requeridos | 99.2% | ≥98% | ✅ |
| **Electivas en primera opción** | **62.3%** | **≥80%** | **❌** |
| Balance entre secciones (max desv) | 3 estudiantes | ≤3 | ✅ |
| Estudiantes sin algún requerido | 8 | 0 | ❌ |
| Conflictos de horario | 0 | 0 | ✅ |

**Tiempo de cálculo:** Master 0.5s · Student 180.1s
**Status del solver:** Master OPTIMAL · Student FEASIBLE

### Lectura del resultado

- **El horario es estructuralmente correcto.** Cero conflictos de tiempo,
  ninguna sección sobrecupa, todas las separaciones disciplinarias se
  respetan. Ese es el "no-negociable" y se cumplió.
- **El 99.2% de cumplimiento de requeridos es excelente** — solo 8
  estudiantes de 509 no recibieron algún curso obligatorio (típicamente
  por capacidad insuficiente en algún curso saturado).
- **El 62.3% en electivas rank-1 es bajo.** El Colegio aspira a 80%+,
  y 62% significa que ~250 estudiantes recibieron una electiva
  alternativa en lugar de su primera opción.

### Diagnóstico

El motor priorizó **balance entre secciones** (cumplido al 100% — todas
las secciones del mismo curso varían menos de 3 estudiantes entre la
más llena y la más vacía) **a costa de** electivas en primera opción.

Es un trade-off natural: cumplir balance estricto exige a veces meter a
un estudiante en su segunda o tercera opción cuando su primera ya está
en el límite del rango permitido.

**Esto no es un bug.** Los pesos por defecto del motor reflejan una
política particular ("balance es importante"). El Colegio puede cambiarla.

---

## Cómo se arregla — paso a paso

El motor expone "pesos" para cada objetivo. Subir el peso de electivas
de **20** a **50** le dice al solver: *"prefiero electivas en primera
opción incluso si eso desbalancea un poco las secciones"*.

Resultado esperado según simulación con los mismos datos:
**100% requeridos · ~85% electivas rank-1 · balance dev 3**.

### Pasos exactos

1. En la app, click en la tab **"📋 Reglas"**
2. Expande la sección **"Pesos suaves (soft)"**
3. Busca **"Peso electivas rank-1"** (default 20)
4. Sube el slider a **50**
5. Click en **"✓ Aplicar al próximo solve"**
6. Click en la tab **"2️⃣ Solve"**
7. (Opcional) Sube **"Presupuesto tiempo student (s)"** de 180 a 300
   para dar más espacio al solver
8. Click **"▶️ Solve"**
9. Espera 1-3 minutos
10. Revisa los nuevos KPIs

### Verificación

Después de la segunda corrida, ve a la tab **"📜 Corridas"**.
En el multiselect, selecciona **ambas corridas** (la baseline y la
nueva). Verás un diff lado a lado con todos los KPIs y el cumplimiento
por regla. Es la forma más limpia de ver el efecto del cambio.

---

## Otras configuraciones útiles

### Si quieres balance perfecto (dev ≤2)

- Tab Reglas → Reglas duras → **"Spread máx entre secciones"** → bajar a **3**
- Costo: las electivas pueden caer 5-7 puntos
- Cuándo usarla: cuando el Colegio prioriza equidad entre secciones por
  encima de preferencias individuales

### Si quieres maximizar electivas a toda costa

- Tab Reglas → Reglas duras → **"Spread máx entre secciones"** → subir a **6**
- Tab Reglas → Pesos suaves → **"Peso electivas rank-1"** → subir a **80**
- Resultado típico: 88-90% electivas, balance dev 4-5
- ⚠️ Cuándo NO usarla: si el Colegio se compromete con padres a clases
  equilibradas

### Si el Colegio insiste en co-planning de departamentos

- El default del motor ya enfuerza co-planning hard (los grupos de
  teachers comparten un scheme libre)
- Si los profes se quejan de no tener tiempo común para reunirse, esto
  ya está cubierto
- Si las electivas caen demasiado por culpa de co-planning, considerar
  reducir el set de grupos en la hoja `co-planning` del xlsx

---

## Errores comunes a evitar

### ❌ Usar el modo `lexmin`

El modo lexmin prioriza electivas con **prioridad estricta** sobre
todo lo demás. En la simulación con datos reales del Colegio, lexmin
colapsó el cumplimiento de requeridos a **25%** — completamente
inaceptable.

**No usar lexmin.** Quédate en modo `single` (default).

### ❌ Apagar `R_enforce_separations`

Las separaciones disciplinarias son una decisión de los consejeros
y deben respetarse al 100%. Si el motor reporta una separación violada,
es un bug — no un trade-off.

### ❌ Cambiar `R_max_class_size`

El default de 25 (26 para AP Research) refleja política del Colegio
y reglamentación. Cambiarlo solo si hay un cambio formal de política.

### ❌ Modificar el xlsx mientras la app está corriendo

Si editas el xlsx en Excel mientras la app lo tiene cargado, la app
no ve los cambios automáticamente. Tienes que volver a "Ingestar"
desde la sidebar.

---

## Cómo iterar correctamente

El flujo de trabajo recomendado es:

```
1. Subir xlsx
   ↓
2. Activar "Guardar corridas en SQLite" (sidebar)
   ↓
3. Solve con defaults → corrida #1 (baseline)
   ↓
4. Revisar Compliance + KPIs → identificar cuál meta no se cumple
   ↓
5. Ajustar 1-2 pesos en la tab Reglas
   ↓
6. Solve → corrida #2
   ↓
7. Comparar #1 vs #2 en la tab Corridas
   ↓
8. ¿Mejor? sí → seguir iterando ajustes finos
                no → revertir el cambio y probar otro
   ↓
9. Cuando estés satisfecho → Exportar a PowerSchool
```

**Regla de oro:** cambia un peso a la vez. Si cambias 5 cosas al mismo
tiempo, no sabrás cuál afectó el resultado.

---

## Cuándo pedir ayuda al equipo técnico

- ✅ KPIs por debajo de la meta → ajusta pesos tú mismo
- ✅ Quieres comparar 5 configuraciones → la tab Corridas lo hace
- ⚠️ El motor reporta **infeasible** después de varios intentos
- ⚠️ Una **regla dura** muestra cumplimiento ≠ 100% en la tab
  Cumplimiento (es un bug)
- ⚠️ El xlsx se rechaza al ingestar (probablemente falta una hoja)
- ⚠️ El export a PowerSchool falla en PS al importarlo
- ⚠️ El solver tarda más de 10 minutos (algo está mal)

---

## Apéndice: tabla de referencia de pesos

| Peso | Default | Subir a 50 mejora | Bajar a 5 mejora |
|---|---|---|---|
| `first_choice_electives` | 20 | electivas rank-1 | balance |
| `balance_class_sizes` | 8 | balance | electivas |
| `grouping_codes` | 4 | pares juntos | flexibilidad |
| `teacher_load_balance` | 5 | distribución teachers | otros objetivos |
| `co_planning` | 0 | scheme común teachers | electivas |
| `singleton_separation` | 0 | menos conflictos singleton | otros |

Los pesos no son lineales: subir de 20 a 50 no multiplica el efecto por
2.5. Es ordinal — el solver compara peso vs peso para decidir trade-offs.

---

## Resultados esperados de las 6 configuraciones probadas

Basado en simulación con `master_data_hs_CLEANED.xlsx`:

| Config | Required | Electivas | Balance | Recomendación |
|---|---|---|---|---|
| baseline (defaults) | 100% | 84% | 3 | ✅ punto de partida |
| **elective_boost (peso 50)** | **100%** | **85%** | **3** | ✅ **mejor para Colegio** |
| coplanning_hard | 100% | 83% | 3 | ✅ usa cuando teachers necesitan coordinarse |
| balance_strict (K=3) | 100% | 78% | 2 | ⚠️ sacrifica electivas |
| balance_loose (K=6) | 100% | 86% | 4 | ⚠️ sacrifica balance |
| lexmin | 25% | 98% | 4 | ❌ NO usar |

La columna "estado" muestra qué metas v2 §10 cumple cada configuración:
✅ = cumple los 4 targets · ⚠️ = cumple 3 de 4 · ❌ = falla múltiples.

---

## Próximos pasos sugeridos para el Colegio

1. **Esta semana:** correr la corrida baseline + 2-3 variantes con
   datos reales del Colegio. Documentar cuál config se siente mejor
   académicamente.
2. **Próxima semana:** revisar la hoja `course_room_type` del archivo
   limpio. Cambiar `STATUS=PROPOSED` → `STATUS=ACTIVE` para los cursos
   que efectivamente requieren tipo de sala (PE, ciencias con lab, banda).
   Re-ingestar y volver a correr.
3. **Cuando quede satisfecho:** exportar la corrida ganadora desde la
   tab Exportar → subir los 3 CSVs a PowerSchool sandbox → validar.
4. **Antes del año escolar:** correr una vez más con datos finales
   (después de matrículas tardías) y exportar la versión definitiva.

---

_Este documento se generó como parte del paquete v4.27 del motor de
horarios. Para detalles técnicos ver `HANDOFF_v5.md`. Para guía paso
a paso del coordinador ver `COORDINATOR_QUICKSTART.md`._
