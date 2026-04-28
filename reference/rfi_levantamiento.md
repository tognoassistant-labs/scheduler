# Levantamiento - Motor de horarios

## Estado
Cerrado por conversación con Juan Pablo. Esta carpeta formaliza el cierre con respaldo documental en `shared-drive` y fue reforzada para facilitar evaluación por proveedor.

## Contexto
Juan Pablo indicó que la etapa podía cerrarse y Perla respondió que el levantamiento funcional quedaba cerrado y suficientemente aterrizado para pasar a una siguiente fase de formalización o priorización.

## Problema identificado
La construcción de horarios depende hoy de una operación manual, compleja y difícil de sostener en el tiempo.

## Necesidad expresada
Contar con una solución flexible y completamente parametrizable que soporte distintos escenarios por escuela, grado y año escolar.

## Solución funcional entendida
Se plantea un motor de horarios con capacidad para manejar:
- inputs canónicos
- constructor y gestión de esquemas
- horario maestro
- asignación de estudiantes
- validación de escenarios
- salidas estructuradas

## Qué problema de negocio busca resolver
La institución necesita reducir dependencia de armado manual, aumentar consistencia del proceso y poder operar distintos modelos académicos sin rediseñar la solución desde cero en cada escuela o grado.

## Escenario funcional base identificado en adjuntos
A partir del material de High School ya compartido por Juan Pablo, se identifican ejemplos concretos de complejidad que el proveedor debe asumir como referencia de diseño:
- cinco días de clase con bloques y rotaciones
- ocho esquemas rotativos para High School
- franja fija de Advisory en Día E, Bloque 3
- límite de clases consecutivas para docentes
- necesidad de coplanificación simultánea entre profesores
- restricciones de cupo por curso y balance entre secciones
- asignación de estudiantes según reglas de convivencia y preferencias
- cursos que pueden compartir franja o salón bajo reglas específicas
- gestión de salones compartidos y rotación de espacios
- generación inicial de horario estimado para profesores y luego carga/ajuste de estudiantes

## Escuelas / contextos mencionados
- High School como caso base ya documentado en adjuntos
- Middle School como escenario adicional que manejaría esquemas distintos, incluyendo separación entre 6th y 7th/8th

## Alcance entendido en esta etapa
El alcance de esta etapa fue de levantamiento funcional, no de implementación técnica ni de definición cerrada de arquitectura.

## Alcance esperado para evaluación por proveedor
Se espera que un proveedor pueda revisar este material para estimar al menos:
- entendimiento del problema
- complejidad funcional
- supuestos clave
- viabilidad de una primera fase
- necesidades de información adicional
- propuesta de aproximación técnica o metodológica
- estimación preliminar de esfuerzo, tiempos y riesgos

## Dependencias e insumos esperados
La evaluación del proveedor debe asumir que la calidad del resultado dependerá de la disponibilidad y estructura de insumos como:
- catálogo de cursos
- número de secciones por curso
- asignación docente por curso o sección
- reglas de bloques, días y esquemas
- restricciones de convivencia estudiantil
- restricciones docente-estudiante
- capacidad y disponibilidad de salones
- reglas de simultaneidad, coplanificación y uso compartido de espacios
- información histórica útil para comparación o entrenamiento operativo

## Preguntas que el proveedor debería ayudar a responder
- cuál debería ser la arquitectura funcional mínima del motor
- qué partes del problema conviene resolver primero
- qué inputs deben normalizarse antes de automatizar
- qué reglas conviene parametrizar desde el inicio y cuáles dejar para fases posteriores
- cómo separar núcleo de generación, validación y reportería
- qué combinación de configurabilidad, mantenibilidad y esfuerzo es razonable para Columbus

## Evidencia de cierre conversacional
- Juan Pablo: `Si entendido, procede con el cierre`
- Perla: `Perfecto, entonces queda cerrada esta etapa`

## Resultado del levantamiento
La necesidad quedó suficientemente aterrizada para:
- formalización posterior
- priorización
- eventual paso a diseño de solución o MVP
- revisión por proveedor para dimensionamiento y propuesta

## Observación importante
Aunque Perla sí cerró la etapa en conversación, no existía carpeta real con archivos base en `shared-drive` al momento de la validación. Esta carpeta corrige ese faltante documental y ya incorpora adjuntos relevantes para soportar evaluación externa.
