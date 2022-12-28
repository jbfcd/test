__all__ = ["__version__", "version_tuple"]

try:
    from ._version import version as __version__, version_tuple
except ImportError:  # pragma: no cover
    # broken installation, we don't even try
    # unknown only works because we do poor mans version compare
    __version__ = "unknown"
    version_tuple = (0, 0, "unknown")  # type:ignore[assignment]


# For the cases when .pth file doesn't work (editable install)
import _pytest._py._loader  # noqa: F401
