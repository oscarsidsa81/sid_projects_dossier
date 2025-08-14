{
    'name': 'sid_projects_dossier',
    'version': '1.0',
    'category': 'Sales',
    'license': 'AGPL-3',
    'summary': 'Control de Base Imponible',
    'description': 'Módulo de gestión de Dossieres de Calidad',
    'author': 'oscarsidsa81',
    'depends': ['base','sale_management','documents'],
    'data': [
        'views/sid_projects_dossier.xml',
        'data/document_actions.xml',
        'data/document_folders.xml',
        'data/documents_tags.xml',
    ],
    'installable': True,
    'auto_install': True,
    'application': False,
}