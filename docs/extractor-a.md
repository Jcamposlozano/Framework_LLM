# Extractor A e integración documental A → V → B

La [guía de extracción personal sintética](primera-extraccion-personal-sintetica.md)
documenta la autorización adicional limitada al fixture verificable
`demo-extractor-epoc-001`. Conserva el modo institucional para documentos clínicos y
no habilita llamadas por defecto. El resto de este documento describe la integración
y los controles institucionales de la entrega original.

Implementado el 19 de octubre de 2026. Pruebas exclusivamente sintéticas: no se han
procesado las 5.924 notas del estudio ni realizado llamadas a OpenAI. La configuración
implementada no equivale a validación científica ni autoriza evaluación confirmatoria.

## Configuración independiente

`laboratorios/mi_estudio_001/configuraciones/extraccion/v1/config.json` configura
OpenAI, `gpt-4.1-mini`, salida estructurada, 4096 tokens y timeout de 60 segundos.
No solicita seed ni temperatura. El CLI desactiva reintentos de proveedor para A;
un fallo queda registrado y una nueva tentativa necesita una ejecución explícita.

La credencial se obtiene de `OPENAI_API_KEY`. Las sobrescrituras admitidas son
`EXTRACTEVAL_EXTRACTOR_MODEL`, `EXTRACTEVAL_EXTRACTOR_MAX_OUTPUT_TOKENS` y
`EXTRACTEVAL_EXTRACTOR_REQUEST_TIMEOUT`; no afectan a V. Se guardan configuración
resuelta, parámetros solicitados y efectivos, identidad devuelta por el proveedor,
identificadores, uso y errores seguros. Nunca se guardan claves.

El diccionario se referencia desde `configuraciones/verificacion/v1/diccionario.json`:
no se crea otro diccionario ni se cambian sus definiciones. Se verifican su identidad,
digest canónico y la vinculación de la fuente preparada en el puente del laboratorio.

El prompt `clinical-extractor.v1` está en
`templates/laboratorio/01_especificacion/prompts/extractor_v1.txt`; su copia versionada
está en `configuraciones/extraccion/v1/extractor_v1.txt`. Su SHA-256 es
`2ffe1fb39905bb106a6663ba647de2bd58dc866f8fb41ce34663eb7c84909e7d`.
Es procedural: las definiciones, categorías, políticas y reglas proceden del diccionario.

## Contratos y conversión

`application/extraction.py` recibe `Document`, `OperationalDictionary`, configuración,
prompt, `ModelPort` y el almacén existente. El contenido enviado excluye procedencia,
identidad de paciente y metadatos no autorizados. La fecha documental sigue siendo
fecha de atención.

Se reutiliza `VerificationPayload` como esquema intermedio de propuestas; su nombre
no implica ejecutar el verificador. A tiene su propia solicitud, prompt, identidad
simulada, auditoría y almacenamiento. `OpenAIResponsesModel` acepta `schema_name`;
su valor predeterminado de V permanece `independent_verification`.

La aplicación exige exactamente las variables del diccionario, sin duplicados ni
variables adicionales. Las cinco variables categóricas usan cadenas, incluyendo
`"true"` y `"false"`; la fecha usa `DateValue` o ausencia de valor con estado explícito.
Un fallo técnico produce seis resultados fallidos, sin estados clínicos inventados.

Cada propuesta válida se convierte en `ExtractionResult` con `ResultTrace`,
`EvidenceAssessment`, `ValidationFinding` y, cuando corresponde, `Abstention`.
Las abstenciones requieren un motivo explícito. Evidencia literal no coincidente
genera advertencias sin sustituir el valor; una referencia a otro documento invalida
la respuesta estructuralmente. La presencia de una cita no acredita suficiencia clínica.
Los detalles de propuestas, reglas indicadas e incertidumbre se conservan en auditoría
y auxiliares. No se inventan políticas para decisiones clínicas pendientes.

Los seis resultados forman una `ExtractionSnapshot` con estados y hash del documento.
La conversión `extraction-mapping.v1` registra el SHA de su implementación.
Se distinguen el esquema de respuesta del modelo y el contrato persistido
`ExtractionResult`, ambos con hashes reales. Los contratos públicos no se modifican.

