from pathlib import Path


def test_app_renders_a_single_assistant_panel() -> None:
    app_source = (Path(__file__).parents[1] / "web_src" / "src" / "App.tsx").read_text()

    assert app_source.count("<AssistantPanel />") == 1
    assert '<section id="assistant"' in app_source
