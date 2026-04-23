from __future__ import annotations

import inspect

import pytest


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
