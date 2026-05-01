# Matriz de decisión académica

Guía rápida para que el coordinador escoja la configuración correcta del
motor según las prioridades del Colegio en cada año académico.

**Antes de leer:** familiarízate con `CASO_DEMO_Y_AJUSTE.md`. Esa guía
explica POR QUÉ los pesos importan. Esta matriz dice CUÁL escoger.

---

## Decide en 4 preguntas

### Pregunta 1 — ¿El Colegio tiene compromiso público sobre tamaño de clases?

> "Las secciones del mismo curso no varían en más de N estudiantes."

- **Sí, N=3 estricto** (FERPA-style equity) → priorizar **balance**
- **Sí, N=4-5 razonable** (default Colegio) → **balance default**
- **No hay compromiso** → priorizar **electivas**

### Pregunta 2 — ¿La satisfacción del estudiante con su electiva es el KPI dominante?

- **Sí** (marketing, retención, experiencia) → **boost electivas**
- **No** (cumplir requeridos es lo importante) → **balance default**

### Pregunta 3 — ¿Los teachers necesitan tiempo común de planeación?

- **Sí** (el Colegio paga horas de coordinación de área) → **coplanning ON**
- **No** (cada teacher organiza su tiempo solo) → **coplanning OFF**

### Pregunta 4 — ¿Hay restricciones de tipo de sala?

- **Sí** (química→lab, banda→música, PE→coliseo) → **importar
  `course_room_type` del xlsx limpio** + activar las que apliquen
- **No** (todo en aulas regulares) → omitir

---

## Las 7 configuraciones más comunes

### A. Default conservador

> "Quiero un horario válido sin pensar mucho."

```
Reglas duras:
  ✅ enforce_separations: ON
  ✅ enforce_restricted_teachers: ON
  ✅ enforce_coplanning_groups: ON
  max_class_size: 25
  max_section_spread_per_course: 4

Pesos suaves:
  first_choice_electives: 20  (default)
  balance_class_sizes: 8       (default)
  grouping_codes: 4            (default)
  teacher_load_balance: 5      (default)
```

**Esperado:** required ~99%, electivas ~62-84% (variable), balance 3.
**Cuándo usarlo:** primera corrida exploratoria.

---

### B. Boost de electivas (recomendado)

> "Quiero electivas en primera opción al máximo sin romper nada."

```
Cambios sobre Default:
  first_choice_electives: 50  (subir desde 20)
  Presupuesto tiempo student: 600s (subir desde 180s) ← CRÍTICO
```

**Esperado:** required 100%, electivas ~90%, balance 3.
**Cuándo usarlo:** producción normal del Colegio. Primera elección.

**⭐ Configuración ganadora absoluta** confirmada en simulación de 9
escenarios. Aceptar el costo de 10 min de cómputo a cambio de +6pp
de electivas vs el budget corto.

---

### C. Maximizar electivas (agresivo)

> "Las electivas son TODO. Aceptemos algo de desbalance."

```
Cambios sobre Default:
  first_choice_electives: 80  (subir desde 20)
  balance_class_sizes: 2       (bajar desde 8)
  max_section_spread_per_course: 5  (subir desde 4)
```

**Esperado:** required 100%, electivas ~88-90%, balance 4-5.
**Cuándo usarlo:** si el Colegio decide priorizar satisfacción
estudiantil sobre equidad de tamaños.

---

### D. Balance perfecto

> "Cada sección del mismo curso debe estar igual."

```
Cambios sobre Default:
  max_section_spread_per_course: 3  (bajar desde 4)
  balance_class_sizes: 15            (subir desde 8)
```

**Esperado:** required ~99%, electivas ~78%, balance 2.
**Cuándo usarlo:** auditorías de equidad o demandas externas de igualdad.

---

### E. Sin co-planning

> "Cada teacher organiza su tiempo solo. Liberar más electivas."

```
Cambios sobre Default:
  enforce_coplanning_groups: OFF
```

**Esperado:** required 100%, electivas ~84%, balance 3.
**Cuándo usarlo:** Colegio no requiere reuniones de área formales,
quiere usar la flexibilidad del coplanning ON para electivas.

---

### F. Cohorte cerrada

> "Estos estudiantes deben quedar todos juntos en estos cursos."

```
Cambios sobre Default:
  Custom rules:
    - cohort_together(student_ids=[lista cohorte], ...)
  Pesos suaves:
    grouping_codes: 30  (subir desde 4)
```

**Esperado:** required 100%, electivas ~80%, balance 3-4.
**Cuándo usarlo:** programas especiales (IB, científicos, atletas)
donde un grupo definido toma cursos juntos.

