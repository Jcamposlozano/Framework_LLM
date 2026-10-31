# Auditoría, integración y consolidación de la Fase 2

Fecha: 19 de octubre de 2026. Estado: consolidación técnica de una versión de desarrollo; no aprobación clínica, selección ganadora ni congelación. Se comparó con la instantánea tomada al iniciar esta auditoría, conservando cambios locales anteriores.

## A. Estado real

| Componente | Implementado | Probado | Pendiente | Archivo principal |
|---|---|---|---|---|
| Diccionario EPOC | Sí: seis variables y dominios de la fuente YAML; revisión pendiente | Carga, tipos y coincidencia de definiciones con la configuración ejecutable | Aprobación clínica y decisiones temporales | `laboratorios/mi_estudio_001/01_especificacion/especificacion.yaml` |
| Extractor A | Parcial: contratos, importación de A externa, ejemplos y mocks; no se identificó un ejecutor LLM clínico | A estructurada de ScriptedModel, validación, archivo original íntegro e integración con V/B | Identificar/proporcionar el extractor ya seleccionado y su configuración real; no se creó otro | `scripts/verificacion_laboratorio.py::register_original`, `src/extracteval/adapters/models/mock.py` |
| Verificador V | Sí: lectura independiente y adaptadores real/mock | Interfaz sin A, metadatos permitidos, evidencia, errores y HTTP simulado | Prueba real autorizada y validación empírica | `src/extracteval/application/verification.py`, `src/extracteval/adapters/models/openai.py` |
| Comparador | Sí: determinista y por variable | Coincidencias, discrepancias, faltantes, normalización aprobada y consistencia | Reglas clínicas adicionales solo cuando estén aprobadas | `src/extracteval/application/comparison.py` |
| Reconciliador B | Sí: cuatro decisiones y política explícita | KEEP_A, REPLACE_WITH_VERIFIED, ABSTAIN y HUMAN_REVIEW en casos sintéticos | Reglas de reemplazo del estudio: ninguna aprobada | `src/extracteval/application/reconciliation.py` |
| Trazabilidad | Sí para A aportada, V, comparación, decisiones y B | Hashes, persistencia, recuperación, inmutabilidad y reanudación | Procedencia del LLM original de A cuando se aporte; no inferible del importador | `src/extracteval/application/pipeline.py`, `src/extracteval/adapters/storage/json_store.py` |
| Configuración YAML | Consolidada con datos técnicos verificables | Loader YAML y validaciones del diseño y contratos | Selección de configuraciones, presupuesto y congelación siguen pendientes | `laboratorios/mi_estudio_001/02_diseno/diseno.yaml` |
| Pruebas | 197 pruebas sintéticas disponibles | 197 correctas, 0 fallidas al cierre | API en vivo y evaluación científica fuera de esta auditoría | `tests/` |

La cadena ejecutable es **A aportada → V independiente → comparación → B**. El tramo **documento → A mediante el LLM clínico seleccionado** no se identificó en este checkout. Esto se determinó inspeccionando código, puertos, configuraciones, prompts, ejemplos y scripts; no se dedujo de campos null.

Se verificaron las variables `estado_paciente`, `exacerbacion_actual`, `exacerbacion_previa`, `fecha_indice_evento`, `precision_temporal` y `metodo_fecha`. Sus tipos y dominios coinciden entre fuente compilada y diccionario ejecutable; las definiciones clínicas no se modificaron.

### Extractor y configuración existente

No se encontraron proveedor, modelo, parámetros ni prompt clínico ejecutable de A. `ModelPort`, `ExperimentConfig.extractor`, `ExtractionResult` y `ExtractionSnapshot` sí existen. Los ejemplos de fase 1 usan ConstantModel/ScriptedModel y notas sintéticas; las plantillas de prompts del organizador legado son borradores. La demostración EPOC construye A como fixture, sin ejecutar un extractor LLM. Los hashes ilustrativos de esas fixtures no se trasladaron al diseño científico.

