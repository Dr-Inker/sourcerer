from sourcerer.config import get_settings


def test_defaults_to_known_model(monkeypatch):
    monkeypatch.delenv("SOURCERER_MODEL", raising=False)
    assert get_settings().model == "openrouter/z-ai/glm-5.1"


def test_reads_model_from_env(monkeypatch):
    monkeypatch.setenv("SOURCERER_MODEL", "gemini-2.5-flash")
    assert get_settings().model == "gemini-2.5-flash"
