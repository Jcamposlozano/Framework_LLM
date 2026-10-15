# extracteval

Paquete Python independiente para contratos de extracción documental y su futura evaluación científica. Versión inicial **0.1.0**, formato de contratos **1.0**. Python **>=3.11**, Pydantic **2**. No inicializa servicios ni realiza llamadas externas al importar.

## Instructivo detallado

**Para usar tus propios documentos y variables:** sigue [Cómo hacer tu propia prueba](docs/tu-primera-prueba.md). Incluye una plantilla editable sin mocks; valida valores suministrados por el usuario. La extracción automática con LLM aún requiere la Fase 2.

Empieza por la [guía de uso en español](docs/guia-de-uso.md): instalación, tutorial completo, diccionarios, evidencia, estados, modelos simulados, referencia experta, manifiestos, integración desde otro proyecto y solución de errores.

Para practicar con archivos sintéticos en una carpeta nueva:

```sh
source .venv/bin/activate
python examples/guia_paso_a_paso.py --salida /tmp/extracteval-tutorial-01
```

El tutorial calcula huellas, guarda 13 archivos y valida su recuperación. No requiere credenciales ni llamadas externas.

## Alcance actual: Fase 1

Incluye documentos, diccionarios operacionales, valores semánticos tipados, resultados, referencias expertas, contratos de modelos, puertos, configuración, manifiestos y dos adaptadores simulados. No incluye ejecución de extractores/verificadores, métricas, calibración, proveedores reales, persistencia ni reglas de dominio.

## Instalación y comprobaciones

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
pytest
ruff check .
ruff format --check .
mypy
python -m build --no-isolation
python examples/minimal.py
```

`requirements-dev.lock` registra las versiones exactas del entorno de desarrollo verificado. Es un archivo de requisitos fijados, no un lock multiplataforma con hashes. Las dependencias compatibles de los consumidores se declaran en `pyproject.toml`.

## Uso mínimo: un consumidor, dos modelos

```python
from extracteval.adapters.models.mock import ConstantModel, ScriptedModel
from extracteval.core.models import ModelRequest
from extracteval.core.ports import ModelPort


def consume(model: ModelPort) -> str:
    request = ModelRequest(
        execution_id="run-1",
        request_id="request-1",
        instructions="Return a synthetic decision.",
        content="Synthetic administrative document.",
    )
    return model.generate(request).text


assert consume(ConstantModel("yes")) == "yes"
assert consume(ScriptedModel(["yes"])) == "yes"
```

`examples/minimal.py` añade un diccionario sintético, resultado trazable y referencia experta con ida y vuelta JSON. `ModelPort` es un `typing.Protocol`; los adaptadores no necesitan heredar de él.

## Semántica

Cada resultado separa cinco dimensiones:

- `value`: valor semántico etiquetado como categórico, booleano, numérico, fecha o texto.
- `operation`: `completed` o `failed`.
- `evidence`: disponibilidad (`available`, `absent`, `not_assessed`), suficiencia y elementos documentales.
- `abstention`: decisión explícita del sistema; no contiene un valor extraído.
- `technical_error`: código seguro de fallo técnico; exige operación fallida.

`indeterminado` o `not_applicable` pueden ser categorías válidas del diccionario con operación completada. Una ausencia documental puede representarse sin valor ni abstención y con evidencia ausente; también puede tener una categoría específica si así lo define el diccionario. Ningún estado implica corrección respecto a una referencia. Un `false` booleano es un valor, no ausencia documental.

Los valores numéricos y booleanos evitan coerciones desde cadenas o entre sí. Las fechas usan `datetime.date` en Python y fechas ISO en JSON. El discriminador `kind` evita ambigüedades al serializar.

La validación estructural se ejecuta al construir cada contrato. La pertenencia al diccionario requiere llamar **explícitamente** a `result.validate_against(dictionary)` o `annotation.validate_against(dictionary)`: no se usa un registro global. El diccionario declara instrucciones de normalización y corrección; todavía no las ejecuta.

## Modelos simulados

- `ConstantModel`: texto constante, sin parámetros opcionales.
- `ScriptedModel`: secuencia finita, fallo simulado con `None`, salida JSON opcional y aceptación simulada de semilla y temperatura. Estos parámetros no alteran el guion. No simula límites de tokens ni consumo o costos.

Las capacidades se validan antes de consumir una respuesta. Ambos modelos son reproducibles respecto de su contenido; para repetir un guion debe crearse una instancia nueva con la misma secuencia y orden de llamadas. Tiempos de ejecución e identificadores de solicitudes no son promesas de igualdad binaria de respuestas. El adaptador secuencial no es seguro para uso concurrente.

## Trazabilidad y seguridad

`ResultTrace` vincula documento, variable, versión/huella del diccionario, configuración, ejecución, esquema y, cuando procede, modelo, instrucciones e identificadores de solicitud. `execution_id` y `request_id` son internos; `provider_request_id` es externo y opcional.

Los manifiestos conservan referencias, parámetros tipados y capacidades; no admiten campos libres para documentos, prompts, credenciales o excepciones originales. Se conserva la limitación explícita cuando no se declara reproducibilidad exacta. `manifest.validate_against(config)` comprueba huella, repetición y bindings registrados. `result.trace.validate_config(config)` comprueba diccionario, esquema e identidad del modelo para el rol indicado. Una versión de modelo desconocida se representa con `None` y exige registrar `model_version_unavailable`; no permite declarar reproducibilidad exacta.

Las huellas de configuración usan JSON ordenado y SHA-256 según el formato 1.0 del paquete. No equivalen a una firma, ni garantizan anonimización o corrección. Las huellas de artefactos declaradas deben ser verificadas por futuras implementaciones de almacenamiento.

**Los identificadores deben ser pseudónimos y las referencias deben carecer de credenciales.** Ningún contrato puede detectar un secreto introducido deliberadamente como identificador válido. Los documentos, evidencias y resultados serializados pueden contener contenido sensible: el consumidor controla su acceso y almacenamiento. No se producen logs.

Los contratos ocultan entradas en `str(ValidationError)` y contenido en `repr`. Al exportar diagnósticos estructurados se debe usar `error.errors(include_input=False)`; el método predeterminado de Pydantic puede incluir datos de entrada. No se deben registrar contratos completos ni JSON documental.

Los modelos son `frozen` para impedir reasignación de atributos, pero sus metadatos anidados no son profundamente inmutables. Las huellas se recalculan del contenido actual; deben conservarse instantáneas serializadas y validarse contra sus referencias.

## Arquitectura y próximos pasos

Ver [decisiones y límites](docs/architecture.md) y [verificación de la Fase 1](docs/phase1-validation.md). La evaluación futura consumirá resultados y referencias sin ejecutar ni inicializar modelos. No existe dependencia del núcleo hacia adaptadores. Las siete etapas metodológicas son responsabilidades combinables y no un flujo obligatorio.
