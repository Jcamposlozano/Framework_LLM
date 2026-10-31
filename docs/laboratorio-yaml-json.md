# Laboratorio sencillo: YAML para definir, JSON para conservar

Esta es la guía vigente para el formato 2 del laboratorio. Sustituye el flujo anterior con CSV, TXT, JSONL y múltiples vistas del diccionario. El código Python sigue en el repositorio; los archivos de trabajo del laboratorio activo usan únicamente `.yaml` y `.json`.

## 1. La regla de uso

- **YAML:** tú escribes definiciones, instrucciones y planes.
- **JSON:** el sistema conserva documentos, la especificación preparada, registros y resultados. Los resultados científicos se incorporarán cuando existan; sus plantillas no los calculan.

En E1 solo trabajas en **`01_especificacion/especificacion.yaml`**. Su compañero `especificacion.json` se genera con un comando. No mantienes un CSV ni una segunda copia editable del diccionario.

El laboratorio `mi_estudio_001` ya está reorganizado. La estructura anterior se conservó fuera del laboratorio activo, bajo `laboratorios/.historial/`; la ruta exacta está en `control/migracion.json`. No se eliminaron los originales ni se modificaron decisiones clínicas para realizar esta reorganización.

## 2. Dónde está cada cosa

```text
mi_estudio_001/
├── LEEME.yaml
├── control/
│   ├── estado.json
│   ├── creacion.json
│   └── migracion.json                 # Solo si se migró una estructura anterior
├── datos/
│   ├── importacion.yaml
│   ├── documentos.json
│   └── informe_importacion.json
├── 01_especificacion/
│   ├── especificacion.yaml            # Única fuente editable del diccionario y prompts
│   └── especificacion.json            # Generado desde el YAML
├── 02_diseno/
│   ├── diseno.yaml
│   └── resultados.json
├── 03_estabilidad/
│   ├── estabilidad.yaml
│   └── resultados.json
├── 04_referencia/
│   ├── protocolo.yaml
│   ├── evaluador_01.json
│   ├── evaluador_02.json
│   └── adjudicacion.json
├── 05_validez/
│   ├── validez.yaml
│   └── resultados.json
├── 06_calidad/
│   ├── calidad.yaml
│   └── resultados.json
├── 07_fiabilidad/
│   ├── fiabilidad.yaml
│   └── resultados.json
└── .privado/                          # Se crea únicamente al importar documentos
    ├── clave_pseudonimos.json
    └── correspondencia_origen.json
```

La plantilla nueva tiene 22 archivos antes de cargar datos. La migración añade su registro administrativo. Los dos archivos privados aparecen al importar; no son materiales de trabajo del evaluador ni entradas para un modelo. `.historial/especificacion/` puede conservar versiones JSON anteriores cuando regeneras la especificación.

La referencia mantiene archivos separados por evaluador para conservar sus originales. El responsable debe proporcionar accesos apropiados: la estructura por sí sola no implementa cegamiento ni permisos individuales de anotación.

## 3. Qué haces ahora en E1

Abre `laboratorios/mi_estudio_001/01_especificacion/especificacion.yaml`.

Contiene tu diccionario, incluidas las seis variables, las categorías y sus significados, los principios, las reglas de consistencia, los requisitos de metadatos y las decisiones pendientes. Los campos técnicos que todavía requieren aprobación siguen identificados como pendientes.

Dentro del mismo archivo encontrarás:

```yaml
instrucciones:
  extractor: null
  verificador: null
```

Cuando definas las instrucciones, puedes escribir texto multilínea en YAML:

```yaml
instrucciones:
  extractor: |
    Aquí se redactarán las instrucciones del extractor.
    Las líneas siguientes forman parte del mismo texto.
  verificador: null
```

Esto conserva instrucciones; no ejecuta el modelo. No necesitas crear archivos TXT.

Para actualizar la representación del framework después de guardar cambios:

```sh
cd /Users/jonathancamposlozano/Documents/Phd/Framework
.venv/bin/python scripts/laboratorio.py preparar-especificacion --laboratorio laboratorios/mi_estudio_001
```

`especificacion.json` contiene:

