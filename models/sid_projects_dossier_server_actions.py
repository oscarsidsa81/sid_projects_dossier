# -*- coding: utf-8 -*-
from odoo import api, models, fields, _
from odoo.exceptions import UserError
import re
import logging
from difflib import SequenceMatcher  # stdlib
from .sid_dossier_similarity import _scoped_domain, _candidate_basenames, _get_root_workspace

_logger = logging.getLogger(__name__)

SEP = re.compile(r'[^A-Za-z0-9]+')


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    # -------------------------------------------------------------------------
    # XMLIDs fijos
    # -------------------------------------------------------------------------
    XMLID_FACETS_SOURCE_FOLDER = 'sid_projects_dossier.sid_workspace_quality_dossiers'
    XMLID_EXCLUDE_FOLDER = 'sid_projects_dossier.sid_workspace_archived'
    XMLID_PATTERN_YEAR_FOLDER = 'sid_projects_dossier.sid_folder_%(year)s'
    XMLID_DOSSIER_OWNER_GROUP = 'sid_projects_dossier.group_dossier_manager'
    XMLID_DOSSIER_USER_GROUP = 'sid_projects_dossier.group_dossier_user'

    # -------------------------------------------------------------------------
    # Helpers menores propios del modelo
    # -------------------------------------------------------------------------
    def _get_folder_by_xmlid(self, xmlid):
        rec = self.env.ref(xmlid, raise_if_not_found=False)
        return rec or self.env['documents.folder'].browse()

    # ------------------------------
    # Similitud (para facetas)
    # ------------------------------
    @api.model
    def _clean_for_similarity(self, name):
        if not name:
            return ''
        name = name.lower()
        return re.sub(r"[,\.;:\?\!@#\$%\^&\*\(\)_\-\+=<>/\\\|\[\]\{\}\s]+", "", name)

    @api.model
    def _parts(self, s):
        return [p for p in SEP.split((s or '').strip().upper()) if p]

    @api.model
    def _family(self, s, n=2):
        ps = self._parts(s)
        return '-'.join(ps[:n]) if ps else ''

    @api.model
    def _is_similar(self, name, targets, fuzzy_threshold=0.86):
        base_clean = self._clean_for_similarity(name)
        bparts = self._parts(name)
        base_hyph = '-'.join(bparts)
        base_family = self._family(name)

        for t in targets or []:
            tc = self._clean_for_similarity(t)
            if tc and (tc in base_clean or base_clean in tc):
                return True

        if base_family:
            for t in targets or []:
                if base_family == self._family(t):
                    return True

        for k in range(len(bparts) - 1, 1, -1):
            pref = '-'.join(bparts[:k])
            for t in targets or []:
                if pref and pref == '-'.join(self._parts(t)[:k]):
                    return True

        for t in targets or []:
            t_hyph = '-'.join(self._parts(t))
            if base_hyph and t_hyph and SequenceMatcher(None, base_hyph, t_hyph).ratio() >= fuzzy_threshold:
                return True

        return False

    @api.model
    def _extract_raw_name(self, so):
        qname = (so.quotations_id and so.quotations_id.name or '').strip()
        return (qname.split()[0] if qname else '').strip()

    # ------------------------------
    # Carpeta del año (validada bajo ROOT)
    # ------------------------------
    def _get_current_year_folder(self):
        """Resuelve la carpeta del año en curso y valida que cuelga del workspace raíz."""
        year = fields.Date.context_today(self).year
        xmlid = self.XMLID_PATTERN_YEAR_FOLDER % {'year': year}
        folder = self._get_folder_by_xmlid(xmlid)
        if not folder:
            raise UserError(_("No existe la carpeta del año en curso (%s). "
                              "Asegúrate de tener datos iniciales con id externo '%s'.") % (year, xmlid))

        # Validar que la carpeta del año está bajo el workspace raíz
        root = _get_root_workspace(self)
        Folder = self.env['documents.folder']
        is_under_root = bool(Folder.search_count([
            ('id', '=', folder.id),
            ('id', 'child_of', root.id),
        ]))
        if not is_under_root:
            raise UserError(_("La carpeta del año (%s) no cuelga del workspace raíz (%s). "
                              "Mueve la carpeta o corrige los XMLIDs.") % (folder.display_name, root.display_name))
        return folder

    # ------------------------------
    # Búsqueda de carpeta existente (ámbito aplicado)
    # ------------------------------
    @api.model
    def _find_existing_folder_for(self, so):
        """
        Estrategia:
          A) Buscar por candidatos deterministas ('…-TIPO-digits[letter]%') bajo ROOT y excluyendo Archivado.
          B) Fallback heurístico (raw ilike y base corta + '%') bajo el mismo ámbito.
        """
        Folder = self.env['documents.folder']
        raw = self._extract_raw_name(so)
        if not raw:
            return Folder.browse()

        # A) Candidatos (no mezcla CON/VAO)
        for base in _candidate_basenames(self, raw):
            res = Folder.search(_scoped_domain(self, [('name', 'ilike', base + '%')]), limit=1)
            if res:
                return res

        # B) Heurística original dentro del ámbito
        candidates = Folder.search(_scoped_domain(self, [('name', 'ilike', raw)]))
        if candidates:
            names = [f.name or '' for f in candidates]
            base_order = min(names, key=len) if names else raw
            res = Folder.search(_scoped_domain(self, [('name', 'ilike', base_order + '%')]), limit=1)
            if res:
                return res

        return Folder.browse()

    # -------------------------------------------------------------------------
    # Abrir carpeta de dossier (y marcar tiene_dossier)
    # -------------------------------------------------------------------------
    def action_open_dossier_folder(self):
        self.ensure_one()
        so = self

        folder = self._find_existing_folder_for(so)
        SaleOrder = self.env['sale.order']

        if folder:
            sale_orders = SaleOrder.search([
                ('quotations_id', '=', so.quotations_id.id),
                ('partner_id', '=', so.partner_id.id),
            ])
            sale_orders.write({'tiene_dossier': True, 'dossier_asignado': folder.name})

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
        else:
            sale_orders = SaleOrder.search([
                ('quotations_id', '=', so.quotations_id.id),
                ('partner_id', '=', so.partner_id.id),
            ])
            sale_orders.write({'tiene_dossier': False})
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Sin carpeta'),
                    'message': _('No se encontró carpeta para el dossier de %s') % (so.quotations_id.name or so.name),
                    'type': 'warning',
                    'sticky': False,
                }
            }

    # -------------------------------------------------------------------------
    # Crear dossier + estructura + facetas + solicitudes (bajo el AÑO actual)
    # -------------------------------------------------------------------------
    def action_create_dossier_folders(self):
        self.ensure_one()
        so = self

        Folder = self.env['documents.folder']
        Request = self.env['documents.request_wizard']  # ajusta si tu modelo difiere

        # Fuente de facetas: workspace raíz
        parent_facets_src = self._get_folder_by_xmlid(self.XMLID_FACETS_SOURCE_FOLDER)
        # Padre donde crear: carpeta del año actual (sid_folder_YYYY)
        target_parent = self._get_current_year_folder()

        # Usuario (único) desde el grupo
        owner_id = self._get_request_owner_id_from_group()

        order_code = (so.quotations_id and so.quotations_id.name) or so.name or _('Dossier')
        confirmed_orders = self.env['sale.order'].search([
            ('state', '=', 'sale'),
            ('quotations_id', '=', so.quotations_id.id),
            ('partner_id', '=', so.partner_id.id),
        ])

        # ¿ya existe?
        existing_folder = self._find_existing_folder_for(so)
        if existing_folder:
            confirmed_orders.write({'tiene_dossier': True, 'dossier_asignado': existing_folder.name})
            orders_str = ', '.join(confirmed_orders.mapped('name')) or _('(ninguno)')
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Carpeta existente detectada'),
                    'message': _('Ya existe un dossier para el contrato principal. '
                                 'Se marcaron como "Dossier" los siguientes presupuestos: %s') % orders_str,
                    'type': 'warning',
                    'sticky': True,
                }
            }

        # Crear carpeta principal bajo la carpeta del año
        workspace_parent = Folder.create({
            'name': order_code,
            'parent_folder_id': target_parent.id,
        })

        # Facetas parecidas (si el workspace raíz tiene facetas “plantilla”)
        child_folders = [
            '0. Plantillas', '1. Lista de documentos', '2. MPR', '3. Schedule', '4. Lista de materiales',
            '5. Packing List', '6.a ITP', '6.b Notificaciones', '6.b Autorizaciones de Envío',
            '7.a Planos', '7.b Datasheets', '7.c Lista de Repuestos', '8. Quality Plan', '9. Procedimientos',
            '10.a Certificados', '10.b Marcado CE/UKCA', '10.c Conformidad', '11. Logística',
            '12. Dossier Final', '13. Contrato', '14. KOM',
        ]
        if parent_facets_src:
            similar_facets_parent = parent_facets_src.facet_ids.filtered(
                lambda f: self._is_similar(f.name, child_folders)
            )
            if similar_facets_parent:
                workspace_parent.write({'facet_ids': [(4, facet.id) for facet in similar_facets_parent]})

        # Marcar pedidos confirmados (usar la carpeta recién creada)
        confirmed_orders.write({'tiene_dossier': True, 'dossier_asignado': workspace_parent.name})

        estados = ['Proveedor', 'Enviado', 'Comentarios', 'Rechazado', 'Aprobado']
        folders_sin_estado = ['0. Plantillas', '6.b Notificaciones', '6.b Autorizaciones de Envío', '11. Logística',
                              '13. Contrato', '14. KOM']
        notificaciones = ['6.b Notificaciones']
        adenda = ['Adendas']
        noi = ['NOI-1', 'NOI-2', 'NOI-3', 'NOI-4', 'NOI-5', 'NOI-6', 'NOI-7', 'NOI-8', 'NOI-9', 'NOI-10']
        contrato = ['13. Contrato']

        seq_child = 10

        for fname in child_folders:
            child = Folder.create({
                'name': fname,
                'parent_folder_id': workspace_parent.id,
                'sequence': seq_child,
            })

            if fname not in folders_sin_estado:
                seq_state = 10
                for est in estados:
                    Folder.create({'name': est, 'parent_folder_id': child.id, 'sequence': seq_state})
                    seq_state += 1

            if fname in notificaciones:
                seq_noi = 10
                for n in noi:
                    Folder.create({'name': n, 'parent_folder_id': child.id, 'sequence': seq_noi})
                    seq_noi += 1

            if fname in contrato:
                for a in adenda:
                    Folder.create({'name': a, 'parent_folder_id': child.id})

            if parent_facets_src:
                similar_facets_child = parent_facets_src.facet_ids.filtered(
                    lambda f, n=fname: self._is_similar(f.name, [n])
                )
                if similar_facets_child:
                    child.write({'facet_ids': [(4, facet.id) for facet in similar_facets_child]})

            # Solicitud de documentos asociada
            try:
                Request.create({
                    'name': _("Solicitud para %s / %s") % (workspace_parent.name, child.name),
                    'folder_id': child.id,
                    'owner_id': owner_id,
                })
            except Exception as e:
                _logger.warning("No se pudo crear documents.request_wizard: %s", e)

            seq_child += 1

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Dossier creado'),
                'message': _('Se creó el dossier "%s" con su estructura de carpetas.') % workspace_parent.name,
                'type': 'success',
                'sticky': False,
            }
        }
