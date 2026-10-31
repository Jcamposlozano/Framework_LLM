# Decisiones de la Fase 1

## Límites

`extracteval` es una biblioteca independiente con distribución y versión propias. No se ha inspeccionado ni modificado ningún repositorio externo. Solo Pydantic es una dependencia de ejecución.

`core` contiene datos y puertos, no llamadas a modelos ni componentes científicos implementados. `adapters.models.mock` depende de esos contratos. No existe dependencia inversa. Los puertos de almacenamiento no tienen implementación en esta fase.

La fase 1 dejó la composición de extracción y verificación para fases posteriores. La fase 2, descrita al final, implementa extracción A, verificación y reconciliación; la calibración sigue pendiente. Consulta [el extractor A](extractor-a.md) para su integración. La configuración permite bindings diferentes para extractor y verificador.

## Valores y estados

Se reemplaza el enum inicialmente propuesto de múltiples estados por dimensiones ortogonales. `indeterminado` es un valor cuando el diccionario lo define; no se infiere abstención por el texto de una categoría. No existe un estado clínico universal ni reconocimiento especial de categorías.

La operación fallida exige un error técnico y prohíbe valor y abstención. La operación completada prohíbe error técnico. Abstenerse prohíbe un valor. La evidencia puede evaluarse independientemente; una salida sin sustento puede conservarse como valor para su futura evaluación de errores. No se presupone que una salida completada sea correcta.

Los valores etiquetados evitan confundir booleanos con números y fechas con texto. `validate_against` comprueba el diccionario explícitamente; no ejecuta todavía instrucciones de interpretación ni reglas de normalización.

## Referencia independiente

La anotación experta no hereda de una respuesta de modelo ni de una extracción. Registra evaluador, cegamiento declarado, diccionario, partición y evidencia. El adjudicado exige al menos dos anotadores distintos, el mismo campo y partición, declaración coherente de desacuerdo y resolución explícita. El valor final puede diferir de ambos anotadores.

El cegamiento es una declaración auditable, no una garantía técnica. Las particiones etiquetadas no implementan separación por entidad ni prevención completa de fuga: eso requiere el diseño de muestreo y los flujos de fases posteriores. En Fase 1 no se ajustan reglas, modelos ni umbrales.

## Reproducibilidad

Los artefactos usan identificador, versión y SHA-256. La configuración tiene una huella canónica local (JSON ordenado, formato de contratos 1.0), no un estándar de canonicalización entre lenguajes. El manifiesto identifica ejecución, configuración, tiempos, repetición, modelos y artefactos. Puede representar también tareas sin modelos.

La identidad del modelo admite una versión desconocida mediante `None`; el registro de ejecución exige entonces `model_version_unavailable` y prohíbe declarar reproducibilidad exacta. No se inventan versiones para completar metadatos. Las semillas solo pueden solicitarse cuando las capacidades lo permitan. Los mocks garantizan su contenido bajo condiciones documentadas, no tiempos idénticos.

Los puertos de fase 1 especifican conservación sin sobrescritura. La fase 2 añade almacenamiento JSON inmutable para sus ejecuciones. Los consumidores conservan instantáneas serializadas; `frozen=True` no congela profundamente metadatos arbitrarios.

## Extensión prevista

1. Diccionarios JSON o estructuras Python, validados sin ejecutar código de configuración.
2. Adaptadores por inyección de `ModelPort`, con SDK confinados a extras opcionales.
3. Evaluación a partir de resultados y referencias importados, sin construir adaptadores.
4. Reglas y políticas registradas explícitamente por identificador.
5. Aplicaciones de dominio en repositorios consumidores.

## Correspondencia metodológica futura

| Etapa | Responsabilidad futura |
|---|---|
| Especificación operacional | Registro, normalización y reglas configurables |
| Diseño estadístico | Muestreo, unidades, pesos y particiones por entidad |
| Estabilidad | Repeticiones controladas y perturbaciones |
| Referencia independiente | Flujos de anotación y adjudicación |
| Validez | PGEC, comparación pareada e incertidumbre agrupada |
| Calidad | Señales observables y taxonomía de errores |
| Fiabilidad | Entrenamiento, calibración y evaluación separadas |

Son capacidades combinables, no siete pasos obligatorios de ejecución.

## Alcance previsto después de Fase 1

Registro y carga de diccionarios, aplicación de reglas, normalización de salida textual, extractor genérico, configuración de esquemas de salida y selección justificada de un primer adaptador real opcional. Ninguno se implementa en Fase 1. PGEC y calibración permanecen en sus fases posteriores.

## Fase 2 (0.2.0)

`core/verification.py` añade contratos documentales sobre los existentes: A agrupa `ExtractionResult` por variable, conserva auxiliares y referencia el diccionario. Los estados semánticos son ortogonales al error técnico; B registra decisiones y no sustituye la referencia experta.

`application/verification.py` recibe un `ModelPort` y expone `verify_independently(document, dictionary, verifier_config)` sin extracción A. Construye un documento nuevo con una lista explícita de metadatos permitidos. `comparison.py` compara en código y `reconciliation.py` aplica una política externa. `pipeline.py` persiste antes de avanzar y verifica huellas al reanudar. `configuration.py` interpreta configuración externa y entorno sin introducir dependencias de infraestructura en el núcleo.

Los adaptadores HTTP, mock y JSON están en `adapters/`. El cliente OpenAI no requiere el SDK. El almacenamiento crea archivos sin reemplazarlos. `scripts/verificacion_laboratorio.py` conecta los procedimientos con el laboratorio YAML/JSON, conserva su diccionario y añade seguimiento técnico separado de sus siete etapas. EPOC permanece en configuraciones externas.

La guía [Fase 2 en el laboratorio](fase2-verificacion-laboratorio.md) describe contratos de entrada, comandos, trazabilidad y límites. La documentación de fase 1 registra el alcance histórico de aquella entrega, anterior a estos módulos.

La auditoría técnica añade comprobación del vínculo diccionario–fuente y prompt–versión en la entrada del laboratorio, y aplica la protección contra enlaces también al escaneo de integridad. Las nuevas importaciones de A plana referencian el esquema real de `ExtractionResult` y conservan la configuración de adaptación en un artefacto separado. No se cambiaron contratos públicos, modelos, prompts ni políticas científicas. Véase [la auditoría](phase2-audit.md).

## Fase 3: coordinación y análisis de estabilidad

`application/stability.py` coordina los casos A/V/B existentes y reserva intentos de generación; `stability_analysis.py` compara resultados por documento y modalidad. `scripts/estabilidad_laboratorio.py` verifica planes YAML, hashes y selección, y publica los artefactos descriptivos. No cambia los contratos públicos ni añade otro reconciliador. La [guía de Fase 3](phase3-stability.md) detalla reanudación, denominadores y la activación separada de la ruta real.
