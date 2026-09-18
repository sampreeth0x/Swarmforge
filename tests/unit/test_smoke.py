"""Smoke test: the package imports and the CLI parses."""


def test_version() -> None:
    import swarmforge

    assert swarmforge.__version__ == "0.1.0"


def test_cli_help() -> None:
    from swarmforge.cli import main

    try:
        main(["--help"])
    except SystemExit as exc:  # argparse exits 0 on --help
        assert exc.code == 0