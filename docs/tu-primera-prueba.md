# Cómo hacer tu propia prueba con extracteval 0.1.0

> **Flujo vigente:** consulta [Laboratorio YAML/JSON](laboratorio-yaml-json.md). Los recorridos con CSV/TXT y varias vistas del diccionario que aparecen más abajo corresponden al formato anterior o a ejemplos didácticos; no son pasos adicionales para `mi_estudio_001`.

## Primero: qué significa «hacer mi prueba» en esta versión

Hay dos trabajos distintos:

1. **Quiero que un LLM lea mi documento y extraiga mis variables.** La versión 0.1.0 todavía no lo hace. Para ese trabajo, el paquete actual incorpora un adaptador real y [el extractor A](extractor-a.md), con configuración propia y pruebas sintéticas. Editar el texto de un ejemplo con un mock no soluciona esa carencia: el mock seguiría devolviendo el valor programado.
2. **Quiero definir una variable mía y comprobar si un valor que yo suministro cumple mi diccionario, conservar su evidencia y guardar una ejecución trazable.** Esto sí puedes hacerlo ahora. Ese es el ejercicio concreto que explica esta página.

La plantilla de este ejercicio no utiliza modelos simulados ni proveedores reales. Tú escribes el documento, la definición de la variable y el valor que quieres comprobar. El framework valida los contratos y guarda los registros. La corrección factual del valor necesita una evaluación independiente que este ejercicio no calcula.

Si lo que necesitas es el punto 1, no tienes que seguir copiando ejemplos esperando que aparezca extracción automática: hace falta desarrollar esa capacidad antes.

## Resultado que vas a conseguir

Al completar este recorrido tendrás tu propia carpeta de laboratorio, un archivo Python que puedes editar y una carpeta con siete archivos que describen la prueba. Podrás cambiar tu documento o variable y ejecutar de nuevo sin modificar el núcleo del framework.

La primera vez usa un texto ficticio para verificar el procedimiento. Esta guía no conecta repositorios ni ejecuta experimentos con bases reales.

## Paso 1. Abre la terminal en Framework

```sh
cd /Users/jonathancamposlozano/Documents/Phd/Framework
.venv/bin/python -c 'import extracteval; print(extracteval.__version__)'
```

Debe aparecer `0.1.0`. Usamos el intérprete explícito `.venv/bin/python` para evitar confusiones con Conda. La instalación del wheel existente permite utilizarlo sin depender del enlace editable.

Los comandos siguientes también se ejecutan desde esta carpeta.

## Paso 2. Crea tu archivo de trabajo

```sh
mkdir -p mi_laboratorio
cp -n examples/mi_primera_prueba.py mi_laboratorio/prueba.py
```

`cp -n` conserva un archivo de destino que ya exista. No copies la plantilla encima de una prueba que ya hayas personalizado.

Tu copia estará aquí:

```text
/Users/jonathancamposlozano/Documents/Phd/Framework/mi_laboratorio/prueba.py
```

Abre ese archivo en tu editor. Puedes hacerlo desde el explorador de archivos de Codex. La copia es tu aplicación de prueba; no edites `src/extracteval/core/` ni los tests para cambiar de variable.

Para un estudio formal puedes colocar `mi_laboratorio` en un proyecto externo e instalar allí el wheel. Aquí lo mantenemos dentro de la carpeta de trabajo únicamente para simplificar los comandos de aprendizaje.

## Paso 3. Localiza el bloque que debes editar

Busca estos comentarios:

```python
# ================= EDITA ESTE BLOQUE PARA TU PRUEBA =================
# ... tus datos y definición ...
# ================= FIN DEL BLOQUE EDITABLE ==========================
```

El resto del archivo calcula referencias, crea los contratos, valida y guarda. Para una primera variable categórica no necesitas modificar esa parte.

Dentro del bloque, cambia lo siguiente:

| Campo | Qué escribes tú | Ejemplo |
|---|---|---|
| `DOCUMENTO_ID` | Un pseudónimo sin espacios | `documento-propio-001` |
| `TEXTO` | El texto que quieres representar | Un documento ficticio tuyo |
| `variable_id` | Nombre estable de tu variable | `estado_solicitud` |
| `data_type` | Tipo de variable | `categorical` |
| `categories` | Valores categóricos admitidos | `("aceptada", "rechazada", "indeterminada")` |
| `operational_definition` | Qué significa la variable | Estado explícito de la solicitud |
| `interpretation_rules` | Cómo interpretar el texto | No inferir por silencio documental |
| `correctness_criteria` | Cómo se decidiría corrección | Acuerdo con referencia independiente |
| `information_policy` | Qué hacer ante ausencia, incertidumbre y no aplicabilidad | Instrucciones explícitas de tu diseño |
| `VALOR_REGISTRADO` | El valor que vas a comprobar | `CategoryValue(value="aceptada")` |
| `CITA` | Fragmento documental que declaras como respaldo | `"La solicitud ha sido aceptada."` |
| `VERSION_DICCIONARIO` | Versión de tus definiciones | `"1"` |
| `VERSION_CONFIGURACION` | Versión de las condiciones de la prueba | `"1"` |

