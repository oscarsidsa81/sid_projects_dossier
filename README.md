# sid_projects_dossier

Módulo de Odoo para gestionar **dossieres de calidad** vinculados a contratos y pedidos de venta, con integración en **Documents** y soporte de jerarquía **contrato principal / adendas**.

## ¿Qué hace este módulo?

Este addon añade una capa funcional para que el área comercial y documental pueda:

- Crear o vincular un dossier desde `sale.order` y `sale.quotations` mediante un asistente.
- Resolver automáticamente el dossier “efectivo” (el propio de la adenda o el del contrato principal).
- Abrir rápidamente todos los documentos del dossier en la app `documents.document` filtrando por carpeta y subcarpetas.
- Estandarizar la estructura de carpetas del dossier (plantillas, certificados, logística, etc.) de forma idempotente.
- Mantener un root de trabajo estable (“Dossieres de calidad”) con soporte para carpetas por año.

## Dependencias

Declaradas en el manifiesto:

- `base`
- `crm`
- `sale_management`
- `documents`
- `oct_sale_extra_fields`
- `sid_bankbonds_mod`

## Funcionalidades principales (análisis)

## 1) Integración con ventas (`sale.order`)

- Se añaden campos calculados/relacionados para indicar si el pedido tiene dossier y cuál es el asignado.
- Se incorporan acciones para:
  - abrir el wizard en modo crear,
  - abrir el wizard en modo vincular,
  - abrir la vista de documentos del dossier.
- Se añade una vista tipo listado “Contratos con Dossier” y un menú `Ventas > Dossieres` filtrando pedidos confirmados con dossier.

**Valor funcional**: el usuario comercial puede operar dossiers sin salir del flujo de ventas.

## 2) Integración con presupuestos/contratos (`sale.quotations`)

- Se modela la jerarquía de contrato principal y adendas con `dossier_root_id`.
- Se distinguen:
  - `dossier_folder_id` (dossier propio de la oferta/contrato),
  - `principal_dossier_folder_id` (dossier del contrato raíz),
  - `dossier_effective_folder_id` (el realmente aplicable).
- Se valida coherencia entre cliente y contrato principal (`parent_id`) para evitar vínculos inconsistentes.
- Se añade estado de dossier (`suministro`, `en_proceso`, `enviado`, `aprobado`).

**Valor funcional**: las adendas pueden heredar dossier o tener uno propio sin perder trazabilidad.

## 3) Wizard de creación/vinculación (`sid.dossier.assign.wizard`)

El asistente concentra la lógica de negocio:

- Operaciones soportadas:
  - **Crear dossier nuevo**,
  - **Vincular dossier existente**.
- Para adendas permite política:
  - usar dossier del principal,
  - dossier propio de la adenda.
- Incluye validaciones y advertencias:
  - evita operaciones inválidas por tipo de contrato,
  - avisa si la carpeta ya contiene documentos,
  - avisa si la carpeta ya está vinculada a otro contrato.
- Crea automáticamente carpeta anual si no existe y evita duplicados por nombre entre años (con reglas específicas para adendas con dossier propio).
- Tras confirmar, fuerza sincronización para refrescar campos almacenados en `sale.order`.

**Valor funcional**: reduce errores operativos al asignar dossiers y unifica el flujo en una sola pantalla.

## 4) Estructura documental estandarizada

La función `create_dossier_structure(...)`:

- crea (o completa) subcarpetas estándar del dossier,
- crea subniveles por estado (Proveedor, Enviado, Comentarios, Rechazado, Aprobado) donde aplica,
- crea subniveles NOI,
- crea “Adendas” bajo “13. Contrato”,
- genera solicitudes (`documents.request_wizard`) por subcarpeta,
- intenta asociar facetas existentes de Documents.

**Valor funcional**: todos los proyectos quedan con la misma taxonomía documental.

## 5) Inicialización y compatibilidad con datos existentes

El módulo usa hooks `pre_init`/`post_init` para:

- detectar carpeta raíz existente de dossiers de calidad,
- vincularla a XML-ID estable `sid_workspace_quality_dossiers`,
- enlazar carpetas de año existentes a XML-IDs predecibles.

Además incluye utilidades para reparar/asegurar XML-ID del root durante inicialización del modelo.

**Valor funcional**: facilita instalación/upgrade en bases con estructura documental previa.

## Seguridad y acceso

- Se define el acceso del wizard para `base.group_user` (lectura/escritura/creación/eliminación).
- Se crean grupos funcionales:
  - `Usuario de Dossier`,
  - `Creador de Dossier`.

## Estructura del repositorio

- `models/`: lógica de negocio y extensiones de modelos de Odoo.
- `views/`: vistas de ventas y placeholders de quotations.
- `data/`: acciones, grupos, tags y vistas del wizard.
- `security/`: ACL y base de seguridad.
- `hooks.py`: binding de XML-IDs en instalación/upgrade.

## Flujo típico de uso

1. El usuario abre un pedido o presupuesto/contrato.
2. Lanza **Crear dossier** o **Vincular dossier**.
3. El wizard decide el target (principal o adenda) según política seleccionada.
4. Se crea o vincula carpeta en Documents.
5. Se completa estructura estándar de subcarpetas.
6. Desde “Ver Dossier” se abre la vista de documentos filtrada al ámbito del dossier.

## Estado actual y observaciones técnicas

- El módulo contiene una base funcional sólida para operar dossiers desde ventas y contratos.
- Existe documentación interna (`ANALISIS_FALLOS.md`) con posibles mejoras de robustez (consolidación de extensiones duplicadas en `sale.order`, evitar IDs hardcodeados, etc.).

## Instalación (Odoo)

1. Copiar el módulo en el path de addons.
2. Actualizar lista de apps.
3. Instalar `sid_projects_dossier`.
4. Verificar que exista la carpeta raíz de Documents “Dossieres de calidad” o que quede vinculada por hooks.
5. Asigna el group_id a los usuarios pertinentes

## Licencia

AGPL-3.
