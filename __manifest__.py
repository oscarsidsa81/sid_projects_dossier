{
    'name': 'sid_projects_dossier',
    'version': '15.0.1.1.0',
    'category': 'Sales',
    'license': 'AGPL-3',
    'summary': 'Gestión de Dossieres de Calidad',
    'description': 'Módulo de gestión de Dossieres de Calidad',
    'author': 'oscarsidsa81',
    'depends': ['base', 'sale_management', 'documents', 'oct_sale_extra_fields', 'sid_bankbonds_mod'],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/document_group.xml',
        'data/documents_tags.xml',
        'data/document_folders.xml',

        # Wizard actions/views must be loaded before views referencing them
        'data/sid_dossier_assign_wizard.xml',

        # Views / menus
        'views/sid_projects_dossier_sales.xml',
        'views/sid_projects_dossier_quotations.xml',

        # Window actions / menus
        'data/document_actions.xml',
    ],
    'installable': True,
    'auto_install': False,
    'application': False,

    # Vincular estructura existente: "Dossieres de calidad" (root) y años
    'pre_init_hook': 'pre_init_bind_quality_dossiers_folders',
    'post_init_hook': 'post_init_bind_quality_dossiers_folders',
}