Para texto de varias líneas puedes usar comillas triples de Python:

```python
TEXTO = """Documento ficticio de mi prueba.
La solicitud ha sido aceptada.
No se informa la fecha de resolución.
"""
```

No pongas nombres personales, números de identidad ni credenciales en `DOCUMENTO_ID`. Usa un pseudónimo. Los campos de identificadores no aceptan espacios ni acentos; el texto documental y las definiciones sí pueden contenerlos.

## Paso 4. Entiende el dato que tú debes proporcionar

Esta es la línea más importante:

```python
VALOR_REGISTRADO: SemanticValue | None = CategoryValue(value="aprobado")
```

El programa **no encuentra** ese valor dentro de `TEXTO`. Tú lo escribes: puede ser el resultado de una lectura manual que estás ensayando. Para este recorrido se registra sin identidad de modelo porque el script no ejecuta ninguno.

Si ya tienes una salida producida por un LLM y quieres incorporarla como resultado científico de ese modelo, conserva su procedencia real —modelo, instrucciones, solicitud y configuración cuando estén disponibles—. Esta plantilla manual no reconstruye esos metadatos. El instructivo general explica `ResultTrace`; no declares una ejecución del LLM que este programa no hizo.

`CITA` también la suministras tú. El framework comprueba su estructura y documento asociado, pero no busca el fragmento ni comprueba que esté literalmente en `TEXTO`. La plantilla deja su suficiencia como `not_assessed`: no decide automáticamente si demuestra el valor.

Si no has evaluado la evidencia, usa:

```python
CITA = None
```

Eso representa evidencia no evaluada, no ausencia documental confirmada. Para representar esa ausencia, abstención o error técnico con precisión, utiliza los contratos descritos en las secciones 7 y 9 del [instructivo general](guia-de-uso.md).

## Paso 5. Ejecuta tu archivo

Guarda tus cambios en el editor y ejecuta:

```sh
.venv/bin/python mi_laboratorio/prueba.py --salida mi_laboratorio/ejecuciones/prueba-001
```

No ejecutes `examples/minimal.py` para este ejercicio: ese archivo seguiría utilizando los datos de su demostración. Aquí ejecutas **tu copia editada**, `mi_laboratorio/prueba.py`.

Si dejaste los valores iniciales válidos, la salida será:

```text
PRUEBA DE CONTRATOS CORRECTA
Variable validada: estado_solicitud
Archivos guardados: 7
Carpeta: .../mi_laboratorio/ejecuciones/prueba-001
El valor fue suministrado por ti. No se ejecutó extracción ni se midió exactitud.
```

El identificador de variable cambiará si modificaste `variable_id`.

## Paso 6. Revisa el resultado de tu prueba

```sh
ls -1 mi_laboratorio/ejecuciones/prueba-001
.venv/bin/python -m json.tool mi_laboratorio/ejecuciones/prueba-001/extraction.json
```

La carpeta contiene:

| Archivo | Para qué sirve |
|---|---|
| `document.json` | Tu documento y pseudónimo |
| `dictionary-payload.json` | Definiciones exactas cuya huella identifica el diccionario |
| `dictionary.json` | Contrato del diccionario y su referencia al payload |
| `output-schema.json` | Esquema estructural de resultados |
| `config.json` | Configuración de esta prueba sin modelos |
| `extraction.json` | Valor suministrado, evidencia y trazabilidad |
| `manifest.json` | Ejecución, tiempos y referencias a entradas/salidas |

En `extraction.json`, comprueba:

- `trace.document_id`: tu documento.
- `trace.variable_id`: tu variable.
- `value.kind`: tipo semántico que elegiste.
- `value.value`: el valor que tú escribiste.
- `operation`: `completed` para esta prueba manual.
- `evidence`: la evidencia declarada, con suficiencia no evaluada.
- `trace.model`: `null`, porque no se ejecutó un modelo.

