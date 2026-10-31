# Fase 3: estabilidad y reproducibilidad

RESULTADOS SINTÉTICOS DE PRUEBA — NO CONSTITUYEN EVIDENCIA DE ESTABILIDAD DEL LLM.

## Implementado y conectado

El coordinador `src/extracteval/application/stability.py` llama a `extract_document`
y a `run_verification`, que conserva el verificador, comparador y reconciliador
existentes. No se cambian contratos públicos, diccionario, prompts, PGEC, política,
particiones, criterios clínicos ni autorizaciones científicas.

`stability_analysis.py` obtiene observaciones de `ExtractionSnapshot` y
`ReconciledExtraction`; no depende de un proveedor. `estabilidad_laboratorio.py`
valida YAML, referencias y hashes, construye exclusivamente los adaptadores mock
cuando corresponde y exporta resultados e informe.

- **Completa:** una A nueva y una V nueva por documento y repetición; B referencia
  exactamente la A de esa repetición.
- **A_fija:** una A por documento y cinco V independientes, cada una reconciliada
  con la misma A. Su invariabilidad es estructural, no una estimación empírica.
- Cada repetición tiene identidad estable dentro de un experimento UUID. Reanudar
  reutiliza identidades y artefactos: no añade filas ni consume nuevos intentos.
- Los dos modos se analizan por separado, sin inferencia confirmatoria.

## Comandos disponibles

Desde la raíz, con el paquete actualizado instalado:

```sh
.venv/bin/python scripts/laboratorio.py preparar-estabilidad --laboratorio laboratorios/mi_estudio_001
.venv/bin/python scripts/laboratorio.py validar-estabilidad --laboratorio laboratorios/mi_estudio_001
.venv/bin/python scripts/laboratorio.py ejecutar-estabilidad --laboratorio laboratorios/mi_estudio_001
.venv/bin/python scripts/laboratorio.py informe-estabilidad --laboratorio laboratorios/mi_estudio_001
```

`ejecutar-estabilidad` acepta `--ejecucion` (predeterminado `piloto-mock-v1`) y
`--modo mock|real`, cuyo predeterminado es siempre `mock`. Repetir el comando sobre
el mismo destino reanuda. Una repetición experimental es otra ranura del plan,
no una reanudación del proceso. El exportador no reemplaza resultados de otro
experimento automáticamente. `preparar-estabilidad` respalda el borrador anterior
y no sustituye un plan diferente que ya tenga resultados.

## Configuración final

Los 10 documentos y las 5 repeticiones son valores operativos provisionales,
no un cálculo muestral. El archivo de entrada contiene notas inventadas y guiones
explícitos de respuestas para provocar categorías cambiantes, fechas diferentes,
abstenciones, falta de respuesta, evidencia inválida y fallos técnicos.
Las referencias proceden de archivos reales y sus SHA-256 se comprueban al cargar.
El diccionario y los modelos solicitados son los existentes; los modelos efectivos
del piloto son `mock-extractor` y `mock-verifier`.

Contenido completo de `03_estabilidad/estabilidad.yaml`:

