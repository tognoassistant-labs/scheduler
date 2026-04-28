# Preguntas para Hector — sesión 2026-04-28 (HC4)

Las decisiones del agente previo (1-10) están en sus notas; algunas siguen abiertas pero no las repito aquí salvo para marcar resueltas. Las nuevas decisiones de esta sesión empiezan en 11.

---

## Decisiones aún abiertas del agente previo

- **Decisión 9** — regenerar bundle v3 con los nuevos formatos PS (PR previa). **Aún abierta** y ahora MÁS apretada porque también tenemos HC4 listo.
- **Decisión 10** — granularidad de TermID 3600 (year vs semester vs quarter). **Aún abierta** y bloquea Decisión 9.
- **Decisiones 5, 7, 8** — ver sus notas. Decisiones 1-4, 6 son menores o resueltas.

---

## Decisión 11 — ¿Regenerar bundle como v3 ahora, o esperar a los archivos prometidos del cliente?

### Estado actual

- `bundle_for_columbus/columbus_2026-2027_bundle_v2.zip` (hash `5a2932b8...`) — sigue siendo el bundle entregado al cliente, con formatos PS VIEJOS y SIN HC4.
- `scheduler/data/columbus_full_hs_v4/` — los CSV exports nuevos: HC4 aplicado, formatos PS correctos (Period `1(A)2(B)3(C)`, SchoolID 13000, TermID 3600).
- Cliente prometió enviar archivos con CourseID/TeacherID/SectionID reales y la "estructura de salida que necesita PowerSchool".

### Opciones

1. **Regenerar v3 AHORA** (sin esperar al cliente) con HC4 + PS format fixes. Ventaja: cliente tiene algo concreto a probar en sandbox YA. Riesgo: cuando lleguen los archivos del cliente, hay que regenerar v4 con los CourseID reales — duplicación de trabajo.

2. **Esperar los archivos del cliente** y regenerar UNA SOLA vez como v3. Ventaja: un solo bundle final. Riesgo: cliente espera más, y la duración hasta May 1 es corta (~3 días).

3. **Regenerar v3 con la advertencia** "los CourseID son slugs internos, esperar archivos del cliente para el mapeo final". Ventaja: cliente puede empezar a probar la estructura sin esperar el mapeo. Yo creo que es la mejor — el verifier puede correr contra v3 inmediatamente, y los IDs se reemplazan al final con búsqueda-y-reemplazo cuando lleguen los archivos.

**Mi recomendación: Opción 3.** Regenerar v3 con HC4. El bundle es para que el cliente pruebe la ESTRUCTURA del horario; los IDs reales son un find-and-replace al final.

**Si decides "sí" a Opción 3, hago:**
- Regenerar PS exports + OneRoster para v4 (ya están en `data/columbus_full_hs_v4/`)
- Actualizar `verify_bundle.py` (ya copia con el bundle, no requiere cambios)
- Empaquetar como `columbus_2026-2027_bundle_v3.zip` con README actualizado
- Calcular nuevo SHA256SUM
- Mantener v2 intacto en disco (cliente puede comparar)

---

## Decisión 12 — Sobre los 3 profesores con 7 secciones académicas

Sofia Arcila Fernandez, Gloria Vélez Cardona, Clara Martínez Cubillos cada una con 7 secciones. Estructuralmente infeasible al `max_consec=4` strict (pigeonhole con 5 bloques/día).

### Opciones

1. **Hablar con cliente para reducir la carga de 1 de ellas a 6 secciones** — eso libera un esquema y permite que TODAS respeten el max=4. Ideal pero requiere coordinación.

2. **Mantener override `max_consec=5`** en el script de re-solve. El warning ya documenta el problema. Cliente acepta que esos 3 profesores tendrán ocasionalmente 5 bloques seguidos.

3. **Excepción por profesor**: agregar `Teacher.max_consecutive_classes_override` y aplicar solo a esos 3. Más complejo pero limpio.

**Mi recomendación:** Opción 2 hasta que llegue una respuesta del cliente sobre si pueden ajustar la carga. La 3 es buena para una versión futura.

---

## Decisión 13 — ¿Confirmar mapeo de nombre con cliente para Julián Zúñiga?

El cliente dijo "Julián Zúñiga sin cursos." Realmente está en el bundle pero como `T_ZUNIGA_JUL` con nombre `"Zuniga, Julian"` (formato del LISTADO MAESTRO sin tildes, apellido primero).

### Opciones

1. **Mensaje al cliente**: "Verificamos: Julián Zúñiga aparece en el bundle como `Zuniga, Julian` (formato LISTADO). Tiene AP CS A + AP CS Principles + Advisory. ¿Es la misma persona? Si sí, ajustamos el formato de nombre en el output a `Julián Zúñiga`." → cliente responde, hacemos search-and-replace.

2. **Cambiar el formato del nombre en el ingester** (ahora) para mostrar nombres tildados con orden "Nombre Apellido": `_normalize_teacher_name("Zuniga, Julian")` → `"Julián Zúñiga"`. Pero requiere normalización a partir de un LISTADO inconsistente, frágil.

3. **No hacer nada por ahora** — el cliente puede confundirse otra vez en el siguiente review.

**Mi recomendación: Opción 1.** Mensaje rápido al cliente para destrabar.

---

## Lo que NO hice (para tu visibilidad)

1. **NO regeneré el bundle** — Decisión 11 explícita.
2. **NO atendí "5 bloques seguidos"** vía solver — el override a 5 sigue siendo el camino. Decisión 12 abierta.
3. **NO investigué a fondo el `_normalize_teacher_name`** — Decisión 13.
4. **NO toqué los exports v4** — están listos en disco para empaquetar cuando decidas.

## Lo que SÍ hice (sin permiso, dentro de scope autorizado por "procede con 2+3")

- Toda la implementación de HC4 (cliente lo marcó como crítico).
- Revertir el auto-relax de max_consec con WARNING explícito.
- Heurística para placeholder + multi-room teachers (descubierta durante implementation).
- Tests + re-solve completo + verify_bundle PASS.
- Resultado: v4 con todos los KPIs cumplidos.
