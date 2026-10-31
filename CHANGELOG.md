# Historial

## 0.1.0

- Fase 1: contratos genéricos, puertos estructurales y dos modelos simulados.
- Valores semánticos separados de operación, evidencia, abstención y fallo técnico.
- Configuración versionada y manifiestos con referencias y huellas.
- Pruebas sintéticas sin proveedores ni datos reales.
- Instructivo detallado en español y tutorial ejecutable con archivos y huellas verificadas.

- Organizador externo de laboratorios con plantillas vacías, 49 actividades y consulta manual de las siete etapas; no implementa nuevas etapas científicas.

- Laboratorios formato 2: YAML editable y JSON de datos/resultados; preparación explícita de especificación e importación local TSV con soporte multilínea e identificadores seudonimizados. Sin ejecución LLM ni métricas nuevas.

- Preparación explícita del plan E2 desde YAML a JSON con pendientes y conservación de registros; no calcula tamaño, muestreo, particiones ni métricas.

- E2: poblaciones diferenciadas, cuatro roles de datos, prompts solo en desarrollo, contraste A/B sobre artefacto idéntico, secundarios y tamaño multicriterio; validación con bloqueo operativo y pruebas sintéticas. Sin ejecución científica.

## 0.2.0 — Fase 2 documental

- Contratos de verificación independiente, comparación, reconciliación, evidencia localizada y manifiestos.
- Casos de uso separados del proveedor, adaptador OpenAI Responses por HTTP y mock sin red.
- Comparación determinista y política conservadora con aprobación y evidencia exigidas para reemplazar.
- Persistencia separada de A, verificación, comparación, decisiones y B; reanudación con integridad.
- CLI `extracteval verify` y comandos integrados del laboratorio para preparar, demostrar, registrar A y consultar progreso.
- Configuración EPOC externa, prompts versionados y pruebas sintéticas; sin métricas clínicas.

### Importación XLSX del laboratorio

- Lector XLSX con hoja y columnas explícitas, fechas Excel y texto literal; sin ejecutar fórmulas.
- Mapeo de fecha de atención separado del inicio de exacerbación y de la identidad del paciente.
- Respaldo del corpus y correspondencia al solicitar reemplazo; recuperación de archivos ante fallo de escritura.
- Dependencia openpyxl en el extra lab y pruebas con libros sintéticos.

### Auditoría y consolidación de fase 2

- Vinculación comprobada del diccionario y prompt con sus fuentes preparadas; escaneo de integridad sin seguir enlaces.
- Hashes reales del esquema y configuración para nuevas importaciones de A, preservando originales e históricos.
- Consolidación del verificador y candidato técnico en el diseño del laboratorio, sin seleccionar otro modelo ni aprobar decisiones científicas.
- Cinco pruebas nuevas y refuerzo de trazabilidad de importación; inventario e informe de estado real, con extractor clínico A pendiente de localizar.

### Extractor A e integración documental

- Caso de uso de extracción con los contratos existentes, configuración independiente, prompt procedural y seis resultados por documento.
- Registro tipado de A, auditoría, integridad, reanudación sin segunda llamada y demostración sintética A/V/B.
- Campos técnicos y candidato de A documentados en el laboratorio; sin aprobación científica ni procesamiento del corpus real.

### Fase 3 técnica: estabilidad

- Coordinador de repetición completa y A fija, con IDs experimentales persistentes, presupuestos y recuperación sin duplicar repeticiones.
- Comparación por variable y registro, fechas, estados y decisiones; contraste A/B sobre pares comunes, sin PGEC ni intervalos confirmatorios.
- Piloto sintético 10 × 5 en dos modalidades, resultados JSON e informes; ruta real deshabilitada con activación explícita separada.
