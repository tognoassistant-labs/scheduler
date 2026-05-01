# Manual de reglas del motor de horarios

> **Para quién es este documento:** coordinador académico del Colegio
> Columbus y miembros del equipo administrativo que toman decisiones
> sobre el horario.
>
> **No necesitas saber programar** — todo se explica en lenguaje
> académico/operativo, con ejemplos del día a día del Colegio.
>
> **Tiempo de lectura:** 25 minutos para todo. Si tienes prisa, lee
> solo la sección 1 y 2 (10 minutos) — eso es lo más importante.

---

## 1. Cómo piensa el motor (en 2 minutos)

El motor de horarios trabaja en **dos etapas** independientes:

```
ETAPA 1 — "Master schedule"
   ├─ Decide en qué scheme va cada sección (1 a 8)
   ├─ Decide qué sala usa cada sección
   └─ Resultado: cada sección tiene día/bloque/sala fijos

ETAPA 2 — "Student assignment"
   ├─ Toma el master de la etapa 1
   ├─ Asigna cada estudiante a UNA sección por curso solicitado
   └─ Resultado: cada estudiante tiene su horario completo
```

**Por qué importa:** una regla puede aplicar solo en la etapa 1, solo
en la etapa 2, o en ambas. La diferencia importa porque te ayuda a
saber **dónde** ajustar cuando algo no sale bien.

### Las dos clases de reglas

El motor distingue dos tipos:

| Tipo | Símbolo en la app | Qué hace |
|---|---|---|
| **Reglas duras** (hard) | toggle on/off | El motor las cumple SIEMPRE al 100%. Si una regla dura no se puede cumplir, no hay horario (el motor reporta "infeasible"). |
| **Pesos suaves** (soft) | slider 0-50 | El motor las CUMPLE LO MÁXIMO POSIBLE pero las puede sacrificar si entran en conflicto. El "peso" le dice cuánto le importa cada una. |

**Analogía:** las reglas duras son como las leyes de tránsito — no
puedes ir en contravía. Los pesos suaves son tus preferencias de
ruta — *prefieres* la ruta escénica, pero si está cerrada, vas por
otra.

---

## 2. Las 19 reglas, una por una

### Reglas duras (hard) — siempre se cumplen al 100%

#### 2.1 Tamaño máximo de clase (`R_max_class_size`)

**Qué hace:** ninguna sección tiene más de N estudiantes inscritos.

**Default:** 25.

**Ejemplo:** si Álgebra II abre 3 secciones y hay 80 estudiantes que
piden el curso, el motor distribuye en 3 secciones de máximo 25 = 75
ubicados, los otros 5 quedan unmet o se asignan a una 4ª sección si
existe.

**Cuándo modificarlo:** si el Colegio cambia su política de capacidad
del aula. Subir a 28 puede sobrecupar el espacio físico real;
bajar a 22 hace infeasible muchos cursos saturados.

#### 2.2 Tamaño máximo AP Research (`R_ap_research_max_size`)

**Qué hace:** excepción del cap general — AP Research permite 26.

**Default:** 26.

**Por qué:** AP Research tiene una mecánica donde 26 funciona
históricamente; subirlo más empieza a dañar la calidad del curso.

#### 2.3 Separaciones obligatorias (`R_enforce_separations`)

**Qué hace:** los pares de estudiantes en `behavior.csv` (lista de
"Separado de") **NUNCA** comparten sección.

**Ejemplo de la vida real:** "Pedro y Juan tuvieron un conflicto
disciplinario el año pasado. Los consejeros piden que NO estén en
ningún curso juntos." → el motor garantiza que no aparezcan en la
misma sección de ningún curso.

**Cuándo desactivarlo:** prácticamente nunca. Si lo desactivas, las
separaciones pasan a ser pesos suaves y pueden romperse.

#### 2.4 Teachers restringidos por estudiante (`R_enforce_restricted_teachers`)

**Qué hace:** cada estudiante tiene una lista de teachers que NO
pueden dictarle (por incompatibilidad histórica). El motor evita
todas esas combinaciones.

**Ejemplo:** "El estudiante 28102 tuvo un problema con la profesora
Sandra Berrío. Que no le toque ninguna clase con ella este año." →
el motor garantiza que ninguna de las secciones que tome 28102 sea
dictada por Sandra.