- `especificacion_completa`: todo lo definido en YAML, sin descartar campos que el núcleo aún no ejecuta.
- `diccionario_framework`: contrato `OperationalDictionary` validado.
- Referencia y huella del YAML utilizado.
- Indicadores de que no se verificó aprobación clínica ni se ejecutaron reglas.

Cada preparación conserva una instantánea exacta del YAML en `.historial/especificacion/`, identificada por su huella. Si ya existía una especificación preparada, también se conserva el JSON anterior allí. El historial mantiene únicamente YAML y JSON. Modificar el YAML no actualiza automáticamente el JSON; ejecuta de nuevo el comando.

**En tu diccionario, "true" y "false" deben seguir entre comillas**, pues son categorías de texto. `fecha_indice_evento` usa `date_or_null` en tu fuente y se proyecta a una variable `date`; la ausencia de valor pertenece al resultado. No se aplican cálculos de fechas ni reglas clínicas al preparar el contrato.

Las marcas de criterio pendiente permiten representar el borrador, pero no hacen suficiente el criterio para evaluar exactitud. E1 sigue en curso hasta revisar las definiciones, resolver pendientes y documentar su aprobación y congelación.

## 4. Cómo se ingresa el archivo de textos que enviaste

### Estructura de origen

La carga inicial utilizó una tabla TSV: dos columnas separadas por tabulador, llamadas `ingreso` y `analisis`. Algunas celdas de `analisis` incluyen saltos de línea y están delimitadas por comillas.

Por eso **una línea física del archivo no equivale a un documento**. El lector usa las reglas de la tabla para reconstruir cada celda completa. En el archivo recibido se reconocieron ocho registros documentales.

`datos/importacion.yaml` declara la correspondencia:

```yaml
formato_entrada: tsv
columna_identificador: ingreso
columna_texto: analisis
tipo_identificador: ingreso
campo_entidad: null
campo_fecha: null
```

Este archivo describe el formato de entrada; el TXT original puede permanecer fuera del laboratorio. La salida de la importación es JSON. No se exige que el archivo externo de donde provienen los textos ya sea YAML o JSON.

### Qué significa cada campo

| Origen | Destino | Tratamiento |
|---|---|---|
| Una celda `analisis` | `Document.text` | Texto completo, incluidos sus saltos de línea; sin resumir ni clasificar |
| Una fila lógica | Un documento | Se asigna un `document_id` pseudonimizado |
| `ingreso` | Identificador de procedencia pseudonimizado | No se usa directamente como `document_id` ni como paciente |
| Identificador de paciente | `entity_id` | Queda `null`, porque no hay una columna inequívoca de paciente |
| Fecha de consulta documental | `document_date` | Queda `null`, porque no hay una columna explícita de fecha |

La edad mencionada en una narrativa no se convierte en metadato ni se extraen eventos. No se interpreta ningún contenido clínico durante la carga.

### Forma de un documento JSON

Ejemplo completamente ficticio, solo para mostrar el formato:

```json
{
  "document_id": "doc-ejemplo-001",
  "entity_id": null,
  "text": "Texto libre del documento.\nSegunda línea del mismo documento.",
  "document_date": null,
  "provenance": {},
  "allowed_context": {}
}
```

`datos/documentos.json` es una lista JSON de objetos `Document`. El texto no se transforma en YAML ni se obliga a separar manualmente cada párrafo. En disco, JSON puede mostrar `\n`; al leerlo desde Python se recupera un salto de línea real.

### Qué se hizo con tu archivo

La carga inicial importó ocho registros en `mi_estudio_001`. Actualmente el corpus activo procede del Excel de 5.924 filas; consulta [Importación desde Excel](importacion-excel.md). Se comprobaron contra `Document` y se verificó que cada texto coincide exactamente con la celda de origen después de leer correctamente su formato TSV. Los saltos de línea se conservaron.

No se llamó a modelos, no se asignaron valores a tus seis variables y no se generaron etiquetas expertas. La importación no completa E1, E2 ni ninguna otra etapa científica.

### Importar otra tabla en un laboratorio nuevo

Desde la raíz de Framework:

