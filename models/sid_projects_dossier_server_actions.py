# -*- coding: utf-8 -*-
from odoo import api, models, fields, _
from odoo.exceptions import UserError
import re
import logging
from datetime import timedelta  # <-- NUEVO

_logger = logging.getLogger(__name__)

class SaleOrder(models.Model):
    _inherit = 'sale.order'

    # ... (mantén tus constantes y utilidades previas)

    # -------------------------------------------------------------------------
    # Helpers adicionales
    # -------------------------------------------------------------------------
    def _get_pm_user_id_required(self, so):
        """
        Devuelve el user_id del Project Manager, o lanza UserError si no está definido
        o no apunta a un usuario utilizable.
        """
        pm = so.project_manager_id
        if not pm:
            raise UserError(_("Debes indicar un 'Project Manager' en el pedido para poder crear las solicitudes."))

        # Admite distintos tipos de campo (res.users u otros con user_id)
        if pm._name == 'res.users':
            return pm.id
        if hasattr(pm, 'user_id') and pm.user_id:
            return pm.user_id.id

        raise UserError(_("El campo 'project_manager_id' debe referenciar a un usuario válido."))

    def _schedule_activity_for_record(self, record, user_id, summary, deadline_date):
        """
        Programa una actividad (To Do) sobre 'record' con vencimiento 'deadline_date'.
        Si el modelo no soporta activity_schedule, cae a mail.activity.create.
        """
        Activity = self.env['mail.activity']
        todo_type = self.env.ref('mail.mail_activity_data_todo', raise_if_not_found=False)

        # Si el record soporta activity_schedule (mixin mail.thread)
        if hasattr(record, 'activity_schedule'):
            try:
                record.activity_schedule(
                    activity_type_id=todo_type.id if todo_type else False,
                    date_deadline=deadline_date,
                    user_id=user_id,
                    summary=summary,
                )
                return
            except Exception as e:
                _logger.warning("Fallo activity_schedule en %s id=%s: %s", record._name, record.id, e)

        # Fallback a mail.activity.create
        try:
            model = record._name
            model_id = self.env['ir.model']._get(model).id
            Activity.create({
                'activity_type_id': todo_type.id if todo_type else False,
                'res_model_id': model_id,
                'res_id': record.id,
                'date_deadline': deadline_date,
                'user_id': user_id,
                'summary': summary,
                'note': '',
            })
        except Exception as e:
            _logger.warning("No se pudo crear mail.activity para %s id=%s: %s", record._name, record.id, e)

    # -------------------------------------------------------------------------
    # Crear dossier + estructura + facetas + solicitudes (bajo el AÑO actual)
    # -------------------------------------------------------------------------
    def action_create_dossier_folders(self):
        self.ensure_one()
        so = self

        Folder = self.env['documents.folder']
        Request = self.env['documents.request_wizard']  # si tu modelo difiere, ajusta aquí

        # Fuente de facetas: workspace raíz
        parent_facets_src = self._get_folder_by_xmlid(self.XMLID_FACETS_SOURCE_FOLDER)
        # Padre donde crear: carpeta del año actual (sid_folder_YYYY)
        target_parent = self._get_current_year_folder()

        # Usuario (único) desde el grupo (Calidad)
        owner_id = self._get_request_owner_id_from_group()
        # Project Manager (obligatorio para KOM/Contrato)
        pm_user_id = self._get_pm_user_id_required(so)

        order_code = (so.quotations_id and so.quotations_id.name) or so.name or _('Dossier')
        confirmed_orders = self.env['sale.order'].search([
            ('state', '=', 'sale'),
            ('quotations_id', '=', so.quotations_id.id),
        ])

        # ¿ya existe?
        existing_folder = self._find_existing_folder_for(so)
        if existing_folder:
            confirmed_orders.write({'tiene_dossier': True})
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
        estados = ['Proveedor', 'Enviado', 'Comentarios', 'Rechazado', 'Aprobado']
        folders_sin_estado = ['0. Plantillas', '6.b Notificaciones', '6.b Autorizaciones de Envío', '11. Logística',
                              '13. Contrato', '14. KOM']

        # Mapa para localizar carpetas de interés tras crearlas
        folder_map = {}
        # Guardaremos la subcarpeta "Enviado" dentro de "1. Lista de documentos"
        lista_docs_enviado = False

        if parent_facets_src:
            similar_facets_parent = parent_facets_src.facet_ids.filtered(
                lambda f: self._is_similar(f.name, child_folders)
            )
            if similar_facets_parent:
                workspace_parent.write({'facet_ids': [(4, facet.id) for facet in similar_facets_parent]})

        # Marcar pedidos confirmados
        confirmed_orders.write({'tiene_dossier': True})

        seq_child = 10

        for fname in child_folders:
            child = Folder.create({
                'name': fname,
                'parent_folder_id': workspace_parent.id,
                'sequence': seq_child,
            })
            folder_map[fname] = child

            if fname not in folders_sin_estado:
                seq_state = 10
                for est in estados:
                    state_folder = Folder.create({'name': est, 'parent_folder_id': child.id, 'sequence': seq_state})
                    seq_state += 1
                    # Detectar "Enviado" bajo "1. Lista de documentos"
                    if fname == '1. Lista de documentos' and est == 'Enviado':
                        lista_docs_enviado = state_folder

            if parent_facets_src:
                similar_facets_child = parent_facets_src.facet_ids.filtered(
                    lambda f, n=fname: self._is_similar(f.name, [n])
                )
                if similar_facets_child:
                    child.write({'facet_ids': [(4, facet.id) for facet in similar_facets_child]})

            # ⚠️ IMPORTANTE: YA NO creamos solicitudes genéricas aquí
            # (antes: Request.create(...) por cada subcarpeta)
            seq_child += 1

        # ---------------------------------------------------------------------
        # Crear SOLO las 4 solicitudes requeridas (vencimiento a 10 días)
        # ---------------------------------------------------------------------
        deadline = fields.Date.context_today(self) + timedelta(days=10)

        # Verificaciones de existencia de carpetas objetivo
        if not lista_docs_enviado:
            raise UserError(_("No se encontró la carpeta 'Enviado' dentro de '1. Lista de documentos'."))

        itp_folder = folder_map.get('6.a ITP')
        if not itp_folder:
            raise UserError(_("No se encontró la carpeta '6.a ITP'."))

        kom_folder = folder_map.get('14. KOM')
        if not kom_folder:
            raise UserError(_("No se encontró la carpeta '14. KOM'."))

        contrato_folder = folder_map.get('13. Contrato')
        if not contrato_folder:
            raise UserError(_("No se encontró la carpeta '13. Contrato'."))

        # Preparar valores base para Request (si el modelo soporta fecha límite, se rellena)
        req_base = {
            'owner_id': owner_id,
        }
        if 'date_deadline' in Request._fields:
            req_base['date_deadline'] = deadline

        # 1) Lista de documentos / Enviado  -> actividad para Calidad (owner_id)
        req_ld = Request.create({
            **req_base,
            'name': _("Solicitud para %s / %s") % (workspace_parent.name, _("1. Lista de documentos / Enviado")),
            'folder_id': lista_docs_enviado.id,
        })
        self._schedule_activity_for_record(
            req_ld, owner_id, summary=_("Enviar documentación: Lista de documentos (Enviado)"), deadline_date=deadline
        )

        # 2) ITP -> actividad para Calidad (owner_id)
        req_itp = Request.create({
            **req_base,
            'name': _("Solicitud para %s / %s") % (workspace_parent.name, _("6.a ITP")),
            'folder_id': itp_folder.id,
        })
        self._schedule_activity_for_record(
            req_itp, owner_id, summary=_("Enviar documentación: ITP"), deadline_date=deadline
        )

        # 3) KOM -> actividad para Project Manager
        req_kom = Request.create({
            **req_base,
            'name': _("Solicitud para %s / %s") % (workspace_parent.name, _("14. KOM")),
            'folder_id': kom_folder.id,
        })
        self._schedule_activity_for_record(
            req_kom, pm_user_id, summary=_("Preparar/adjuntar documentación KOM"), deadline_date=deadline
        )

        # 4) Contrato -> actividad para Project Manager
        req_contrato = Request.create({
            **req_base,
            'name': _("Solicitud para %s / %s") % (workspace_parent.name, _("13. Contrato")),
            'folder_id': contrato_folder.id,
        })
        self._schedule_activity_for_record(
            req_contrato, pm_user_id, summary=_("Contratos / Adendas: documentación requerida"), deadline_date=deadline
        )

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Dossier creado'),
                'message': _('Se creó el dossier "%s", la estructura de carpetas y 4 solicitudes a 10 días vista.') % workspace_parent.name,
                'type': 'success',
                'sticky': False,
            }
        }