**Cuándo desactivarlo:** raramente. Si las restricciones acumuladas
hacen el horario infeasible, primero negocia con consejería para
revisarlas, antes de desactivar la regla.

#### 2.5 Co-planning de departamentos (`R_enforce_coplanning_groups`)

**Qué hace:** los grupos de teachers definidos en la hoja
`co-planning` deben tener al menos un scheme libre EN COMÚN para
poder reunirse.

**Ejemplo:** "El departamento de matemáticas (5 profesores) necesita
una hora libre común para coordinar contenidos." → el motor garantiza
que esos 5 profesores tengan un scheme donde ninguno está dictando
clase.

**Costo:** activarlo cuesta ~50 estudiantes que pierden su electiva
en primera opción (porque limita las posibles ubicaciones de
secciones).

**Cuándo desactivarlo:** si el Colegio acepta que los profesores
coordinen por otros medios (Slack, correo, reuniones extraescolares),
desactivar libera ~50 cupos de electivas.

#### 2.6 Spread máximo entre secciones del mismo curso (`R_max_section_spread_per_course`)

**Qué hace:** si Álgebra II tiene 3 secciones, la diferencia entre
la sección más llena y la más vacía no puede pasar de N estudiantes.

**Default:** 4 (política del Colegio: ideal 4, aceptable 5).

**Ejemplo:** si las 3 secciones de Álgebra II terminan con 24, 21,
20 estudiantes → spread = 24-20 = 4 ✅ cumple. Si terminan con 25,
20, 19 → spread = 6 ❌ no cumple.

**Cuándo modificarlo:**
- **Bajar a 3** si el Colegio quiere balance estricto (sacrifica
  electivas)
- **Subir a 6** si el Colegio prioriza electivas (acepta más
  desbalance)

#### 2.7 Mínimo de secciones para evaluar balance (`R_min_sections_for_balance`)

**Qué hace:** cursos con menos de N secciones no se someten al
constraint de balance (no tiene sentido balancear 1 sola sección).

**Default:** 2.

**Cuándo modificarlo:** prácticamente nunca. Subirlo a 3 deja muchos
cursos sin balance medido.

#### 2.8 Máximo clases consecutivas por teacher (`R_max_consecutive_classes`)

**Qué hace:** ningún teacher dicta más de N bloques **seguidos** en
un mismo día.

**Default:** 4.

**Ejemplo:** si Sandra dicta bloques 1, 2, 3, 4 el lunes, eso son 4
bloques consecutivos = ✅. Si le agregaran el bloque 5 también,
serían 5 consecutivos = ❌.

**Por qué:** garantiza que los teachers tengan tiempo de descanso/
preparación entre clases.

**Cuándo modificarlo:** si un teacher específico necesita más cap por
su carga (raro), se puede subir a 5 solo para ese teacher (campo
`max_consecutive_classes` por teacher en el csv).

##### 2.8.bis HC3b — Cap secundario para teachers con override

**Qué hace:** si un teacher tiene `max_consecutive_classes=5` (override),
no puede tener jornada completa (5 bloques) en **más de 2 días por
semana**. Los demás días sigue limitado a 4 consecutivos.

**Por qué:** sin este cap, los 3 teachers del Colegio con 7+ secciones
podrían terminar con 5 bloques los lunes, miércoles y viernes — carga
inhumana. Política del Colegio (2026-05-01): *"5 bloques seguidos solo
en 1 o 2 días por semana"*.

**Implementación:** automática. El ingester detecta teachers con 7+
secciones y les asigna override; HC3b limita a 2 días por semana de
jornada completa. Sin acción del coordinador.

**Para verificar:** en la tab **Cumplimiento** → drill-down de
`R_max_consecutive_classes` muestra cumplimiento. En `teacher_loads.csv`
puedes ver la distribución por teacher por día.

---

### Pesos suaves (soft) — el motor optimiza, no garantiza

#### 2.9 Peso electivas rank-1 (`R_w_first_choice_electives`)

**Qué hace:** premia cada vez que un estudiante recibe una electiva
en su PRIMERA opción.

**Default:** 20.

