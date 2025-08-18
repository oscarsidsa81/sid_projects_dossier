from odoo import fields, models, api


class SaleOrderDossier ( models.Model ) :
    _inherit = 'sale.order'

    dossier_asignado = fields.Char (
        string="Dossier",
        store=True,
        help="Campo para definir la carpeta de Documentos"
    )

    tiene_dossier = fields.Boolean (
        string="Tiene Dossier",
        help="	Campo para saber si se creó un dossier para este nº de contrato",
        store=True,
        readonly=True,
    )

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