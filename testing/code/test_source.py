# -*- coding: utf-8 -*-
# flake8: noqa
# disable flake check on this file because some constructs are strange
# or redundant on purpose and can't be disable on a line-by-line basis
from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import ast
import inspect
import sys

import six

import _pytest._code
import pytest
from _pytest._code import Source


astonly = pytest.mark.nothing
failsonjython = pytest.mark.xfail("sys.platform.startswith('java')")


def test_source_str_function():
    x = Source("3")
    assert str(x) == "3"

    x = Source("   3")
    assert str(x) == "3"

    x = Source(
        """
        3
        """
    )
    assert str(x) == "\n3"


def test_unicode():
    x = Source(u"4")
    assert str(x) == "4"
    co = _pytest._code.compile(u'u"å"', mode="eval")
    val = eval(co)
    assert isinstance(val, six.text_type)


def test_source_from_function():
    source = _pytest._code.Source(test_source_str_function)
    assert str(source).startswith("def test_source_str_function():")


def test_source_from_method():
    class TestClass(object):
        def test_method(self):
            pass

    source = _pytest._code.Source(TestClass().test_method)
    assert source.lines == ["def test_method(self):", "    pass"]


def test_source_from_lines():
    lines = ["a \n", "b\n", "c"]
    source = _pytest._code.Source(lines)
    assert source.lines == ["a ", "b", "c"]


def test_source_from_inner_function():
    def f():
        pass

    source = _pytest._code.Source(f, deindent=False)
    assert str(source).startswith("    def f():")
    source = _pytest._code.Source(f)
    assert str(source).startswith("def f():")


def test_source_putaround_simple():
    source = Source("raise ValueError")
    source = source.putaround(
        "try:",
        """\
        except ValueError:
            x = 42
        else:
            x = 23""",
    )
    assert (
        str(source)
        == """\
try:
    raise ValueError
except ValueError:
    x = 42
else:
    x = 23"""
    )


def test_source_putaround():
    source = Source()
    source = source.putaround(
        """
        if 1:
            x=1
    """
    )
    assert str(source).strip() == "if 1:\n    x=1"


def test_source_strips():
    source = Source("")
    assert source == Source()
    assert str(source) == ""
    assert source.strip() == source


def test_source_strip_multiline():
    source = Source()
    source.lines = ["", " hello", "  "]
    source2 = source.strip()
    assert source2.lines == [" hello"]


def test_syntaxerror_rerepresentation():
    ex = pytest.raises(SyntaxError, _pytest._code.compile, "xyz xyz")
    assert ex.value.lineno == 1
    assert ex.value.offset in (4, 5, 7)  # XXX pypy/jython versus cpython?
    assert ex.value.text.strip(), "x x"


def test_isparseable():
    assert Source("hello").isparseable()
    assert Source("if 1:\n  pass").isparseable()
    assert Source(" \nif 1:\n  pass").isparseable()
    assert not Source("if 1:\n").isparseable()
    assert not Source(" \nif 1:\npass").isparseable()
    assert not Source(chr(0)).isparseable()


class TestAccesses(object):
    source = Source(
        """\
        def f(x):
            pass
        def g(x):
            pass
    """
    )

    def test_getrange(self):
        x = self.source[0:2]
        assert x.isparseable()
        assert len(x.lines) == 2
        assert str(x) == "def f(x):\n    pass"

    def test_getline(self):
        x = self.source[0]
        assert x == "def f(x):"

    def test_len(self):
        assert len(self.source) == 4

    def test_iter(self):
        values = [x for x in self.source]
        assert len(values) == 4