**Subirlo a 50:** más estudiantes obtienen su electiva preferida.
**⭐ Ajuste #1 más impactante** — confirmado en 9 simulaciones.

**Subirlo a 80:** maximiza electivas pero puede sacrificar balance.

#### 2.10 Peso balance entre secciones (`R_w_balance_class_sizes`)

**Qué hace:** penaliza desviación entre tamaños de secciones del
mismo curso (similar al hard, pero suave).

**Default:** 8.

**Trade-off:** subir → balance más estricto, electivas bajan. Bajar →
electivas suben, balance peor.

#### 2.11 Peso co-planning suave (`R_w_co_planning`)

**Qué hace:** versión suave de la regla 2.5. Premia agrupar teachers
del mismo departamento en horarios compatibles.

**Default:** 0 (desactivado).

**Cuándo activarlo:** si la versión hard es demasiado estricta y
empuja muchos infeasibles, este es un middle-ground: reza por que
los teachers tengan tiempo común sin obligarlo.

#### 2.12 Peso grouping codes (`R_w_grouping_codes`)

**Qué hace:** premia mantener juntos pares de estudiantes en la lista
"Compartir clases con" (groupings).

**Default:** 4.

**Ejemplo:** "María y Juana son hermanas y la mamá pidió que estén
juntas en cuantas clases sea posible." → el motor intenta meterlas
en las mismas secciones.

**Subirlo:** más groupings respetados (a costa de otros objetivos).

#### 2.13 Peso balance carga teacher (`R_w_teacher_load_balance`)

**Qué hace:** penaliza desbalance en cantidad de bloques por día
entre teachers.

**Default:** 5.

**Por qué:** evita que un teacher tenga 5 clases el lunes y 0 el
viernes mientras otro tiene lo opuesto.

#### 2.14 Peso cursos preferidos por teacher (`R_w_teacher_preferred_courses`)

**Qué hace:** premia asignar a un teacher cursos en su lista
"preferred_course_ids".

**Default:** 3.

**Ejemplo:** "Norberto Villa prefiere dictar AP Spanish Language
sobre G0901." → el motor intenta darle AP Spanish, no G0901.

#### 2.15 Peso cursos evitados por teacher (`R_w_teacher_avoid_courses`)

**Qué hace:** penaliza asignar a un teacher cursos en su lista
"avoid_course_ids".

**Default:** 5.

**Ejemplo:** "Sandra evita dictar Álgebra II porque su especialidad
es Cálculo." → el motor intenta NO darle Álgebra II.

#### 2.16 Peso bloques preferidos por teacher (`R_w_teacher_preferred_blocks`)

**Qué hace:** premia dictar en bloques que el teacher prefiere.

**Default:** 2.

**Ejemplo:** "Carlos Marín prefiere bloques 1 y 2 (mañana) sobre 4 y
5 (tarde)." → el motor intenta darle bloques de mañana.

#### 2.17 Peso bloques evitados por teacher (`R_w_teacher_avoid_blocks`)

**Qué hace:** penaliza dictar en bloques que el teacher evita.

**Default:** 3.

#### 2.18 Peso separación de cursos singleton (`R_w_singleton_separation`)

**Qué hace:** empuja cursos con UNA sola sección hacia schemes
diferentes para reducir conflictos.

**Default:** 0 (desactivado).

**Cuándo activarlo:** si hay muchos cursos singleton (ej: AP de poca
demanda) que están todos en el mismo scheme y eso causa que muchos
estudiantes elegibles no puedan tomarlos.

#### 2.19 Peso violación de separación (`R_w_separation_violation`)

**Qué hace:** solo se evalúa si la regla 2.3 (`R_enforce_separations`)
está APAGADA.

**Default:** 1000.

**Cómo funciona:** si la regla hard está off, este peso reemplaza el
"siempre" por "casi siempre" — el motor aún intenta cumplir las
separaciones pero puede romperlas si necesario para coverage.

---

## 3. Parámetros del solver — botones, sliders y modos

Las reglas (sección 2) controlan **qué** quieres que el horario
respete. Los parámetros de esta sección controlan **cómo** y
**cuánto tiempo** el solver busca el horario óptimo.

