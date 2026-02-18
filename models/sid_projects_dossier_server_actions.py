# -*- coding: utf-8 -*-
"""Funciones auxiliares reutilizadas por wizard/acciones.

Notas de diseño:
- Se respeta la estructura y lógica de la acción existente `action_create_dossier_folders`
  (nomenclatura de carpetas, subcarpetas de estado, NOI y Adendas).
- La función es idempotente: si parte de la estructura ya existe, no la duplica.
"""

from odoo import _


def _is_similar(name, targets):
    """Replica la lógica de "similitud" de la acción original."""
    characters_to_remove = ",.;:?!@#$%^&*()_-+=<>/\\|[]{}"
    cleaned_name = (name or "").lower()
    for char in characters_to_remove:
        cleaned_name = cleaned_name.replace(char, "")
    for target in targets:
        cleaned_target = (target or "").lower()
        for char in characters_to_remove:
            cleaned_target = cleaned_target.replace(char, "")
        if cleaned_target in cleaned_name:
            return True
    return False


def _get_or_create_folder(Folder, parent_id, name, **extra_vals):
    """Busca/crea carpeta hija por nombre (idempotente)."""
    folder = Folder.search([
        ('parent_folder_id', '=', parent_id),
        ('name', '=', name),
    ], limit=1)
    if folder:
        # Actualizamos solo si se pasan valores explícitos.
        if extra_vals:
            folder.write(extra_vals)
        return folder
    vals = {'name': name, 'parent_folder_id': parent_id}
    vals.update(extra_vals or {})
    return Folder.create(vals)


def create_dossier_structure(env, workspace_parent_1):
    """Crea (o completa) la estructura de subcarpetas del dossier.

    Args:
        env: Environment
        workspace_parent_1 (documents.folder): carpeta raíz del dossier (contrato o adenda)
    """
    Folder = env['documents.folder'].sudo()
    Request = env['documents.request_wizard'].sudo()

    # Plantilla de facetas: se mantiene el browse(7) de la acción original.
    parent_folder_7 = Folder.browse(7)

    # Nombres de carpetas (exactamente como la acción original).
    child_folders = [
        '0. Plantillas',
        '1. Lista de documentos',
        '2. MPR',
        '3. Schedule',
        '4. Lista de materiales',
        '5. Packing List',
        '6.a ITP',
        '6.b Notificaciones',
        '6.b Autorizaciones de Envío',
        '7.a Planos',
        '7.b Datasheets',
        '7.c Lista de Repuestos',
        '8. Quality Plan',
        '9. Procedimientos',
        '10.a Certificados',
        '10.b Marcado CE/UKCA',
        '10.c Conformidad',
        '11. Logística',
        '12. Dossier Final',
        '13. Contrato',
        '14. KOM',
        '15. Milestones',
    ]
    estados = ['Proveedor', 'Enviado', 'Comentarios', 'Rechazado', 'Aprobado']
    folders_sin_estado = [
        '0. Plantillas',
        '6.b Notificaciones',
        '6.b Autorizaciones de Envío',
        '11. Logística',
        '13. Contrato',
        '14. KOM',
        '15. Milestones',
    ]
    notificaciones = ['6.b Notificaciones']
    noi = [f'NOI-{i}' for i in range(1, 11)]
    contrato = ['13. Contrato']
    adenda = ['Adendas']

    # 1) Facetas para el padre (carpeta raíz del dossier)
    try:
        similar_facets_parent = parent_folder_7.facet_ids.filtered(lambda f: _is_similar(f.name, child_folders))
        if similar_facets_parent:
            workspace_parent_1.write({'facet_ids': [(4, facet.id) for facet in similar_facets_parent]})
    except Exception:
        # No bloqueamos el proceso por facetas.
        pass

    # 2) Crear/Completar estructura
    sequence = 10
    user_id = 8  # se mantiene el usuario fijo del script original

    for folder_name in child_folders:
        workspace_child = _get_or_create_folder(
            Folder,
            workspace_parent_1.id,
            folder_name,
            sequence=sequence,
        )

        # Subcarpetas por estado (si aplica)
        if folder_name not in folders_sin_estado:
            seq_estado = 10
            for folder_name_estado in estados:
                _get_or_create_folder(
                    Folder,
                    workspace_child.id,
                    folder_name_estado,
                    sequence=seq_estado,
                )
                seq_estado += 1

        # Subcarpetas NOI
        if folder_name in notificaciones:
            seq_noi = 10
            for folder_name_noi in noi:
                _get_or_create_folder(
                    Folder,
                    workspace_child.id,
                    folder_name_noi,
                    sequence=seq_noi,
                )
                seq_noi += 1

        # Subcarpeta Adendas
        if folder_name in contrato:
            for folder_name_adenda in adenda:
                _get_or_create_folder(
                    Folder,
                    workspace_child.id,
                    folder_name_adenda,
                )

        # Facetas para cada hijo
        try:
            similar_facets_child = parent_folder_7.facet_ids.filtered(lambda f: _is_similar(f.name, [folder_name]))
            if similar_facets_child:
                workspace_child.write({'facet_ids': [(4, facet.id) for facet in similar_facets_child]})
        except Exception:
            pass

        # Solicitud de documentos (idempotente)
        req_name = f"Solicitud para {workspace_parent_1.name} / {workspace_child.name}"
        existing_req = Request.search([('name', '=', req_name), ('folder_id', '=', workspace_child.id)], limit=1)
        if not existing_req:
            Request.create({
                'name': req_name,
                'folder_id': workspace_child.id,
                'owner_id': user_id,
            })

        sequence += 1

    return True