class TestSourceParsingAndCompiling(object):
    source = Source(
        """\
        def f(x):
            assert (x ==
                    3 +
                    4)
    """
    ).strip()

    def test_compile(self):
        co = _pytest._code.compile("x=3")
        d = {}
        exec(co, d)
        assert d["x"] == 3

    def test_compile_and_getsource_simple(self):
        co = _pytest._code.compile("x=3")
        exec(co)
        source = _pytest._code.Source(co)
        assert str(source) == "x=3"

    def test_compile_and_getsource_through_same_function(self):
        def gensource(source):
            return _pytest._code.compile(source)

        co1 = gensource(
            """
            def f():
                raise KeyError()
        """
        )
        co2 = gensource(
            """
            def f():
                raise ValueError()
        """
        )
        source1 = inspect.getsource(co1)
        assert "KeyError" in source1
        source2 = inspect.getsource(co2)
        assert "ValueError" in source2

    def test_getstatement(self):
        # print str(self.source)
        ass = str(self.source[1:])
        for i in range(1, 4):
            # print "trying start in line %r" % self.source[i]
            s = self.source.getstatement(i)
            # x = s.deindent()
            assert str(s) == ass

    def test_getstatementrange_triple_quoted(self):
        # print str(self.source)
        source = Source(
            """hello('''
        ''')"""
        )
        s = source.getstatement(0)
        assert s == str(source)
        s = source.getstatement(1)
        assert s == str(source)

    @astonly
    def test_getstatementrange_within_constructs(self):
        source = Source(
            """\
            try:
                try:
                    raise ValueError
                except SomeThing:
                    pass
            finally:
                42
        """
        )
        assert len(source) == 7
        # check all lineno's that could occur in a traceback
        # assert source.getstatementrange(0) == (0, 7)
        # assert source.getstatementrange(1) == (1, 5)
        assert source.getstatementrange(2) == (2, 3)
        assert source.getstatementrange(3) == (3, 4)
        assert source.getstatementrange(4) == (4, 5)
        # assert source.getstatementrange(5) == (0, 7)
        assert source.getstatementrange(6) == (6, 7)

    def test_getstatementrange_bug(self):
        source = Source(
            """\
            try:
                x = (
                   y +
                   z)
            except:
                pass
        """
        )
        assert len(source) == 6
        assert source.getstatementrange(2) == (1, 4)

    def test_getstatementrange_bug2(self):
        source = Source(
            """\
            assert (
                33
                ==
                [
                  X(3,
                      b=1, c=2
                   ),
                ]
              )
        """
        )
        assert len(source) == 9
        assert source.getstatementrange(5) == (0, 9)

    def test_getstatementrange_ast_issue58(self):
        source = Source(
            """\

            def test_some():
                for a in [a for a in
                    CAUSE_ERROR]: pass

            x = 3
        """
        )
        assert getstatement(2, source).lines == source.lines[2:3]
        assert getstatement(3, source).lines == source.lines[3:4]

    def test_getstatementrange_out_of_bounds_py3(self):
        source = Source("if xxx:\n   from .collections import something")
        r = source.getstatementrange(1)
        assert r == (1, 2)

    def test_getstatementrange_with_syntaxerror_issue7(self):
        source = Source(":")
        pytest.raises(SyntaxError, lambda: source.getstatementrange(0))

    def test_compile_to_ast(self):
        source = Source("x = 4")
        mod = source.compile(flag=ast.PyCF_ONLY_AST)
        assert isinstance(mod, ast.Module)
        compile(mod, "<filename>", "exec")

    def test_compile_and_getsource(self):
        co = self.source.compile()
        six.exec_(co, globals())
        f(7)
        excinfo = pytest.raises(AssertionError, f, 6)
        frame = excinfo.traceback[-1].frame
        stmt = frame.code.fullsource.getstatement(frame.lineno)
        assert str(stmt).strip().startswith("assert")

    @pytest.mark.parametrize("name", ["", None, "my"])
    def test_compilefuncs_and_path_sanity(self, name):
        def check(comp, name):
            co = comp(self.source, name)
            if not name:
                expected = "codegen %s:%d>" % (mypath, mylineno + 2 + 2)
            else:
                expected = "codegen %r %s:%d>" % (name, mypath, mylineno + 2 + 2)
            fn = co.co_filename
            assert fn.endswith(expected)

        mycode = _pytest._code.Code(self.test_compilefuncs_and_path_sanity)
        mylineno = mycode.firstlineno
        mypath = mycode.path

        for comp in _pytest._code.compile, _pytest._code.Source.compile:
            check(comp, name)

    def test_offsetless_synerr(self):
        pytest.raises(SyntaxError, _pytest._code.compile, "lambda a,a: 0", mode="eval")


def test_getstartingblock_singleline():
    class A(object):
        def __init__(self, *args):
            frame = sys._getframe(1)
            self.source = _pytest._code.Frame(frame).statement

    x = A("x", "y")

    values = [i for i in x.source.lines if i.strip()]
    assert len(values) == 1