Todos están en la **tab "2️⃣ Solve"** o en la **tab "📋 Reglas"**.

### 3.1 Modo del solver — `single` vs `lexmin`

**Qué controla:** la estrategia matemática que usa el solver para
manejar los pesos suaves cuando hay conflicto entre objetivos.

#### Modo `single` (default — siempre úsalo)

**Qué hace:** suma ponderada. El solver calcula:

```
puntaje = (peso_electivas × electivas_cumplidas)
        + (peso_balance × balance_cumplido)
        + (peso_groupings × groupings_cumplidos)
        + ... (todos los pesos suaves)
```

Y maximiza el `puntaje` total. Los pesos definen el ratio entre
objetivos.

**Ventajas:**
- Rápido (1-3 minutos en datasets típicos)
- Predecible (subir un peso → más cumplimiento de esa regla)
- Es lo que usa el 99% de las herramientas de scheduling reales

**Desventajas:** ninguna relevante para el caso del Colegio.

#### Modo `lexmin` — NO usar

**Qué hace:** lex-min en 2 fases. Primero maximiza electivas a toda
costa, después maximiza groupings dado el resultado de fase 1.

**Por qué NO usarlo:** la prioridad estricta de electivas hace que
el motor saque a estudiantes de cursos REQUERIDOS para meterlos en
electivas preferidas. En la simulación con datos reales del Colegio,
`lexmin` colapsó el cumplimiento de requeridos a **22.7%** —
inaceptable.

**Cuándo tendría sentido:** sólo si las electivas fueran ABSOLUTAMENTE
prioritarias sobre los requeridos académicos, lo cual no es la
política del Colegio.

**Recomendación:** déjalo en `single` permanentemente.

---

### 3.2 Presupuesto tiempo master — `master_time`

**Qué controla:** cuántos segundos máximos puede tomar la **etapa 1**
(decidir scheme + sala para cada sección).

**Default UI:** 30 segundos.

**Qué pasa si lo subes / bajas:**

| Valor | Efecto |
|---|---|
| 5-15s | Suficiente para datasets pequeños (<100 secciones). Para 248 secciones puede dar FEASIBLE en lugar de OPTIMAL. |
| 30s (default) | Funciona bien en la mayoría de los casos del Colegio. |
| 60-120s | Para multi-grado o datasets complejos. Mejora marginal vs 30s. |
| 300s+ | Casi nunca útil — el master normalmente converge en <5s para datasets del Colegio. |

**En la práctica:** el master suele dar OPTIMAL en menos de 1
segundo. Subirlo no ayuda. **Déjalo en 30s.**

---

### 3.3 Presupuesto tiempo student — `student_time` ⭐

**Qué controla:** cuántos segundos máximos puede tomar la **etapa 2**
(asignar cada estudiante a sus secciones).

**Default UI:** 180 segundos.

**Hallazgo clave de la simulación:** este es el parámetro de mayor
impacto. Subirlo de 120s a 600s sube electivas ~5 puntos
porcentuales en cualquier configuración.

| Valor | Tiempo total | Cumplimiento electivas (en Columbus) |
|---|---|---|
| 60s | 1-2 min | ~70-75% (pobre) |
| 180s (default) | 3-4 min | ~80-83% (aceptable) |
| **600s** ⭐ | **10-11 min** | **~89-90% (excelente)** |
| 1200s | 20-21 min | ~90-91% (rendimientos decrecientes) |

**Cuándo subir:**
- ⭐ **Siempre que hagas la corrida final** que vas a exportar a
  PowerSchool — sube a 600s
- Cuando el motor reporta "FEASIBLE" en lugar de "OPTIMAL" → puede
  beneficiarse de más tiempo
- Multi-grado (los 4 grados juntos) → sube mínimo a 600s

**Cuándo NO subir:**
- Iteraciones rápidas para tunear pesos — déjalo en 180s
- Pruebas con sample integrado de 130 estudiantes — 60s suficiente

---

### 3.4 Hard balance cap K — `max_section_spread_per_course`

**Qué controla:** la máxima diferencia permitida entre la sección
más llena y la más vacía de un mismo curso.

**Default UI:** 4.

**Política del Colegio:** ideal 4, aceptable 5.

