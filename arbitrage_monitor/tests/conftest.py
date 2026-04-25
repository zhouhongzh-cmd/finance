from __future__ import annotations

import inspect
import sys

import pytest


@pytest.fixture(autouse=True)
def isolated_db_manager(tmp_path, monkeypatch):
    db_path = tmp_path / "monitor_history.db"
    monkeypatch.setenv("ARBITRAGE_MONITOR_DB_PATH", str(db_path))

    from utils.db_manager import DBManager

    DBManager._instance = None
    manager = DBManager()

    for module_name, attr_name in (
        ("utils.source_health", "db_manager"),
        ("config.audit", "db_manager"),
        ("core_scheduler", "db_manager"),
    ):
        module = sys.modules.get(module_name)
        if module is not None:
            setattr(module, attr_name, manager)

    futures_margin_module = sys.modules.get("fetchers.futures_margin")
    if futures_margin_module is not None:
        futures_margin_module.futures_margin_fetcher.db_manager = manager

    notifier_module = sys.modules.get("utils.notifier")
    if notifier_module is not None:
        notifier_module._notifier_instance = None

    try:
        yield
    finally:
        if notifier_module is not None:
            instance = notifier_module._notifier_instance
            if instance is not None:
                instance.flush()
                instance.client.close()
            notifier_module._notifier_instance = None
        DBManager._instance = None


@pytest.hookimpl(tryfirst=True)
def pytest_pyfunc_call(pyfuncitem):
    testfunction = pyfuncitem.obj
    if not inspect.isfunction(testfunction):
        return None

    funcargs = {
        arg: pyfuncitem.funcargs[arg]
        for arg in pyfuncitem._fixtureinfo.argnames
    }
    result = testfunction(**funcargs)
    if result == "SKIP":
        pytest.skip("legacy test returned SKIP")
    if result is False:
        pytest.fail("legacy test returned False")
    return True
