from odoo import fields, models, api, _
from odoo.exceptions import UserError


class SaleOrderDossier ( models.Model ) :
    _inherit = 'sale.order'

    dossier_asignado = fields.Char (
        string="Dossier actual",
        store=True,
        help="Campo para definir la carpeta de Documentos"
    )

    tiene_dossier = fields.Boolean (
        string="Dossier activo",
        help="	Campo para saber si se creó un dossier para este nº de contrato",
        store=True,
        readonly=True,
    )

    # ---------------------------------------------------------------------
    # Botones usados en vistas
    # ---------------------------------------------------------------------
    # Nota: estos métodos se definen también en otros mixins del módulo.
    # Dejar aquí una implementación "segura" evita errores de validación
    # de vistas si por cualquier motivo no se cargara el otro mixin.

    def action_open_dossier_assign_wizard(self):
        """Abre el wizard de asignación de dossier."""
        self.ensure_one()
        action = self.env.ref('sid_projects_dossier.action_dossier_assign_wizard', raise_if_not_found=False)
        if not action:
            raise UserError(_("No se encuentra la acción del wizard de dossier."))
        vals = action.read()[0]
        ctx = dict(self.env.context or {})
        ctx.update({'default_sale_order_id': self.id})
        vals['context'] = ctx
        return vals

    def action_open_dossier_folder(self):
        """Compatibilidad: si el otro mixin no está, al menos abre el wizard."""
        return self.action_open_dossier_assign_wizard()

    def action_create_dossier_folders(self):
        """Compatibilidad: garantiza que el botón de la vista no rompa la instalación.
        La lógica completa vive en sid_projects_dossier_server_actions.
        Aquí devolvemos el wizard para que el usuario continúe de forma segura.
        """
        return self.action_open_dossier_assign_wizard()


class DocumentsDocumentDossier ( models.Model ) :
    _inherit = 'documents.document'

    dossier_contrato = fields.Text (
        string="Nª de Contrato",
        compute="_sid_dossier_contrato",
        store=True,
        readonly=True,
        help="Campo para reflejar el Nº de contrato vinculado",
    )

    document_description = fields.Char (
        string="Descripción",
        store=True,
        help="Campo para poner la descripción de la VDDL"
    )

    document_transmittal = fields.Char (
        string="Descripción",
        store=True,
        help="Campo para poner el transmittal de la VDDL"
    )

    # === MÉTODOS ===

    @api.depends ( 'folder_id', 'folder_id.parent_folder_id', 'folder_id.parent_folder_id.parent_folder_id' )
    def _sid_dossier_contrato(self) :
        for doc in self :
            folder = doc.folder_id
            section = None

            # Obtenemos el registro del workspace por XML ID
            dossier_root = self.env.ref ( 'sid_projects_dossier.sid_workspace_quality_dossiers', raise_if_not_found=False )
            # Recorremos hacia arriba hasta encontrar que el abuelo sea el workspace
            while folder and folder.parent_folder_id :
                grandparent = folder.parent_folder_id.parent_folder_id
                if grandparent and dossier_root and grandparent.id == dossier_root.id :
                    section = folder
                    break
                folder = folder.parent_folder_id

            doc.write ( {'dossier_contrato' : section.name if section else ''} )