"""Shared test helpers.

Not fixtures (nothing here needs pytest injection) — just a place for a
structural-scan primitive several tests independently need, so it isn't
duplicated across them.
"""

import importlib
import pkgutil

import app as app_package


def iter_app_modules():
    """Yields every module in the ``app`` package, imported.

    Used by structural regression-guard tests that scan real, live
    objects (agent trees, module source) rather than hardcoding
    expectations — see tests/test_agent_tool_guard.py and
    tests/test_dev_ui_absent.py.
    """
    yield app_package
    for info in pkgutil.walk_packages(app_package.__path__, "app."):
        yield importlib.import_module(info.name)
