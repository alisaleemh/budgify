from pathlib import Path


def test_dashboard_does_not_render_or_link_to_assistant_panel() -> None:
    app_source = (Path(__file__).parents[1] / "web_src" / "src" / "App.tsx").read_text()
    layout_source = (Path(__file__).parents[1] / "web_src" / "src" / "components" / "AppLayout.tsx").read_text()

    assert "AssistantPanel" not in app_source
    assert '#assistant' not in layout_source
    assert 'label: "Ask Budgify"' not in layout_source