```yaml
estudio_id: epoc-stability-technical
version: stability-pilot.v1
modo: mock
finalidad: piloto_tecnico_no_confirmatorio
subconjunto:
  tipo: sintetico
  documentos_objetivo: 10
  documentos_ids:
  - synthetic-stability-001
  - synthetic-stability-002
  - synthetic-stability-003
  - synthetic-stability-004
  - synthetic-stability-005
  - synthetic-stability-006
  - synthetic-stability-007
  - synthetic-stability-008
  - synthetic-stability-009
  - synthetic-stability-010
  archivo:
    ruta: 03_estabilidad/documentos_sinteticos.v1.json
    version: stability-fixtures.v1
    sha256: e1f5ce1a6823fa7e6328ab975ac00161b88cb99543b0cfecf19eed9861625c6d
  criterio_seleccion: Diez casos inventados con guiones explícitos de variación; sin datos reales.
  uso: desarrollo_tecnico
repeticiones:
  cantidad_por_documento: 5
  modalidades:
  - id: completa
    regenerar_A: true
    regenerar_V: true
    reconciliar_B: true
  - id: A_fija
    regenerar_A: false
    regenerar_V: true
    reconciliar_B: true
  ejecuciones_independientes: true
  reanudacion_no_cuenta_como_repeticion: true
configuracion_fija:
  extractor:
    ruta: configuraciones/extraccion/v1/config.json
    version: lab-extractor-v1
    sha256: 5a7a07de5d5740157f82246e7127605095e4eac50390cc0f029cecce3a4f07c4
  verificador:
    ruta: configuraciones/verificacion/v1/config.json
    version: lab-phase2-v1
    sha256: 786c87a362b5bd6272d5e78de9dff5dcc064f67f5013fcda8902dd56a754f2a1
  archivos:
    prompt_A:
      ruta: configuraciones/extraccion/v1/extractor_v1.txt
      version: clinical-extractor.v1
      sha256: 2ffe1fb39905bb106a6663ba647de2bd58dc866f8fb41ce34663eb7c84909e7d
    prompt_V:
      ruta: configuraciones/verificacion/v1/verificador.v1.txt
      version: independent-verifier.v1
      sha256: cd5d64eb7f395e7a374e2cd48ba475b933a9a450a0c2cc34074d2dda52fbd2fe
    diccionario:
      ruta: configuraciones/verificacion/v1/diccionario.json
      version: 1.0.0-draft
      sha256: cdafcd00d24dbbbebcc284424a582d60f6ba3ef9c5aa8ff8d21489c445f3efbd
    politica:
      ruta: configuraciones/verificacion/v1/politica.json
      version: conservative.v1
      sha256: 6ef48ae4b249ace36254e0f8a19afdb536a3d06ee5370b11a0c2676e2cc2eb65
    especificacion_fuente:
      ruta: 01_especificacion/especificacion.yaml
      version: 1.0.0-draft
      sha256: 3f6ad5e592c39d1125815c063895087f4fe66d5bb2778ca7e9236aa5a12b0101
    posprocesamiento_A:
      ruta: ../../src/extracteval/application/extraction.py
      version: extraction-mapping.v1
      sha256: fa4d75f34adee8da736c55d39e8c10fdb52bddfcbca8cc3d4278e826ab4d3a53
    coordinador:
      ruta: ../../src/extracteval/application/stability.py
      version: stability.v1
      sha256: 415bb820503e45d0426ebcdd8ecdb17611095e42964742c2027f09307cef8603
    analisis:
      ruta: ../../src/extracteval/application/stability_analysis.py
      version: stability-analysis.v1
      sha256: 656af6de65040ce64d681a0cd59ebad6ae6452e78ff43e53e84697d951f9809f
  diccionario:
    contract_version: '1.0'
    artifact_id: epoc_exacerbation_extraction
    version: 1.0.0-draft
    sha256: d104de50e839bac1b54f3424595960a064276358993c9c8357a40976e9636a5c
  contratos:
    Document:
      contract_version: '1.0'
      sha256_canonico: 56f2a9677ac766c36b160b989cab5e9a1b506e7432b9362958f871b1c9787d82
    ExtractionResult:
      contract_version: '1.0'
      sha256_canonico: 05c29a1a3765b230f635a518c1d14a4ced8a42a3df6e616c90cca5ab7aa2d984
    ExtractionSnapshot:
      contract_version: '1.0'
      sha256_canonico: e05d6310dca784dc9f5411917a9e61cf63a5a5bbae156a95bcf2da244b5e722b
    ExperimentConfig:
      contract_version: '1.0'
      sha256_canonico: 757b1494f74a358e418d3aa9667244813c763e26827580ee97091a836ed720c3
    ModelBinding:
      contract_version: '1.0'
      sha256_canonico: 83cc598d855882263ad100cd54bdcbb1aa18e9fd19ce2f4a0475c22837cfbd8a
    ReconciledExtraction:
      contract_version: '1.0'
      sha256_canonico: 952a2592ca018f0663330ee45b49c9e9ab54c28548a281c8b86f4f2e6f793cc0
    respuesta_estructurada:
      contract_version: '1.0'
      artifact_id: extracteval.core.verification.VerificationPayload
      version: '1.0'
      sha256: 109118f244bd07d15ee68cb1b8dc108a5e1c35e9920de0c2c28aa0f298e8b488
    posprocesamiento:
      contract_version: '1.0'
      artifact_id: extracteval.application.extraction
      version: extraction-mapping.v1
      sha256: fa4d75f34adee8da736c55d39e8c10fdb52bddfcbca8cc3d4278e826ab4d3a53
  modelos_solicitados:
    A: gpt-4.1-mini
    V: gpt-4.1-mini
  reconciliacion_version: conservative.v1
  verificar_hashes: true
perturbaciones: []
condiciones_constantes:
- mismo_documento_por_repeticion
- misma_configuracion_de_modelos
- mismos_prompts_y_diccionario
- mismo_esquema_de_salida
- misma_politica_de_reconciliacion
- verificacion_independiente
- A_inmutable_en_cada_ejecucion
metricas_planificadas:
- acuerdo_exacto_por_variable
- acuerdo_registro_completo
- documentos_invariables
- categorias_observadas
- variacion_fecha_indice
- tasa_abstencion
- tasa_fallos_tecnicos
- frecuencia_cambio_decisiones_B
- diferencia_estabilidad_A_B
incertidumbre:
  estado: pendiente_diseno_confirmatorio
  unidad_agrupacion: documento
  repeticiones_no_independientes: true
  intervalos_confianza: no_calcular_en_piloto
  nota: 10 documentos y 5 repeticiones son valores operativos provisionales, no un cálculo muestral.
presupuesto:
  max_llamadas: 160
  reintentos_automaticos: 0
  limite_gasto_estimado: null
ejecucion_real_habilitada: false

```

