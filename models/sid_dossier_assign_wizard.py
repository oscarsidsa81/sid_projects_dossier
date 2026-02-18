# -*- coding: utf-8 -*-

from datetime import date

from odoo import api, fields, models, _
from odoo.exceptions import UserError

# Reutilizamos la lógica histórica de creación de estructura de dossier
from .sid_projects_dossier_server_actions import create_dossier_structure


class SidDossierAssignWizard(models.TransientModel):
    _name = 'sid.dossier.assign.wizard'
    _description = 'Crear/Vincular dossier de calidad'

    sale_order_id = fields.Many2one('sale.order', string='Pedido', readonly=True)
    quotation_id = fields.Many2one('sale.quotations', string='Presupuesto/Contrato', required=True, readonly=True)
    quotation_is_child = fields.Boolean(
        string='Es adenda (por jerarquía)',
        compute='_compute_quotation_is_child',
        readonly=True,
    )
    quotation_has_children = fields.Boolean(
        string='Tiene adendas',
        compute='_compute_quotation_has_children',
        readonly=True,
    )

    contract_kind = fields.Selection(
        selection=[('principal', 'Contrato principal'), ('adenda', 'Adenda')],
        string='Tipo',
        required=True,
        default='principal',
    )

    addenda_policy = fields.Selection(
        selection=[
            ('use_principal', 'Usar dossier del contrato principal'),
            ('own_dossier', 'Crear/vincular dossier propio para la adenda'),
        ],
        string='Política de dossier (adenda)',
        default='use_principal',
        help='Para adendas: permite decidir si se reutiliza el dossier del contrato principal o si la adenda tiene su propio dossier.',
    )

    mode = fields.Selection(
        selection=[('new', 'Crear dossier nuevo'), ('existing', 'Vincular dossier existente')],
        string='Operación',
        required=True,
        default='new',
    )

    principal_quotation_id = fields.Many2one(
        'sale.quotations',
        string='Contrato principal',
        domain="[('parent_id','=',False)]",
        readonly=True,
    )

    existing_folder_id = fields.Many2one(
        'documents.folder',
        string='Dossier existente (nivel 2)',
        domain=[],
    )

    new_folder_name = fields.Char(string='Nombre del dossier', readonly=True)

    warning_message = fields.Text(string='Aviso', readonly=True)

    # ---------------------------------------------------------------------
    # Helpers: root/year folders
    # ---------------------------------------------------------------------

    def _get_root_folder(self):
        # XML-ID canónico gestionado por hooks/datos del módulo.
        root = self.env.ref('sid_projects_dossier.sid_workspace_quality_dossiers', raise_if_not_found=False)
        if root:
            return root

        # Retrocompatibilidad: instalaciones antiguas pudieron usar este XML-ID.
        legacy_root = self.env.ref('sid_projects_dossier.folder_root_dossieres_calidad', raise_if_not_found=False)
        if legacy_root:
            return legacy_root

        # Fallback by name
        return self.env['documents.folder'].sudo().search([
            ('name', '=', 'Dossieres de calidad'),
            ('parent_folder_id', '=', False)
        ], limit=1)

    def _ensure_year_folder(self, year_int: int):
        root = self._get_root_folder()
        if not root:
            raise UserError(_('No se ha encontrado el root "Dossieres de calidad" en Documentos.'))
        Folder = self.env['documents.folder'].sudo()
        yname = str(year_int)
        year_folder = Folder.search([('parent_folder_id', '=', root.id), ('name', '=', yname)], limit=1)
        if not year_folder:
            year_folder = Folder.create({'name': yname, 'parent_folder_id': root.id})
        return year_folder

    def _folder_has_documents(self, folder):
        Doc = self.env['documents.document'].sudo()
        return bool(Doc.search_count([('folder_id', '=', folder.id)]))

    def _folder_linked_to_other_contract(self, folder, root_quotation):
        Q = self.env['sale.quotations'].sudo()
        other = Q.search([
            ('dossier_folder_id', '=', folder.id),
            ('id', '!=', root_quotation.id),
        ], limit=1)
        return other

    # ---------------------------------------------------------------------
    # Onchange / defaults
    # ---------------------------------------------------------------------

    @api.depends('quotation_id', 'quotation_id.parent_id')
    def _compute_quotation_is_child(self):
        for wizard in self:
            wizard.quotation_is_child = bool(wizard.quotation_id and wizard.quotation_id.parent_id)

    @api.depends('quotation_id', 'quotation_id.child_ids')
    def _compute_quotation_has_children(self):
        for wizard in self:
            wizard.quotation_has_children = bool(wizard.quotation_id and wizard.quotation_id.child_ids)

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)

        qid = res.get('quotation_id')
        if qid:
            q = self.env['sale.quotations'].browse(qid).exists()
            if q:
                root = q.dossier_root_id or q
                # default contract_kind from relationship
                res['contract_kind'] = 'principal' if not q.parent_id else 'adenda'
                if res.get('contract_kind') == 'adenda' and res.get('addenda_policy') == 'own_dossier':
                    res['new_folder_name'] = q.name
                else:
                    res['new_folder_name'] = root.name

                if res.get('contract_kind') == 'adenda':
                    res['principal_quotation_id'] = root.id

                    # Si la adenda ya tiene dossier propio, priorizamos conservarlo por defecto.
                    if q.dossier_folder_id:
                        res['addenda_policy'] = 'own_dossier'
                        res['new_folder_name'] = q.name
                    elif res.get('addenda_policy') != 'own_dossier' and root.dossier_folder_id:
                        res['mode'] = 'existing'
                        res['existing_folder_id'] = root.dossier_folder_id.id

        return res

    @api.onchange('quotation_id')
    def _onchange_quotation(self):
        if not self.quotation_id:
            return
        root = self.quotation_id.dossier_root_id or self.quotation_id
        self.contract_kind = 'principal' if not self.quotation_id.parent_id else 'adenda'
        if not self.quotation_id.parent_id and not self.quotation_id.child_ids:
            self.contract_kind = 'principal'
        if self.contract_kind == 'adenda':
            self.principal_quotation_id = root

            # Si la adenda ya tiene dossier propio, no forzar vínculo al principal.
            if self.quotation_id.dossier_folder_id:
                self.addenda_policy = 'own_dossier'
            elif self.addenda_policy == 'use_principal' and root.dossier_folder_id:
                self.mode = 'existing'
                self.existing_folder_id = root.dossier_folder_id

        self._apply_dossier_name_policy()

    @api.onchange('contract_kind')
    def _onchange_contract_kind(self):
        if not self.quotation_id:
            return

        if self.contract_kind == 'adenda' and not self.quotation_id.parent_id and not self.quotation_id.child_ids:
            self.contract_kind = 'principal'
            return

        root = self.quotation_id.dossier_root_id or self.quotation_id
        if self.contract_kind == 'adenda':
            self.principal_quotation_id = root

            # Si la adenda ya tiene dossier propio, no forzar vínculo al principal.
            if self.quotation_id.dossier_folder_id:
                self.addenda_policy = 'own_dossier'
            elif self.addenda_policy == 'use_principal' and root.dossier_folder_id:
                self.mode = 'existing'
                self.existing_folder_id = root.dossier_folder_id

        self._apply_dossier_name_policy()

    @api.onchange('addenda_policy')
    def _onchange_addenda_policy(self):
        if not self.quotation_id or self.contract_kind != 'adenda':
            return

        root = self.principal_quotation_id or self.quotation_id.dossier_root_id or self.quotation_id
        if self.addenda_policy == 'use_principal':
            if root.dossier_folder_id:
                self.mode = 'existing'
                self.existing_folder_id = root.dossier_folder_id
        else:
            if self.mode == 'existing' and self.existing_folder_id == root.dossier_folder_id:
                self.mode = 'new'
                self.existing_folder_id = False

        self._apply_dossier_name_policy()

    def _apply_dossier_name_policy(self):
        self.ensure_one()
        if not self.quotation_id:
            self.new_folder_name = False
            return

        root = self.quotation_id.dossier_root_id or self.quotation_id
        if self.contract_kind == 'adenda' and (self.addenda_policy == 'own_dossier' or self.mode == 'new'):
            self.new_folder_name = self.quotation_id.name
        else:
            self.new_folder_name = root.name

    @api.onchange('mode', 'existing_folder_id', 'principal_quotation_id', 'quotation_id')
    def _onchange_warnings(self):
        self.warning_message = False
        if self.mode != 'existing' or not self.existing_folder_id:
            return

        # Evaluate warnings
        q = self.quotation_id
        if not q:
            return
        root_q = (q.dossier_root_id or q) if self.contract_kind != 'adenda' else (self.principal_quotation_id or q.dossier_root_id or q)

        msgs = []
        if self._folder_has_documents(self.existing_folder_id):
            msgs.append(_('La carpeta seleccionada ya contiene documentos. Se recomienda NO reasignar salvo que sea intencionado.'))

        other = self._folder_linked_to_other_contract(self.existing_folder_id, root_q)
        if other:
            msgs.append(_('La carpeta ya está vinculada al contrato: %s') % (other.display_name or other.name))

        self.warning_message = '\n'.join(msgs) if msgs else False

    # Dynamic domain for existing_folder_id (nivel 2 de todos los años)
    @api.onchange('quotation_id')
    def _onchange_existing_folder_domain(self):
        root = self._get_root_folder()
        if root:
            return {
                'domain': {
                    'existing_folder_id': [('parent_folder_id.parent_folder_id', '=', root.id)],
                }
            }
        return {
            'domain': {'existing_folder_id': []}
        }

    # ---------------------------------------------------------------------
    # Confirm
    # ---------------------------------------------------------------------

    def action_confirm(self):
        self.ensure_one()
        if not self.quotation_id:
            raise UserError(_('Seleccione un presupuesto/contrato.'))

        if self.quotation_id.parent_id and self.contract_kind != 'adenda':
            raise UserError(_('Esta oferta pertenece a una adenda. Seleccione el tipo "Adenda".'))

        if self.contract_kind == 'adenda' and not self.quotation_id.parent_id and not self.quotation_id.child_ids:
            raise UserError(_('Este contrato no tiene adendas hijas. Solo puede gestionarse como "Contrato principal".'))

        # 1) Identificar el contrato principal (root_q)
        root_q = self.quotation_id.dossier_root_id or self.quotation_id
        if self.contract_kind == 'adenda':
            if not self.principal_quotation_id:
                raise UserError(_('Seleccione el contrato principal.'))
            root_q = self.principal_quotation_id.dossier_root_id or self.principal_quotation_id

        # 2) Sobre qué oferta escribimos el vínculo:
        #    - Contrato principal: siempre en root_q
        #    - Adenda: puede heredar el dossier del contrato principal (no escribimos en la adenda)
        #      o tener su propio dossier (escribimos en la adenda)
        target_q = root_q
        if self.contract_kind == 'adenda' and (self.addenda_policy == 'own_dossier' or self.mode == 'new'):
            # En adendas, "Crear dossier nuevo" siempre opera sobre la adenda para
            # evitar sobrescribir/revincular el dossier del contrato principal.
            target_q = self.quotation_id

        Folder = self.env['documents.folder'].sudo()

        def _find_existing_dossier_any_year(name):
            """Busca un dossier por nombre bajo cualquier año (evita duplicar 2025/2026)."""
            name = (name or '').strip()
            if not name:
                return Folder

            root = self._get_root_folder()
            # Carpeta de año: hija directa del root
            candidates = Folder.search([
                ('parent_folder_id.parent_folder_id', '=', root.id),
                ('name', '=', name),
            ])
            if not candidates:
                return Folder

            # Preferimos el año más antiguo (p.ej. si existe en 2025 no crear en 2026)
            def _year_of(f):
                try:
                    return int((f.parent_folder_id.name or '9999').strip())
                except Exception:
                    return 9999
            return candidates.sorted(key=_year_of)[:1]

        if self.mode == 'existing':
            # Vincular una carpeta ya existente (puede pertenecer a cualquier año)
            if not self.existing_folder_id:
                raise UserError(_('Seleccione una carpeta de dossier existente.'))
            dossier_folder = self.existing_folder_id
            target_q.sudo().write({'dossier_folder_id': dossier_folder.id})
            # Asegurar estructura mínima (idempotente) sin tocar el año
            create_dossier_structure(self.env, dossier_folder)

        else:
            # Crear (o reutilizar) el dossier.
            # - Si ya existe en target_q => reusar
            # - Si no existe, pero ya hay una carpeta con ese nombre en otro año => reusar
            # - Si no existe => crear bajo el año actual
            if target_q.dossier_folder_id:
                dossier_folder = target_q.dossier_folder_id
                create_dossier_structure(self.env, dossier_folder)
            else:
                year_folder = self._ensure_year_folder(date.today().year)
                dossier_name = (self.new_folder_name or target_q.name or '').strip()
                if not dossier_name:
                    raise UserError(_('No se pudo determinar el nombre del dossier.'))

                # Para adendas con política "dossier propio" debemos crear carpeta NUEVA.
                # Si reusamos por nombre, una adenda puede terminar enlazada al dossier
                # del principal cuando ambos comparten denominación.
                force_new_folder = self.contract_kind == 'adenda' and self.addenda_policy == 'own_dossier'

                dossier_folder = Folder
                if not force_new_folder:
                    dossier_folder = _find_existing_dossier_any_year(dossier_name)
                    if not dossier_folder:
                        dossier_folder = Folder.search([
                            ('parent_folder_id', '=', year_folder.id),
                            ('name', '=', dossier_name),
                        ], limit=1)
                if not dossier_folder:
                    dossier_folder = Folder.create({'name': dossier_name, 'parent_folder_id': year_folder.id})

                # Crear subcarpetas estándar bajo el dossier (contratos, certificados, etc.)
                create_dossier_structure(self.env, dossier_folder)

                target_q.sudo().write({'dossier_folder_id': dossier_folder.id})

        # Optional: chatter note (if mail.thread available)
        try:
            msg = _('Dossier asignado: %s') % (target_q.dossier_folder_id.display_name)
            target_q.message_post(body=msg)
        except Exception:
            pass

        return {'type': 'ir.actions.act_window_close'}
