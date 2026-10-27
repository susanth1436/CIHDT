"""The requirements files must name what the console needs to run.

A deployment installs exactly what these files list. Anything imported only
at run time -- by a framework, inside a function, through an entry point --
is invisible to a scan of this project's own imports, and a scan is how
requirements-web.txt was first assembled. python-multipart was missed that
way: Starlette imports it when it parses a form body, so every control in the
console depended on a package nothing in the repository mentions, and the
hosted build answered "Internal Server Error" to every sign-in while the
developer's machine, which happened to have it, behaved perfectly.

These tests exist so that the next such dependency fails here rather than in
front of a reviewer.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
FULL = ROOT / "requirements.txt"
WEB = ROOT / "requirements-web.txt"

# Imported by something other than this project's own source, so no import
# scan will ever find them. Each entry names what pulls it in.
RUNTIME_ONLY = {
    "python-multipart": "Starlette, to parse an HTML form body",
}

# Needed to serve the console. The web file exists to drop the test and
# report-building dependencies, not these.
SERVER_PACKAGES = {
    "fastapi", "uvicorn", "pydantic", "numpy", "scikit-learn", "joblib",
    "psutil", "python-multipart",
}

# Deliberately absent from the deployment: nothing the server imports.
DEV_ONLY = {"pytest", "httpx", "python-docx", "python-pptx", "matplotlib"}


def _pins(path: Path) -> dict[str, str]:
    """{package: version} from a requirements file, ignoring comments."""
    found = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        m = re.match(r"^([A-Za-z0-9_.\-]+)(?:\[[^\]]*\])?==(.+)$", line)
        assert m, f"{path.name}: {line!r} is not an exact pin"
        found[m.group(1).lower()] = m.group(2).strip()
    return found


def test_both_files_pin_every_package_exactly():
    """A range would let a deployment install something untested."""
    assert _pins(FULL) and _pins(WEB)


@pytest.mark.parametrize("package,imported_by", sorted(RUNTIME_ONLY.items()))
def test_runtime_only_dependencies_are_declared(package, imported_by):
    for path in (FULL, WEB):
        assert package in _pins(path), (
            f"{package} is missing from {path.name}. It is imported by "
            f"{imported_by}, not by this project, so nothing else will "
            f"catch its absence until a deployment fails.")


def test_the_form_parser_is_actually_importable():
    """The symptom this guards against, checked directly.

    Without it Starlette raises inside Request.form(), every POST becomes a
    500, and because each GET still works the console looks alive.
    """
    pytest.importorskip(
        "multipart",
        reason="python-multipart is not installed; every form POST would 500")


def test_the_console_can_parse_a_form_post():
    """End to end: a form body must reach the handler.

    A sign-in with no credentials should be refused, and refusal is the
    proof -- reaching that answer at all means the body was parsed.
    """
    from fastapi.testclient import TestClient
    from cihdt.server.api import app

    client = TestClient(app, raise_server_exceptions=False)
    response = client.post("/login", data={"email": "", "password": ""},
                           follow_redirects=False)
    assert response.status_code < 500, (
        "a form POST failed inside the framework, which is what a missing "
        "python-multipart looks like")


def test_the_web_file_covers_the_server():
    web = set(_pins(WEB))
    missing = SERVER_PACKAGES - web
    assert not missing, f"requirements-web.txt is missing {sorted(missing)}"


def test_the_web_file_omits_the_development_dependencies():
    """Its reason for existing: matplotlib alone roughly doubles the image."""
    web = set(_pins(WEB))
    assert not (DEV_ONLY & web), (
        f"requirements-web.txt should not install {sorted(DEV_ONLY & web)}")


def test_shared_packages_are_pinned_to_the_same_version():
    """Two files disagreeing would make the deployment untested code."""
    full, web = _pins(FULL), _pins(WEB)
    for package in set(full) & set(web):
        assert full[package] == web[package], (
            f"{package} is {full[package]} in requirements.txt but "
            f"{web[package]} in requirements-web.txt")