| Valor | Significado | Efecto en electivas |
|---|---|---|
| 2 | Spread muy estricto. Cualquier desbalance se penaliza. | Electivas caen ~5 pp |
| 3 | Estricto. Balance casi perfecto. | Electivas caen ~3 pp |
| **4 (default)** ⭐ | Política Colegio "ideal" | Electivas equilibradas |
| 5 | Política Colegio "aceptable" | Electivas suben ~2 pp |
| 6+ | Holgura permite priorizar electivas | Electivas suben ~5 pp pero balance dev=4-5 |

**Recomendación:** déjalo en 4 (default) para producción. Si vas a
ajustar electivas, primero sube `R_w_first_choice_electives` (ver 2.9)
antes de relajar este cap.

---

### 3.5 Sliders rápidos en tab Solve

La tab Solve expone estos pesos como **sliders rápidos** para no
tener que ir a la tab Reglas. Son atajos a las mismas reglas
descritas en sección 2.

| Slider en Solve | Equivale a regla | Default | Range UI |
|---|---|---|---|
| First-choice elective weight | `R_w_first_choice_electives` (2.9) | 20 | 1-50 |
| Soft balance weight | `R_w_balance_class_sizes` (2.10) | 8 | 0-30 |
| Grouping pairs weight | `R_w_grouping_codes` (2.12) | 4 | 0-20 |
| Co-planning weight | `R_w_co_planning` (2.11) | 0 | 0-10 |
| Teacher-load balance weight | `R_w_teacher_load_balance` (2.13) | 5 | 0-20 |

**Si modificas en Solve, sobrescribe lo de Reglas para esa corrida.**

---

### 3.6 Verbose mode (CLI only)

Disponible solo desde línea de comandos: `--verbose`.

**Qué hace:** imprime el log interno del solver de OR-Tools (cómo va
encontrando soluciones intermedias, cuántas variables y constraints
hay, etc.).

**Cuándo usarlo:** debugging técnico — el coordinador no lo necesita.

---

### 3.7 Persistencia — `--persist` / "Guardar corridas en SQLite"

**Qué hace:** guarda cada solve en una base de datos local
(`data/columbus.sqlite`).

**Por qué activarlo:**
- Permite comparar corridas en la tab Corridas
- Permite re-exportar una corrida pasada sin re-correr el solver
- Tu trabajo no se pierde si cierras la app

**Por qué NO activarlo:** raramente. Quizás solo si la BD se está
volviendo muy grande (>1 GB) y no necesitas histórico.

**Recomendación:** **siempre activado** en producción.

---

### 3.8 Modo de la fuente de datos

En el sidebar, "Fuente de datos" tiene 3 opciones:

| Opción | Para qué |
|---|---|
| **Sample integrado (Grado 12, 130 estudiantes)** | Pruebas rápidas con datos sintéticos. Sin necesidad de archivos. |
| **Carpeta canónica de CSVs** | Si ya convertiste tu xlsx a 8 CSVs (vía CLI). |
| **xlsx real de Columbus** | Subir directamente los archivos del Colegio. |

Y dentro de "xlsx real de Columbus":

| Sub-opción | Cuándo usarlo |
|---|---|
| Workbook de demanda (`1._STUDENTS_PER_COURSE_*.xlsx`) | Obligatorio. Es el archivo principal con cursos, estudiantes, requests. |
| Workbook de schedule (`HS_Schedule_*.xlsx`) | Opcional pero recomendado. Aporta groupings/separations de la programación pasada. |

### 3.9 Selector de grados

Tres modos:

| Modo | Cuándo usarlo | Tiempo solver estimado |
|---|---|---|
| Un grado | Pruebas rápidas | 2-3 min |
| Todo HS (9-12) | Producción del bachillerato completo | 10-15 min con student_time=600s |
| Selección personalizada | Combinaciones (ej: solo 11+12, o 9+10) | Depende |

---

## 4. Cómo decide el motor cuando hay conflictos

### Caso 1 — Conflicto entre 2 reglas duras

Si subir el peso de electivas hace que el balance se rompa, **las
reglas duras GANAN siempre**. Si no se pueden cumplir todas las
duras simultáneamente, el motor reporta "infeasible" y no genera
horario.