## Métricas y denominadores

El acuerdo exacto exige igualdad del valor tipado y estado semántico. Los pares
son no ordenados y siempre pertenecen al mismo documento y modalidad. Se excluyen
pares con fallo técnico o falta de respuesta, registrando esas tasas por separado.
Indeterminaciones y abstenciones explícitas siguen siendo estados observables:
acuerdo entre ellas no equivale a valor clínico determinado ni a acierto.

También se informa acuerdo operativo sobre todos los pares, incluyendo errores;
no debe interpretarse como acuerdo semántico. Todos los numeradores, denominadores
y cocientes se guardan en JSON. Sin denominador, la proporción es `null`.

- Documentos invariables: documentos con al menos dos repeticiones y todas elegibles.
- Categorías: frecuencias observadas y denominador de valores categóricos no nulos.
- Tasas de abstención, indeterminación, falta de respuesta y fallo: todos los resultados
  documento-repetición del sistema y modalidad; los estados no se mezclan.
- Registro completo: pares con las seis variables elegibles en ambas repeticiones.
- Fechas: coincidencia entre pares con dos fechas válidas; número de fechas distintas,
  rango máximo menos mínimo en días y número de fechas válidas por documento.
- Contraste A/B: diferencia descriptiva de acuerdos sobre exactamente los mismos
  pares elegibles para ambos sistemas, disponible en `contraste_pareado`.
- Decisiones B: pares de repeticiones por variable; cambios de categorías A/B:
  resultados emparejados categóricos válidos dentro de cada repetición.

Los perfiles identifican las variables que explican diferencias. No se calcula
PGEC, exactitud, sensibilidad, calibración ni intervalos confirmatorios.

## Ejemplo ejecutado y probado

Experimento `stability-025bcb511fba46d28728b3a5875380ea`, realizado con mocks:

- 10 documentos, dos modalidades y cinco repeticiones: **100 filas experimentales**.
- 60 intentos A y 100 intentos V: **160 generaciones simuladas**.
- 157 respuestas guardadas; tres fallos de timeout programados y conservados.
- 97 repeticiones sin fallo y tres con fallo técnico; ninguna historia real procesada.
- La reanudación conserva las mismas 100 filas y los mismos 160 intentos.

| Medida del guion sintético | Completa A | Completa B |
|---|---:|---:|
| Acuerdo de estado_paciente | 90/96 | 90/96 |
| Acuerdo de fecha_indice_evento y estado | 80/92 | 80/92 |
| Acuerdo del registro completo | 74/92 | 74/92 |

La modalidad A_fija tiene acuerdo completo 100/100 por construcción y conservación
de A. Aun así, las decisiones B cambian en 18/600 pares-variable por variación
programada de V. El caso de fechas cambiantes tiene dos fechas distintas con
rango de dos días. Estos números describen guiones de prueba, no un LLM.