---

### G. Restricciones físicas estrictas

> "Química SOLO en labs, PE SOLO en coliseo, banda SOLO en sala de música."

```
Cambios sobre Default:
  Custom rules (importadas desde course_room_type del xlsx limpio):
    - require_room_type(course_id="A1106", room_type="science_lab")
    - require_room_type(course_id="E0901", room_type="gym")
    - require_room_type(course_id="K0902", room_type="music")
    - ... (una por curso especial)
```

**Esperado:** required 100%, electivas ~83%, balance 3.
**Cuándo usarlo:** SIEMPRE que el Colegio tenga aulas especializadas.
Ignora esto solo si todas las clases son intercambiables.

**Nota:** las reglas se generan automáticamente al correr
`scripts/cleanup_master_data.py` y se importan con un click en la app
desde la tab Reglas → "📥 Importar `course_room_type`".

---

## Tabla de decisión rápida

| Tu prioridad principal | Configuración |
|---|---|
| Funcionalidad básica sin pensar | A — Default conservador |
| **Producción normal** ⭐ | **B — Boost de electivas** |
| Máxima satisfacción estudiantil | C — Maximizar electivas |
| Equidad estricta de tamaños | D — Balance perfecto |
| Liberar tiempo de teachers | E — Sin co-planning |
| Programa especial / cohorte | F — Cohorte cerrada |
| Aulas especializadas | G — Restricciones físicas |

**Combinables:** B + G es la combinación más común para producción
real (boost de electivas + tipos de sala).

---

## Anti-patrones (NO hacer)

### ❌ Modo `lexmin`

Probado en simulación con datos del Colegio: colapsó required a **25%**.
La prioridad estricta de electivas vacía cursos requeridos. **No usar.**

### ❌ Cambiar `max_class_size` sin política formal

El default 25 (26 AP Research) refleja capacidad real del aula. Subirlo
a 28 puede sobrecupar el espacio físico. Bajarlo a 22 hace infeasible
muchos cursos saturados.

### ❌ Desactivar `enforce_separations`

Las separaciones disciplinarias son decisiones de los consejeros.
Cumplirlas es no-negociable. Si el motor no puede cumplirlas, el
problema son los datos (cohorte muy chica o demasiadas separaciones),
no el motor.

### ❌ Subir `singleton_separation` arriba de 5

En cursos con una sola sección, este peso fuerza que estén en schemes
distintos. Si lo subes mucho, el master se vuelve infeasible
rápidamente porque hay finite schemes.

---

## Iteración recomendada — 3 pasos

1. **Iteración 1:** Configuración A (default). Documentar los KPIs base.
2. **Iteración 2:** Configuración B (boost electivas). Comparar con #1
   en la tab Corridas. Si mejora claramente → adoptar.
3. **Iteración 3:** Si el Colegio tiene aulas especiales, agregar
   Configuración G a #2. Re-correr. Verificar que required y electivas
   siguen altos.

Si después de las 3 iteraciones algún target sigue por debajo de meta,
revisar:
- ¿La hoja `co-planning` del xlsx está sobre-restringida?
- ¿Hay cursos saturados que necesitan más secciones?
- ¿La política del Colegio puede aceptar 78% electivas en lugar de 80%?

---

## Apéndice — referencia de pesos

| Peso | Default | Subir 50% mejora | Bajar 50% empeora |
|---|---|---|---|
| `first_choice_electives` | 20 | electivas ↑ | electivas ↓ |
| `balance_class_sizes` | 8 | balance ↑ | electivas ↑ |
| `grouping_codes` | 4 | pares juntos ↑ | flexibilidad ↑ |
| `teacher_load_balance` | 5 | distribución teachers ↑ | otros objetivos ↑ |
| `co_planning` | 0 | scheme común teachers ↑ | electivas ↑ |
| `singleton_separation` | 0 | menos conflictos ↑ | otros ↑ |

Los pesos se evalúan **proporcionalmente entre sí**. Subir uno hace
que el solver lo prefiera sobre los demás. La magnitud absoluta importa
menos que el RATIO.

---

## Cuándo escalar al equipo técnico

- ✅ Iterar pesos: el coordinador puede solo
- ⚠️ Master infeasible después de 3 intentos: IT
- ⚠️ Compliance de regla dura ≠ 100%: IT (es bug)
- ⚠️ Necesidad de reglas que NO están en la matriz: IT (custom rule
  Phase 2)
- ⚠️ Tiempo de cálculo > 10 min: IT (probable problema de datos)
