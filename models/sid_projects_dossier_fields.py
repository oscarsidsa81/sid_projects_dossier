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