**Solución:** debes desactivar alguna regla dura o relajar sus
parámetros (subir el cap del balance, por ejemplo).

### Caso 2 — Conflicto entre 2 pesos suaves

El motor calcula una "suma ponderada" — multiplica cada métrica
satisfecha por su peso, y maximiza la suma total. El que tenga peso
más alto domina.

**Ejemplo concreto:**
- Peso electivas = 20, peso balance = 8 → electivas dominan
  ligeramente
- Peso electivas = 50, peso balance = 8 → electivas dominan mucho
- Peso electivas = 5, peso balance = 30 → balance domina

### Caso 3 — Conflicto entre dura y suave

La dura siempre tiene prioridad. El peso suave se evalúa **dentro de
la región factible** que la dura permite.

---

## 5. Qué hacer cuando una regla no se cumple al 100%

### Si una regla DURA muestra <100% en la tab Cumplimiento

**Esto NO debería pasar.** Si lo ves, es un bug del motor.

**Acción:**
1. Toma screenshot de la tab Cumplimiento
2. Reporta a IT con el screenshot + el ID de la corrida
3. **No uses ese horario en producción** hasta que IT confirme

### Si una regla SUAVE muestra <80%

Esto SÍ es esperado a veces — los pesos no garantizan 100%.

**Acción:**
1. Identifica la regla con bajo cumplimiento
2. Sube su peso en la tab Reglas
3. Re-corre Solve
4. Compara las dos corridas en la tab Corridas

**Cuidado:** subir un peso suele bajar otros. Es un trade-off.

---

## 6. Reglas personalizadas (Phase 2)

Además de las 19 reglas builtin, puedes crear reglas custom desde la
tab Reglas → "➕ Reglas personalizadas".

### Las 6 reglas custom disponibles

#### 5.1 `forbid_pair` — pares que nunca se separan

**Qué hace:** equivalente a una separación pero creada en el momento.

**Ejemplo:** "Acabamos de detectar que María y Sofía no pueden estar
juntas — no estaba en el archivo original."

**Params:** `student_a`, `student_b` (ambos student IDs).

#### 5.2 `forbid_slot` — teacher no puede dictar en cierto bloque

**Qué hace:** marca un bloque como prohibido para un teacher.

**Ejemplo:** "El profesor Andrés tiene capacitación los miércoles a
las 7am, no puede dictar bloque 1 ese día."

**Params:** `teacher_id`, `block` (1-5).

**Nota:** se aplica como "soft" via `avoid_blocks` con peso muy alto.
Para hard sería necesario otro mecanismo.

#### 5.3 `require_room` — curso solo en sala específica

**Qué hace:** todas las secciones de un curso van a UNA sala fija.

**Ejemplo:** "AP Bio solo se puede dictar en el Lab 901 porque tiene
los reactivos."

**Params:** `course_id`, `room_id`.

#### 5.4 `require_room_type` — curso solo en tipo de sala

**Qué hace:** todas las secciones del curso van a salas DEL TIPO
indicado (cualquiera del tipo).

**Ejemplo:** "Educación Física tiene que ser en algún coliseo (gym).
No me importa cuál de los 4."

**Params:** `course_id`, `room_type` ∈ {gym, science_lab,
computer_lab, music, art, special_ed, standard}.

#### 5.5 `prefer_teacher` — estudiante con teacher específico

**Qué hace:** un estudiante debe quedar con un teacher específico
para un curso.

**Ejemplo:** "Ariana Agudelo es TA de Gloria Vélez en AP Drawing.
Necesita estar en la sección de AP Drawing que dicta Gloria."

**Params:** `student_id`, `course_id`, `teacher_id`.

**Cómo lo hace:** marca a todos los demás teachers de ese curso como
"restringidos" para ese estudiante.

#### 5.6 `cohort_together` — lista de estudiantes en mismas secciones

**Qué hace:** N estudiantes deben compartir secciones (idealmente).

**Ejemplo:** "El equipo de robótica son 8 estudiantes que necesitan
estar en la misma sección de Álgebra II y Física para sincronizar
horarios de práctica."

**Params:** `student_ids` (lista).

**Tipo:** soft (no hard).

---

## 7. Reglas que el motor NO maneja (todavía)

