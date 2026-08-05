"""rsscan — block commits and builds that introduce secrets.

The version is read from installed package metadata rather than hardcoded here.
A hardcoded copy silently drifted in 0.1.1: `pyproject.toml` said 0.1.1 while
this file still said 0.1.0, so `--version` lied and -- worse -- the `--org`
adoption signal reported the wrong version, which is exactly the data that
signal exists to collect. One source of truth (pyproject) removes the class.
"""

from importlib.metadata import PackageNotFoundError, version as _pkg_version

try:
    __version__ = _pkg_version("rsscan")
except PackageNotFoundError:      # running from a source checkout, not installed
    __version__ = "0.0.0+source"
