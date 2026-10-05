"""Keep UI tests from changing the user's macOS clipboard."""

import subprocess

import pytest


@pytest.fixture(autouse=True)
def isolate_system_clipboard(monkeypatch):
    run = subprocess.run

    def isolated_run(args, *positional, **kwargs):
        if args == ["/usr/bin/pbcopy"]:
            return subprocess.CompletedProcess(args, 0)
        return run(args, *positional, **kwargs)

    monkeypatch.setattr(subprocess, "run", isolated_run)
