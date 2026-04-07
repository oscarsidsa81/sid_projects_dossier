# -*- coding: utf-8 -*-

from odoo import api, fields, models


class SaleOrderDossier(models.Model):
    _inherit = 'sale.order'

    # Visible/agrupable en sale.order, pero el vínculo vive en sale.quotations
    dossier_folder_id = fields.Many2one(
        comodel_name='documents.folder',
        string='Dossier (carpeta)',
        related='quotations_id.dossier_folder_id',
        store=True,
        readonly=True,
    )
    dossier_asignado = fields.Char(
        string='Dossier asignado',
        compute='_compute_dossier_asignado',
        store=True,
        readonly=True,
    )
    tiene_dossier = fields.Boolean(
        string='Dossier activo',
        compute='_compute_tiene_dossier',
        store=True,
        readonly=True,
    )

    @api.depends('dossier_folder_id')
    def _compute_tiene_dossier(self):
        for so in self:
            so.tiene_dossier = bool(so.dossier_folder_id)

    @api.depends('dossier_folder_id', 'dossier_folder_id.name')
    def _compute_dossier_asignado(self):
        for so in self:
            so.dossier_asignado = so.dossier_folder_id.name if so.dossier_folder_id else ''

    def action_open_dossier_wizard_create(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Crear dossier',
            'res_model': 'sid.dossier.assign.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_sale_order_id': self.id,
                'default_quotation_id': self.quotations_id.id if self.quotations_id else False,
                'default_mode': 'new',
            },
        }

    def action_open_dossier_wizard_link(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Vincular dossier',
            'res_model': 'sid.dossier.assign.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_sale_order_id': self.id,
                'default_quotation_id': self.quotations_id.id if self.quotations_id else False,
                'default_mode': 'existing',
            },
        }

    def action_view_dossier(self):
        self.ensure_one()
        if not self.dossier_folder_id:
            return self.action_open_dossier_wizard_link()
        folder = self.dossier_folder_id
        # Abrir DOCUMENTOS (documents.document) filtrados por la carpeta del dossier.
        # Usamos child_of para incluir subcarpetas.
        return {
            'name': 'Documentos',
            'type': 'ir.actions.act_window',
            'res_model': 'documents.document',
            'view_mode': 'tree,kanban,form',
            'domain': [('folder_id', 'child_of', folder.id)],
            'context': {
                'default_folder_id': folder.id,
                'searchpanel_default_folder_id': folder.id,
                'searchpanel_default_folder_id_domain': [('folder_id', 'child_of', folder.id)],
                'group_by': 'folder_id',
            },
            'target': 'current',
        }


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

        doc_facet = self._sid_find_facet_by_names(workspace, ['DOC', 'ITP'])
        estado_facet = self._sid_find_facet_by_names(workspace, ['ESTADO', 'PLANOS'])
        if not doc_facet and not estado_facet:
            return

        for doc in self:
            folder = doc.folder_id
            if not folder or not folder.parent_folder_id or folder.name in excluded_folders:
                continue

            doc_tag_name = self._sid_pick_tag_name(folder.parent_folder_id.name, self._SID_DOC_TAG_BY_PARENT_KEYWORD)
            estado_tag_name = self._sid_pick_tag_name(folder.name, self._SID_ESTADO_TAG_BY_FOLDER_KEYWORD)

            target_doc_tag = Tag
            target_estado_tag = Tag
            if doc_facet and doc_tag_name:
                target_doc_tag = Tag.search([
                    ('facet_id', '=', doc_facet.id),
                    ('name', '=', doc_tag_name),
                ], limit=1)
            if estado_facet and estado_tag_name:
                target_estado_tag = Tag.search([
                    ('facet_id', '=', estado_facet.id),
                    ('name', '=', estado_tag_name),
                ], limit=1)

            commands = []
            if doc_facet:
                current_doc_tags = doc.tag_ids.filtered(lambda t: t.facet_id.id == doc_facet.id)
                for current_tag in current_doc_tags:
                    if not target_doc_tag or current_tag.id != target_doc_tag.id:
                        commands.append((3, current_tag.id))
                if target_doc_tag and target_doc_tag.id not in doc.tag_ids.ids:
                    commands.append((4, target_doc_tag.id))

            if estado_facet:
                current_estado_tags = doc.tag_ids.filtered(lambda t: t.facet_id.id == estado_facet.id)
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
