# Requerimientos funcionales - Motor de horarios

## Estado del documento
Documento de formalización posterior al cierre del levantamiento funcional. Resume y estructura los requerimientos entendidos a partir de la conversación validada con Juan Pablo y los adjuntos revisados.

## Objetivo
Definir los requerimientos funcionales iniciales para una solución de generación de horarios académicos que reduzca la dependencia del trabajo manual y permita operar escenarios diversos de forma parametrizable.

## Objetivo de negocio
Contar con una solución que permita construir y gestionar horarios académicos por escuela, grado y año escolar, con reglas configurables y capacidad de validación antes de publicar resultados.

## Alcance funcional entendido
La solución debe comportarse como un motor de horarios capaz de recibir información estructurada, aplicar reglas configurables y producir salidas utilizables por la operación académica.

## Requerimientos funcionales

### RF-01. Parametrización por contexto académico
El sistema debe permitir configurar reglas y estructuras diferenciadas por:
- escuela
- grado
- año escolar

### RF-02. Gestión de inputs canónicos
El sistema debe permitir registrar, importar o administrar los insumos base requeridos para la construcción del horario en un formato estructurado y consistente.

### RF-03. Definición y gestión de esquemas
El sistema debe permitir crear, editar y mantener esquemas de construcción de horarios que sirvan como base para distintos escenarios.

### RF-04. Construcción de horario maestro
El sistema debe permitir generar un horario maestro a partir de los insumos definidos y de las reglas configuradas.

### RF-05. Asignación de estudiantes
El sistema debe contemplar la asignación de estudiantes dentro de la estructura horaria generada, de acuerdo con los criterios y restricciones definidos.

### RF-06. Validación de escenarios
El sistema debe permitir validar escenarios antes de su adopción, identificando inconsistencias, conflictos o incumplimientos de reglas.

### RF-07. Manejo de escenarios alternos
El sistema debe soportar la creación o evaluación de múltiples escenarios de horario para facilitar análisis, comparación y toma de decisiones.

### RF-08. Salidas estructuradas
El sistema debe generar salidas estructuradas que permitan usar el resultado del horario en procesos posteriores, revisión operativa o comunicación interna.

### RF-09. Trazabilidad de configuración
El sistema debe permitir reconocer con qué parámetros, reglas o esquema fue generado cada escenario de horario.

### RF-10. Revisión operativa
La solución debe permitir que el resultado generado pueda ser revisado por usuarios responsables antes de considerarse definitivo.

### RF-11. Configuración de bloques, días y rotaciones
El sistema debe permitir modelar calendarios académicos con días nombrados, bloques y secuencias de rotación configurables.

### RF-12. Reserva de franjas fijas
El sistema debe permitir bloquear franjas específicas para actividades obligatorias, por ejemplo espacios como Advisory que no admiten sustitución por otros cursos.

### RF-13. Restricciones de carga docente
El sistema debe permitir aplicar reglas sobre carga y continuidad docente, incluyendo límites de clases consecutivas y restricciones por bloque o día.

### RF-14. Coplanificación docente
El sistema debe permitir expresar y validar necesidades de tiempo simultáneo libre para pares o grupos de profesores que requieran coplanificación.

### RF-15. Balanceo entre secciones
El sistema debe permitir distribuir estudiantes entre secciones procurando balance por cupo y criterios definidos por la institución.

### RF-16. Restricciones de convivencia y agrupación estudiantil
El sistema debe permitir modelar restricciones para separar o agrupar estudiantes según prioridades institucionales.

### RF-17. Restricciones docente-estudiante
El sistema debe permitir incorporar información que sugiera evitar determinadas combinaciones entre estudiantes y profesores cuando aplique.

### RF-18. Gestión de salones y recursos compartidos
El sistema debe permitir asignar salones bajo restricciones de capacidad, disponibilidad, propiedad y uso compartido.

### RF-19. Simultaneidad entre cursos o áreas
El sistema debe permitir modelar casos donde cursos distintos deban ocurrir al mismo tiempo o compartir condiciones operativas específicas.

### RF-20. Generación progresiva por fases
El sistema debe soportar al menos dos momentos funcionales distintos: generación inicial de horario base y posterior asignación o ajuste de estudiantes.

## Información que un proveedor debería solicitar o validar
Para poder dimensionar bien la solución, un proveedor debería validar al menos:
- definición exacta de actores usuarios
- estructura del catálogo de cursos
- estructura de secciones y relación curso-profesor
- modelo de bloques, días y rotaciones por escuela
- reglas duras vs reglas deseables
- formato y calidad de los insumos actuales
- necesidad de integraciones
- expectativas de salidas y reportes
- trazabilidad esperada de cambios y versiones

## Reglas de negocio inferidas
- La solución no debe depender de un único modelo rígido de operación.
- La parametrización debe soportar diferencias reales entre escuelas, grados y periodos académicos.
- La validación de escenarios es parte del proceso funcional, no un paso opcional aislado.
- La salida del motor debe ser suficientemente estructurada para habilitar uso operativo posterior.
- Debe existir capacidad de distinguir restricciones obligatorias de criterios deseables.
- La construcción del horario no es solo académica: también depende de disponibilidad docente, convivencia estudiantil y uso de salones.

## Criterios sugeridos para evaluación de proveedor
Un proveedor debería ser evaluado por su capacidad de responder con claridad sobre:
- entendimiento del problema multivariable
- estrategia para modelar reglas y excepciones
- propuesta de parametrización mantenible
- manejo de restricciones duras y blandas
- enfoque de implementación por fases
- estrategia de validación con usuarios reales
- dependencia o no de optimización compleja desde la fase inicial

## Supuestos actuales
- Este documento consolida requerimientos iniciales, no una especificación exhaustiva final.
- Aún no se ha documentado aquí el detalle técnico de integración con otros sistemas.
- La priorización por fases o MVP deberá definirse en una siguiente etapa si la iniciativa se retoma.
- El caso de High School funciona hoy como referencia importante, pero no debe asumirse como única estructura futura.

## Pendientes para una siguiente fase
- precisar actores y perfiles usuarios
- definir entradas exactas requeridas por el motor
- documentar restricciones operativas detalladas
- priorizar MVP
- definir salidas esperadas por audiencia o proceso
- aterrizar criterios de validación específicos
- identificar reglas comunes y reglas particulares por escuela
- decidir qué debe ser configurable por negocio sin depender de desarrollo

## Relación con el cierre aprobado
Este documento es coherente con el cierre ya aceptado por Juan Pablo y formaliza en lenguaje documental la solución funcional entendida por Perla en la etapa de levantamiento, fortalecida con material adicional útil para evaluación por proveedor.