El importador admite A tipada o plana, valida tipos/dominios, conserva evidencia aportada, estados y campos auxiliares y guarda los bytes originales y su hash. La adaptación explícita de booleanos JSON a categorías no define una heurística clínica. Esa configuración de adaptación no describe al LLM que produjo A; los cinco campos de `extractor_base` permanecen pendientes por falta de evidencia verificable sobre ese LLM.

Para V, el archivo existente configura **OpenAI / gpt-4.1-mini**, `max_output_tokens=4096`, salida estructurada y timeout de 60 segundos. No se solicitan seed ni temperature. La CLI usa mock de forma predeterminada; la demostración persistida utilizó `mock-verifier`, versión 1. El modelo efectivo de la API no se conoce porque no se realizó una llamada real. El modelo configurado no se cambió.

El reconciliador es determinista: `reconciler_model: null` no indica ausencia del componente. La política vigente es `documentary-conservative`, versión `conservative.v1`, sin reglas de reemplazo autorizadas. El motor admite las cuatro decisiones, pero el estudio pendiente de aprobación conserva A y deriva discrepancias a revisión.

### Corpus e independencia

El informe de importación registra 5.924 filas de `datos/Texto Libre.xlsx`, hoja `Hoja1`, y 136 filas completamente vacías omitidas. El lector XLSX y su mapeo fueron inspeccionados; no se repitió la importación ni se ejecutaron modelos sobre el corpus. `ingreso` se seudonimiza y cada fila obtiene document_id propio; no se convierte en identidad de paciente.

`FECHA ATENCIÓN` se conserva en `Document.document_date` y su procedencia declara fecha de atención. El diseño ahora referencia ese campo técnico. No se infiere inicio del episodio. La agrupación por paciente queda pendiente para la evaluación estadística: no es un requisito de los casos de uso documentales A con mock, V, comparación o reconciliación, que están probados con entity_id ausente.

V recibe una nueva representación del documento, el diccionario y las instrucciones; no recibe A. Se descartan provenance, entity_id y metadatos no permitidos. El resultado independiente se persiste antes de comparar. El comparador no llama a un LLM y no interpreta el acuerdo como corrección clínica.

## B. Defectos comprobados y correcciones

1. **Diccionario desvinculable de su fuente.** Cambiar `dictionary_path` a otro diccionario válido con otra versión no era rechazado por la entrada del laboratorio. Ahora se compara su ArtifactRef con la fuente preparada, además de verificar el hash del contenido mediante el loader.
2. **Prompt modificable bajo la misma versión.** El contenido podía diferir de `prompt.json` manteniendo la versión declarada. Ahora se comprueban contenido y versión antes de cualquier ejecución del laboratorio. No se modificó el prompt existente.
3. **Protección de enlaces incompleta.** `get/put` rechazaban enlaces simbólicos, pero `artifact_hashes()` los seguía. Ahora el escaneo utiliza la misma validación de rutas y rechaza el enlace antes de leerlo.
4. **Esquema de importación con huella incorrecta.** La referencia del esquema se calculaba a partir de `{"version": 1}`. Las nuevas importaciones planas referencian el contrato existente `extracteval.core.results.ExtractionResult`, su versión real y el hash canónico de su JSON Schema.
5. **Configuración confundida con el archivo A.** El ConfigRef de adaptación utilizaba el hash de A. Las nuevas importaciones conservan `configuracion_importacion.json` con el mapeo, diccionario, esquema y hash de implementación; ConfigRef referencia ese contenido. El hash del archivo A continúa separado.

Los tres primeros defectos se reprodujeron con tres pruebas fallidas antes de corregirlos. La aserción añadida sobre el esquema de importación también falló antes de la corrección. Las pruebas originales no se eliminaron ni se relajaron. Las ejecuciones y A históricas no se reescribieron.

### Archivos modificados en esta auditoría

Rutas relativas al repositorio. Las escrituras automáticas del historial del laboratorio son respaldos, no resultados científicos nuevos.

