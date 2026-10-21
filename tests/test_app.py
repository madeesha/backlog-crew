import pytest

from backlog_crew import app, config


@pytest.fixture(autouse=True)
def allowed(monkeypatch):
    monkeypatch.setenv("ALLOWED_REPOS", "acme/shop")
    config.settings.cache_clear()
    yield
    config.settings.cache_clear()


@pytest.mark.parametrize(
    "payload, error",
    [
        ({"mode": "plan", "repo": "acme/shop"}, None),
        ({"mode": "run", "repo": "ACME/shop", "issue": 3}, None),
        ({"mode": "run", "repo": "acme/shop"}, "integer 'issue'"),
        ({"mode": "plan", "repo": "other/repo"}, "not in ALLOWED_REPOS"),
        ({"mode": "plan", "repo": "../etc"}, "owner/name"),
        ({"mode": "deploy", "repo": "acme/shop"}, "mode must be"),
    ],
)
def test_validate(payload, error):
    result = app.validate(payload)
    assert result is None if error is None else error in result