Un resultado estructuralmente válido puede ser factualmente incorrecto. Por ejemplo, el contrato acepta `denegado` si es una categoría permitida, aunque tu documento diga `aprobado`. Detectar esa diferencia requiere evaluación contra una referencia, no solo validación del dominio.

## Paso 7. Haz una prueba deliberadamente inválida

En tu archivo cambia únicamente:

```python
VALOR_REGISTRADO: SemanticValue | None = CategoryValue(value="categoria-no-permitida")
```

No añadas esa categoría a `categories`. Guarda y ejecuta en otra carpeta:

```sh
.venv/bin/python mi_laboratorio/prueba.py --salida mi_laboratorio/ejecuciones/prueba-invalida-001
```

Debe aparecer:

```text
ValueError: Semantic value is outside the variable domain
```

El script valida antes de crear la carpeta de salida. Una categoría inválida no genera una ejecución guardada. Este error esperado demuestra que tu definición se está aplicando.

Restaura el valor válido antes de continuar.

## Paso 8. Prueba tu categoría indeterminada

Si tu diccionario declara `indeterminado`, puedes escribir:

```python
VALOR_REGISTRADO: SemanticValue | None = CategoryValue(value="indeterminado")
```

Usa un texto ficticio que exprese esa incertidumbre y una cita consistente, o deja la evidencia no evaluada. Ejecuta con una carpeta nueva, por ejemplo `prueba-002`.

Debe seguir siendo una operación `completed`, sin abstención ni error técnico. La palabra `indeterminado` es una categoría de tu diccionario, no una orden para fallar.

## Paso 9. Cambia a una variable de otro tipo

Además de cambiar la definición, debes importar y usar la clase de valor correspondiente. Puedes agregar el import al principio de tu copia.

| Tipo | Import adicional desde `extracteval.core.specification` | `data_type` | `categories` | Valor registrado |
|---|---|---|---|---|
| Booleano | `BooleanValue` | `"boolean"` | `()` | `BooleanValue(value=False)` |
| Número | `NumberValue` | `"numeric"` | `()` | `NumberValue(value=12.5)` |
| Fecha | `DateValue` | `"date"` | `()` | `DateValue(value=date(2026, 10, 15))` |
| Texto | `TextValue` | `"text"` | `()` | `TextValue(value="Texto ficticio")` |

Para fechas añade también `from datetime import date`. Actualiza `variable_id`, definición, políticas, criterios y cita para que correspondan al nuevo significado. No basta con cambiar la clase de valor dejando la definición anterior.

Un booleano `False` es un valor válido; no representa que falte información. Para una variable numérica no escribas `"12.5"` con comillas: eso sería texto.

## Paso 10. Repite y conserva tus versiones

Cada ejecución necesita una carpeta nueva:

```sh
.venv/bin/python mi_laboratorio/prueba.py --salida mi_laboratorio/ejecuciones/prueba-003
```

El script genera identificadores nuevos para ejecución y resultado, y rechaza carpetas existentes. No modifica las ejecuciones anteriores. Los nombres `prueba-001`, `prueba-002`, etc. son nombres de carpeta, no los identificadores internos.

Si cambias el significado, categorías o políticas de la variable, aumenta su `version` y `VERSION_DICCIONARIO`. Si cambias condiciones de la prueba, aumenta `VERSION_CONFIGURACION`. Las huellas se recalculan automáticamente sobre los contenidos de esta ejecución.

La configuración de esta plantilla no es un historial completo del código de tu aplicación ni incluye una copia del script. Conserva también tu copia de `prueba.py` y su versión si necesitas reconstruir cómo preparaste los datos.

## Qué falta para convertir esto en tu experimento de extracción

La prueba anterior permite comprobar representación y validación de tu propia variable. No es todavía el experimento completo con LLM.

Para extracción automática necesitamos definir e implementar:

1. Integrar el adaptador del motor elegido; ya existe OpenAI Responses, además de mocks.
2. El extractor que compone la solicitud a partir de tu diccionario y documento.
3. La normalización y validación de la respuesta.
4. La conservación de la procedencia efectiva de la llamada.

Esta plantilla no implementa un extractor clínico inicial. El paquete 0.2.0 ya incorpora verificación independiente, comparación y reconciliación de una A aportada externamente o producida por [el extractor A](extractor-a.md); consulta [Fase 2 en el laboratorio](fase2-verificacion-laboratorio.md). La evaluación estadística sigue pendiente. La plantilla conserva su alcance didáctico y no ejecuta esos procedimientos automáticamente.