### Reglas condicionales

> "Si el profesor X no tiene clase, asignar Y a la sección Z"

Esto requiere lógica del estilo *if-then-else* que el motor actual no
soporta. Hay 6 reglas así en el archivo del Colegio (la hoja
"CONSTRAINTS"). El motor las **lee y reporta** pero no las aplica
automáticamente.

**Workaround:** convertirlas en reglas estáticas. Ejemplo, en lugar
de "si X libre, asigna Y", quedarse con "asigna Y siempre" o "asigna
X siempre" — la decisión condicional no la toma el motor.

### Restricciones por trimestre/semestre

El motor asume horarios anuales. Para clases que cambian a la mitad
del año (ej: una sección que cambia de profesor en febrero) se debe
manejar como dos secciones distintas y manualmente decidir cuál
aplica cuándo.

### Estudiantes que cambian de grado a mitad de año

No soportado. Ingestar los datos del año completo o re-correr a
mitad de año si pasa.

---

## 8. Anti-patrones (qué NO hacer)

### ❌ Modo `lexmin`

En la tab Solve hay un selector de "Modo": single vs lexmin.
**SIEMPRE usa `single`.**

Probado en simulación con datos reales: `lexmin` colapsó el
cumplimiento de cursos requeridos a **22.7%** porque prioriza
estrictamente las electivas sobre todo lo demás.

### ❌ Apagar `R_enforce_separations`

Las separaciones disciplinarias son decisión de los consejeros y son
no-negociables. Si el motor no puede cumplirlas, el problema son los
datos (cohorte muy chica o demasiadas separaciones), no el motor.

### ❌ Subir `R_max_class_size` arriba de 28

Sobrecuparía las aulas físicas reales. Si necesitas más capacidad,
agrega más secciones del curso saturado, no inflas el cap.

### ❌ Subir `R_w_singleton_separation` arriba de 5

En cursos con una sola sección, este peso fuerza que estén en
schemes distintos. Si lo subes mucho, el master se vuelve infeasible
porque hay solo 8 schemes posibles para muchos singletons.

### ❌ Cambiar muchas reglas al mismo tiempo

Si cambias 5 cosas y vuelves a correr, no sabrás cuál ayudó. **Cambia
una a la vez** y compara con la corrida anterior.

---

## 9. Glosario

- **Scheme** — número 1..8 que representa una "huella" de día/bloque.
  Cada scheme tiene 3 momentos en la semana (típico: lunes B1,
  miércoles C2, jueves D3 → eso es scheme 3).

- **Sección** — instancia específica de un curso. Álgebra II tiene 3
  secciones: ALG2.1, ALG2.2, ALG2.3.

- **Master** — etapa 1 del solver (decide schemes y salas).

- **Student** — etapa 2 del solver (asigna estudiantes a secciones).

- **Bundle** — un conjunto de inputs (xlsx + interpretación). Cada
  bundle tiene un ID único en la BD.

- **Run** — una corrida del solver. Tiene un bundle + una config de
  reglas + sus resultados.

- **Singleton** — curso con UNA sola sección.

- **Coplanning group** — grupo de teachers que necesitan tiempo
  común libre.

- **Hard rule** / **regla dura** — siempre se cumple.

- **Soft rule** / **peso suave** — se intenta cumplir, ponderado.

- **Compliance** — % de cuántas instancias de una regla se
  cumplieron en una corrida específica.

- **KPI** — métrica de alto nivel (fully_scheduled, required_pct,
  electivas_rank1_pct, etc.) — los 4 targets v2 §10.

- **v2 §10** — sección 10 del documento de requirements del Colegio
  que define las 4 metas críticas:
  - Fully scheduled ≥ 98%
  - Required fulfillment ≥ 98%
  - First-choice electives ≥ 80%
  - Section balance dev ≤ 3

---

## 10. Preguntas frecuentes

### ¿Por qué el motor no cumple electivas al 100%?

Porque hay restricciones físicas (capacidad finita) y conflictos
naturales (un estudiante pide una electiva en bloque 3 pero su
required ya está en bloque 3). El motor escoge el subconjunto
óptimo dadas tus reglas y pesos.

