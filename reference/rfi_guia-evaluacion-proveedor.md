# Guía de evaluación para proveedor - Motor de horarios

## Propósito
Este documento busca ayudar a que un proveedor externo pueda evaluar la idea con suficiente contexto funcional, sin asumir que el problema ya está completamente especificado.

## Qué se espera del proveedor
Se espera una evaluación preliminar que permita responder:
- si el problema está bien planteado para avanzar a diseño de solución
- qué nivel de complejidad funcional y técnica ve el proveedor
- qué supuestos está haciendo para dimensionar el trabajo
- qué faltantes de información considera críticos
- qué enfoque recomendaría para una fase inicial
- qué riesgos ve en alcance, datos, reglas e implementación
- si propondría un motor configurable, una solución híbrida o un enfoque por fases

## Material disponible para evaluación
El proveedor debe revisar al menos:
- `levantamiento.md`
- `resumen-ejecutivo.md`
- `conversacion-base.md`
- `requerimientos-funcionales.md`
- `mvp-priorizado.md`
- carpeta `adjuntos/`

## Resumen ejecutivo para proveedor
La institución busca evaluar una solución para construir horarios académicos de forma parametrizable, sostenible y reusable entre distintos contextos escolares.

El caso de High School ya muestra una complejidad real relevante, incluyendo rotaciones, bloques, restricciones docentes, balanceo estudiantil, convivencia, coplanificación y gestión de salones. Middle School aparece como segundo escenario importante, con estructuras distintas por subgrupos de grados.

No se busca todavía una definición cerrada de producto final, sino una evaluación seria de viabilidad, enfoque recomendado, riesgos, información faltante y posible camino de implementación.

## Preguntas guía para respuesta del proveedor

### Entendimiento del problema
1. ¿Cómo entiende el proveedor el problema principal que Columbus quiere resolver?
2. ¿Qué partes del problema considera estructurales y cuáles considera específicas del caso actual?
3. ¿Qué complejidad ve en la coexistencia de High School y Middle School bajo un mismo enfoque?

### Viabilidad de solución
4. ¿Recomienda un motor de reglas configurable, una solución más acotada o una aproximación por módulos?
5. ¿Qué tan viable ve resolver una primera fase sin intentar automatizar todos los casos especiales?
6. ¿Qué riesgos ve en intentar diseñar una solución demasiado general desde el inicio?

### Datos e insumos
7. ¿Qué insumos mínimos necesita para estimar bien una fase 1?
8. ¿Qué problemas potenciales ve en calidad, estructura o disponibilidad de datos?
9. ¿Qué inputs deberían normalizarse antes de construir la solución?

### Alcance y fases
10. ¿Qué recomendaría incluir dentro de una primera fase útil y evaluable?
11. ¿Qué debería dejarse explícitamente por fuera del MVP?
12. ¿Cómo propondría separar generación de horario, validación, asignación estudiantil y reportería?

### Modelamiento de reglas
13. ¿Cómo abordaría reglas duras vs reglas deseables?
14. ¿Qué restricciones convendría parametrizar desde el inicio?
15. ¿Qué tipo de reglas considera demasiado prematuras para la primera fase?

### Implementación y operación
16. ¿Qué perfil de equipo cree necesario para construir e implantar esto?
17. ¿Qué riesgos de adopción operativa identifica?
18. ¿Qué capacidad de mantenimiento o gobierno funcional recomienda dejar en manos del negocio?

## Entregables esperables de una buena evaluación
Una buena respuesta del proveedor debería incluir, idealmente:
- lectura del problema en lenguaje claro
- supuestos explícitos
- vacíos de información detectados
- propuesta de enfoque
- propuesta de fase inicial o MVP
- riesgos principales
- dependencias críticas
- estimación preliminar de esfuerzo o rango
- recomendaciones sobre próximos pasos

## Criterios sugeridos para comparar proveedores
Se sugiere comparar proveedores con base en:
- claridad de entendimiento del problema
- capacidad de abstraer reglas sin perder operatividad
- criterio para priorizar una primera fase viable
- madurez para trabajar con restricciones y excepciones
- calidad de preguntas sobre datos e insumos
- realismo en tiempos, alcance y riesgos
- habilidad para proponer una solución mantenible, no solo una demo funcional

## Observaciones importantes
- Este material no debe interpretarse como BRD final cerrado.
- El caso High School aporta evidencia concreta, pero no agota la necesidad institucional.
- La evaluación del proveedor debe ayudar a refinar el alcance, no solo a cotizar sobre supuestos implícitos.

## Resultado deseado de esta evaluación
Que Columbus pueda decidir con mejor fundamento:
- si avanza o no con la idea
- con qué enfoque conviene avanzar
- qué fase tiene sentido ejecutar primero
- qué información falta consolidar antes de contratar desarrollo
