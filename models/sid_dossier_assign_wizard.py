# models/sid_dossier_assign_wizard.py
from odoo import api, fields, models, _
from .sid_dossier_similarity import _scoped_domain, _candidate_basenames, _get_root_workspace

class DossierAssignWizard(models.TransientModel):
    _name = 'dossier.assign.wizard'
    _description = 'Asignar carpeta de dossier'

    sale_order_id = fields.Many2one('sale.order', required=True)
    mode = fields.Selection([
        ('existing', 'Usar carpeta existente'),
        ('new', 'Crear nueva carpeta'),
    ], required=True, default='existing')

    existing_folder_id = fields.Many2one(
        'documents.folder',
        string='Carpeta existente',
    )
    new_folder_name = fields.Char(string='Nombre de la nueva carpeta')

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        so_id = self.env.context.get('default_sale_order_id') or self.env.context.get('active_id')
        so = self.env['sale.order'].browse(so_id)
        res['sale_order_id'] = so.id

        # Sugerencias basadas en candidatos
        candidates = _candidate_basenames(so, so._extract_raw_name(so))
        Folder = self.env['documents.folder']
        existing = Folder.search(
            _scoped_domain(so, [('name', 'ilike', (candidates[0] + '%') if candidates else '')]),
            limit=1
        )
        if existing:
            res['mode'] = 'existing'
            res['existing_folder_id'] = existing.id
        else:
            res['mode'] = 'new'
            res['new_folder_name'] = (candidates[0] if candidates else (so.quotations_id.name or so.name))
        return res

    @api.onchange('sale_order_id', 'mode')
    def _onchange_set_domain(self):
        """Limita la selección al ROOT y excluye 'Archivado'."""
        if not self.sale_order_id:
            return {}
        root = _get_root_workspace(self.sale_order_id)
        exclude = self.sale_order_id._get_folder_by_xmlid(self.sale_order_id.XMLID_EXCLUDE_FOLDER)
        dom = [('id', 'child_of', root.id)]
        if exclude:
            dom += ['!', ('id', 'child_of', exclude.id)]
        return {'domain': {'existing_folder_id': dom}}

    @api.onchange('mode')
    def _onchange_mode(self):
        if self.mode == 'existing':
            self.new_folder_name = False
        else:
            self.existing_folder_id = False

    def action_confirm(self):
        self.ensure_one()
        so = self.sale_order_id
        Folder = self.env['documents.folder']

        if self.mode == 'existing' and self.existing_folder_id:
            folder = self.existing_folder_id
        elif self.mode == 'new' and self.new_folder_name:
            parent = so._get_current_year_folder()  # valida que cuelga del ROOT
            folder = Folder.create({'name': self.new_folder_name, 'parent_folder_id': parent.id})
        else:
            return

        related = self.env['sale.order'].search([
            ('quotations_id', '=', so.quotations_id.id),
            ('partner_id', '=', so.partner_id.id),
        ])
        related.write({'tiene_dossier': True, 'dossier_asignado': folder.name})

        return {
            'name': _('Document Folder'),
            'type': 'ir.actions.act_window',
            'res_model': 'documents.document',
            'view_mode': 'tree,kanban,form',
            'context': {
                'searchpanel_default_folder_id': folder.id,
                'searchpanel_default_folder_id_domain': [('folder_id', '=', folder.id)],
                'group_by': 'folder_id',
                'search_default_folder_id': folder.id,
                'default_folder_id': folder.id,
            },
            'target': 'current',
        }