| Archivo | Motivo y cambio concreto | Validación |
|---|---|---|
| `src/extracteval/adapters/storage/json_store.py` | Aplicar la protección de rutas también al escaneo de integridad | Regresión de enlace y pruebas de persistencia/reanudación |
| `scripts/verificacion_laboratorio.py` | Vincular diccionario y prompt con sus fuentes; inventario técnico sin API; referencias reales de esquema/configuración en nuevas importaciones | Regresiones de laboratorio e importación |
| `tests/test_phase2.py` | Añadir rechazo de enlaces e integración de A estructurada mediante mock con V/B, sin segunda extracción | Batería completa |
| `tests/test_phase2_laboratorio.py` | Añadir regresiones de fuente/prompt e inventario; reforzar hashes reales de esquema/configuración | Batería completa |
| `laboratorios/mi_estudio_001/02_diseno/diseno.yaml` | Completar solo B y candidato técnico; mapear fecha documental; corregir dos menciones actuales a ocho notas | YAML, contratos, validación del diseño y comparación de campos protegidos |
| `laboratorios/mi_estudio_001/02_diseno/resultados.json` | Regenerar el plan consolidado y sus pendientes, sin muestra, particiones, pesos ni estadísticas | `preparar-diseno`; listas operativas conservadas |
| `laboratorios/mi_estudio_001/02_diseno/auditoria_fase2.json` | Inventario de archivos, versiones y hashes existentes; estado explícito de A y conservación | Hashes recalculados y correspondencia con YAML |
| `docs/crear-y-dirigir-un-laboratorio.md` | Sustituir el estado actual obsoleto de software 0.1.0 por el alcance real de 0.2.0 | Contraste con módulos y CLI |
| `docs/tu-primera-prueba.md` | Distinguir el tutorial de fase 1 de V/comparación/B ya disponibles | Contraste con ejemplos y código |
| `templates/laboratorio_yaml_json/LEEME.yaml` | Aclarar que crear la estructura no ejecuta modelos; fase 2 requiere preparación explícita | Pruebas de creación y YAML |
| `docs/phase2-validation.md` | Conservar resultados históricos y aclarar el corpus activo; añadir cierre de auditoría | Resultados reales de las comprobaciones |
| `docs/fase2-verificacion-laboratorio.md` | Documentar consolidación, controles de fuente y trazabilidad de nuevas importaciones | Contraste con código y pruebas |
| `docs/architecture.md` | Documentar los controles técnicos añadidos, sin cambios de contratos públicos | Guarda arquitectónica, Ruff y mypy |
| `README.md` | Enlazar el estado auditado y separar configuración de ejecución/validación | Revisión documental |
| `CHANGELOG.md` | Registrar los defectos corregidos y el alcance conservado | Revisión documental |
| `docs/phase2-audit.md` | Este informe, incluidos bloques reales del diseño y pendientes | Concordancia con inventario y resultados |

Se preservaron las referencias históricas válidas a la carga TSV de ocho registros, los informes anteriores y sus respaldos. Se corrigieron únicamente menciones que describían el estado actual de forma obsoleta.

## C. Configuración experimental consolidada

Los bloques siguientes se extraen literalmente como datos YAML del archivo consolidado. Los campos null de A y de decisiones metodológicas se conservan. No se asignaron versiones retroactivas: las instrucciones, configuración, diccionario y política conservan sus identificadores existentes; el inventario y las referencias corregidas de importación se materializaron en esta auditoría.

