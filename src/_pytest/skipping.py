""" support for skip/xfail functions and markers. """
from _pytest.config import hookimpl
from _pytest.mark.evaluate import MarkEvaluator
from _pytest.outcomes import fail
from _pytest.outcomes import skip
from _pytest.outcomes import xfail
from _pytest.store import StoreToken


skipped_by_mark_token = StoreToken.mint(bool)
evalxfail_token = StoreToken.mint(MarkEvaluator)
unexpectedsuccess_token = StoreToken.mint(str)


def pytest_addoption(parser):
    group = parser.getgroup("general")
    group.addoption(
        "--runxfail",
        action="store_true",
        dest="runxfail",
        default=False,
        help="report the results of xfail tests as if they were not marked",
    )

    parser.addini(
        "xfail_strict",
        "default for the strict parameter of xfail "
        "markers when not given explicitly (default: False)",
        default=False,
        type="bool",
    )


def pytest_configure(config):
    if config.option.runxfail:
        # yay a hack
        import pytest

        old = pytest.xfail
        config._cleanup.append(lambda: setattr(pytest, "xfail", old))

        def nop(*args, **kwargs):
            pass

        nop.Exception = xfail.Exception
        setattr(pytest, "xfail", nop)

    config.addinivalue_line(
        "markers",
        "skip(reason=None): skip the given test function with an optional reason. "
        'Example: skip(reason="no way of currently testing this") skips the '
        "test.",
    )
    config.addinivalue_line(
        "markers",
        "skipif(condition): skip the given test function if eval(condition) "
        "results in a True value.  Evaluation happens within the "
        "module global context. Example: skipif('sys.platform == \"win32\"') "
        "skips the test if we are on the win32 platform. see "
        "https://docs.pytest.org/en/latest/skipping.html",
    )
    config.addinivalue_line(
        "markers",
        "xfail(condition, reason=None, run=True, raises=None, strict=False): "
        "mark the test function as an expected failure if eval(condition) "
        "has a True value. Optionally specify a reason for better reporting "
        "and run=False if you don't even want to execute the test function. "
        "If only specific exception(s) are expected, you can list them in "
        "raises, and if the test fails in other ways, it will be reported as "
        "a true failure. See https://docs.pytest.org/en/latest/skipping.html",
    )


@hookimpl(tryfirst=True)
def pytest_runtest_setup(item):
    # Check if skip or skipif are specified as pytest marks
    item._store[skipped_by_mark_token] = False
    eval_skipif = MarkEvaluator(item, "skipif")
    if eval_skipif.istrue():
        item._store[skipped_by_mark_token] = True
        skip(eval_skipif.getexplanation())

    for skip_info in item.iter_markers(name="skip"):
        item._store[skipped_by_mark_token] = True
        if "reason" in skip_info.kwargs:
            skip(skip_info.kwargs["reason"])
        elif skip_info.args:
            skip(skip_info.args[0])
        else:
            skip("unconditional skip")

    item._store[evalxfail_token] = MarkEvaluator(item, "xfail")
    check_xfail_no_run(item)


@hookimpl(hookwrapper=True)
def pytest_pyfunc_call(pyfuncitem):
    check_xfail_no_run(pyfuncitem)
    outcome = yield
    passed = outcome.excinfo is None
    if passed:
        check_strict_xfail(pyfuncitem)


def check_xfail_no_run(item):
    """check xfail(run=False)"""
    if not item.config.option.runxfail:
        evalxfail = item._store[evalxfail_token]
        if evalxfail.istrue():
            if not evalxfail.get("run", True):
                xfail("[NOTRUN] " + evalxfail.getexplanation())


def check_strict_xfail(pyfuncitem):
    """check xfail(strict=True) for the given PASSING test"""
    evalxfail = pyfuncitem._store[evalxfail_token]
    if evalxfail.istrue():
        strict_default = pyfuncitem.config.getini("xfail_strict")
        is_strict_xfail = evalxfail.get("strict", strict_default)
        if is_strict_xfail:
            del pyfuncitem._store[evalxfail_token]
            explanation = evalxfail.getexplanation()
            fail("[XPASS(strict)] " + explanation, pytrace=False)


@hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    rep = outcome.get_result()
    evalxfail = item._store.get(evalxfail_token, None)
    # unittest special case, see setting of unexpectedsuccess_token
    if unexpectedsuccess_token in item._store and rep.when == "call":
        reason = item._store[unexpectedsuccess_token]
        if reason:
            rep.longrepr = "Unexpected success: {}".format(reason)
        else:
            rep.longrepr = "Unexpected success"
        rep.outcome = "failed"

    elif item.config.option.runxfail:
        pass  # don't interfere
    elif call.excinfo and call.excinfo.errisinstance(xfail.Exception):
        rep.wasxfail = "reason: " + call.excinfo.value.msg
        rep.outcome = "skipped"
    elif evalxfail and not rep.skipped and evalxfail.wasvalid() and evalxfail.istrue():
        if call.excinfo:
            if evalxfail.invalidraise(call.excinfo.value):
                rep.outcome = "failed"
            else:
                rep.outcome = "skipped"
                rep.wasxfail = evalxfail.getexplanation()
        elif call.when == "call":
            strict_default = item.config.getini("xfail_strict")
            is_strict_xfail = evalxfail.get("strict", strict_default)
            explanation = evalxfail.getexplanation()
            if is_strict_xfail:
                rep.outcome = "failed"
                rep.longrepr = "[XPASS(strict)] {}".format(explanation)
            else:
                rep.outcome = "passed"
                rep.wasxfail = explanation
    elif (
        item._store.get(skipped_by_mark_token, True)
        and rep.skipped
        and type(rep.longrepr) is tuple
    ):
        # skipped by mark.skipif; change the location of the failure
        # to point to the item definition, otherwise it will display
        # the location of where the skip exception was raised within pytest
        _, _, reason = rep.longrepr
        filename, line = item.location[:2]
        rep.longrepr = filename, line + 1, reason


# called by terminalreporter progress reporting


def pytest_report_teststatus(report):
    if hasattr(report, "wasxfail"):
        if report.skipped:
            return "xfailed", "x", "XFAIL"
        elif report.passed:
            return "xpassed", "X", "XPASS"
