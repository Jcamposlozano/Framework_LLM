# Fase 2: trabajar desde mi_estudio_001

Esta fase añade un procedimiento ejecutable de lectura independiente, comparación y reconciliación. El laboratorio conserva sus siete etapas metodológicas: producir B no cierra E1–E7 ni demuestra mejora clínica. El corpus importado no se usa en la demostración.

## Instalación local

Desde la raíz del repositorio, usa Python ≥3.11:

```bash
.venv/bin/python -m pip install --no-deps --no-build-isolation .
```

La biblioteca mantiene Pydantic como única dependencia directa. Los comandos del laboratorio requieren el extra `lab` (PyYAML y openpyxl), ya instalado en el entorno de desarrollo. Para una instalación nueva: `python -m pip install '.[lab]'`.

Durante el desarrollo puedes ejecutar el código fuente sin reinstalar con `PYTHONPATH=src .venv/bin/python …`. El ejecutable `extracteval` usa la versión instalada: reinstala después de cambiar el código fuente.

## Preparar y observar una demostración

```bash
.venv/bin/python scripts/laboratorio.py preparar-verificacion --laboratorio laboratorios/mi_estudio_001
.venv/bin/python scripts/laboratorio.py demo-verificacion --laboratorio laboratorios/mi_estudio_001 --etapa independent
.venv/bin/python scripts/laboratorio.py demo-verificacion --laboratorio laboratorios/mi_estudio_001 --etapa compare
.venv/bin/python scripts/laboratorio.py demo-verificacion --laboratorio laboratorios/mi_estudio_001 --etapa reconcile
.venv/bin/python scripts/laboratorio.py estado-verificacion --laboratorio laboratorios/mi_estudio_001
```

También puedes ejecutar todo con `demo-verificacion --laboratorio laboratorios/mi_estudio_001`. Repetir el comando reanuda la ejecución sin pedir otra respuesta al proveedor ni reemplazar sus artefactos. `--dry-run` valida la entrada sin crear una ejecución.

La demostración contiene una discrepancia deliberada: A propone `exacerbacion_actual="false"`; el verificador simulado propone `"true"` con cita literal. B conserva A y solicita revisión porque el diccionario no está aprobado. Las otras cinco variables quedan semánticamente indeterminadas, sin evidencia suficiente: también requieren revisión. El mock reproduce una respuesta escrita de antemano; no interpreta clínicamente el documento.

## Dónde mirar

| Ruta dentro del laboratorio | Para qué sirve |
|---|---|
| `01_especificacion/especificacion.yaml` | Fuente del diccionario del estudio; se conserva sin cambios |
| `configuraciones/verificacion/v1/fuente.json` | Relaciona la huella del YAML y la del diccionario ejecutable |
| `configuraciones/verificacion/v1/diccionario.json` | Mismas seis variables y categorías; reglas de consistencia como avisos pendientes |
| `configuraciones/verificacion/v1/config.json` | Modelo, límites, timeout, metadatos permitidos y rutas |
| `configuraciones/verificacion/v1/politica.json` | Política conservadora sin reglas de reemplazo aprobadas |
| `configuraciones/verificacion/v1/verificador.v1.txt` | Prompt independiente versionado |
| `configuraciones/verificacion/v1/mapeo-a.json` | Conversión explícita de booleanos JSON a categorías `"true"`/`"false"` |
| `configuraciones/verificacion/v1/demo-entrada.json` | Documento y A sintéticos |
| `configuraciones/verificacion/v1/demo-verificador.json` | Propuestas simuladas, independientes de A |
| `ejecuciones/fase2/demo-v1/` | Artefactos de la demostración, uno por procedimiento |
| `control/progreso_verificacion.json` | Progreso técnico obtenido de los artefactos; no modifica el tablero metodológico |

Cada ejecución guarda `document.json`, `extraction_a.json`, `verification.json`, `comparison.json`, `decisions.json`, `extraction_b.json`, `configuration.json`, `context.json` y manifiestos de las etapas completadas. Solo se crean los archivos de los procedimientos realmente ejecutados.

`verification.json` debe existir antes de comparar. `comparison.json` identifica cada variable, relación y problemas de evidencia. `extraction_b.json` registra por variable el valor anterior/posterior, estado semántico, acción, motivo y regla. El hash y el identificador de A aparecen en comparación, B y manifiestos. Los campos auxiliares permanecen fuera de las seis variables principales.

Las citas y respuestas pueden contener información sensible: son artefactos privados, no logs. Los nuevos archivos de ejecuciones se crean con permisos 0600 y el directorio de ejecución con 0700. El responsable del laboratorio debe gestionar retención, cifrado, copias y acceso. `/laboratorios/` permanece excluido de Git.

## Registrar una extracción A real ya existente

Esta fase **no implementa un extractor inicial**. Recibe A del extractor que ustedes utilicen. El repositorio inspeccionado no contenía ese extractor: contenía contratos, mocks y herramientas de planificación.

Guarda la respuesta A en un JSON local. Se admite `ExtractionSnapshot` tipado o una salida plana con las seis variables, por ejemplo:

