"""A tiny page renderer — the fixture repo the swarm modifies during missions."""


def load_template() -> str:
    with open("templates/base.html", encoding="utf-8") as f:
        return f.read()


def render_page(title: str, body: str, theme: str = "light") -> str:
    """Render the index page with the given theme (only 'light' for now)."""
    html = load_template()
    html = html.replace("{{ title }}", title)
    html = html.replace("{{ theme }}", theme)
    html = html.replace("{{ body }}", body)
    return html


def main() -> None:
    print(render_page("Fixture", "<p>Hello from the target repo.</p>"))


if __name__ == "__main__":
    main()