```yaml
configuraciones_comparadas:
  extractor_base:
    modelo_y_parametros: null
    instrucciones_version: null
    instrucciones_sha256: null
    esquema_version: null
    reglas_posprocesamiento_version: null
  A:
    descripcion: Extracción base original
    extractor_base_ref: extractor_base
  B:
    descripcion: Verificación y reconciliación sobre exactamente la salida de A
    extractor_base_ref: extractor_base
    reutiliza_exactamente_salida_A: true
    repite_extraccion: false
    modelo_verificador_y_parametros:
      proveedor: openai
      modelo_solicitado: gpt-4.1-mini
      modelo_efectivo_api: null
      estado: configurado_sin_ejecucion_real
      parametros_solicitados:
        contract_version: '1.0'
        seed: null
        temperature: null
        max_output_tokens: 4096
        response_format: structured
      request_timeout: 60.0
      configuracion_version: lab-phase2-v1
      configuracion_ruta: configuraciones/verificacion/v1/config.json
      configuracion_sha256: 786c87a362b5bd6272d5e78de9dff5dcc064f67f5013fcda8902dd56a754f2a1
      sobrescrituras_entorno:
      - EXTRACTEVAL_VERIFIER_MODEL
      - EXTRACTEVAL_RECONCILER_MODEL
      - EXTRACTEVAL_MAX_OUTPUT_TOKENS
      - EXTRACTEVAL_REQUEST_TIMEOUT
      modo_predeterminado_cli: mock
      modelo_demostracion: mock-verifier
      reconciliador_motor: deterministic
      reconciliador_modelo: null
    instrucciones_version: independent-verifier.v1
    politica_reconciliacion_version: conservative.v1
    lectura_independiente_verificador: true
    instrucciones_sha256: cd5d64eb7f395e7a374e2cd48ba475b933a9a450a0c2cc34074d2dda52fbd2fe
  mismos_documentos: true
  mismas_variables: true
  misma_referencia_independiente: true
  misma_definicion_pares_evaluables: true
  salidas_originales_separadas: true
  trazabilidad_pareada:
    mismo_base_extraction_id: true
    mismo_base_output_sha256: true
    mismo_extractor_config_sha256: true
    original_A_inmutable: true
validacion_prompts:
  particiones_para_seleccion:
  - development
  acceso_etiquetas_finales: false
  seleccionar_con_referencia_independiente: true
  candidatos:
  - id: independent-verifier.v1
    rol: verificador
    estado: candidato_tecnico_no_validado
    particion: development
    instrucciones_ruta: configuraciones/verificacion/v1/verificador.v1.txt
    instrucciones_version: independent-verifier.v1
    instrucciones_sha256: cd5d64eb7f395e7a374e2cd48ba475b933a9a450a0c2cc34074d2dda52fbd2fe
    configuracion_version: lab-phase2-v1
    configuracion_ruta: configuraciones/verificacion/v1/config.json
    configuracion_sha256: 786c87a362b5bd6272d5e78de9dff5dcc064f67f5013fcda8902dd56a754f2a1
    modelo_y_parametros:
      proveedor: openai
      modelo_solicitado: gpt-4.1-mini
      modelo_efectivo_api: null
      estado: configurado_sin_ejecucion_real
      parametros_solicitados:
        contract_version: '1.0'
        seed: null
        temperature: null
        max_output_tokens: 4096
        response_format: structured
      request_timeout: 60.0
      configuracion_version: lab-phase2-v1
      configuracion_ruta: configuraciones/verificacion/v1/config.json
      configuracion_sha256: 786c87a362b5bd6272d5e78de9dff5dcc064f67f5013fcda8902dd56a754f2a1
      sobrescrituras_entorno:
      - EXTRACTEVAL_VERIFIER_MODEL
      - EXTRACTEVAL_RECONCILER_MODEL
      - EXTRACTEVAL_MAX_OUTPUT_TOKENS
      - EXTRACTEVAL_REQUEST_TIMEOUT
      modo_predeterminado_cli: mock
      modelo_demostracion: mock-verifier
      reconciliador_motor: deterministic
      reconciliador_modelo: null
    esquema:
      contrato: extracteval.core.verification.VerificationPayload
      contract_version: '1.0'
      sha256_canonico: 109118f244bd07d15ee68cb1b8dc108a5e1c35e9920de0c2c28aa0f298e8b488
      origen: Esquema generado del contrato existente; no se crea otro esquema.
    diccionario:
      contract_version: '1.0'
      artifact_id: epoc_exacerbation_extraction
      version: 1.0.0-draft
      sha256: d104de50e839bac1b54f3424595960a064276358993c9c8357a40976e9636a5c
    politica_reconciliacion:
      policy_id: documentary-conservative
      version: conservative.v1
      ruta: configuraciones/verificacion/v1/politica.json
      sha256: 6ef48ae4b249ace36254e0f8a19afdb536a3d06ee5370b11a0c2676e2cc2eb65
    resultados_desarrollo: null
    aprobacion_cientifica: false
  criterio_seleccion_predefinido: PGEC en desarrollo con criterios aprobados; secundarios como restricciones
    preespecificadas.
  regla_desempate: null
  presupuesto_iteraciones: null
  validacion_interna_por_entidad: true
  extractor_seleccionado: null
  verificador_seleccionado: null
  congelacion:
    estado: pendiente
    fecha: null
    aprobador: null
    versiones_y_sha256: null
  regla_cambios_posteriores: Crear nueva versión y nueva evaluación independiente; no reutilizar la confirmación
    original para ajustar.
  procedimiento:
  - Definir candidatos versionados y huellas antes de compararlos.
  - Fijar presupuesto, criterio, desempate y restricciones con referencia independiente de desarrollo.
  - Validar dentro de desarrollo agrupando por paciente, sin acceso a etiquetas finales.
  - Registrar estabilidad en repeticiones y variaciones predefinidas; estabilidad no implica corrección.
  - Seleccionar extractor y verificador, registrar resultados de desarrollo y aprobación; congelar versiones,
    parámetros, esquema, reglas y SHA256.
  - Tras congelar, no ajustar instrucciones con reliability_fit, calibration ni evaluation.
  estabilidad:
    repeticiones: null
    variaciones_permitidas: null
    metricas:
    - acuerdo_intra_configuracion
    - variacion_PGEC_en_desarrollo
    - variacion_cobertura_y_fallos
    umbral_aceptacion: null
    datos: development exclusivamente
```