```sh
.venv/bin/python scripts/laboratorio.py importar-textos \
  --laboratorio laboratorios/otro_estudio \
  --archivo /ruta/a/tu/archivo.txt
```

El laboratorio debe existir y su lista de documentos debe estar vacía. Si ya hay documentos, el comando se detiene: no los reemplaza ni agrega nuevos silenciosamente. Para la carga actual no es necesario ejecutar otra vez este comando.

El lector admite el TSV declarado y XLSX con mapeo explícito de hoja, columnas y fecha. Consulta [Importación desde Excel](importacion-excel.md). Otros formatos requieren su propio lector. No detecta automáticamente qué identificador representa a una persona.

## 5. Identificadores, privacidad y agrupación

Los identificadores de origen se sustituyeron mediante HMAC-SHA256 con una clave local. La correspondencia y la clave quedan en `.privado/`, con permisos de usuario local en sistemas compatibles; no se incorporan al documento enviado al modelo ni a los manifiestos experimentales.

**Seudonimizar el identificador no anonimiza la narrativa.** Los textos se conservaron sin borrar ni modificar lo documentado; pueden seguir conteniendo información sensible. La lista de documentos y el informe de carga se escriben con permisos locales restrictivos, pero esto no es cifrado ni un sistema multiusuario de control de acceso.

Un mismo `ingreso` obtiene la misma referencia de procedencia dentro del laboratorio, aunque tenga varias notas; cada nota obtiene un identificador de documento propio. Esa referencia no demuestra que dos ingresos diferentes sean de personas diferentes. Antes de diseñar particiones por paciente debes aportar un identificador pseudonimizado de paciente o una correspondencia autorizada. No se deben afirmar ausencia de fuga ni agrupación correcta con esta entrada sola.

El archivo tampoco aporta una fecha de consulta en columna. Si la fecha es necesaria como ancla para la extracción, debe incorporarse desde una fuente explícita y validada; no se tomó una fecha mencionada en el texto como sustituto automático.

## 6. Qué archivo corresponde a cada etapa

| Etapa | Lo que defines en YAML | Lo que conservará JSON |
|---|---|---|
| E1 | Variables, interpretación, corrección, reglas e instrucciones | Especificación preparada y contrato del diccionario |
| E2 | Población, unidades, muestreo, particiones y análisis | Muestra, particiones, pesos y verificaciones realizadas |
| E3 | Repeticiones, condiciones fijas y perturbaciones | Salidas originales, perfiles y concordancia |
| E4 | Protocolo, evaluadores y cegamiento | Anotaciones originales y adjudicación por separado |
| E5 | Comparación A/B, evaluabilidad, métodos e incertidumbre | PGEC, diferencia, intervalos y resultados por variable |
| E6 | Taxonomía y definición de señales | Errores codificados y señales observables |
| E7 | Ajuste, calibración, evaluación y política de uso | Probabilidades, calibración, riesgo-cobertura y decisiones |

Los JSON de resultados futuros empiezan con listas vacías o `null`, nunca con cifras de desempeño inventadas. La mayoría son contenedores de trabajo propuestos, no APIs de análisis implementadas. Tener el archivo no ejecuta su etapa.

No se modificó el núcleo para incorporar EPOC, proveedores o reglas clínicas. La preparación de especificación y la importación local son utilidades del laboratorio. La extracción automática con un modelo real sigue pendiente.

## 7. Seguimiento sin CSV

Edita únicamente `control/estado.json` para el avance metodológico. Contiene las siete etapas y la lista de 49 actividades, con su criterio de cierre. Los estados admitidos son `pendiente`, `en_curso`, `bloqueado`, `completado` y `no_aplica`.

Usa `resultado_obtenido` para el producto real de una etapa y `ruta_evidencia` para un archivo dentro del laboratorio. La marca `completado` necesita una revisión real; ni una importación ni una compilación de YAML la establecen automáticamente.

Para consultar:

```sh
.venv/bin/python scripts/laboratorio.py estado --laboratorio laboratorios/mi_estudio_001
```

Los controles del comando son administrativos, no una certificación científica. El estado es declarado por el responsable, no detectado a partir de un proceso de modelo en ejecución.

