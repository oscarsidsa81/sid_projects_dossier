# -*- coding: utf-8 -*-
# models/sid_dossier_assign_wizard.py

from odoo import api, fields, models, _
from odoo.exceptions import UserError

from .sid_dossier_similarity import _get_root_workspace


class DossierAssignCandidate(models.TransientModel):
    _name = "dossier.assign.candidate"
    _description = "Candidatos de carpeta para dossier (wizard)"

    wizard_id = fields.Many2one("dossier.assign.wizard", required=True, ondelete="cascade")
    folder_id = fields.Many2one("documents.folder", required=True, string="Carpeta")
    match_basis = fields.Char(string="Criterio")
    parent_folder_id = fields.Many2one(
        related="folder_id.parent_folder_id", string="Padre", store=False, readonly=True
    )

    def action_pick(self):
        self.ensure_one()
        self.wizard_id.write({"mode": "existing", "existing_folder_id": self.folder_id.id})


class DossierAssignWizard(models.TransientModel):
    _name = "dossier.assign.wizard"
    _description = "Asignar carpeta de dossier"

    sale_order_id = fields.Many2one("sale.order", required=True, readonly=True)

    dossier_type = fields.Selection(
        [("principal", "Contrato principal"), ("adenda", "Adenda")],
        string="Tipo",
        required=True,
        default="principal",
    )

    dossier_key = fields.Char(string="Dossier (según sale.quotations)", readonly=True)

    mode = fields.Selection(
        [("existing", "Usar carpeta existente"), ("new", "Crear dossier")],
        required=True,
        default="existing",
    )

    existing_folder_id = fields.Many2one("documents.folder", string="Carpeta existente")
    new_folder_name = fields.Char(string="Nombre del dossier", readonly=True)

    warning_msg = fields.Text(string="Avisos", readonly=True)
    force_override = fields.Boolean(
        string="Forzar reasignación",
        help="Solo administradores. Permite asignar aunque haya documentos/asignaciones o el nombre no coincida.",
    )

    candidate_ids = fields.One2many("dossier.assign.candidate", "wizard_id", string="Carpetas encontradas")

    # ---------------------------------------------------------------------
    # Permisos
    # ---------------------------------------------------------------------
    def _user_can_force(self):
        so = self.sale_order_id or self.env["sale.order"]
        return bool(self.env.user.has_group(so.XMLID_DOSSIER_OWNER_GROUP))

    # ---------------------------------------------------------------------
    # Cálculo dossier (sale.quotations)
    # ---------------------------------------------------------------------
    def _compute_dossier_key(self, so, dossier_type):
        """Dossier = quotations_id.name o parent_id.name si es adenda."""
        q = so.quotations_id
        if not q:
            return (so.name or "").strip()
        if dossier_type == "adenda" and getattr(q, "parent_id", False):
            return (q.parent_id.name or q.name or so.name or "").strip()
        return (q.name or so.name or "").strip()

    def _list_candidate_folders(self, dossier_key):
        """Devuelve folders candidatos en TODOS los años (bajo el workspace root)."""
        Folder = self.env["documents.folder"].sudo()
        root = _get_root_workspace(self.sale_order_id)
        exclude = self.sale_order_id._get_folder_by_xmlid(self.sale_order_id.XMLID_EXCLUDE_FOLDER)

        dom = [("id", "child_of", root.id)]
        if exclude:
            dom += ["!", ("id", "child_of", exclude.id)]

        # 1) exact match
        exact = Folder.search(dom + [("name", "=", dossier_key)], limit=20)

        # 2) por si hay sufijos/prefijos, ofrecer ilike (limitado)
        like = Folder.search(dom + [("name", "ilike", dossier_key)], limit=20)

        # mantener orden: exact primero, luego el resto
        seen = set()
        res = []
        for f in exact:
            if f.id not in seen:
                res.append((f, "Nombre exacto"))
                seen.add(f.id)
        for f in like:
            if f.id not in seen:
                res.append((f, "Coincidencia parcial"))
                seen.add(f.id)
        return res

    def _compute_warnings(self, dossier_key, target_folder):
        """Devuelve (warning_msg, block_reason_or_None)."""
        so = self.sale_order_id
        if not so:
            return ("", None)

        msgs = []
        block_reason = None

        # coherencia nombre carpeta
        if target_folder and dossier_key and (target_folder.name or "").strip() != dossier_key:
            msgs.append(
                _(
                    "La carpeta seleccionada ('%s') NO coincide con el dossier esperado ('%s')."
                )
                % (target_folder.name, dossier_key)
            )
            block_reason = _(
                "No se permite asignar una carpeta cuyo nombre no coincide con el dossier (según sale.quotations)."
            )

        # guardarraíles por cambio de asignación
        current_key = (so.dossier_asignado or "").strip()
        if current_key and dossier_key and current_key != dossier_key:
            Folder = self.env["documents.folder"].sudo()
            Documents = self.env["documents.document"].sudo()

            current_folder = Folder.search([("name", "=", current_key)], limit=1)
            if current_folder:
                doc_count = Documents.search_count([("folder_id", "child_of", current_folder.id)])
                if doc_count:
                    msgs.append(_("El dossier actual '%s' ya contiene %s documento(s).") % (current_key, doc_count))
                    block_reason = _(
                        "No se permite modificar la asignación porque el dossier actual ya tiene documentos."
                    )

            other_orders = self.env["sale.order"].sudo().search_count(
                [("id", "!=", so.id), ("tiene_dossier", "=", True), ("dossier_asignado", "=", current_key)]
            )
            if other_orders:
                msgs.append(
                    _("El dossier actual '%s' está asignado a otros %s pedido(s).") % (current_key, other_orders)
                )
                block_reason = block_reason or _(
                    "No se permite modificar la asignación porque el dossier actual está referenciado por otros pedidos."
                )

        return ("\n".join(msgs), block_reason)

    # ---------------------------------------------------------------------
    # Defaults / onchange
    # ---------------------------------------------------------------------
    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)

        so_id = self.env.context.get("default_sale_order_id") or self.env.context.get("active_id")
        so = self.env["sale.order"].browse(so_id)
        res["sale_order_id"] = so.id

        # tipo por defecto basado en quotations.parent_id
        is_adenda = bool(so.quotations_id and getattr(so.quotations_id, "parent_id", False))
        res["dossier_type"] = "adenda" if is_adenda else "principal"

        dossier_key = self._compute_dossier_key(so, res["dossier_type"])
        res["dossier_key"] = dossier_key
        res["new_folder_name"] = dossier_key

        # candidatos por nombre en todos los años
        candidates = self._list_candidate_folders(dossier_key)
        lines = []
        for f, reason in candidates:
            lines.append((0, 0, {"folder_id": f.id, "match_basis": reason}))
        res["candidate_ids"] = lines

        # modo por defecto
        exact = candidates[0][0] if candidates and candidates[0][1] == "Nombre exacto" else None
        if exact:
            res["mode"] = "existing"
            res["existing_folder_id"] = exact.id
        else:
            # si es adenda, no crear automáticamente: obligar a elegir existente
            if is_adenda:
                res["mode"] = "existing"
                res["existing_folder_id"] = False
            else:
                res["mode"] = "new"

        return res

    @api.onchange("dossier_type")
    def _onchange_dossier_type(self):
        if not self.sale_order_id:
            return
        dossier_key = self._compute_dossier_key(self.sale_order_id, self.dossier_type)
        self.dossier_key = dossier_key
        self.new_folder_name = dossier_key

        # refrescar candidatos
        self.candidate_ids = [(5, 0, 0)]
        candidates = self._list_candidate_folders(dossier_key)
        self.candidate_ids = [(0, 0, {"folder_id": f.id, "match_basis": reason}) for f, reason in candidates]

        # por defecto: si hay match exacto, seleccionar y poner modo existing
        exact = next((f for f, reason in candidates if reason == "Nombre exacto"), False)
        if exact:
            self.mode = "existing"
            self.existing_folder_id = exact
        else:
            # si es adenda, no permitir crear por defecto
            if self.dossier_type == "adenda":
                self.mode = "existing"
                self.existing_folder_id = False
            else:
                self.mode = "new"
                self.existing_folder_id = False

    @api.onchange("sale_order_id")
    def _onchange_sale_order_id(self):
        if not self.sale_order_id:
            return
        is_adenda = bool(self.sale_order_id.quotations_id and getattr(self.sale_order_id.quotations_id, "parent_id", False))
        self.dossier_type = "adenda" if is_adenda else "principal"
        self._onchange_dossier_type()

    @api.onchange("sale_order_id")
    def _onchange_set_domain(self):
        if not self.sale_order_id:
            return {}
        root = _get_root_workspace(self.sale_order_id)
        exclude = self.sale_order_id._get_folder_by_xmlid(self.sale_order_id.XMLID_EXCLUDE_FOLDER)
        dom = [("id", "child_of", root.id)]
        if exclude:
            dom += ["!", ("id", "child_of", exclude.id)]
        return {"domain": {"existing_folder_id": dom}}

    @api.onchange("mode", "existing_folder_id")
    def _onchange_mode(self):
        # mantener new_folder_name = dossier_key
        self.new_folder_name = self.dossier_key

        target = self.existing_folder_id if self.mode == "existing" else None
        self.warning_msg, _block = self._compute_warnings(self.dossier_key, target)

    # ---------------------------------------------------------------------
    # Confirm
    # ---------------------------------------------------------------------
    def action_confirm(self):
        self.ensure_one()
        so = self.sale_order_id
        Folder = self.env["documents.folder"].sudo()

        dossier_key = (self.dossier_key or "").strip()
        if not dossier_key:
            raise UserError(_("No se ha podido determinar el dossier (sale.quotations)."))

        is_adenda = self.dossier_type == "adenda"

        # seleccionar / crear carpeta
        if self.mode == "existing":
            if not self.existing_folder_id:
                raise UserError(_("Selecciona una carpeta existente."))
            folder = self.existing_folder_id
        else:
            if is_adenda:
                raise UserError(_("No se puede crear un dossier desde una adenda. Selecciona el dossier del contrato principal."))
            parent = so._get_current_year_folder()
            # crear SOLO si no existe ya exact match
            folder = Folder.search([("name", "=", dossier_key)], limit=1)
            if not folder:
                folder = Folder.create({"name": dossier_key, "parent_folder_id": parent.id})

        warning_msg, block_reason = self._compute_warnings(dossier_key, folder)
        self.warning_msg = warning_msg

        if block_reason and not (self.force_override and self._user_can_force()):
            raise UserError(block_reason + ("\n\n" + warning_msg if warning_msg else ""))

        # asignación: dossier_asignado = quotations_id.name o parent_id.name (si adenda)
        # si el usuario fuerza una carpeta con nombre distinto, mantenemos coherencia con lo que se va a abrir: folder.name
        assign_value = dossier_key
        if folder and (folder.name or "").strip() != dossier_key and (self.force_override and self._user_can_force()):
            assign_value = (folder.name or dossier_key).strip()

        so.write({"tiene_dossier": True, "dossier_asignado": assign_value})

        return {
            "name": _("Documentos del dossier"),
            "type": "ir.actions.act_window",
            "res_model": "documents.document",
            "view_mode": "tree,kanban,form",
            "context": {
                "searchpanel_default_folder_id": folder.id,
                "searchpanel_default_folder_id_domain": [("folder_id", "=", folder.id)],
                "group_by": "folder_id",
            },
            "domain": [("folder_id", "child_of", folder.id)],
        }