def test_getline_finally():
    def c():
        pass

    with pytest.raises(TypeError) as excinfo:
        teardown = None
        try:
            c(1)
        finally:
            if teardown:
                teardown()
    source = excinfo.traceback[-1].statement
    assert str(source).strip() == "c(1)"


def test_getfuncsource_dynamic():
    source = """
        def f():
            raise ValueError

        def g(): pass
    """
    co = _pytest._code.compile(source)
    six.exec_(co, globals())
    assert str(_pytest._code.Source(f)).strip() == "def f():\n    raise ValueError"
    assert str(_pytest._code.Source(g)).strip() == "def g(): pass"


def test_getfuncsource_with_multine_string():
    def f():
        c = """while True:
    pass
"""

    expected = '''\
    def f():
        c = """while True:
    pass
"""
'''
    assert str(_pytest._code.Source(f)) == expected.rstrip()


def test_deindent():
    from _pytest._code.source import deindent as deindent

    assert deindent(["\tfoo", "\tbar"]) == ["foo", "bar"]

    source = """\
        def f():
            def g():
                pass
    """
    lines = deindent(source.splitlines())
    assert lines == ["def f():", "    def g():", "        pass"]


def test_source_of_class_at_eof_without_newline(tmpdir):
    # this test fails because the implicit inspect.getsource(A) below
    # does not return the "x = 1" last line.
    source = _pytest._code.Source(
        """
        class A(object):
            def method(self):
                x = 1
    """
    )
    path = tmpdir.join("a.py")
    path.write(source)
    s2 = _pytest._code.Source(tmpdir.join("a.py").pyimport().A)
    assert str(source).strip() == str(s2).strip()


if True:

    def x():
        pass


def test_getsource_fallback():
    from _pytest._code.source import getsource

    expected = """def x():
    pass"""
    src = getsource(x)
    assert src == expected


def test_idem_compile_and_getsource():
    from _pytest._code.source import getsource

    expected = "def x(): pass"
    co = _pytest._code.compile(expected)
    src = getsource(co)
    assert src == expected


def test_findsource_fallback():
    from _pytest._code.source import findsource

    src, lineno = findsource(x)
    assert "test_findsource_simple" in str(src)
    assert src[lineno] == "    def x():"


def test_findsource():
    from _pytest._code.source import findsource

    co = _pytest._code.compile(
        """if 1:
    def x():
        pass
"""
    )

    src, lineno = findsource(co)
    assert "if 1:" in str(src)

    d = {}
    eval(co, d)
    src, lineno = findsource(d["x"])
    assert "if 1:" in str(src)
    assert src[lineno] == "    def x():"


def test_get_path_and_lineno():
    from _pytest._code import get_path_and_lineno

    def f(x):
        pass

    fspath, lineno = get_path_and_lineno(f)

    assert fspath.name == "test_source.py"
    assert lineno == _pytest._code.getrawcode(f).co_firstlineno - 1  # see findsource

    class A(object):
        pass

    fspath, lineno = get_path_and_lineno(A)

    _, A_lineno = inspect.findsource(A)
    assert fspath.name == "test_source.py"
    assert lineno == A_lineno

    assert getfslineno(3) == ("", -1)

    class B(object):
        pass

    B.__name__ = "B2"
    assert get_path_and_lineno(B)[1] == -1


def test_code_of_object_instance_with_call():
    class A(object):
        pass

    pytest.raises(TypeError, lambda: _pytest._code.Source(A()))

    class WithCall(object):
        def __call__(self):
            pass

    code = _pytest._code.Code(WithCall())
    assert "pass" in str(code.source())

    class Hello(object):
        def __call__(self):
            pass

    pytest.raises(TypeError, lambda: _pytest._code.Code(Hello))


def getstatement(lineno, source):
    from _pytest._code.source import getstatementrange_ast

    source = _pytest._code.Source(source, deindent=False)
    ast, start, end = getstatementrange_ast(lineno, source)
    return source[start:end]


def test_oneline():
    source = getstatement(0, "raise ValueError")
    assert str(source) == "raise ValueError"