## 8. Crear el siguiente laboratorio

```sh
.venv/bin/python scripts/laboratorio.py crear --destino laboratorios/otro_estudio
```

El formato predeterminado ya es YAML/JSON. Se rechazan destinos existentes. La opción `--formato legado` se conserva solo para compatibilidad y pruebas de la estructura anterior; no es el flujo que debes utilizar ahora.

Las herramientas YAML usan el extra opcional `lab` (`PyYAML`), separado de la dependencia mínima del núcleo. En un entorno nuevo desde el repositorio fuente:

```sh
python -m pip install '.[lab]'
```

Esto instala el soporte necesario sin convertir la biblioteca en dependiente de ningún proveedor LLM. Los scripts y plantillas se distribuyen con el código fuente; no son comandos de consola instalados por el wheel.

## 9. Qué debes hacer a continuación

1. Abre `01_especificacion/especificacion.yaml` y revisa las decisiones pendientes de tu diccionario.
2. Define con los expertos las ventanas, ancla temporal, reglas y criterios de corrección; no necesitas editar otros formatos del diccionario.
3. Guarda y ejecuta `preparar-especificacion` para actualizar su JSON.
4. Completa el origen de la fecha documental y la agrupación por paciente antes de usarlos como condiciones del estudio.
5. Mantén E1 en curso hasta su revisión y congelación. El archivo de textos ya está incorporado; no hace falta volver a pegarlo o convertirlo manualmente.

## 10. Parametrizar E2: diseño estadístico (borrador 1.1.0)

La estructura está aprobada como borrador. **No están autorizadas la congelación ni las operaciones del estudio.** En `laboratorios/mi_estudio_001/02_diseno/` se conservan dos archivos:

- `diseno.yaml`: fuente editable del plan, con decisiones todavía en `null`.
- `resultados.json`: copia del plan, referencia versionada y SHA256, pendientes y bloqueos. Sus listas `muestra`, `particiones`, `pesos` y `controles_fuga` están vacías. Un informe de validación de parámetros no es un resultado estadístico.

### Poblaciones y alcance de la inferencia

| Sección YAML | Qué significa | Qué falta |
|---|---|---|
| `poblacion.fuente` | Universo documental de origen, antes de aplicar elegibilidad | Institución, periodo y marco que permita enumerar documentos/pacientes |
| `poblacion.elegible` | Subconjunto que cumple criterios clínicos y documentales aprobados | Inclusión, exclusión y cantidades de notas/pacientes; justificar explícitamente si no hay exclusiones |
| `poblacion.inferencia` | Población a la que se pretende generalizar el resultado | Relación con la elegible, límites y justificación de transportabilidad |

Los documentos cargados no demuestran representatividad, suficiencia muestral ni independencia entre pacientes. Su función —desarrollo, parte del corpus o corpus completo— sigue sin confirmarse. El identificador de ingreso no constituye por sí mismo un identificador de paciente. No se inspeccionan narrativas para inventar agrupaciones o fechas.

### Contraste principal y experimentos secundarios

PGEC conserva su función primaria: proporción global de pares documento-variable correctos según referencia y evaluabilidad preespecificadas, con pesos cuando el diseño lo exija. El contraste principal es `PGEC_B - PGEC_A`.

1. El bloque `configuraciones_comparadas.extractor_base` define una única configuración de extracción: modelo y parámetros, prompt, esquema y posprocesamiento versionados.
2. A produce y conserva la extracción original.
3. B consume exactamente ese artefacto; añade verificación y reconciliación sin volver a ejecutar el extractor.
4. El enlace exige documento, variable, experimento, identificador de extracción base, huella de sus bytes y huella de configuración comunes. La salida reconciliada no sustituye la original.

El efecto principal corresponde al conjunto **verificación más reconciliación**. Separar sus contribuciones requeriría otro experimento. El verificador puede usar otro modelo; permanece fijo dentro del contraste definido. Cambiar el extractor, su prompt o proveedor exige un experimento secundario identificado y con resultados separados. Se modifica un factor declarado y se conservan corpus, referencia, diccionario, evaluabilidad, particiones y método estadístico. Cuando modelo/proveedor no pueden aislarse, se declara el cambio conjunto y se limita la atribución causal. No se seleccionan configuraciones con etiquetas finales.

