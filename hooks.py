# -*- coding: utf-8 -*-
from datetime import date

from odoo import api, SUPERUSER_ID


def _pick_root_folder(Folder):
    """Return the existing root folder for quality dossiers.

    We intentionally accept spelling variants (Dosieres/Dossieres) and
    different casing, because the DB may already contain a manually created
    folder.
    """
    # Root folders only
    candidates = Folder.search([("parent_folder_id", "=", False)])
    if not candidates:
        return Folder

    def score(name):
        n = (name or "").strip().lower()
        s = 0
        if "calidad" in n:
            s += 10
        if "dosi" in n:  # dosieres/dossieres
            s += 10
        if "dossier" in n:
            s += 5
        if n in ("dosieres de calidad", "dossieres de calidad", "dossieres de calidad"):
            s += 50
        return s

    best = max(candidates, key=lambda r: score(r.name))
    # If nothing looks like dossiers, return empty recordset.
    return best if score(best.name) > 0 else Folder


def _ensure_xmlid(env, module, name, model, res_id):
    """Create/update an ir.model.data binding."""
    imd = env["ir.model.data"].sudo()
    existing = imd.search([("module", "=", module), ("name", "=", name)], limit=1)
    vals = {"module": module, "name": name, "model": model, "res_id": res_id, "noupdate": True}
    if existing:
        existing.write(vals)
    else:
        imd.create(vals)


def _bind_existing_folders(cr):
    """Bind existing folder structure (root + year folders) to stable xml_ids.

    IMPORTANT: this is used by *pre_init_hook* so XML data can safely ref the xml_ids.
    """
    env = api.Environment(cr, SUPERUSER_ID, {})
    Folder = env["documents.folder"].sudo().with_context(active_test=False)
    module = "sid_projects_dossier"

    root = _pick_root_folder(Folder)
    if not root:
        # Nothing to bind; module XML should not hard-require the root.
        return

    _ensure_xmlid(env, module, "sid_workspace_quality_dossiers", "documents.folder", root.id)

    # Bind year folders if present (children directly under root)
    year_folders = Folder.search([("parent_folder_id", "=", root.id)])
    for yf in year_folders:
        yname = (yf.name or "").strip()
        if yname.isdigit():
            _ensure_xmlid(env, module, "sid_workspace_quality_dossiers_%s" % yname, "documents.folder", yf.id)


def pre_init_bind_quality_dossiers_folders(cr):
    _bind_existing_folders(cr)


def post_init_bind_quality_dossiers_folders(cr, registry):
    # Keep it idempotent after install/upgrade too.
    _bind_existing_folders(cr)