def test_comment_and_no_newline_at_end():
    from _pytest._code.source import getstatementrange_ast

    source = Source(
        [
            "def test_basic_complex():",
            "    assert 1 == 2",
            "# vim: filetype=pyopencl:fdm=marker",
        ]
    )
    ast, start, end = getstatementrange_ast(1, source)
    assert end == 2


def test_oneline_and_comment():
    source = getstatement(0, "raise ValueError\n#hello")
    assert str(source) == "raise ValueError"


@pytest.mark.xfail(hasattr(sys, "pypy_version_info"), reason="does not work on pypy")
def test_comments():
    source = '''def test():
    "comment 1"
    x = 1
      # comment 2
    # comment 3

    assert False

"""
comment 4
"""
'''
    for line in range(2, 6):
        assert str(getstatement(line, source)) == "    x = 1"
    for line in range(6, 10):
        assert str(getstatement(line, source)) == "    assert False"
    assert str(getstatement(10, source)) == '"""'


def test_comment_in_statement():
    source = """test(foo=1,
    # comment 1
    bar=2)
"""
    for line in range(1, 3):
        assert (
            str(getstatement(line, source))
            == "test(foo=1,\n    # comment 1\n    bar=2)"
        )


def test_single_line_else():
    source = getstatement(1, "if False: 2\nelse: 3")
    assert str(source) == "else: 3"


def test_single_line_finally():
    source = getstatement(1, "try: 1\nfinally: 3")
    assert str(source) == "finally: 3"


def test_issue55():
    source = (
        "def round_trip(dinp):\n  assert 1 == dinp\n"
        'def test_rt():\n  round_trip("""\n""")\n'
    )
    s = getstatement(3, source)
    assert str(s) == '  round_trip("""\n""")'


def test_multiline():
    source = getstatement(
        0,
        """\
raise ValueError(
    23
)
x = 3
""",
    )
    assert str(source) == "raise ValueError(\n    23\n)"


class TestTry(object):
    pytestmark = astonly
    source = """\
try:
    raise ValueError
except Something:
    raise IndexError(1)
else:
    raise KeyError()
"""

    def test_body(self):
        source = getstatement(1, self.source)
        assert str(source) == "    raise ValueError"

    def test_except_line(self):
        source = getstatement(2, self.source)
        assert str(source) == "except Something:"

    def test_except_body(self):
        source = getstatement(3, self.source)
        assert str(source) == "    raise IndexError(1)"

    def test_else(self):
        source = getstatement(5, self.source)
        assert str(source) == "    raise KeyError()"


class TestTryFinally(object):
    source = """\
try:
    raise ValueError
finally:
    raise IndexError(1)
"""

    def test_body(self):
        source = getstatement(1, self.source)
        assert str(source) == "    raise ValueError"

    def test_finally(self):
        source = getstatement(3, self.source)
        assert str(source) == "    raise IndexError(1)"


class TestIf(object):
    pytestmark = astonly
    source = """\
if 1:
    y = 3
elif False:
    y = 5
else:
    y = 7
"""

    def test_body(self):
        source = getstatement(1, self.source)
        assert str(source) == "    y = 3"

    def test_elif_clause(self):
        source = getstatement(2, self.source)
        assert str(source) == "elif False:"

    def test_elif(self):
        source = getstatement(3, self.source)
        assert str(source) == "    y = 5"

    def test_else(self):
        source = getstatement(5, self.source)
        assert str(source) == "    y = 7"


def test_semicolon():
    s = """\
hello ; pytest.skip()
"""
    source = getstatement(0, s)
    assert str(source) == s.strip()


def test_def_online():
    s = """\
def func(): raise ValueError(42)

def something():
    pass
"""
    source = getstatement(0, s)
    assert str(source) == "def func(): raise ValueError(42)"


def XXX_test_expression_multiline():
    source = """\
something
'''
'''"""
    result = getstatement(1, source)
    assert str(result) == "'''\n'''"


def test_getstartingblock_multiline():
    class A(object):
        def __init__(self, *args):
            frame = sys._getframe(1)
            self.source = _pytest._code.Frame(frame).statement

    # fmt: off
    x = A('x',
          'y'
          ,
          'z')
    # fmt: on
    values = [i for i in x.source.lines if i.strip()]
    assert len(values) == 4
