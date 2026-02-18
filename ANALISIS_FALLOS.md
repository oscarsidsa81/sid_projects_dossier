# Análisis de posibles fallos en `sid_projects_dossier`

## 1) Duplicidad/conflicto de definición en `sale.order`
- El modelo `sale.order` se extiende en **dos ficheros** distintos con campos y métodos del mismo nombre (`dossier_folder_id`, `dossier_asignado`, `tiene_dossier`, `action_view_dossier`, `action_open_dossier_wizard_create`, `action_open_dossier_wizard_link`).
- En particular, `dossier_folder_id` se define con dos `related` diferentes:
  - `quotations_id.dossier_folder_id`
  - `quotations_id.dossier_effective_folder_id`
- Esto puede generar comportamiento no determinista (depende del orden de carga), sobreescrituras silenciosas y efectos laterales en vistas/acciones.

**Recomendación:** Consolidar toda la lógica de `sale.order` en un único fichero/clase y mantener una sola definición por campo/método.

## 2) XML-ID del root inconsistente en el wizard
- El wizard busca el root con el XML-ID `sid_projects_dossier.folder_root_dossieres_calidad`.
- Sin embargo, el XML-ID definido en datos y hooks es `sid_projects_dossier.sid_workspace_quality_dossiers`.
- Resultado: la búsqueda por XML-ID del wizard falla sistemáticamente y cae al fallback por nombre (más frágil).

**Recomendación:** usar un único XML-ID canónico en todo el módulo (`sid_workspace_quality_dossiers`) y eliminar referencias antiguas.

## 3) Datos de carpetas no cargados en `__manifest__.py`
- Existe un archivo `data/document_folders.xml` con el root y carpetas por año.
- Ese fichero **no está** en la lista `data` del `__manifest__.py`.
- En instalaciones limpias, esto puede dejar el módulo sin estructura base y provocar errores funcionales en el wizard.

**Recomendación:** añadir `data/document_folders.xml` al `__manifest__.py` (o justificar explícitamente por qué no debe cargarse).

## 4) IDs hardcodeados (`browse(7)` y `owner_id = 8`)
- En la creación de estructura se usa `Folder.browse(7)` para facetas y `owner_id = 8` para solicitudes.
- Estos IDs dependen de cada base de datos; en otra instancia pueden apuntar a registros incorrectos o inexistentes.

**Recomendación:** reemplazar por XML-IDs (`env.ref(...)`) o por configuración parametrizable.

## 5) Uso de `except Exception: pass` en rutas críticas
- Hay varios bloques que silencian cualquier excepción durante asignación de facetas/chatter.
- Esto oculta errores reales, dificulta debugging y puede dejar datos a medio crear sin trazabilidad.

**Recomendación:** capturar excepciones esperadas de forma específica y registrar (`_logger.exception`) para diagnóstico.

## 6) Inconsistencia en estructura declarada vs creada
- Se declara `'15. Milestones'` en `folders_sin_estado`, pero no existe en `child_folders`, por lo que nunca se crea.

**Recomendación:** alinear ambos arrays (`child_folders` y reglas auxiliares) para evitar configuración muerta.

## Comprobaciones rápidas ejecutadas
- `python -m compileall -q .` ✅ (sin errores de sintaxis Python).