El SHA-256 de instrucciones se calculó sobre los bytes del archivo indicado, sin sustituir el prompt. El hash de configuración corresponde a `config.json`. El hash canónico del esquema proviene del contrato Pydantic existente, no de un nuevo esquema duplicado. Las sobrescrituras de entorno se describen, pero no se leyeron claves ni se resolvieron modelos alternativos para seleccionar candidatos.

## D. Pruebas y evidencias

| Comando / comprobación | Resultado |
|---|---|
| `.venv/bin/pytest -q` antes de modificar código | 192 correctas, 0 fallidas |
| Tres regresiones dirigidas antes de la corrección | 3 fallidas: defectos reproducidos |
| Aserción del esquema real en importación, antes de la corrección | 1 fallida: huella incorrecta reproducida |
| `PYTHONPATH=src .venv/bin/pytest -q` tras las correcciones | 197 correctas, 0 fallidas |
| `.venv/bin/ruff check .` | Sin hallazgos |
| `.venv/bin/ruff format --check .` | 80 archivos conformes |
| `.venv/bin/mypy` | Sin errores en 31 archivos |
| `preparar-diseno --laboratorio laboratorios/mi_estudio_001` | Plan regenerado; 23 decisiones pendientes; sin estadísticas |
| `demo-verificacion --laboratorio laboratorios/mi_estudio_001` | Reanudó demo-v1, mismo run_id; 1 discrepancia, 6 revisiones humanas; integridad correcta |
| `.venv/bin/pytest -q` con wheel instalado tras construirlo | 197 correctas, 0 fallidas |
| `python -m build --no-isolation` y reinstalación de wheel | Correctos; sin dependencias rotas con pip check |
| `validar-diseno --accion congelar` | Bloqueada, código 2 esperado; todas las autorizaciones científicas siguen false |
| Conservación de archivos protegidos | 9 archivos idénticos: diccionario fuente/compilado, configuración ejecutable, política, prompts y corpus/Excel |
| Comparación de campos científicos del plan | Sin cambios fuera de la consolidación técnica y las dos aclaraciones documentales declaradas |