`ExperimentConfig` conserva el binding solicitado; una configuración efectiva separada
registra la identidad realmente devuelta. Cada resultado valida su traza contra esta
última. Las ejecuciones mock registran `mock-extractor`; el modelo configurado OpenAI
permanece documentado separadamente, sin atribuirle las respuestas de prueba.

## Uso local

Desde la raíz del repositorio, con el paquete actual instalado:

```sh
.venv/bin/python scripts/laboratorio.py preparar-extractor --laboratorio laboratorios/mi_estudio_001
.venv/bin/python scripts/laboratorio.py demo-extractor --laboratorio laboratorios/mi_estudio_001
```

La demostración usa un documento inventado independiente del corpus, ejecuta A mock,
registra el JSON tipado mediante `register_original`, obtiene V de otra instancia
mock y ejecuta la comparación y reconciliación existentes. No cambia la configuración
ni el fixture de V. Artefactos:

```text
ejecuciones/fase2/demo-extractor-v1/
  a/request.json
  a/execution.json
  a/extraction_a.json
  a/manifest.json
  b/verification.json
  b/comparison.json
  b/decisions.json
  b/extraction_b.json
  b/manifest-all.json
  demostracion.json
```

El registro conserva además `a-original.json`, `entrada.json` y `registro.json` en
una carpeta identificada por hash dentro de `datos/verificacion/`; no modifica
`datos/documentos.json`. El parámetro opcional `document` de `register_original`
permite registrar esta nota sintética sin añadirla al inventario clínico.

El CLI de paquete también permite una nota individual:

```sh
extracteval extract --config CONFIG.json --input DOCUMENTO.json --output CARPETA_NUEVA --mode mock
```

El modo mock necesita un fixture explícito coherente con el documento; no interpreta
notas reales. El comando de laboratorio `ejecutar-extractor` selecciona un documento
por `--documento-id`, utiliza `--ejecucion` como destino y registra A por la misma vía
tipada. Su modo real exige `--autorizar-real`, `--gobierno` y credencial de entorno.
La autorización existente debe estar vinculada al hash del documento. La disponibilidad
del modelo se verifica antes de transmitir contenido. Ningún modo real se ha ejecutado
en esta entrega; no se inicia procesamiento masivo.

## Inmutabilidad y reanudación

`JSONRunStore` persiste sin sobrescribir contenidos diferentes. Antes de generar A
se registra la solicitud. Una ejecución completa se reanuda comprobando configuración,
documento, fixture, esquemas, implementación y hashes de todos sus artefactos; no llama
otra vez a A. Una ejecución interrumpida sin manifiesto se detiene para inspección,
evitando un segundo envío silencioso. Esta precaución puede requerir recuperación
manual si el proceso se interrumpe después de recibir una respuesta.

V recibe solo documento, diccionario y su configuración. Después de persistir V,
el pipeline compara exactamente la A registrada y genera decisiones B aparte.
Se conservan bytes originales, identidad y hash de A. La política `conservative.v1`
permanece intacta, sin reglas de reemplazo; las discrepancias requieren revisión.

## Evidencia de comprobación

`tests/test_extraction.py` cubre seis variables, tipos y dominios, fecha explícita y
desconocida, negación e incertidumbre en respuestas programadas, evidencia inválida,
abstenciones, errores, registro, separación A/V, comparación, reconciliación,
inmutabilidad, reanudación, integridad, CLI, identidad efectiva y YAML.
Estas pruebas comprueban mecánica y contratos, no la capacidad clínica de un LLM.

La demostración guardada tiene seis decisiones: dos `KEEP_A` y cuatro `HUMAN_REVIEW`.
Al repetirla no realiza nuevas llamadas mock. Los cinco campos de `extractor_base`
y el candidato técnico se documentan en `02_diseno/diseno.yaml`; selección,
resultados de desarrollo y aprobación científica siguen pendientes. La congelación
continúa bloqueada, con 22 decisiones pendientes.

El informe local `02_diseno/implementacion_extractor_a.json` registra comprobaciones,
hashes y artefactos entregados. Las auditorías anteriores describen el estado previo
a esta implementación y se conservan como historial.
