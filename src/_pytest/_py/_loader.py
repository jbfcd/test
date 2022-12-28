import importlib.abc
import importlib.util
import sys


class _PylibShimLoader(importlib.abc.Loader):
    def create_module(self, spec):
        assert spec.name == "py"

        return None

    def exec_module(self, module):
        assert module.__name__ == "py"

        from . import error, path

        module.error = error
        module.path = path

        sys.modules["py.error"] = error
        sys.modules["py.path"] = path


class _PylibShimFinder(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path, target=None):
        if fullname != "py":
            return None

        return importlib.util.spec_from_loader(
            fullname, _PylibShimLoader(), is_package=True
        )


sys.meta_path.append(_PylibShimFinder())
