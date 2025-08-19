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
    existing_folder_id = fields.Many2one('documents.folder', string='Carpeta existente')
    new_folder_name = fields.Char(string='Nombre de la nueva carpeta')
    candidate_ids = fields.One2many('dossier.assign.candidate', 'wizard_id', string='Sugerencias')

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        so_id = self.env.context.get('default_sale_order_id') or self.env.context.get('active_id')
        so = self.env['sale.order'].browse(so_id)
        res['sale_order_id'] = so.id

        candidates = _candidate_basenames(so, so._extract_raw_name(so))
        Folder = self.env['documents.folder']

        first_existing = Folder.search(
            _scoped_domain(so, [('name', 'ilike', (candidates[0] + '%') if candidates else '')]),
            limit=1
        )
        if first_existing:
            res['mode'] = 'existing'
            res['existing_folder_id'] = first_existing.id
        else:
            res['mode'] = 'new'
            res['new_folder_name'] = (candidates[0] if candidates else (so.quotations_id.name or so.name))

        # poblar tabla
        lines = []
        for base in candidates:
            for f in Folder.search(_scoped_domain(so, [('name', 'ilike', base + '%')]), limit=50):
                lines.append((0, 0, {'folder_id': f.id, 'match_basis': base}))
        res['candidate_ids'] = lines
        return res

    @api.onchange('sale_order_id', 'mode')
    def _onchange_set_domain(self):
        if not self.sale_order_id:
            return {}
        root = _get_root_workspace(self.sale_order_id)
        exclude = self.sale_order_id._get_folder_by_xmlid(self.sale_order_id.XMLID_EXCLUDE_FOLDER)
        dom = [('id', 'child_of', root.id)]
        if exclude:
            dom += ['!', ('id', 'child_of', exclude.id)]
        return {'domain': {'existing_folder_id': dom}}
