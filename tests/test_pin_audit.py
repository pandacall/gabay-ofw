"""Pin audit (issue #49, PRD #34): exact pins verified in the deployed
artifact so a demo can never break because an upstream package or the
Gemini model string moved out from under it between rehearsal and the
judged run.
"""

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent


def _requirements_txt() -> str:
    return (_REPO_ROOT / "requirements.txt").read_text(encoding="utf-8")


def _requirements_lock_txt() -> str:
    return (_REPO_ROOT / "requirements-lock.txt").read_text(encoding="utf-8")


def _dockerfile() -> str:
    return (_REPO_ROOT / "Dockerfile").read_text(encoding="utf-8")


def test_google_adk_is_exact_pinned_in_requirements_txt():
    lines = [
        line.strip()
        for line in _requirements_txt().splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    adk_lines = [line for line in lines if line.split("==")[0].strip() == "google-adk"]
    assert adk_lines == ["google-adk==2.8.0"], (
        "google-adk must be exact-pinned (==), never a range: "
        f"found {adk_lines!r}"
    )


def test_no_requirement_uses_an_unpinned_or_ranged_adk_or_genai_package():
    # google-genai (the Gemini client) is allowed a floor (>=) today per
    # requirements.txt, but must never resolve to a moving "-latest" style
    # marker string, and google-adk itself must stay exact.
    lines = [
        line.strip()
        for line in _requirements_txt().splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    for line in lines:
        assert "-latest" not in line.lower(), f"-latest alias in requirements.txt: {line!r}"


def test_a_full_lockfile_is_committed_and_pins_the_same_adk_version():
    lock_text = _requirements_lock_txt()
    lock_lines = [
        line.strip()
        for line in lock_text.splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    # Every resolved dependency in a `pip freeze`-style lockfile is
    # exact-pinned by construction (`==`); assert that shape holds so a
    # hand-edit can't quietly reintroduce a range into the deployed lock.
    assert lock_lines, "requirements-lock.txt must not be empty"
    for line in lock_lines:
        assert "==" in line, f"requirements-lock.txt line is not exact-pinned: {line!r}"

    assert "google-adk==2.8.0" in lock_lines
    # The lockfile is what the Dockerfile actually installs — a mismatch
    # here would mean the audited pin never reaches the deployed artifact.
    dockerfile = _dockerfile()
    assert "requirements-lock.txt" in dockerfile
    assert "pip install --no-cache-dir -r requirements-lock.txt" in dockerfile


def test_gemini_model_string_is_pinned_not_a_latest_alias():
    from app.agent import GEMINI_MODEL

    assert GEMINI_MODEL, "GEMINI_MODEL must be set"
    lowered = GEMINI_MODEL.lower()
    assert "latest" not in lowered, f"GEMINI_MODEL uses a -latest alias: {GEMINI_MODEL!r}"
    # A pinned Gemini model string is a dated/numbered release identifier,
    # e.g. "gemini-2.5-flash" or "gemini-2.0-flash-001" — never bare
    # "gemini-pro"/"gemini-flash" with no version component, and never a
    # preview/experimental tag that Google can swap without notice.
    assert any(char.isdigit() for char in GEMINI_MODEL), (
        f"GEMINI_MODEL has no version number: {GEMINI_MODEL!r}"
    )
    for banned in ("preview", "exp", "experimental"):
        assert banned not in lowered, (
            f"GEMINI_MODEL looks unpinned/preview: {GEMINI_MODEL!r}"
        )


def test_no_gemini_model_alias_anywhere_in_app_source():
    """Belt-and-suspenders: GEMINI_MODEL (app.agent) is the only place a
    model string may be named. Scans app/*.py source text for any other
    hardcoded "-latest" Gemini model string that would bypass the pin."""
    import re

    pattern = re.compile(r"gemini-[a-z0-9.\-]*-latest", re.IGNORECASE)
    for path in (_REPO_ROOT / "app").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert not pattern.search(text), f"-latest Gemini alias found in {path}"