```json
{
  "base_extraction_id": "a-ejemplo-001",
  "estado_paciente": "sintomatico",
  "exacerbacion_actual": "indeterminado",
  "exacerbacion_previa": "indeterminado",
  "fecha_indice_evento": null,
  "precision_temporal": "indeterminada",
  "metodo_fecha": "no_determinable",
  "semantic_states": {
    "exacerbacion_actual": "indeterminate",
    "exacerbacion_previa": "indeterminate",
    "fecha_indice_evento": "indeterminate"
  },
  "offset_estimado_dias": null,
  "ventana_ambiental": null,
  "criterios_detectados": [],
  "justificacion_clinica": "Ejemplo de formato; no es una nota real.",
  "nivel_confianza": 0.7
}
```

Se puede usar un objeto `values` con las seis variables y un objeto `auxiliary`. La evidencia opcional va en `evidence`, indexada por variable, con listas de objetos `Evidence`. Los errores técnicos van en `technical_errors` por variable: su valor debe ser null, y no deben recibir estado semántico. La evidencia ausente queda registrada y nunca habilita una corrección.

Sin `semantic_states`, un null se registra como falta de respuesta; no se convierte por defecto en indeterminación clínica, negación o no aplicabilidad. Indica explícitamente esos estados cuando estén presentes en A. Los booleanos de variables categóricas solo se adaptan mediante `mapeo-a.json`; el archivo A recibido conserva sus bytes originales. `nivel_confianza` se conserva sin tratarlo como probabilidad calibrada.

```bash
.venv/bin/python scripts/laboratorio.py registrar-extraccion-a \
  --laboratorio laboratorios/mi_estudio_001 \
  --documento-id DOCUMENT_ID_DEL_INVENTARIO \
  --archivo /ruta/local/extraccion-a.json
```

Se selecciona **un** documento ya importado. El comando imprime la ruta `datos/verificacion/entrada-…/entrada.json`. Junto a ella quedan `a-original.json` intacto y `registro.json` con sus huellas. No se sobrescribe el corpus ni se hace una llamada externa.

Para usar otra respuesta mock, crea un `VerificationPayload` sintético correspondiente a ese documento y configura `mock_payload_path`; el mock de la demostración no es un verificador de notas distintas. La comparación detecta citas o identificadores ajenos.

```bash
.venv/bin/python scripts/laboratorio.py ejecutar-verificacion \
  --laboratorio laboratorios/mi_estudio_001 \
  --entrada /ruta/obtenida/entrada.json \
  --ejecucion piloto-local-001 --modo mock --dry-run
```

Quita `--dry-run` para ejecutar con la respuesta simulada configurada. Usa `--etapa independent`, `compare`, `reconcile` o `all` para avanzar por procedimientos. No hay procesamiento masivo implícito.

## Proveedor real: autorización explícita

La disponibilidad de GPT-4.1 mini y su soporte de salida estructurada están documentados oficialmente. Esto no acredita acceso desde una cuenta concreta. Antes de transmitir un documento el adaptador consulta `GET /v1/models/{modelo}` y rechaza un identificador distinto o no disponible. La solicitud Responses usa un JSON Schema estricto; rechazos, respuestas incompletas o incompatibilidad se registran como fallos técnicos. No hay sustitución silenciosa de modelo ni temperatura forzada.

Variables de entorno:

| Variable | Uso |
|---|---|
| `OPENAI_API_KEY` | Credencial; no se persiste |
| `EXTRACTEVAL_VERIFIER_MODEL` | Modelo verificador; por defecto el modelo de `config.json` |
| `EXTRACTEVAL_RECONCILER_MODEL` | Identificador independiente, registrado en configuración; **no se invoca** con reconciliación determinista |
| `EXTRACTEVAL_MAX_OUTPUT_TOKENS` | Límite de salida, por defecto 4096 |
| `EXTRACTEVAL_REQUEST_TIMEOUT` | Timeout por intento HTTP en segundos, por defecto 60 |

Se registran modelo solicitado y reportado, parámetros solicitados y reportados cuando existen, id de respuesta, tokens de entrada/salida/razonamiento, latencia, reintentos y códigos de error. Los límites se reintentan con un presupuesto total de dos reintentos. Los costos quedan null: esta entrega no incorpora una tabla de precios verificada y versionada. No se atribuye reproducibilidad exacta a las respuestas del LLM.

El modo real requiere `--autorizar-real` y un archivo de gobierno de datos revisado por ustedes. Su contrato es `GovernanceAuthorization`: `document_hash`, `authorization_reference`, `institutional_authorization`, `personal_data_processing_authorized`, `appropriately_deidentified`, `retention_and_access_reviewed`, `provider_transfer_authorized`. Las cinco comprobaciones deben ser verdaderas y el hash debe corresponder al contrato `Document` enviado. La aplicación comprueba la declaración y su vinculación; no puede emitir una autorización institucional ni verificar jurídicamente su contenido.

El corpus activo contiene 5.924 notas importadas desde Excel. El informe de importación indica que la narrativa **no está anonimizada**. La seudonimización del identificador de ingreso no resuelve ese requisito. No se ha enviado el corpus a OpenAI.

