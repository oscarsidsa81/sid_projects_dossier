# -*- coding: utf-8 -*-
from odoo import api, models, fields, _
from odoo.exceptions import UserError
import re
import logging

_logger = logging.getLogger ( __name__ )


class SaleOrder ( models.Model ) :
    _inherit = 'sale.order'

    # -------------------------------------------------------------------------
    # XMLIDs fijos
    # -------------------------------------------------------------------------
    XMLID_FACETS_SOURCE_FOLDER = 'sid_projects_dossier.sid_workspace_quality_dossiers'  # workspace raíz (para facetas)
    XMLID_EXCLUDE_FOLDER = 'sid_projects_dossier.sid_workspace_archived'  # workspace "Archivado"

    # Patrón del xmlid para las carpetas de año: sid_folder_YYYY
    XMLID_PATTERN_YEAR_FOLDER = 'sid_projects_dossier.sid_folder_%(year)s'

    # Grupo con exactamente 1 usuario (propietario de solicitudes)
    XMLID_DOSSIER_OWNER_GROUP = 'sid_projects_dossier.group_dossier_manager'
    XMLID_DOSSIER_USER_GROUP = 'sid_projects_dossier.group_dossier_user'

    # -------------------------------------------------------------------------
    # Utilidades
    # -------------------------------------------------------------------------
    @api.model
    def _clean_for_similarity(self, name) :
        if not name :
            return ''
        name = name.lower ()
        name = re.sub ( r"[,\.;:\?\!@#\$%\^&\*\(\)_\-\+=<>/\\\|\[\]\{\}\s]+", "", name )
        return name

    @api.model
    def _is_similar(self, name, targets) :
        base = self._clean_for_similarity ( name )
        for t in targets or [] :
            if self._clean_for_similarity ( t ) in base :
                return True
        return False

    @api.model
    def _extract_raw_name(self, so) :
        qname = (so.quotations_id and so.quotations_id.name or '').strip ()
        return (qname.split ()[0] if qname else '').strip ()

    def _get_folder_by_xmlid(self, xmlid) :
        rec = self.env.ref ( xmlid, raise_if_not_found=False )
        return rec or self.env['documents.folder'].browse ()

    def _get_request_owner_id_from_group(self) :
        group = self.env.ref ( self.XMLID_DOSSIER_OWNER_GROUP, raise_if_not_found=False )
        if not group :
            raise UserError ( _ (
                "No se encuentra el grupo de administrador de dossieres (%s). "
                "Carga el XML de seguridad."
            ) % self.XMLID_DOSSIER_OWNER_GROUP )

        users = group.users
        if len ( users ) == 0 :
            raise UserError ( _ (
                "El grupo '%s' no tiene usuarios. Asigna exactamente uno."
            ) % (group.display_name or 'Administrador de Dossieres de calidad') )

        if len ( users ) > 1 :
            raise UserError ( _ (
                "El grupo '%s' tiene %s usuarios. Debe haber exactamente uno."
            ) % (group.display_name or 'Administrador de Dossieres de calidad', len ( users )) )

        user = users[0]

        # Buscar el empleado vinculado a este usuario
        employee = self.env['hr.employee'].search ( [('user_id', '=', user.id)], limit=1 )
        if not employee or not employee.department_id or employee.department_id.name != "Calidad" :
            raise UserError ( _ (
                "El usuario asignado al grupo '%s' debe pertenecer al departamento 'Calidad'."
            ) % (group.display_name or 'Administrador de Dossieres de calidad') )

        return user.id

    def _get_current_year_folder(self) :
        """Resuelve la carpeta del año en curso por xmlid sid_folder_YYYY."""
        year = fields.Date.context_today ( self ).year
        xmlid = self.XMLID_PATTERN_YEAR_FOLDER % {'year' : year}
        folder = self._get_folder_by_xmlid ( xmlid )
        if not folder :
            # Si no existe la carpeta del año, avisamos con error claro.
            # (Alternativa: crearla aquí o caer al workspace raíz)
            raise UserError ( _ (
                "No existe la carpeta del año en curso (%s). "
                "Asegúrate de tener datos iniciales con id externo '%s'."
            ) % (year, xmlid) )
        return folder

    @api.model
    def _find_existing_folder_for(self, so) :
        """
        1) Buscar por 'ilike' el raw_name (excluye 'Archivado')
        2) Si hay candidatos, tomar el nombre más corto como base y buscar por 'base%'
        """
        Folder = self.env['documents.folder']
        exclude_folder = self._get_folder_by_xmlid ( self.XMLID_EXCLUDE_FOLDER )
        raw_name = self._extract_raw_name ( so )
        if not raw_name :
            return Folder.browse ()

        domain_base = [('name', 'ilike', raw_name)]
        if exclude_folder :
            domain_base.append ( ('parent_folder_id', '!=', exclude_folder.id) )

        candidates = Folder.search ( domain_base )
        if candidates :
            names = [f.name for f in candidates]
            base_order = min ( names, key=len ) if names else raw_name
            domain_final = [('name', 'ilike', base_order + '%')]
            if exclude_folder :
                domain_final.append ( ('parent_folder_id', '!=', exclude_folder.id) )
            return Folder.search ( domain_final, limit=1 )
        return Folder.browse ()

    # -------------------------------------------------------------------------
    # Abrir carpeta de dossier (y marcar tiene_dossier)
    # -------------------------------------------------------------------------
    def action_open_dossier_folder(self) :
        self.ensure_one ()
        so = self

        folder = self._find_existing_folder_for ( so )
        SaleOrder = self.env['sale.order']

        if folder :
            sale_orders = SaleOrder.search ( [('quotations_id.name', '=', so.quotations_id.name)] )
            sale_orders.write ( {'tiene_dossier' : True} )

            return {
                'name' : _ ( 'Document Folder' ),
                'type' : 'ir.actions.act_window',
                'res_model' : 'documents.document',
                'view_mode' : 'tree,kanban,form',
                'context' : {
                    'searchpanel_default_folder_id' : folder.id,
                    'searchpanel_default_folder_id_domain' : [('folder_id', '=', folder.id)],
                    'group_by' : 'folder_id',
                    'search_default_folder_id' : folder.id,
                    'default_folder_id' : folder.id,
                },
                'target' : 'current',
            }
        else :
            sale_orders = SaleOrder.search ( [('quotations_id.name', '=', so.quotations_id.name)] )
            sale_orders.write ( {'tiene_dossier' : False} )
            return {
                'type' : 'ir.actions.client',
                'tag' : 'display_notification',
                'params' : {
                    'title' : _ ( 'Sin carpeta' ),
                    'message' : _ ( 'No se encontró carpeta para el dossier de %s' ) % (
                                so.quotations_id.name or so.name),
                    'type' : 'warning',
                    'sticky' : False,
                }
            }

    # -------------------------------------------------------------------------
    # Abrir carpeta de dossier (y marcar tiene_dossier)
    # -------------------------------------------------------------------------
    def action_open_dossier_folder(self) :
        self.ensure_one ()
        so = self

        folder = self._find_existing_folder_for ( so )
        SaleOrder = self.env['sale.order']

        if folder :
            sale_orders = SaleOrder.search ( [('quotations_id.name', '=', so.quotations_id.name)] )
            sale_orders.write ( {'tiene_dossier' : True} )

            return {
                'name' : _ ( 'Document Folder' ),
                'type' : 'ir.actions.act_window',
                'res_model' : 'documents.document',
                'view_mode' : 'tree,kanban,form',
                'context' : {
                    'searchpanel_default_folder_id' : folder.id,
                    'searchpanel_default_folder_id_domain' : [('folder_id', '=', folder.id)],
                    'group_by' : 'folder_id',
                    'search_default_folder_id' : folder.id,
                    'default_folder_id' : folder.id,
                },
                'target' : 'current',
            }
        else :
            sale_orders = SaleOrder.search ( [('quotations_id.name', '=', so.quotations_id.name)] )
            sale_orders.write ( {'tiene_dossier' : False} )
            return {
                'type' : 'ir.actions.client',
                'tag' : 'display_notification',
                'params' : {
                    'title' : _ ( 'Sin carpeta' ),
                    'message' : _ ( 'No se encontró carpeta para el dossier de %s' ) % (
                                so.quotations_id.name or so.name),
                    'type' : 'warning',
                    'sticky' : False,
                }
            }

    # -------------------------------------------------------------------------
    # Crear dossier + estructura + facetas + solicitudes (bajo el AÑO actual)
    # -------------------------------------------------------------------------
    def action_create_dossier_folders(self) :
        self.ensure_one ()
        so = self

        Folder = self.env['documents.folder']
        Request = self.env['documents.request_wizard']  # ajusta si tu modelo difiere

        # Fuente de facetas: workspace raíz
        parent_facets_src = self._get_folder_by_xmlid ( self.XMLID_FACETS_SOURCE_FOLDER )
        # Padre donde crear: carpeta del año actual (sid_folder_YYYY)
        target_parent = self._get_current_year_folder ()

        # Usuario (único) desde el grupo
        owner_id = self._get_request_owner_id_from_group ()

        order_code = (so.quotations_id and so.quotations_id.name) or so.name or _ ( 'Dossier' )
        confirmed_orders = self.env['sale.order'].search ( [
            ('state', '=', 'sale'),
            ('quotations_id', '=', so.quotations_id.id),
        ] )

        # ¿ya existe?
        existing_folder = self._find_existing_folder_for ( so )
        if existing_folder :
            confirmed_orders.write ( {'tiene_dossier' : True} )
            orders_str = ', '.join ( confirmed_orders.mapped ( 'name' ) ) or _ ( '(ninguno)' )
            return {
                'type' : 'ir.actions.client',
                'tag' : 'display_notification',
                'params' : {
                    'title' : _ ( 'Carpeta existente detectada' ),
                    'message' : _ ( 'Ya existe un dossier para el contrato principal. '
                                    'Se marcaron como "Dossier" los siguientes presupuestos: %s' ) % orders_str,
                    'type' : 'warning',
                    'sticky' : True,
                }
            }

        # Crear carpeta principal bajo la carpeta del año
        workspace_parent = Folder.create ( {
            'name' : order_code,
            'parent_folder_id' : target_parent.id,
        } )

        # Facetas parecidas (si el workspace raíz tiene facetas “plantilla”)
        child_folders = [
            '0. Plantillas', '1. Lista de documentos', '2. MPR', '3. Schedule', '4. Lista de materiales',
            '5. Packing List', '6.a ITP', '6.b Notificaciones', '6.b Autorizaciones de Envío',
            '7.a Planos', '7.b Datasheets', '7.c Lista de Repuestos', '8. Quality Plan', '9. Procedimientos',
            '10.a Certificados', '10.b Marcado CE/UKCA', '10.c Conformidad', '11. Logística',
            '12. Dossier Final', '13. Contrato', '14. KOM',
        ]
        if parent_facets_src :
            similar_facets_parent = parent_facets_src.facet_ids.filtered (
                lambda f : self._is_similar ( f.name, child_folders )
            )
            if similar_facets_parent :
                workspace_parent.write ( {'facet_ids' : [(4, facet.id) for facet in similar_facets_parent]} )

        # Marcar pedidos confirmados
        confirmed_orders.write ( {'tiene_dossier' : True} )

        estados = ['Proveedor', 'Enviado', 'Comentarios', 'Rechazado', 'Aprobado']
        folders_sin_estado = ['0. Plantillas', '6.b Notificaciones', '6.b Autorizaciones de Envío', '11. Logística',
                              '13. Contrato', '14. KOM']
        notificaciones = ['6.b Notificaciones']
        adenda = ['Adendas']
        noi = ['NOI-1', 'NOI-2', 'NOI-3', 'NOI-4', 'NOI-5', 'NOI-6', 'NOI-7', 'NOI-8', 'NOI-9', 'NOI-10']
        contrato = ['13. Contrato']

        seq_child = 10

        for fname in child_folders :
            child = Folder.create ( {
                'name' : fname,
                'parent_folder_id' : workspace_parent.id,
                'sequence' : seq_child,
            } )

            if fname not in folders_sin_estado :
                seq_state = 10
                for est in estados :
                    Folder.create ( {'name' : est, 'parent_folder_id' : child.id, 'sequence' : seq_state} )
                    seq_state += 1

            if fname in notificaciones :
                seq_noi = 10
                for n in noi :
                    Folder.create ( {'name' : n, 'parent_folder_id' : child.id, 'sequence' : seq_noi} )
                    seq_noi += 1

            if fname in contrato :
                for a in adenda :
                    Folder.create ( {'name' : a, 'parent_folder_id' : child.id} )

            if parent_facets_src :
                similar_facets_child = parent_facets_src.facet_ids.filtered (
                    lambda f, n=fname : self._is_similar ( f.name, [n] )
                )
                if similar_facets_child :
                    child.write ( {'facet_ids' : [(4, facet.id) for facet in similar_facets_child]} )

            # Solicitud de documentos asociada
            try :
                Request.create ( {
                    'name' : _ ( "Solicitud para %s / %s" ) % (workspace_parent.name, child.name),
                    'folder_id' : child.id,
                    'owner_id' : owner_id,
                } )
            except Exception as e :
                _logger.warning ( "No se pudo crear documents.request_wizard: %s", e )

            seq_child += 1

        return {
            'type' : 'ir.actions.client',
            'tag' : 'display_notification',
            'params' : {
                'title' : _ ( 'Dossier creado' ),
                'message' : _ ( 'Se creó el dossier "%s" con su estructura de carpetas.' ) % workspace_parent.name,
                'type' : 'success',
                'sticky' : False,
            }
        }