### Métricas secundarias preespecificadas

`metricas_secundarias` incluye las seis variables y todas las categorías del diccionario, incluida la indeterminación semántica:

| Nivel | Qué se registrará después de aprobación e implementación |
|---|---|
| Por variable | Corrección, cobertura, abstención, error técnico y no evaluabilidad; matriz de confusión en variables categóricas |
| Por categoría | Soporte de referencia, sensibilidad, precisión predictiva y F1; un denominador cero se informa como no estimable |
| Fecha índice | Coincidencia exacta, acierto dentro de tolerancia aprobada, error absoluto en días y disponibilidad |
| Grupo temporal | Exactitud conjunta de fecha, precisión temporal y método; inconsistencias según reglas aprobadas; discrepancia por precisión/método |
| Grupo estado/exacerbación | Exactitud conjunta e inconsistencias entre estado, exacerbación actual y previa, según reglas aprobadas |
| Cambio pareado | Errores corregidos, introducidos, persistentes y casos sin cambio, con la misma referencia |

Los denominadores clínicos se basan en referencia evaluable común A/B; las tasas operativas informan intentos esperados y sus conteos. La exactitud conjunta requiere reglas de evaluabilidad del grupo. Las tolerancias temporales y reglas clínicas siguen pendientes en E1. No se identifica automáticamente `indeterminado` con abstención o fallo, ni dos valores nulos con un acierto. Las métricas secundarias son descriptivas; si se añaden contrastes confirmatorios, debe preespecificarse multiplicidad antes de acceder a resultados finales.

### Cuatro funciones de datos separadas

| ID del plan | Función permitida | Restricción |
|---|---|---|
| `development` | Diccionario, candidatos de prompts, reglas y selección de configuración | Referencia independiente de desarrollo; validación interna agrupada por paciente |
| `reliability_fit` | Ajuste del estimador de fiabilidad e hiperparámetros | Sin seleccionar prompts ni acceder a etiquetas finales |
| `calibration` | Calibración y políticas autorizadas | Sin reajustar extractor, prompts ni estimador base |
| `evaluation` | Evaluación final reservada | Sin selección, ajuste, calibración o elección de umbrales con sus etiquetas |

La separación se define por paciente, incluyendo todas sus notas. No se han asignado documentos ni fijado porcentajes. Se justificarán tamaños con el corpus y los objetivos. El contrato actual de anotaciones del núcleo solo contempla las etiquetas históricas `development`, `calibration` y `evaluation`: estos cuatro roles son **parametrización metodológica**; el soporte de exportación de `reliability_fit` queda pendiente. No debe renombrarse silenciosamente como desarrollo ni confundirse con datos ya asignados.

### Validación y congelación de prompts

`validacion_prompts` reserva la selección exclusivamente a desarrollo. Antes de cualquier validación deben definirse candidatos versionados, presupuesto de iteraciones, criterio de selección y desempate, repeticiones, variaciones permitidas y umbral de estabilidad. Se usará referencia independiente de desarrollo para corrección, y se registrarán acuerdo, variación de PGEC, cobertura y fallos. Estabilidad y corrección son propiedades distintas.

Después de validar en desarrollo se registrarán las instrucciones elegidas para extractor y verificador, versiones, SHA256, parámetros, esquema, reglas, fecha y aprobador. Los conjuntos de ajuste, calibración y evaluación no se utilizarán para escoger instrucciones. Un cambio posterior exige nueva versión y un diseño de confirmación independiente; no se ajusta y vuelve a presentar como reservada la misma evaluación. Aquí solo queda descrito el plan: no se han ejecutado candidatos ni congelado instrucciones.

### Justificación del tamaño sin porcentajes arbitrarios

`justificacion_muestral_multicriterio.objetivos` exige cinco argumentos documentados:

