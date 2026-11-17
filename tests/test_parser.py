"""Tests for reading and validating the input files."""

import os
from pathlib import Path

import pytest
from pydantic import ValidationError

from src.errors import InputFileError
from src.parser import Parser

ADD = (
    '{"name": "fn_add", "description": "Add two numbers.",'
    ' "parameters": {"a": {"type": "number"}, "b": {"type": "number"}},'
    ' "returns": {"type": "number"}}'
)
GREET = (
    '{"name": "fn_greet", "description": "Greet someone.",'
    ' "parameters": {"name": {"type": "string"}},'
    ' "returns": {"type": "string"}}'
)


def write(
    tmp_path: Path, content: str | bytes, name: str = "input.json"
) -> Path:
    """Write content to a file in a temporary directory.

    Args:
        tmp_path: Temporary directory provided by pytest.
        content: Text or raw bytes to write.
        name: File name inside the directory.

    Returns:
        Path of the written file.
    """
    path = tmp_path / name
    if isinstance(content, bytes):
        path.write_bytes(content)
    else:
        path.write_text(content, encoding="utf-8")
    return path


def parser_for(path: Path) -> Parser:
    """Build a parser that reads both input kinds from the same file.

    Each test only calls one load method, so the other path is unused.

    Args:
        path: File to read.

    Returns:
        A parser pointing at the file.
    """
    return Parser(functions_path=path, prompts_path=path)


def test_load_reads_both_files(tmp_path: Path) -> None:
    """load() returns the functions and the prompts together."""
    parser = Parser(
        functions_path=write(tmp_path, f"[{ADD}]", "functions.json"),
        prompts_path=write(tmp_path, '[{"prompt": "1+1"}]', "prompts.json"),
    )
    parsed = parser.load()
    assert [f.name for f in parsed.functions] == ["fn_add"]
    assert [p.prompt for p in parsed.prompts] == ["1+1"]


def test_load_reports_the_functions_file_first(tmp_path: Path) -> None:
    """When both files are broken, the functions file is reported."""
    parser = Parser(
        functions_path=tmp_path / "functions.json",
        prompts_path=tmp_path / "prompts.json",
    )
    with pytest.raises(InputFileError, match="functions.json"):
        parser.load()


def test_paths_may_be_strings(tmp_path: Path) -> None:
    """Plain strings are converted to Path by pydantic at runtime."""
    path = write(tmp_path, f"[{ADD}]")
    parser = Parser(
        functions_path=str(path),  # type: ignore[arg-type]
        prompts_path=str(path),  # type: ignore[arg-type]
    )
    assert parser.functions_path == path
    assert parser.load_function_definitions()[0].name == "fn_add"


def test_paths_are_required() -> None:
    """A parser cannot be created without its paths."""
    with pytest.raises(ValidationError):
        Parser()  # type: ignore[call-arg]


def test_parser_is_frozen(tmp_path: Path) -> None:
    """The paths cannot be changed after creation."""
    parser = parser_for(tmp_path / "input.json")
    with pytest.raises(ValidationError):
        parser.prompts_path = tmp_path / "other.json"


def test_load_function_definitions(tmp_path: Path) -> None:
    """Valid definitions are returned in file order."""
    path = write(tmp_path, f"[{ADD}, {GREET}]")
    functions = parser_for(path).load_function_definitions()
    assert [f.name for f in functions] == ["fn_add", "fn_greet"]
    assert functions[1].parameters["name"].type == "string"


def test_load_prompts(tmp_path: Path) -> None:
    """Valid prompts are returned in file order."""
    path = write(tmp_path, '[{"prompt": "Greet john"}, {"prompt": "1+1"}]')
    prompts = parser_for(path).load_prompts()
    assert [p.prompt for p in prompts] == ["Greet john", "1+1"]


def test_empty_prompt_list_is_allowed(tmp_path: Path) -> None:
    """An empty prompt file is valid and gives no prompts."""
    assert parser_for(write(tmp_path, "[]")).load_prompts() == []


def test_empty_function_list_is_rejected(tmp_path: Path) -> None:
    """Without functions there is nothing to call."""
    with pytest.raises(InputFileError, match="no functions defined"):
        parser_for(write(tmp_path, "[]")).load_function_definitions()


def test_duplicate_function_name(tmp_path: Path) -> None:
    """Two functions with the same name are rejected."""
    path = write(tmp_path, f"[{ADD}, {GREET}, {ADD}]")
    with pytest.raises(InputFileError, match="'fn_add' is defined twice"):
        parser_for(path).load_function_definitions()


def test_missing_file(tmp_path: Path) -> None:
    """A path that does not exist gives a clear error."""
    with pytest.raises(InputFileError, match="file not found"):
        parser_for(tmp_path / "nope.json").load_prompts()


def test_directory(tmp_path: Path) -> None:
    """A directory instead of a file gives a clear error."""
    with pytest.raises(InputFileError, match="is a directory"):
        parser_for(tmp_path).load_prompts()


@pytest.mark.skipif(
    os.name != "posix" or os.geteuid() == 0,
    reason="file permissions are not enforced",
)
def test_permission_denied(tmp_path: Path) -> None:
    """An unreadable file gives a clear error."""
    path = write(tmp_path, "[]")
    path.chmod(0)
    try:
        with pytest.raises(InputFileError, match="permission denied"):
            parser_for(path).load_prompts()
    finally:
        path.chmod(0o644)


def test_not_utf8(tmp_path: Path) -> None:
    """Binary content gives a clear error instead of a crash."""
    path = write(tmp_path, b'[{"prompt": "\xff\xfe"}]')
    with pytest.raises(InputFileError, match="not a UTF-8 text file"):
        parser_for(path).load_prompts()


@pytest.mark.parametrize("content", ["", "[{", '[{"prompt": "a"},]'])
def test_invalid_json(tmp_path: Path, content: str) -> None:
    """Malformed JSON is reported as such."""
    with pytest.raises(InputFileError, match="Invalid JSON"):
        parser_for(write(tmp_path, content)).load_prompts()


def test_top_level_not_a_list(tmp_path: Path) -> None:
    """A JSON object instead of an array is rejected."""
    with pytest.raises(InputFileError, match="valid array"):
        parser_for(write(tmp_path, '{"prompt": "a"}')).load_prompts()


def test_error_message_points_to_the_problem(tmp_path: Path) -> None:
    """Schema errors name the item and the field that is wrong."""
    bad = ADD.replace('{"type": "number"}', '{"type": "float"}', 1)
    path = write(tmp_path, f"[{GREET}, {bad}]")
    with pytest.raises(InputFileError) as info:
        parser_for(path).load_function_definitions()
    message = str(info.value)
    assert message.startswith(f"{path}: [1].parameters.a.type: ")
    assert "\n" not in message


def test_every_problem_is_reported(tmp_path: Path) -> None:
    """Each schema problem gets its own line."""
    path = write(tmp_path, '[{"promt": "a"}, {"prompt": 3}]')
    with pytest.raises(InputFileError) as info:
        parser_for(path).load_prompts()
    lines = str(info.value).splitlines()
    assert lines == [
        f"{path}: [0].prompt: Field required",
        f"{path}: [1].prompt: Input should be a valid string",
    ]
