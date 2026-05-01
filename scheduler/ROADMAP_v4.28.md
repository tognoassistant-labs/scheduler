# Roadmap v4.28 — mejoras solicitadas por el cliente

**Estado:** captura de requirements (2026-05-01) — pendiente de implementar.

Notas tomadas de feedback del coordinador del Colegio durante la
prueba con `rfi_1._STUDENTS_PER_COURSE_2026-2027.xlsx`. Cada
requirement abajo tiene contexto, propuesta técnica, y estimado.

---

## REQ-1 — Selector de grados más flexible

### Lo que pidió el cliente

> "Dar la opción de hacer otros grados, 9º y 10º por ejemplo o tres grados."

### Estado actual (v4.27.15)

La UI ya tiene 3 modos:
- "Un grado" (number_input)
- "Todo HS (9-12)" (auto)
- "Selección personalizada" (multiselect)

### Lo que probablemente quería decir

El cliente NO sabía que el modo "Selección personalizada" ya hace
exactamente eso. Es un problema de **descubribilidad**, no de
funcionalidad faltante.

### Propuestas

**Opción A — más visible y didáctica (recomendada)**

Reemplazar el radio actual por **3 botones-rápido** + multiselect
siempre visible:

```
Grados a incluir
[9-12 (todo HS)]  [11-12 (último ciclo)]  [9-10 (primer ciclo)]
☑️ G9  ☑️ G10  ☑️ G11  ☑️ G12   ← checkboxes individuales debajo
```

Click en un botón rápido = pre-marca esos grados en los checkboxes.
El usuario ve siempre qué grados están seleccionados (no escondidos
detrás de "Selección personalizada").

**Opción B — preset dropdown**

Un solo dropdown con presets nombrados:
- "Solo G12 (último año)"
- "G11-G12 (últimos dos años)"
- "G9-G10 (primer ciclo HS)"
- "G9-G10-G11 (sin G12)"
- "Todo HS (G9-G12)"
- "Personalizado..."

Más limpio pero menos flexible.

### Esfuerzo estimado

- Opción A: 30 min (cambios solo en `app.py`)
- Opción B: 20 min

**Recomiendo A** porque expone mejor la flexibilidad.

---

## REQ-2 — Mostrar el archivo que se montó con su ruta

### Lo que pidió el cliente

> "Que muestre el archivo que se montó con ruta."

### Estado actual (v4.27.15)

Parcialmente implementado en v4.27 — al subir un archivo, aparece:

```
📁 Demanda en disco: `/tmp/scheduler_uploads/<archivo>.xlsx` (557,309 bytes)
```

Pero solo aparece en el sidebar al subir, no se preserva una vez
ingresado el dataset (después de "Ingestar").

### Propuesta

Añadir una **sección permanente "📂 Archivos cargados"** en la tab
Inputs que muestre, después de ingestar:

```markdown
## 📂 Archivos cargados

| Rol | Archivo | Path completo | Tamaño | SHA256 |
|---|---|---|---|---|
| Demanda | rfi_1._STUDENTS_PER_COURSE_2026-2027.xlsx | /tmp/scheduler_uploads/... | 557 KB | a94e... |
| Schedule | rfi_HS_Schedule_25-26.xlsx | /tmp/scheduler_uploads/... | 1.0 MB | b8c1... |

✅ Última ingesta: 2026-05-01 17:35:42 UTC
```

Esto le da al coordinador trazabilidad: "¿qué versión del xlsx
generó esta corrida?".

### Bonus: vincular esto con la BD

En la tabla `input_bundle` ya guardamos hashes y filenames. Mostrar
los archivos del bundle activo como parte de la metadata de
cualquier corrida en la tab Corridas.

### Esfuerzo estimado

- Display básico: 30 min
- Integración con tab Corridas: 1 h

---

## REQ-3 — Documentar qué debe contener el archivo

### Lo que pidió el cliente

> "Que diga que debe contener el archivo que esta esperando."

### Estado actual (v4.27.15)

Solo dice "Workbook de demanda (1._STUDENTS_PER_COURSE_*.xlsx)" — no
explica qué hojas ni qué columnas.

### Propuesta

**A. Tooltip expandido en cada uploader:**

```
ℹ️ Workbook de demanda (1._STUDENTS_PER_COURSE_*.xlsx)
   Click [?] para ver el schema esperado
```

Click en `?` muestra un expander:

```
El workbook debe tener estas hojas:
• UPDATED MARCH 20 - COURSE_GRADE
  Columnas: COURSE_NUMBER, COURSE_NAME, GRADE_LEVEL, ...
• LISTADO MAESTRO CURSOS Y SECCIO
  Columnas: COURSE_NUMBER, TEACHER, ROOM, ...
• [...]

Para descargar una plantilla con la estructura exacta, click "📥
Descargar plantilla" abajo.
```

**B. Validación inmediata al subir:**

Antes de "Ingestar", la app valida el archivo y muestra:

```
✅ Hojas requeridas: 5/5 presentes
⚠️ Hojas opcionales faltantes: ['UPDATED MARCH 20 - COURSE_GRADE']
❌ Problemas: ['Hoja "Demanda" no encontrada']
```

Si faltan hojas, no permite "Ingestar" hasta que el usuario corrija
o use otro archivo.

### Esfuerzo estimado

- A (tooltip + expander): 1 h
- B (validador pre-ingest): 2 h
- Total: ~3 h

---

## REQ-4 — Plantilla descargable con estructura esperada

### Lo que pidió el cliente

> "Dar la plantilla para que los datos se suban como se esperan."

### Propuesta

**A. Plantilla legacy (1._STUDENTS_PER_COURSE_*.xlsx):**

Generar un xlsx vacío con todas las hojas esperadas y headers
correctos pero sin datos. El coordinador lo descarga, llena con sus
datos, y vuelve a subirlo.

```
Botón en sidebar: "📥 Descargar plantilla (formato legacy)"
→ Genera xlsx en memoria → download
```

**B. Plantilla v5 (master_data consolidado):**

Lo mismo pero para el formato nuevo. Hojas:
- `courses`, `rooms`, `teachers`, `teacher_assignments`,
  `student_requests`, `course_relationships`,
  `conselours_recommendations`, `teacher_avoid`, `co-planning`,
  `required_courses`, `teacher_assistants`

Cada hoja con headers + 1-2 filas de **ejemplo dummy** (no datos
reales) para que el coordinador entienda el formato.

**C. Script de generación:**

```python
# scripts/generate_template_xlsx.py
# Genera ambas plantillas (legacy y v5) en data/templates/
```

Las plantillas se commiten al repo (sin datos reales) y se sirven
desde la app via `st.download_button`.

### Esfuerzo estimado

- Plantilla legacy: 2 h (entender el schema)
- Plantilla v5: 1 h (ya conocemos el schema vía ps_ingest_official)
- Botón en UI: 30 min
- Total: ~3.5 h

---

## REQ-5 (bonus) — Validación de fechas/años

### Por qué incluirlo

Detectado durante prueba: el coordinador puede subir un xlsx del año
2025 mientras pone "2026-2027" en el campo Año. El motor no detecta
el mismatch y produce horario para el año equivocado.

### Propuesta

Validador que compare:
- Año en el campo Año del UI
- Año en el nombre del archivo (`2026-2027.xlsx`)
- Año en alguna hoja interna (si existe)

Si no coinciden → warning antes de ingestar.

### Esfuerzo estimado

1 h.

---

## Plan de implementación sugerido

### Sprint 1 (3 horas) — UX inmediato

1. REQ-1: selector de grados con botones rápido (Opción A)
2. REQ-2: display permanente de archivos cargados
3. REQ-3 parte A: tooltips con schema esperado

→ **Release v4.28.0** — coordinador tiene mejor visibilidad.

### Sprint 2 (4 horas) — Plantillas y validación

4. REQ-4: plantillas descargables (ambos formatos)
5. REQ-3 parte B: validador pre-ingest con feedback visual
6. REQ-5: validación de años

→ **Release v4.28.1** — coordinador puede self-service más
problemas sin escalar a IT.

---

## Cuándo arrancar

Cuando el cliente termine la primera ronda de pruebas con v4.27.15
y haya feedback adicional. Esperar a que confirme que multi-grado
funciona antes de hacer Sprint 1.

---

## Notas para el implementador

- Todos los cambios son en `app.py` excepto las plantillas (script
  + archivos en `data/templates/`)
- No requiere cambios al solver, models, ni compliance
- Los tests existentes deben seguir pasando — añadir tests solo
  para el validador pre-ingest (REQ-3 parte B)
- Coordinar con IT del Colegio para confirmar el schema EXACTO de
  los xlsx legacy (REQ-3, REQ-4) — el repo tiene la info pero
  puede haber sutilezas no documentadas

---

_Notas tomadas el 2026-05-01 durante prueba con cliente. Author:
implementador del Sprint 1 cuando arranque._
