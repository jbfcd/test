import functools
import warnings
from pathlib import Path
from typing import Optional

from ..compat import LEGACY_PATH
from ..compat import legacy_path
from ..deprecated import HOOK_LEGACY_PATH_ARG
from _pytest.nodes import _check_path

# hookname: (Path, LEGACY_PATH)
imply_paths_hooks = {
    "pytest_ignore_collect": ("collection_path", "path"),
    "pytest_collect_file": ("file_path", "path"),
    "pytest_pycollect_makemodule": ("module_path", "path"),
    "pytest_report_header": ("start_path", "startdir"),
    "pytest_report_collectionfinish": ("startpath", "startdir"),
}


class PathAwareHookProxy:
    """
    this helper wraps around hook callers
    until pluggy supports fixingcalls, this one will do

    it currently doesnt return full hook caller proxies for fixed hooks,
    this may have to be changed later depending on bugs
    """

    def __init__(self, hook_caller):
        self.__hook_caller = hook_caller

    def __dir__(self):
        return dir(self.__hook_caller)

    def __getattr__(self, key, _wraps=functools.wraps):
        hook = getattr(self.__hook_caller, key)
        if key not in imply_paths_hooks:
            self.__dict__[key] = hook
            return hook
        else:
            path_var, fspath_var = imply_paths_hooks[key]

            @_wraps(hook)
            def fixed_hook(**kw):

                path_value: Optional[Path] = kw.pop(path_var, None)
                fspath_value: Optional[LEGACY_PATH] = kw.pop(fspath_var, None)
                if fspath_value is not None:
                    warnings.warn(
                        HOOK_LEGACY_PATH_ARG.format(
                            pylib_path_arg=fspath_var, pathlib_path_arg=path_var
                        ),
                        stacklevel=2,
                    )
                if path_value is not None:
                    if fspath_value is not None:
                        _check_path(path_value, fspath_value)
                    else:
                        fspath_value = legacy_path(path_value)
                else:
                    assert fspath_value is not None
                    path_value = Path(fspath_value)

                kw[path_var] = path_value
                kw[fspath_var] = fspath_value
                return hook(**kw)

            fixed_hook.__name__ = key
            self.__dict__[key] = fixed_hook
            return fixed_hook
