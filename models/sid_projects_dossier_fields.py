# -*- coding: utf-8 -*-

from odoo import api, fields, models


class DocumentsDocumentDossier(models.Model):
    _inherit = 'documents.document'

    _SID_DOC_TAG_BY_PARENT_KEYWORD = {
        'itp': 'ITP',
        'procedimientos': 'PROCEDIMIENTO',
        'certificados': 'CERTIFICADOS',
        'plano': 'PLANO',
        'mpr': 'MPR',
        'schedule': 'SCHEDULE',
        'lista de materiales': 'LISTA DE MATERIALES',
        'packing list': 'PACKING LIST',
        'quality plan': 'QUALITY PLAN',
        'dossier final': 'DOSSIER',
        'lista de documentos': 'LISTA DE DOCUMENTOS',
    }
    _SID_ESTADO_TAG_BY_FOLDER_KEYWORD = {
        'enviado': 'ENVIADO',
        'proveedor': 'PROVEEDOR',
        'comentarios': 'COMENTARIOS',
        'rechazado': 'RECHAZADO',
        'aprobado': 'APROBADO',
    }
    _SID_FACET_BY_PARENT_KEYWORD = {
        'itp': 'ITP',
        'plano': 'PLANOS',
        'contrato': 'CONTRATO',
    }

    dossier_contrato = fields.Char(
        string='Dossier (contrato)',
        compute='_compute_dossier_contrato',
        store=True,
        readonly=True,
        help='Carpeta de dossier (nivel 2) a la que cuelga el documento.',
    )

    document_description = fields.Char(string='Descripción', store=True)
    document_transmittal = fields.Char(string='Transmittal', store=True)

    def _sid_get_quality_workspace(self):
        return self.env.ref('sid_projects_dossier.sid_workspace_quality_dossiers', raise_if_not_found=False)

    def _sid_find_facet_by_names(self, workspace, names):
        Facet = self.env['documents.facet'].sudo()
        return Facet.search([
            ('folder_id', '=', workspace.id),
            ('name', 'in', names),
        ], limit=1)

    def _sid_get_target_facet(self, workspace, parent_folder_name):
        facet_name = self._sid_pick_tag_name(parent_folder_name, self._SID_FACET_BY_PARENT_KEYWORD)
        if facet_name:
            return self._sid_find_facet_by_names(workspace, [facet_name])
        return self._sid_find_facet_by_names(workspace, ['DOC', 'ESTADO'])

    def _sid_pick_tag_name(self, source_name, mapping):
        source_name = (source_name or '').lower()
        for keyword, tag_name in mapping.items():
            if keyword in source_name:
                return tag_name
        return False

    def _sid_sync_tags_from_folder(self):
        Tag = self.env['documents.tag'].sudo()
        excluded_folders = {'12. Contrato', '0. Plantillas'}

        workspace = self._sid_get_quality_workspace()
        if not workspace:
            return

        for doc in self:
            folder = doc.folder_id
            if not folder or not folder.parent_folder_id or folder.name in excluded_folders:
                continue

            target_facet = self._sid_get_target_facet(workspace, folder.parent_folder_id.name)
            if not target_facet:
                continue

            doc_tag_name = self._sid_pick_tag_name(folder.parent_folder_id.name, self._SID_DOC_TAG_BY_PARENT_KEYWORD)
            estado_tag_name = self._sid_pick_tag_name(folder.name, self._SID_ESTADO_TAG_BY_FOLDER_KEYWORD)

            target_doc_tag = Tag
            target_estado_tag = Tag
            if doc_tag_name:
                target_doc_tag = Tag.search([
                    ('facet_id', '=', target_facet.id),
                    ('name', '=', doc_tag_name),
                ], limit=1)
            if estado_tag_name:
                target_estado_tag = Tag.search([
                    ('facet_id', '=', target_facet.id),
                    ('name', '=', estado_tag_name),
                ], limit=1)

            commands = []
            if doc_tag_name:
                current_doc_tags = doc.tag_ids.filtered(lambda t: t.facet_id.id == target_facet.id and t.name in self._SID_DOC_TAG_BY_PARENT_KEYWORD.values())
                for current_tag in current_doc_tags:
                    if not target_doc_tag or current_tag.id != target_doc_tag.id:
                        commands.append((3, current_tag.id))
                if target_doc_tag and target_doc_tag.id not in doc.tag_ids.ids:
                    commands.append((4, target_doc_tag.id))

            if estado_tag_name:
                current_estado_tags = doc.tag_ids.filtered(lambda t: t.facet_id.id == target_facet.id and t.name in self._SID_ESTADO_TAG_BY_FOLDER_KEYWORD.values())
                for current_tag in current_estado_tags:
                    if not target_estado_tag or current_tag.id != target_estado_tag.id:
                        commands.append((3, current_tag.id))
                if target_estado_tag and target_estado_tag.id not in doc.tag_ids.ids:
                    commands.append((4, target_estado_tag.id))

            if commands:
                doc.write({'tag_ids': commands})

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._sid_sync_tags_from_folder()
        return records

    def write(self, vals):
        res = super().write(vals)
        if 'folder_id' in vals:
            self._sid_sync_tags_from_folder()
        return res

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
