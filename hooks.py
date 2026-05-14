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




def _pick_facet(workspace, names):
    Facet = workspace.env["documents.facet"].sudo().with_context(active_test=False)
    return Facet.search([("folder_id", "=", workspace.id), ("name", "in", names)], limit=1)


def _bind_existing_facets(env, workspace):
    if not workspace:
        return
    module = "sid_projects_dossier"

    # Prefer existing business facets to avoid duplicates on production DBs.
    doc_facet = _pick_facet(workspace, ["DOC", "ITP", "CONTRATO"])
    estado_facet = _pick_facet(workspace, ["ESTADO", "PLANOS"])

    if doc_facet:
        _ensure_xmlid(env, module, "sid_tagcat_doc", "documents.facet", doc_facet.id)
    if estado_facet:
        _ensure_xmlid(env, module, "sid_tagcat_estado", "documents.facet", estado_facet.id)


def _consolidate_facets(env, workspace):
    if not workspace:
        return
    Facet = env["documents.facet"].sudo().with_context(active_test=False)

    doc_facet = _pick_facet(workspace, ["DOC", "ITP", "CONTRATO"])
    estado_facet = _pick_facet(workspace, ["ESTADO", "PLANOS"])

    if doc_facet and doc_facet.name != "DOC":
        doc_facet.write({"name": "DOC"})
    if estado_facet and estado_facet.name != "ESTADO":
        estado_facet.write({"name": "ESTADO"})

    _bind_existing_facets(env, workspace)
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
    _bind_existing_facets(env, root)

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
    env = api.Environment(cr, SUPERUSER_ID, {})
    workspace = env.ref("sid_projects_dossier.sid_workspace_quality_dossiers", raise_if_not_found=False)
    _consolidate_facets(env, workspace)

    SaleOrder = env["sale.order"].sudo().with_context(active_test=False)
    Document = env["documents.document"].sudo().with_context(active_test=False)

    # Backfill sale.order.tiene_dossier from historical x_dossier flag.
    if "x_dossier" in SaleOrder._fields and "tiene_dossier" in SaleOrder._fields:
        orders = SaleOrder.search([("x_dossier", "=", True)])
        if orders:
            orders._compute_tiene_dossier()

    # Backfill document description/transmittal from legacy fields.
    if "x_name_2" in Document._fields and "document_description" in Document._fields:
        docs_missing_description = Document.search([("document_description", "=", False), ("x_name_2", "!=", False)])
        for doc in docs_missing_description:
            doc.write({"document_description": doc.x_name_2})

    if "x_transmittal" in Document._fields and "document_transmittal" in Document._fields:
        docs_missing_transmittal = Document.search([("document_transmittal", "=", False), ("x_transmittal", "!=", False)])
        for doc in docs_missing_transmittal:
            doc.write({"document_transmittal": doc.x_transmittal})
