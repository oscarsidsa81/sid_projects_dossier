# -*- coding: utf-8 -*-

from datetime import date

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class SaleQuotationsDossier(models.Model):
    _inherit = 'sale.quotations'

    dossier_root_id = fields.Many2one(
        comodel_name='sale.quotations',
        string='Contrato principal',
        compute='_compute_dossier_root_id',
        store=True,
        readonly=True,
    )

    dossier_folder_id = fields.Many2one(
        comodel_name='documents.folder',
        string='Dossier (oferta)',
        help=(
            'Carpeta del dossier asociada a ESTA oferta (sale.quotations). '
            'En el contrato principal este campo apunta a la carpeta principal. '
            'En una adenda puede estar vacío (usa el dossier principal) o apuntar '
            'a una carpeta propia si se decide que la adenda tenga su propio dossier.'
        ),
    )

    principal_dossier_folder_id = fields.Many2one(
        comodel_name='documents.folder',
        string='Dossier (principal)',
        related='dossier_root_id.dossier_folder_id',
        store=True,
        readonly=True,
        help='Carpeta del dossier del contrato principal (root de la jerarquía).',
    )

    dossier_effective_folder_id = fields.Many2one(
        comodel_name='documents.folder',
        string='Dossier (efectivo)',
        compute='_compute_dossier_effective_folder_id',
        store=True,
        readonly=True,
        help='Dossier a utilizar: el propio de la oferta si existe; si no, el del contrato principal.',
    )

    dossier_state = fields.Selection(
        selection=[
            ('suministro', 'Suministro'),
            ('en_proceso', 'En proceso'),
            ('enviado', 'Enviado'),
            ('aprobado', 'Aprobado'),
        ],
        string='Estado del dossier',
        default='en_proceso',
        tracking=True,
    )

    has_dossier = fields.Boolean(
        string='Tiene dossier',
        compute='_compute_has_dossier',
        store=True,
        readonly=True,
    )

    @api.depends('parent_id')
    def _compute_dossier_root_id(self):
        for q in self:
            root = q
            seen = set()
            while root.parent_id and root.id not in seen:
                seen.add(root.id)
                root = root.parent_id
            q.dossier_root_id = root

    @api.depends('dossier_effective_folder_id')
    def _compute_has_dossier(self):
        for q in self:
            q.has_dossier = bool(q.dossier_effective_folder_id)

    @api.depends('dossier_folder_id', 'principal_dossier_folder_id')
    def _compute_dossier_effective_folder_id(self):
        for q in self:
            q.dossier_effective_folder_id = q.dossier_folder_id or q.principal_dossier_folder_id

    # ---------------------------------------------------------------------
    # Actions
    # ---------------------------------------------------------------------

    def action_view_dossier(self):
        self.ensure_one()
        folder = self.dossier_effective_folder_id
        if not folder:
            raise UserError(_('Este contrato no tiene dossier asignado. Use "Crear dossier" o "Vincular dossier".'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Dossier'),
            'res_model': 'documents.document',
            'view_mode': 'tree,kanban',
            'domain': [('folder_id', 'child_of', folder.id)],
            'context': {
                'default_folder_id': folder.id,
                'searchpanel_default_folder_id': folder.id,
                'searchpanel_default_folder_id_domain': [('folder_id', 'child_of', folder.id)],
                'group_by': ['folder_id'],
            },
            'target': 'current',
        }

    def action_open_dossier_wizard_create(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Crear dossier'),
            'res_model': 'sid.dossier.assign.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_sale_order_id': False,
                'default_quotation_id': self.id,
                'default_contract_kind': 'principal' if not self.parent_id else 'adenda',
                'default_mode': 'new',
            },
        }

    def action_open_dossier_wizard_link(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Vincular dossier'),
            'res_model': 'sid.dossier.assign.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_sale_order_id': False,
                'default_quotation_id': self.id,
                'default_contract_kind': 'principal' if not self.parent_id else 'adenda',
                'default_mode': 'existing',
            },
        }


class SaleOrderDossierRelated(models.Model):
    _inherit = 'sale.order'

    dossier_folder_id = fields.Many2one(
        comodel_name='documents.folder',
        string='Dossier',
        related='quotations_id.dossier_effective_folder_id',
        store=True,
        readonly=True,
    )

    principal_dossier_folder_id = fields.Many2one(
        comodel_name='documents.folder',
        string='Dossier (principal)',
        related='quotations_id.principal_dossier_folder_id',
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
        string='Tiene dossier',
        compute='_compute_tiene_dossier',
        store=True,
        readonly=True,
    )

    @api.depends('dossier_folder_id')
    def _compute_tiene_dossier(self):
        for so in self:
            so.tiene_dossier = bool(so.dossier_folder_id)

    @api.depends('quotations_id', 'quotations_id.parent_id', 'quotations_id.dossier_folder_id', 'quotations_id.dossier_root_id')
    def _compute_dossier_asignado(self):
        for so in self:
            q = so.quotations_id
            if not q:
                so.dossier_asignado = False
                continue
            # Si la oferta tiene dossier propio (ej. adenda con estructura propia), mostramos su nombre.
            # Si no, mostramos el nombre del contrato principal.
            so.dossier_asignado = q.name if q.dossier_folder_id else (q.dossier_root_id.name if q.dossier_root_id else q.name)

    def action_view_dossier(self):
        self.ensure_one()
        folder = self.dossier_folder_id
        if not folder:
            # Open wizard (link/create) instead of raising to speed up user flow
            return {
                'type': 'ir.actions.act_window',
                'name': _('Asignar dossier'),
                'res_model': 'sid.dossier.assign.wizard',
                'view_mode': 'form',
                'target': 'new',
                'context': {
                    'default_sale_order_id': self.id,
                    'default_quotation_id': self.quotations_id.id if self.quotations_id else False,
                    'default_contract_kind': 'principal' if (self.quotations_id and not self.quotations_id.parent_id) else 'adenda',
                    'default_mode': 'existing',
                },
            }
        # Open Documents view filtered to this folder (and children) and select it in the SearchPanel.
        return {
            'name': _('Document Folder'),
            'type': 'ir.actions.act_window',
            'res_model': 'documents.document',
            'view_mode': 'tree,kanban',
            'domain': [('folder_id', 'child_of', folder.id)],
            'context': {
                # Preselect folder in the SearchPanel
                'searchpanel_default_folder_id': folder.id,
                # Some UIs look for a default domain in context (harmless if unused)
                'searchpanel_default_folder_id_domain': [('folder_id', '=', folder.id)],
                # Optional: group by folder
                'group_by': 'folder_id',
            },
            'target': 'current',
        }

    def action_open_dossier_wizard_create(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Crear dossier'),
            'res_model': 'sid.dossier.assign.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_sale_order_id': self.id,
                'default_quotation_id': self.quotations_id.id if self.quotations_id else False,
                'default_contract_kind': 'principal' if (self.quotations_id and not self.quotations_id.parent_id) else 'adenda',
                'default_mode': 'new',
            },
        }

    def action_open_dossier_wizard_link(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Vincular dossier'),
            'res_model': 'sid.dossier.assign.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_sale_order_id': self.id,
                'default_quotation_id': self.quotations_id.id if self.quotations_id else False,
                'default_contract_kind': 'principal' if (self.quotations_id and not self.quotations_id.parent_id) else 'adenda',
                'default_mode': 'existing',
            },
        }
