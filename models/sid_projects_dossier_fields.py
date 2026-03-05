# -*- coding: utf-8 -*-

from odoo import api, fields, models


class DocumentsDocumentDossier(models.Model):
    _inherit = 'documents.document'

    dossier_contrato = fields.Char(
        string='Dossier (contrato)',
        compute='_compute_dossier_contrato',
        store=True,
        readonly=True,
        help='Carpeta de dossier (nivel 2) a la que cuelga el documento.',
    )

    document_description = fields.Char(string='Descripción', store=True)
    document_transmittal = fields.Char(string='Transmittal', store=True)

    @api.depends('folder_id', 'folder_id.parent_folder_id', 'folder_id.parent_folder_id.parent_folder_id')
    def _compute_dossier_contrato(self):
        root = self.env.ref('sid_projects_dossier.sid_workspace_quality_dossiers', raise_if_not_found=False)
        for doc in self:
            dossier_folder = False
            folder = doc.folder_id
            while folder and folder.parent_folder_id:
                # Dossier folder is the one whose grandparent is the root
                if root and folder.parent_folder_id.parent_folder_id and folder.parent_folder_id.parent_folder_id.id == root.id:
                    dossier_folder = folder
                    break
                folder = folder.parent_folder_id
            doc.dossier_contrato = dossier_folder.name if dossier_folder else ''
