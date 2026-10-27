"""Skip this suite when collected by the root interpreter.

These tests import pyiceberg. Run them with the experiment's own
interpreter when that package is not installed in the root venv:

    experimentation/iceberg/.venv/bin/python -m pytest experimentation/iceberg/tests
"""

collect_ignore_glob: list[str] = []

try:
    import pyiceberg  # noqa: F401
except ImportError:  # pragma: no cover - depends on which interpreter collects
    collect_ignore_glob = ["test_*.py"]
