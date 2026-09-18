import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import render_page


def test_renders_light_theme() -> None:
    html = render_page("Hi", "<p>body</p>")
    assert "<body class=\"light\">" in html
    assert "/static/light.css" in html
    assert "Hi" in html


def test_title_is_substituted() -> None:
    html = render_page("My Page", "")
    assert "{{ title }}" not in html
    assert "<title>My Page</title>" in html