La prueba de A con mock usa ScriptedModel existente y valida una ExtractionSnapshot estructurada. Después V se ejecuta mediante su propio modelo simulado y no recibe el marcador exclusivo de A. El pipeline no dispone de una llamada al extractor A para producir B. Esto verifica integración técnica, no implementa un extractor clínico nuevo ni demuestra corrección de su contenido.

Las pruebas existentes cubren las seis variables, validación de diccionario/YAML, independencia, comparación determinista, discrepancias, las cuatro decisiones, abstenciones, errores técnicos, persistencia/recuperación, inmutabilidad y trazabilidad A/B. Todos los documentos de prueba son inventados y los sockets están bloqueados en pruebas. El adaptador OpenAI se comprueba con HTTP falso; no se llamó a la API.

### Límites de trazabilidad comprobados

- `base_extraction_hash` identifica la representación canónica de A persistida. `source_sha256` y el registro de importación identifican los bytes recibidos cuando corresponde; no se confunden con el hash de configuración.
- B registra por variable acción, motivo, regla y valores/estados anteriores y posteriores. Las citas permanecen en A/V y se recuperan mediante los identificadores y hashes enlazados.
- La versión del prompt y los hashes de entrada/configuración se conservan por ejecución. El contenido completo de instrucciones está en la configuración persistida y protegido por el manifiesto; el hash explícito del archivo fuente queda en el diseño e inventario técnico. No se añadieron campos a contratos públicos ni se migraron manifiestos históricos.
- La procedencia del LLM original de A no se puede deducir del adaptador de importación; permanece pendiente hasta recibir su configuración real.
- El modelo efectivo de la API, costos reales y comportamiento en vivo no se verificaron. Los costos siguen null sin una tabla de precios verificable/versionada.
- Los hashes no son firmas digitales ni prueban anonimización o corrección clínica. La aprobación institucional y el control de acceso siguen siendo responsabilidad operativa.

## E. Pendientes priorizados

### Técnicos

1. **P0:** localizar/aportar el ejecutor A ya seleccionado y su configuración, prompt versionado, esquema y posprocesamiento. Integrarlo por los puertos existentes cuando su alcance esté autorizado; esta auditoría no crea otro extractor ni escoge un modelo.
2. **P1:** ejecutar una comprobación de integración con la API únicamente después de autorización explícita y gobierno de datos. La prueba debe conservar identificación efectiva y telemetría; no sustituir silenciosamente el modelo configurado.
3. **P1:** antes de confirmar un experimento, conservar una versión del código y de sus dependencias junto con los artefactos de ejecución. El manifiesto incluye versión de paquete y hashes de datos/configuración; no equivale a una instantánea completa del repositorio.

### Metodológicos

1. Aprobar diccionario, criterios de corrección/evaluabilidad y reglas temporales; ninguna heurística de fecha se autorizó en esta auditoría.
2. Definir población, rol del corpus, dependencia entre visitas, muestreo, precisión/tamaño y separación justificada de roles, sin inferir pacientes de ingresos.
3. Obtener referencia experta independiente y adjudicación según protocolo; después evaluar PGEC y el contraste pareado, sin usar V como verdad.
4. Preespecificar presupuesto, desempate, repeticiones, umbrales, selección de candidatos y congelación. Todos los valores pendientes y autorizaciones científicas permanecen como estaban.

### Operativos

1. Aportar los archivos/metadatos del extractor A que exista fuera de este checkout.
2. Verificar autorización institucional, tratamiento de datos, desidentificación de narrativas, retención/acceso y transferencia al proveedor antes de llamadas reales.
3. Proporcionar credenciales mediante entorno local cuando corresponda; no introducirlas en YAML, Git o logs. Comprobar acceso de la cuenta al modelo ya configurado durante la ejecución autorizada.

## Conclusión de la auditoría

V, comparación, reconciliación y persistencia están integrados y probados sobre A aportada. Se corrigieron defectos de vinculación e identificación técnica y el diseño refleja los componentes que realmente existen. El extractor LLM clínico A sigue sin identificarse en este repositorio. La Fase 2 no se declara científicamente validada y no se calculó PGEC, superioridad de B ni calibración.
