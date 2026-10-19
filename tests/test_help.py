import re
from dataclasses import replace
from pathlib import Path

from fastapi.testclient import TestClient

from support_pilot.app import PAGE_HELP, create_app
from support_pilot.config import PACKAGE_DIR, load_settings
from support_pilot.db import make_engine
from support_pilot.help_reference import SETTINGS
from support_pilot.kb import PASSAGES
from support_pilot.tickets import RISING_MIN


def client(tmp_path):
    settings = replace(load_settings(), db_path=str(tmp_path / "t.db"))
    return TestClient(create_app(settings, engine=make_engine(settings.db_path)))


def test_help_pages_reference_and_suite_guide(tmp_path):
    c = client(tmp_path)
    assert "Who does what" in c.get("/help").text
    for p in (PACKAGE_DIR / "help").glob("*.md"):
        slug = re.sub(r"^\d+-", "", p.stem)
        assert c.get(f"/help/{slug}").status_code == 200, slug
    ref = c.get("/help/reference").text
    assert f"the {PASSAGES} most relevant" in ref  # live values, not copies
    assert f"at least {RISING_MIN} more" in ref and "SP_SUITE_TOKEN" in ref
    assert "How Mission Control works" in c.get("/help/mission-control").text


def test_every_screen_has_a_help_section(tmp_path):
    screens = {p.name for p in (PACKAGE_DIR / "templates").glob("*.html")} - {"base.html"}
    assert screens == set(PAGE_HELP)  # startup also checks each target section exists
    page = client(tmp_path).get("/problems").text
    assert f'href="/help/{PAGE_HELP["problems.html"]}"' in page


def test_every_setting_the_code_reads_is_documented():
    source = "\n".join(p.read_text() for p in Path(PACKAGE_DIR).rglob("*.py"))
    used = set(re.findall(r'"((?:SP|ANTHROPIC)_[A-Z_]+)"', source))
    assert {"SP_BACKLOG_URL", "SP_SUITE_TOKEN", "SP_OIDC_CLIENT_ID"} <= used  # the scan works
    assert used - set(SETTINGS) == set()
