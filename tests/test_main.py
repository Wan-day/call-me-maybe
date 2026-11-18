"""Tests for the command-line entry point."""

import sys
from pathlib import Path

import pytest

from src.__main__ import (
    DEFAULT_FUNCTIONS,
    DEFAULT_INPUT,
    DEFAULT_OUTPUT,
    main,
    parse_args,
)

VALID_FUNCTIONS = """[
  {
    "name": "fn_add_numbers",
    "description": "Add two numbers together and return their sum.",
    "parameters": {"a": {"type": "number"}, "b": {"type": "number"}},
    "returns": {"type": "number"}
  }
]"""
VALID_PROMPTS = """[
  {
    "prompt": "What is the sum of 2 and 3?"
  }
]"""


def write(tmp_path: Path, name: str, content: str) -> Path:
    """Write content to a file in a temporary directory.

    Args:
        tmp_path: Temporary directory provided by pytest.
        name: File name inside the directory.
        content: Text to write.

    Returns:
        Path of the written file.
    """
    path = tmp_path / name
    path.write_text(content, encoding="utf-8")
    return path


def run_args(functions: Path, prompts: Path, output: Path) -> list[str]:
    """Build the argument list for main from three paths.

    Args:
        functions: Functions definition file.
        prompts: Prompts file.
        output: Output file.

    Returns:
        The arguments, as they would come from the command line.
    """
    return [
        "--functions_definition", str(functions),
        "--input", str(prompts),
        "--output", str(output),
    ]


# --- parse_args ---------------------------------------------------------


def test_defaults_without_arguments() -> None:
    """No arguments gives the three DEFAULT_* paths."""
    args = parse_args([])
    assert args.functions_definition == DEFAULT_FUNCTIONS
    assert args.input == DEFAULT_INPUT
    assert args.output == DEFAULT_OUTPUT


@pytest.mark.parametrize(
    ("option", "attribute"),
    [
        ("--functions_definition", "functions_definition"),
        ("--input", "input"),
        ("--output", "output"),
    ],
)
def test_each_option_overrides_its_default(
    option: str, attribute: str
) -> None:
    """Each option replaces only its own default."""
    args = parse_args([option, "custom.json"])
    assert getattr(args, attribute) == Path("custom.json")
    defaults = {
        "functions_definition": DEFAULT_FUNCTIONS,
        "input": DEFAULT_INPUT,
        "output": DEFAULT_OUTPUT,
    }
    del defaults[attribute]
    for name, default in defaults.items():
        assert getattr(args, name) == default


def test_options_are_paths() -> None:
    """The namespace attributes are Path objects, not strings."""
    args = parse_args(["--input", "custom.json"])
    assert isinstance(args.functions_definition, Path)
    assert isinstance(args.input, Path)
    assert isinstance(args.output, Path)


def test_none_reads_sys_argv(monkeypatch: pytest.MonkeyPatch) -> None:
    """argv=None reads the options from sys.argv."""
    monkeypatch.setattr(sys, "argv", ["prog", "--input", "from_argv.json"])
    assert parse_args(None).input == Path("from_argv.json")


def test_help_exits_with_zero(capsys: pytest.CaptureFixture[str]) -> None:
    """--help prints the options and exits with status 0."""
    with pytest.raises(SystemExit) as info:
        parse_args(["--help"])
    assert info.value.code == 0
    out = capsys.readouterr().out
    for option in ("--functions_definition", "--input", "--output"):
        assert option in out


def test_unknown_option_exits_with_two(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """An unknown option exits with status 2 and a usage error."""
    with pytest.raises(SystemExit) as info:
        parse_args(["--inptu", "x.json"])
    assert info.value.code == 2
    assert "usage" in capsys.readouterr().err


def test_missing_value_exits_with_two() -> None:
    """An option without a value exits with status 2."""
    with pytest.raises(SystemExit) as info:
        parse_args(["--input"])
    assert info.value.code == 2


def test_main_does_not_catch_usage_errors() -> None:
    """main lets argparse's SystemExit through for invalid usage."""
    with pytest.raises(SystemExit) as info:
        main(["--inptu", "x.json"])
    assert info.value.code == 2


# --- main ---------------------------------------------------------------


def test_valid_files_return_zero(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Valid input files return 0 and print nothing to stderr."""
    argv = run_args(
        write(tmp_path, "functions.json", VALID_FUNCTIONS),
        write(tmp_path, "prompts.json", VALID_PROMPTS),
        tmp_path / "out.json",
    )
    assert main(argv) == 0
    assert capsys.readouterr().err == ""


@pytest.mark.parametrize("missing", ["functions", "prompts"])
def test_missing_file_is_critical(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], missing: str
) -> None:
    """A missing input file returns 1 with one critical line naming it."""
    functions = write(tmp_path, "functions.json", VALID_FUNCTIONS)
    prompts = write(tmp_path, "prompts.json", VALID_PROMPTS)
    absent = tmp_path / "absent.json"
    if missing == "functions":
        functions = absent
    else:
        prompts = absent
    assert main(run_args(functions, prompts, tmp_path / "out.json")) == 1
    lines = capsys.readouterr().err.splitlines()
    assert len(lines) == 1
    assert lines[0].startswith("[CRITICAL ERROR] ")
    assert str(absent) in lines[0]


def test_invalid_json_is_critical(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """An input file with invalid JSON returns 1 with one critical line."""
    argv = run_args(
        write(tmp_path, "functions.json", VALID_FUNCTIONS),
        write(tmp_path, "prompts.json", '[{"prompt": '),
        tmp_path / "out.json",
    )
    assert main(argv) == 1
    lines = capsys.readouterr().err.splitlines()
    assert len(lines) == 1
    assert lines[0].startswith("[CRITICAL ERROR] ")


def test_every_line_of_a_critical_error_is_prefixed(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A message with several problems gets the prefix on every line."""
    argv = run_args(
        write(tmp_path, "functions.json", VALID_FUNCTIONS),
        write(tmp_path, "prompts.json", '[{"promt": "a"}, {"prompt": 3}]'),
        tmp_path / "out.json",
    )
    assert main(argv) == 1
    lines = capsys.readouterr().err.splitlines()
    assert len(lines) == 2
    assert all(line.startswith("[CRITICAL ERROR] ") for line in lines)


def test_no_traceback_on_critical_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A critical error prints no traceback to stderr."""
    argv = run_args(
        tmp_path / "absent.json",
        write(tmp_path, "prompts.json", VALID_PROMPTS),
        tmp_path / "out.json",
    )
    assert main(argv) == 1
    assert "Traceback" not in capsys.readouterr().err


def test_nothing_printed_to_stdout_on_critical_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Error messages go to stderr only."""
    argv = run_args(
        tmp_path / "absent.json",
        write(tmp_path, "prompts.json", VALID_PROMPTS),
        tmp_path / "out.json",
    )
    main(argv)
    assert capsys.readouterr().out == ""
