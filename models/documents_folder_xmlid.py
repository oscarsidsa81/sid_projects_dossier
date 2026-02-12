# -*- coding: utf-8 -*-

from odoo import api, models, SUPERUSER_ID


class DocumentsFolder(models.Model):
    _inherit = "documents.folder"

    @api.model
    def _sid_find_quality_dossiers_root(self):
        """Find the existing root workspace folder.

        We re-use the customer existing folder structure (no folder creation here).
        """
        return self.sudo().search(
            [
                ("parent_folder_id", "=", False),
                ("name", "ilike", "dosi"),
                ("name", "ilike", "calidad"),
            ],
            limit=1,
        )

    @api.model
    def _sid_ensure_quality_dossiers_root_xmlid(self):
        """Ensure sid_projects_dossier.sid_workspace_quality_dossiers exists and points to the real folder.

        This must work in **both** scenarios:
        - Fresh install (xmlid doesn't exist yet)
        - Upgrade (xmlid may exist already and/or point to a wrong res_id)
        """
        env = api.Environment(self._cr, SUPERUSER_ID, {})
        folder = env["documents.folder"]._sid_find_quality_dossiers_root()
        if not folder:
            return

        imd = env["ir.model.data"].sudo()
        module = "sid_projects_dossier"
        name = "sid_workspace_quality_dossiers"

        xmlid = imd.search([("module", "=", module), ("name", "=", name)], limit=1)
        if xmlid:
            # Fix stale pointers after refactors / manual changes.
            if xmlid.model != "documents.folder" or xmlid.res_id != folder.id:
                xmlid.write({"model": "documents.folder", "res_id": folder.id, "noupdate": True})
        else:
            # Create the xmlid for an existing folder.
            imd.create(
                {
                    "module": module,
                    "name": name,
                    "model": "documents.folder",
                    "res_id": folder.id,
                    "noupdate": True,
                }
            )

    def init(self):
        # Called at registry init (install & upgrade). Must be idempotent.
        self._sid_ensure_quality_dossiers_root_xmlid()
