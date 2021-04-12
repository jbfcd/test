"""Submit failure or test session information to a pastebin service."""
import tempfile
from io import StringIO
from typing import IO
from typing import Union

import pytest
from _pytest.config import Config
from _pytest.config import create_terminal_writer
from _pytest.config.argparsing import Parser
from _pytest.store import StoreKey
from _pytest.terminal import TerminalReporter


pastebinfile_key = StoreKey[IO[bytes]]()


def pytest_addoption(parser: Parser) -> None:
    group = parser.getgroup("terminal reporting")
    group._addoption(
        "--pastebin",
        metavar="mode",
        action="store",
        dest="pastebin",
        default=None,
        choices=["failed", "all"],
        help="send failed|all info to bpaste.net pastebin service.",
    )


@pytest.hookimpl(trylast=True)
def pytest_configure(config: Config) -> None:
    if config.option.pastebin == "all":
        tr = config.pluginmanager.getplugin("terminalreporter")
        # If no terminal reporter plugin is present, nothing we can do here;
        # this can happen when this function executes in a worker node
        # when using pytest-xdist, for example.
        if tr is not None:
            # pastebin file will be UTF-8 encoded binary file.
            config._store[pastebinfile_key] = tempfile.TemporaryFile("w+b")
            oldwrite = tr._tw.write

            def tee_write(s, **kwargs):
                oldwrite(s, **kwargs)
                if isinstance(s, str):
                    s = s.encode("utf-8")
                config._store[pastebinfile_key].write(s)

            tr._tw.write = tee_write


def pytest_unconfigure(config: Config) -> None:
    if pastebinfile_key in config._store:
        pastebinfile = config._store[pastebinfile_key]
        # Get terminal contents and delete file.
        pastebinfile.seek(0)
        sessionlog = pastebinfile.read()
        pastebinfile.close()
        del config._store[pastebinfile_key]
        # Undo our patching in the terminal reporter.
        tr = config.pluginmanager.getplugin("terminalreporter")
        del tr._tw.__dict__["write"]
        # Write summary.
        tr.write_sep("=", "Sending information to Paste Service")
        pastebinurl = create_new_paste(sessionlog)
        tr.write_line("pastebin session-log: %s\n" % pastebinurl)


def create_new_paste(contents: Union[str, bytes]) -> str:
    """Create a new paste using the bpaste.net service.

    :contents: Paste contents string.
    :returns: URL to the pasted contents, or an error message.
    """
    import re
    from urllib.request import urlopen
    from urllib.parse import urlencode

    params = {"code": contents, "lexer": "text", "expiry": "1week"}
    url = "https://bpaste.net"
    try:
        response: str = (
            urlopen(url, data=urlencode(params).encode("ascii")).read().decode("utf-8")
        )
    except OSError as exc_info:  # urllib errors
        return "bad response: %s" % exc_info
    m = re.search(r'href="/raw/(\w+)"', response)
    if m:
        return f"{url}/show/{m.group(1)}"
    else:
        return "bad response: invalid format ('" + response + "')"


def pytest_terminal_summary(terminalreporter: TerminalReporter) -> None:
    if terminalreporter.config.option.pastebin != "failed":
        return
    if "failed" in terminalreporter.stats:
        terminalreporter.write_sep("=", "Sending information to Paste Service")
        for rep in terminalreporter.stats["failed"]:
            try:
                msg = rep.longrepr.reprtraceback.reprentries[-1].reprfileloc
            except AttributeError:
                msg = terminalreporter._getfailureheadline(rep)
            file = StringIO()
            tw = create_terminal_writer(terminalreporter.config, file)
            rep.toterminal(tw)
            s = file.getvalue()
            assert len(s)
            pastebinurl = create_new_paste(s)
            terminalreporter.write_line(f"{msg} --> {pastebinurl}")