1. **PGEC:** valor esperado o escenarios con fuente, precisión deseada y ponderación.
2. **Diferencia pareada:** discordancias esperadas sobre la misma extracción A y precisión del contraste; diferencia mínima relevante si se propone potencia.
3. **Dependencia por paciente:** pacientes distintos, notas por paciente, variabilidad y correlación; dependencia entre variables de una nota.
4. **Categorías infrecuentes:** frecuencia y soporte requeridos por categoría/estrato; eventual enriquecimiento y ponderación para inferencia poblacional.
5. **Fiabilidad y calibración posteriores:** complejidad prevista, soporte de aciertos/errores en ajuste y calibración y precisión suficiente en evaluación separada.

Cada objetivo necesita insumos con fuente, criterio de suficiencia y justificación. La síntesis debe reconciliar las exigencias con los cuatro roles, recursos y limitaciones. Las estimaciones preliminares deben proceder de referencia independiente de desarrollo o evidencia externa documentada. No se sustituyen por pseudoetiquetas LLM tratadas como verdad. No se ha calculado un tamaño ni adoptado un método definitivo: el remuestreo agrupado pareado con estratos/pesos sigue como candidato sujeto a aprobación y suficiencia del corpus.

### Preparar parámetros y consultar bloqueos

Después de editar el YAML, preparar su representación JSON:

```sh
.venv/bin/python scripts/laboratorio.py preparar-diseno --laboratorio laboratorios/mi_estudio_001
```

Este comando admite pendientes metodológicos, rechaza contradicciones y guarda instantáneas en `.historial/diseno/`. No calcula tamaños, no selecciona muestra, no asigna particiones ni calcula métricas. Si ya hay registros y cambia el plan, rechaza reemplazarlos silenciosamente; si el plan coincide, los conserva sin reescritura.

Para comprobar el bloqueo de una operación, sin ejecutarla:

```sh
.venv/bin/python scripts/laboratorio.py validar-diseno --laboratorio laboratorios/mi_estudio_001 --accion congelar
```

Las acciones consultables son `congelar`, `muestreo`, `particionado`, `extraccion`, `evaluacion` y `calibracion`. **Código de salida 2 significa bloqueo esperado**, acompañado de los pendientes. El comando relee YAML, especificación e informe actuales; no confía en un JSON de resultados antiguo. Rechaza una especificación JSON desactualizada.

Los controles rechazan roles incompletos o solapamiento declarado, selección de prompts fuera de desarrollo, cambios locales del extractor A/B, repetición de extracción en B, mezcla de experimentos secundarios, omisión de categorías/grupo temporal y tamaños inválidos. Existen además verificadores puros de metadatos suministrados para detectar pacientes entre roles y comprobar identidad de bytes y trazabilidad A/B; se prueban con datos sintéticos y no han sido aplicados como una ejecución del laboratorio.

La congelación permanece bloqueada por identificación de pacientes, criterios clínicos, diseño muestral y evaluabilidad pendientes, además del resto de decisiones registradas. Aprobar la estructura o cambiar una bandera YAML no autoriza ejecutar. Esta fase no dispone de ejecutores científicos; todas las operaciones quedan denegadas en la interfaz aunque se alteren sus autorizaciones declaradas. El informe distingue pendientes, falta de autorización y ausencia de ejecutor. Son controles del organizador, no permisos del sistema operativo ni protección frente a programas externos. Los futuros ejecutores deberán integrar estas validaciones y sus controles de evidencia/autorización por fase antes de habilitarse.

El tablero `control/estado.json` conserva E2 en curso; no se ha cerrado ninguna actividad por el mero hecho de preparar archivos.

## Ejecución documental de fase 2

La planificación descrita arriba ahora se complementa con [verificación independiente, comparación y reconciliación por documento](fase2-verificacion-laboratorio.md). Usa `preparar-verificacion`, `demo-verificacion`, `registrar-extraccion-a`, `ejecutar-verificacion` y `estado-verificacion` desde `scripts/laboratorio.py`.

Estos procedimientos generan artefactos y seguimiento técnico en el laboratorio; no cierran sus siete etapas ni cambian autorizaciones de muestreo, evaluación o calibración. La demostración de `mi_estudio_001` usa datos sintéticos separados de su corpus importado.
