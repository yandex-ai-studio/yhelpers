from __future__ import annotations

import subprocess
import sys
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10
    import tomli as tomllib

ROOT = Path(__file__).parents[1]


def test_distribution_name_matches_import_namespace():
    config = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert config["project"]["name"] == "yhelpers"


def test_distribution_and_package_versions_match():
    from yhelpers import __version__

    config = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    lock = tomllib.loads((ROOT / "uv.lock").read_text(encoding="utf-8"))
    locked_package = next(
        package for package in lock["package"] if package["name"] == "yhelpers"
    )
    assert config["project"]["version"] == __version__ == "0.1.1"
    assert locked_package["version"] == __version__


def test_agents_is_an_optional_dependency():
    config = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert not any(
        value.startswith("openai-agents") for value in config["project"]["dependencies"]
    )
    assert any(
        value.startswith("openai-agents")
        for value in config["project"]["optional-dependencies"]["agents"]
    )


def test_missing_agents_dependency_has_actionable_error():
    code = r"""
import builtins
import sys

sys.path.insert(0, "src")
real_import = builtins.__import__

def blocked(name, *args, **kwargs):
    if name == "agents" or name.startswith("agents."):
        raise ImportError("blocked for test")
    return real_import(name, *args, **kwargs)

builtins.__import__ = blocked
try:
    import yhelpers.agents.streaming
except ImportError as error:
    assert "optional Agents SDK dependency" in str(error)
    assert "yhelpers[agents]" in str(error)
else:
    raise AssertionError("import unexpectedly succeeded")
"""
    subprocess.run(
        [sys.executable, "-c", code],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