### ¿Puedo forzar que un estudiante específico reciba SU electiva?

Sí — usa la regla custom `prefer_teacher` o más directo: súbele un
peso muy alto a `R_w_first_choice_electives` (ej: 80) y re-corre.
Si aún así no se cumple, ese estudiante tiene un conflicto físico
con sus otros cursos requeridos.

### ¿El balance perfecto es posible?

Casi nunca con datasets reales. Cumplir spread ≤ 2 obliga a
distribuir tan equitativamente que se sacrifican electivas. La meta
v2 §10 (≤ 3) es razonable.

### ¿Las separaciones se pueden romper si "es muy difícil"?

No, son hard. Si el motor reporta infeasible por separaciones, debes
revisar la lista — probablemente hay separaciones acumuladas de años
que ya no aplican.

### ¿Cuántos pesos puedo cambiar al tiempo?

Recomendado: 1 por iteración. Si cambias 3 pesos y comparas con la
baseline, no sabrás cuál ayudó. Itera lentamente.

### ¿Las reglas custom se pierden al cerrar la app?

Si tienes "Guardar corridas en SQLite" activo, se persisten en la
config de la corrida. Si no, se pierden. **Activa siempre la
persistencia** para conservar tu trabajo.

### ¿Por qué el motor tarda 10 minutos para multi-grado?

Porque pasa de 509 estudiantes (solo G12) a ~2,000 estudiantes
(toda HS), y la complejidad del solver crece de forma no-lineal con
el tamaño. Sube el "Presupuesto tiempo student (s)" a 600 o 900.

### ¿Puedo correr el motor durante el año escolar?

Sí, pero ten en cuenta:
- Si hay matrículas tardías → el horario cambia → impacta secciones
  ya con estudiantes
- Recomendable: una corrida ANTES del año (con estudiantes esperados),
  una segunda DESPUÉS de matrículas tardías

---

## 11. Cuándo escalar al equipo técnico (IT)

Resuelve tú solo:
- ✅ Iterar pesos
- ✅ Probar configuraciones
- ✅ Comparar corridas
- ✅ Subir distintos archivos xlsx
- ✅ Activar/desactivar reglas duras
- ✅ Crear reglas custom

Escala a IT:
- ⚠️ Master infeasible después de varios intentos con distintos
  parámetros
- ⚠️ Una regla dura muestra <100% en Compliance (es un bug)
- ⚠️ El motor tarda más de 15 minutos
- ⚠️ El xlsx no se ingesta y el error no es claro
- ⚠️ El export a PowerSchool falla en PS al importarlo
- ⚠️ Necesitas una regla que no está documentada arriba

---

## 12. Resumen de una página

```
┌─────────────────────────────────────────────────────────────┐
│  EL MOTOR EN 1 MINUTO                                       │
├─────────────────────────────────────────────────────────────┤
│  • 8 reglas duras (siempre 100%) — toggles on/off           │
│  • 11 pesos suaves (optimización) — sliders 0-50            │
│  • 6 reglas custom Phase 2 — tab Reglas                     │
│                                                             │
│  CONFIGURACIÓN GANADORA (probada en 9 escenarios):          │
│  • peso electivas rank-1 = 50  ← subir desde 20             │
│  • presupuesto tiempo student = 600s  ← subir desde 180     │
│  → 100% required, 90% electivas, balance 3 ✅               │
│                                                             │
│  ANTI-PATRONES:                                             │
│  • NUNCA usar modo lexmin (colapsa required a 25%)          │
│  • NUNCA apagar separaciones (decisión de consejería)       │
│  • Cambiar UN peso a la vez (para que la comparación sea    │
│    interpretable)                                           │
└─────────────────────────────────────────────────────────────┘
```

---

## 13. Para profundizar

- **`MATRIZ_DECISION.md`** — qué configuración escoger según tus
  prioridades académicas
- **`CASO_DEMO_Y_AJUSTE.md`** — caso de iteración con datos reales
- **`COORDINATOR_QUICKSTART.md`** — flujo de 8 pasos para tu día a día

---

_Este documento se mantiene actualizado con cada nueva versión del
motor. Si algo cambia (regla nueva, default distinto), revisa el
`CHANGELOG.md` para saber qué se modificó._