Resultados y reporte legible se encuentran en `03_estabilidad/resultados.json` y
`03_estabilidad/informe.md`. Sus copias inmutables están en
`ejecuciones/estabilidad/piloto-mock-v1/`, junto con el índice, los artefactos A/V/B,
intentos, respuestas, recibos y `integridad.json` con hashes de los archivos.
El JSON conserva las listas `ejecuciones`, `perfiles`, `concordancia` y
`conclusiones: null`; amplía el esquema con procedencia, denominadores y consumo.

## Persistencia, límites y recuperación

El almacenamiento existente impide sobrescribir artefactos con contenido diferente.
Se verifican los manifiestos A/V/B y un inventario de archivos de todo el experimento
al reanudar. El ledger reserva cada llamada antes de generar, con bloqueo POSIX para
la reserva de presupuesto, y guarda la respuesta y su recibo hash antes de devolverla.
Una V interrumpida después de guardar su respuesta puede recuperarla sin llamar de
nuevo al modelo. Una A completa se recupera del manifiesto existente.

La interrupción de A durante una llamada, antes de completar sus artefactos, conserva
la protección anterior: no se reenvía automáticamente. La ranura queda marcada
`interrupted`, requiere inspección manual y no se cuenta como una observación en las
métricas. No se convierte una llamada de resultado desconocido en otra repetición.
Los fallos terminales persistidos tampoco se reintentan automáticamente.

El piloto es secuencial. No promete recuperación automática de una respuesta de A
que nunca llegó a persistirse ni ejecución distribuida. Los hashes comprueban
consistencia local, no constituyen firma contra un atacante que reescriba todos los
archivos y sus manifiestos.

## Ruta real preparada, deshabilitada y no ejecutada

El CLI requiere simultáneamente un plan explícito con `modo: real`, habilitación
real en ese plan, `--modo real`, `--activar-real` y `--autorizacion-real ARCHIVO`.
El documento de autorización debe coincidir con el hash del plan y de la selección,
incluyendo autorizaciones de gobernanza vinculadas a cada documento. Solo después
se construye el adaptador existente y se lee `OPENAI_API_KEY`. El modo mock ignora
credenciales disponibles y solo admite los adaptadores simulados incorporados.
No se ha solicitado ni utilizado ninguna credencial real.

La ruta permite cambiar subconjunto, repeticiones, modalidades y configuraciones
mediante un nuevo plan explícito. El presupuesto limita intentos lógicos `generate`
de A/V, incluyendo fallos; no cuenta cada petición HTTP interna como otra generación.
Los reintentos automáticos están deshabilitados para evitar envíos duplicados tras
un timeout. Se conservan modelos efectivos, errores, respuestas y tokens reportados.

El límite de gasto estimado solo se admite con moneda, tarifas versionadas y límites
de tokens. Se comprueba una estimación conservadora antes de ejecutar y un filtro
local por bytes con margen adicional por solicitud. Este filtro no es un tokenizador
oficial, ni el límite constituye una garantía de facturación. El gasto real queda
sin verificar; hacen falta precios aplicables y revisión presupuestaria antes de
activar un experimento real. Los mocks no generan consumo real de tokens.

## Probado y pendiente

Pruebas automáticas sin conectividad: ambas modalidades, A fija, IDs, inmutabilidad,
reanudación, respuesta V recuperada, hashes, independencia de V, fallos, fechas,
categorías, estados nulos distintos, denominadores calculados a mano, contraste
pareado, JSON, informes, presupuestos y bloqueo de modo real y transporte HTTP.
Los detalles finales se registran en `03_estabilidad/implementacion_fase3.json`.

Pendiente: seleccionar y autorizar documentos para una ejecución real, revisar los
presupuestos y tarifas, comprobar acceso al modelo con autorización, aprobar las
transformaciones documentales y completar las decisiones metodológicas del diseño.
`VariantRecord` define procedencia versionada de variantes, hashes y aprobación;
no existe un transformador clínico automático y el ejecutor rechaza perturbaciones.

Las repeticiones no son pacientes independientes. Una salida estable puede repetir
un error. La política conservadora preserva A cuando requiere revisión; por ello,
igual estabilidad de A y B no demuestra eficacia clínica de la verificación.
