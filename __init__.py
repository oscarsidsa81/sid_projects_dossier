# -*- coding: utf-8 -*-

from . import models

# Hooks must be importable from the module namespace for Odoo to resolve
# pre_init_hook / post_init_hook by name.
from .hooks import pre_init_bind_quality_dossiers_folders, post_init_bind_quality_dossiers_folders  # noqa: F401
