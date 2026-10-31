# Corpus desde Excel

El importador local admite TSV y XLSX. No modifica el archivo fuente, no ejecuta fórmulas ni llama a modelos.

## Configuración de mi_estudio_001

El archivo fuente está en `laboratorios/mi_estudio_001/datos/Texto Libre.xlsx`. La hoja `Hoja1` contiene 5.924 registros documentales con fecha de atención. Se omitieron 136 filas completamente vacías.

El archivo `datos/importacion.yaml` declara:

```yaml
formato_entrada: xlsx
archivo_origen: Texto Libre.xlsx
hoja_entrada: Hoja1
columna_identificador: ingreso
columna_texto: analisis
campo_fecha: FECHA ATENCIÓN
significado_fecha: fecha_atencion
formato_fecha_texto: '%d/%m/%Y'
tipo_identificador: ingreso
campo_entidad: null
```

- `ingreso` se conserva únicamente en la correspondencia privada. No identifica automáticamente al paciente. Cada fila recibe un identificador de documento seudonimizado distinto, incluso si se repite el ingreso.
- `analisis` pasa íntegro a `Document.text`, incluidos espacios, saltos de línea y etiquetas literales como `<br>`.
- `FECHA ATENCIÓN` pasa a `Document.document_date`, con procedencia que declara `fecha_atencion`. No se calcula inicio del episodio ni fecha índice de exacerbación.

Las fechas numéricas con formato de fecha Excel se interpretan usando la época del libro. Las fechas textuales requieren el formato declarado con año de cuatro cifras. Una fecha ausente permanece ausente. Una fecha inválida o un año textual de dos cifras bloquea la carga para evitar decidir silenciosamente un siglo. Las columnas requeridas no admiten fórmulas ni errores de Excel.

## Ejecutar

Instala el extra de laboratorio en tu entorno: `python -m pip install '.[lab]'`. Añade openpyxl; el núcleo científico conserva Pydantic como única dependencia directa.

```bash
.venv/bin/python scripts/laboratorio.py importar-textos \
  --laboratorio laboratorios/mi_estudio_001 \
  --archivo 'laboratorios/mi_estudio_001/datos/Texto Libre.xlsx'
```

Si existe una carga anterior, el comando la rechaza. Para sustituir el corpus activo conservando los archivos disponibles:

```bash
.venv/bin/python scripts/laboratorio.py importar-textos \
  --laboratorio laboratorios/mi_estudio_001 \
  --archivo 'laboratorios/mi_estudio_001/datos/Texto Libre.xlsx' \
  --reemplazar-con-respaldo
```

No se añaden silenciosamente filas al corpus anterior ni se deduplican notas por ingreso. La sustitución crea una carpeta privada en `.historial/importaciones/`, que respalda documentos, informe y correspondencia cuando esos archivos existen. Todas las filas nuevas se validan antes de sustituir archivos activos. Un fallo de escritura restaura los archivos activos anteriores.

## Salidas

| Archivo | Contenido |
|---|---|
| `datos/documentos.json` | Corpus activo tipado, textos literales y fechas de atención |
| `datos/informe_importacion.json` | Conteos, hash del Excel, mapeo de columnas y ruta del respaldo |
| `.privado/correspondencia_origen.json` | Relación entre documento seudonimizado e ingreso original |
| `.privado/clave_pseudonimos.json` | Clave local; se conserva al cambiar de corpus |

En la carga realizada, el antiguo `datos/documentos.json` no estaba presente. Se conservaron el informe y la correspondencia existentes de ocho registros; no se afirma haber recuperado los textos ausentes. El nuevo informe registra esta circunstancia con `corpus_anterior_disponible: false`.

Se compararon las 5.924 notas y sus fechas contra el Excel: los textos y las fechas coinciden en todas las filas, y los identificadores de documento son únicos. El libro original conserva su hash.

El diseño del estudio refleja el nuevo número disponible, sin asignar roles, justificar tamaño muestral, agrupar pacientes ni calcular métricas. La narrativa sigue sin anonimización automática y no se ha enviado a servicios externos.
