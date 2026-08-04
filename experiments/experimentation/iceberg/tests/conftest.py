"""Skip this suite when collected by the root interpreter.

These tests need pyiceberg, which cannot be installed into the root venv (it
pins rich<15, the project requires rich>=15). Run them with the experiment's own
interpreter:

    experimentation/iceberg/.venv/bin/python -m pytest experimentation/iceberg/tests
"""

collect_ignore_glob: list[str] = []

try:
    import pyiceberg  # noqa: F401
except ImportError:  # pragma: no cover - depends on which interpreter collects
    collect_ignore_glob = ["test_*.py"]
