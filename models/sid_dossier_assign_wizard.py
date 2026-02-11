# models/sid_dossier_assign_wizard.py
# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError

from .sid_dossier_similarity import _get_root_workspace


class DossierAssignCandidate(models.TransientModel):
    _name = "dossier.assign.candidate"
    _description = "Candidatos de carpeta para dossier (wizard)"

    wizard_id = fields.Many2one("dossier.assign.wizard", required=True, ondelete="cascade")
    folder_id = fields.Many2one("documents.folder", required=True, string="Carpeta")
    match_basis = fields.Char(string="Criterio")  # por qué se sugiere
    parent_folder_id = fields.Many2one(
        related="folder_id.parent_folder_id", string="Padre", store=False, readonly=True
    )

    def action_pick(self):
        """Selecciona esta carpeta en el wizard (no cierra)."""
        self.ensure_one()
        self.wizard_id.write({"mode": "existing", "existing_folder_id": self.folder_id.id})


class DossierAssignWizard(models.TransientModel):
    _name = "dossier.assign.wizard"
    _description = "Asignar carpeta de dossier"

    sale_order_id = fields.Many2one("sale.order", required=True)
    mode = fields.Selection(
        [("existing", "Usar carpeta existente"), ("new", "Crear nueva carpeta")],
        required=True,
        default="existing",
    )
    existing_folder_id = fields.Many2one("documents.folder", string="Carpeta existente")
    new_folder_name = fields.Char(string="Nombre de la nueva carpeta")

    warning_msg = fields.Text(string="Avisos", readonly=True)
    force_override = fields.Boolean(
        string="Forzar reasignación",
        help="Solo administradores. Permite reasignar aunque haya documentos/asignaciones.",
    )

    candidate_ids = fields.One2many("dossier.assign.candidate", "wizard_id", string="Sugerencias")

    # ---------------------------------------------------------------------
    # Helpers
    # ---------------------------------------------------------------------
    def _user_can_force(self):
        so = self.sale_order_id or self.env["sale.order"]
        return bool(self.env.user.has_group(so.XMLID_DOSSIER_OWNER_GROUP))

    def _compute_warnings(self, target_folder):
        """Devuelve (warning_msg, block_reason_or_None)."""
        so = self.sale_order_id
        if not so:
            return ("", None)

        current_key = (so.dossier_asignado or "").strip()
        target_name = (target_folder.name or "").strip() if target_folder else ""

        # Si no hay cambio real, sin avisos
        if current_key and target_name and current_key == target_name:
            return ("", None)

        msgs = []
        block_reason = None

        # Si quieren CAMBIAR la asignación a otro dossier, aplicar guardarraíles
        if current_key and target_name and current_key != target_name:
            Folder = self.env["documents.folder"]
            Documents = self.env["documents.document"]

            # 1) Dossier actual con docs -> bloquear (salvo override/admin)
            current_folder = Folder.search([("name", "=", current_key)], limit=1)
            if current_folder:
                doc_count = Documents.search_count([("folder_id", "child_of", current_folder.id)])
                if doc_count:
                    msgs.append(
                        _("El dossier actual '%s' ya contiene %s documento(s).") % (current_key, doc_count)
                    )
                    block_reason = _(
                        "No se permite modificar la asignación porque el dossier actual ya tiene documentos."
                    )

            # 2) Dossier actual usado por otros pedidos -> bloquear (salvo override/admin)
            other_orders = self.env["sale.order"].search_count(
                [("id", "!=", so.id), ("tiene_dossier", "=", True), ("dossier_asignado", "=", current_key)]
            )
            if other_orders:
                msgs.append(
                    _("El dossier actual '%s' está asignado a otros %s presupuesto(s)/pedido(s).")
                    % (current_key, other_orders)
                )
                block_reason = block_reason or _(
                    "No se permite modificar la asignación porque el dossier actual ya está referenciado por otros pedidos."
                )

        # 3) Aviso si el dossier destino ya está asignado (no bloquea por defecto)
        if target_name:
            used = self.env["sale.order"].search_count(
                [("tiene_dossier", "=", True), ("dossier_asignado", "=", target_name)]
            )
            if used:
                msgs.append(_("El dossier destino '%s' ya está asignado a %s pedido(s).") % (target_name, used))

        return ("\n".join(msgs), block_reason)

    # ---------------------------------------------------------------------
    # Defaults / domains / onchange
    # ---------------------------------------------------------------------
    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)

        so_id = self.env.context.get("default_sale_order_id") or self.env.context.get("active_id")
        so = self.env["sale.order"].browse(so_id)
        res["sale_order_id"] = so.id

        root_key = (so._get_dossier_key(so) or "").strip()
        is_adenda = bool(so.quotations_id and getattr(so.quotations_id, "parent_id", False))

        folder = so._find_existing_folder_for(so)

        if folder:
            res["mode"] = "existing"
            res["existing_folder_id"] = folder.id
        else:
            if is_adenda:
                # Adenda sin carpeta -> obligar a seleccionar existente (no crear desde adenda)
                res["mode"] = "existing"
                res["existing_folder_id"] = False
            else:
                res["mode"] = "new"
                res["new_folder_name"] = root_key or (so.quotations_id.name if so.quotations_id else so.name)

        # Sugerencias sobrias: root (si existe) + dossieres ya usados por el partner
        lines = []
        Folder = self.env["documents.folder"]
        seen = set()

        if folder:
            lines.append((0, 0, {"folder_id": folder.id, "match_basis": "Contrato principal (root)"}))
            seen.add(folder.id)

        partner_orders = self.env["sale.order"].search(
            [("partner_id", "=", so.partner_id.id), ("tiene_dossier", "=", True), ("dossier_asignado", "!=", False)]
        )
        for name in sorted(set(partner_orders.mapped("dossier_asignado"))):
            f = Folder.search([("name", "=", name)], limit=1)
            if f and f.id not in seen:
                lines.append((0, 0, {"folder_id": f.id, "match_basis": "Dossier del partner"}))
                seen.add(f.id)

        res["candidate_ids"] = lines
        return res

    @api.onchange("sale_order_id", "mode")
    def _onchange_set_domain(self):
        """Limita selección al ROOT y excluye 'Archivado'."""
        if not self.sale_order_id:
            return {}
        root = _get_root_workspace(self.sale_order_id)
        exclude = self.sale_order_id._get_folder_by_xmlid(self.sale_order_id.XMLID_EXCLUDE_FOLDER)
        dom = [("id", "child_of", root.id)]
        if exclude:
            dom += ["!", ("id", "child_of", exclude.id)]
        return {"domain": {"existing_folder_id": dom}}

    @api.onchange("mode", "existing_folder_id", "new_folder_name")
    def _onchange_mode(self):
        if self.mode == "existing":
            self.new_folder_name = False
            target = self.existing_folder_id
        else:
            self.existing_folder_id = False
            target = None
        self.warning_msg, _block = self._compute_warnings(target)

    # ---------------------------------------------------------------------
    # Confirm
    # ---------------------------------------------------------------------
    def action_confirm(self):
        self.ensure_one()
        so = self.sale_order_id
        Folder = self.env["documents.folder"]

        is_adenda = bool(so.quotations_id and getattr(so.quotations_id, "parent_id", False))

        if self.mode == "existing" and self.existing_folder_id:
            folder = self.existing_folder_id
        elif self.mode == "new" and self.new_folder_name:
            if is_adenda:
                raise UserError(_("No se puede crear un dossier desde una adenda. Selecciona el dossier del contrato principal."))
            parent = so._get_current_year_folder()
            folder = Folder.create({"name": self.new_folder_name, "parent_folder_id": parent.id})
        else:
            return

        warning_msg, block_reason = self._compute_warnings(folder)
        self.warning_msg = warning_msg

        if block_reason and not (self.force_override and self._user_can_force()):
            raise UserError(block_reason + ("\n\n" + warning_msg if warning_msg else ""))

        related = self.env["sale.order"].search(
            [("quotations_id", "=", so.quotations_id.id), ("partner_id", "=", so.partner_id.id)]
        )
        related.write({"tiene_dossier": True, "dossier_asignado": folder.name})

        return {
            "name": _("Document Folder"),
            "type": "ir.actions.act_window",
            "res_model": "documents.document",
            "view_mode": "tree,kanban,form",
            "context": {
                "searchpanel_default_folder_id": folder.id,
                "searchpanel_default_folder_id_domain": [("folder_id", "=", folder.id)],
                "group_by": "folder_id",
                "search_default_folder_id": folder.id,
                "default_folder_id": folder.id,
            },
            "target": "current",
        }