```bash
.venv/bin/python scripts/laboratorio.py ejecutar-verificacion \
  --laboratorio laboratorios/mi_estudio_001 \
  --entrada /ruta/local/entrada-autorizada.json \
  --ejecucion piloto-autorizado-001 --modo real \
  --autorizar-real --gobierno /ruta/local/autorizacion.json
```

Un fallo técnico se persiste y el comando devuelve código 2. Reanudar conserva ese fallo y evita nuevas llamadas. Para un nuevo intento deliberado usa otra ejecución; no borres artefactos para cambiar resultados. Los comandos de comparación y reconciliación sobre resultados persistidos no necesitan credenciales ni vuelven a consultar al proveedor.

## Versiones, reglas y límites

El YAML del estudio sigue siendo la fuente única de las definiciones. La preparación conserva esas definiciones y registra la transformación desde su hash de archivo a un hash canónico JSON. Las implicaciones `consistency_checks` se convierten en avisos declarativos pendientes de aprobación. No se habilitan equivalencias, tolerancias de fecha ni las heurísticas `consulta_menos_7d` y `consulta_menos_15d`.

Si cambia la especificación, regenera su JSON y crea una versión nueva:

```bash
.venv/bin/python scripts/laboratorio.py preparar-especificacion --laboratorio laboratorios/mi_estudio_001
.venv/bin/python scripts/laboratorio.py preparar-verificacion --laboratorio laboratorios/mi_estudio_001 --version v2
.venv/bin/python scripts/laboratorio.py demo-verificacion --laboratorio laboratorios/mi_estudio_001 --version v2 --ejecucion demo-v2
```

Una configuración distinta no puede reanudar una ejecución anterior. Cambios en diccionario, prompt, política, parámetros o respuesta mock se incluyen en las huellas.

El núcleo es independiente de EPOC y del proveedor. Las normalizaciones requieren reglas explícitas aprobadas en el diccionario. La reconciliación admite `KEEP_A`, `REPLACE_WITH_VERIFIED`, `ABSTAIN` y `HUMAN_REVIEW`. Un reemplazo requiere aprobación de diccionario y regla, coincidencia de variable/valor/estado, citas exigidas por la regla, evidencia verificable y ausencia de incertidumbre o inconsistencias. Una cita literal existente demuestra localización documental; su suficiencia clínica requiere una regla aprobada.

Pendientes del estudio: revisión clínica del diccionario, decisiones temporales, reglas de reemplazo, gobierno de datos para uso externo, A producida por su extractor y referencia experta. No se calculan PGEC, exactitud, correcciones verdaderas ni errores introducidos. La señal `clinically_validated` permanece false incluso si posteriormente se autoriza una regla técnica.

## CLI genérica y pruebas

```bash
.venv/bin/extracteval verify --config configs/epoc/phase2.json \
  --input examples/phase2/input.json --output /tmp/extracteval-demo --mode mock
.venv/bin/python -m pytest -q
.venv/bin/ruff check .
.venv/bin/mypy
```

La CLI genérica admite las mismas cuatro etapas, dry-run y reanudación. Para llamadas reales usa `--mode real --authorize-real --governance …`. La entrada es un único `VerificationInput`; no se acepta una lista de historias para iniciar un lote.

Las pruebas bloquean sockets y usan únicamente documentos inventados, respuestas simuladas y un transporte HTTP falso. Verifican comportamiento del software, no capacidad de extracción clínica del mock.

Fuentes de la interfaz OpenAI, consultadas el 19 de octubre de 2026: [Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=responses), [GPT-4.1 mini](https://developers.openai.com/api/docs/models/gpt-4.1-mini), [Retrieve model](https://developers.openai.com/api/reference/resources/models/methods/retrieve).

## Auditoría y consolidación técnica

`02_diseno/diseno.yaml` distingue ahora la configuración existente del verificador (GPT-4.1 mini configurado, sin llamada real) y su demostración con `mock-verifier`. El prompt y la política conservan sus versiones y bytes. El candidato de instrucciones se registra como técnico, sin selección ganadora, aprobación o congelación.

`extractor_base` conserva campos pendientes porque no se identificó un ejecutor clínico A ni su configuración LLM en este repositorio. Los contratos y mocks sí existen; no se usan los identificadores ficticios de las fixtures como versiones o hashes de un extractor científico.

La entrada al laboratorio comprueba que el diccionario configurado corresponde a la fuente preparada y que el prompt coincide con su versión guardada. Los hashes de integridad rechazan también los archivos enlazados. Para nuevas importaciones de A plana, `configuracion_importacion.json` conserva la configuración real de adaptación y el hash del esquema `ExtractionResult`; no atribuye esa configuración al LLM que produjo A. Los originales y las ejecuciones históricas no se reescriben.

La ausencia de `entity_id` no impide ejecutar V, comparar o reconciliar un documento. Los requisitos de agrupación por paciente pertenecen al diseño estadístico posterior; `validar-diseno` comprueba ese protocolo científico y no sustituye a la CLI documental.

El informe [Auditoría de fase 2](phase2-audit.md) contiene el inventario, los bloques consolidados, defectos corregidos, pruebas y pendientes.
