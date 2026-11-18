"""Tests for the input pydantic models."""

import pytest
from pydantic import TypeAdapter, ValidationError

from src.models import FunctionDefinition, PromptItem

FUNCTIONS = TypeAdapter(list[FunctionDefinition])
PROMPTS = TypeAdapter(list[PromptItem])

VALID_FUNCTION = (
    '{"name": "fn_add_numbers", "description": "Add two numbers.",'
    ' "parameters": {"a": {"type": "number"}, "b": {"type": "number"}},'
    ' "returns": {"type": "number"}}'
)


def test_valid_function_definition() -> None:
    """A well-formed definition is parsed into nested models."""
    result = FUNCTIONS.validate_json(f"[{VALID_FUNCTION}]")
    assert result[0].name == "fn_add_numbers"
    assert list(result[0].parameters) == ["a", "b"]
    assert result[0].parameters["a"].type == "number"
    assert result[0].returns.type == "number"


def test_function_without_parameters() -> None:
    """A function may take no arguments."""
    text = (
        '[{"name": "fn_now", "description": "", "parameters": {},'
        ' "returns": {"type": "string"}}]'
    )
    assert FUNCTIONS.validate_json(text)[0].parameters == {}


def test_extra_keys_are_ignored() -> None:
    """Unknown keys in the input do not cause an error."""
    text = VALID_FUNCTION[:-1] + ', "extra": 1}'
    assert FUNCTIONS.validate_json(f"[{text}]")[0].name == "fn_add_numbers"


@pytest.mark.parametrize(
    "text",
    [
        # unsupported parameter type
        VALID_FUNCTION.replace('{"type": "number"}', '{"type": "float"}', 1),
        # empty function name
        VALID_FUNCTION.replace('"fn_add_numbers"', '""'),
        # missing "returns"
        VALID_FUNCTION.split(', "returns"')[0] + "}",
        # wrong type for "name"
        VALID_FUNCTION.replace('"fn_add_numbers"', "42"),
        # wrong case for a type
        VALID_FUNCTION.replace('{"type": "number"}', '{"type": "Number"}', 1),
        # empty parameter name
        VALID_FUNCTION.replace('"a":', '"":'),
        # parameters as a list instead of an object
        VALID_FUNCTION.replace(
            '{"a": {"type": "number"}, "b": {"type": "number"}}', "[]"
        ),
        # null description
        VALID_FUNCTION.replace('"Add two numbers."', "null"),
        # return value without a type
        VALID_FUNCTION.replace(
            '"returns": {"type": "number"}', '"returns": {}'
        ),
    ],
)
def test_invalid_function_definition(text: str) -> None:
    """Definitions that break the schema are rejected."""
    with pytest.raises(ValidationError):
        FUNCTIONS.validate_json(f"[{text}]")


@pytest.mark.parametrize("name", ["fn_add", "_private", "F2", "x"])
def test_identifier_style_names_are_accepted(name: str) -> None:
    """Letters, digits and underscores, not starting with a digit."""
    text = VALID_FUNCTION.replace("fn_add_numbers", name)
    assert FUNCTIONS.validate_json(f"[{text}]")[0].name == name


@pytest.mark.parametrize(
    "name", ["2fn", "fn add", "fn-add", 'fn\\"x', "   ", "fn.add", "fné"]
)
def test_other_names_are_rejected(name: str) -> None:
    """Spaces, punctuation, quotes, non-ASCII and leading digits fail."""
    text = VALID_FUNCTION.replace("fn_add_numbers", name)
    with pytest.raises(ValidationError, match="letters, digits and under"):
        FUNCTIONS.validate_json(f"[{text}]")


def test_valid_prompts() -> None:
    """A list of prompt objects is parsed in order."""
    text = '[{"prompt": "Greet john"}, {"prompt": " 1+1 "}]'
    result = PROMPTS.validate_json(text)
    assert [item.prompt for item in result] == ["Greet john", " 1+1 "]


@pytest.mark.parametrize("prompt", ["", " ", "\\n\\t "])
def test_blank_prompts_are_rejected(prompt: str) -> None:
    """A prompt with nothing to translate is rejected."""
    with pytest.raises(ValidationError, match="empty or only whitespace"):
        PROMPTS.validate_json(f'[{{"prompt": "{prompt}"}}]')


@pytest.mark.parametrize(
    "text",
    [
        '[{"promt": "typo"}]',
        '[{"prompt": 1}]',
        '[{"prompt": null}]',
        '[1, "x"]',
        "null",
        "[{",
        "",
    ],
)
def test_invalid_prompts(text: str) -> None:
    """Malformed prompt files are rejected."""
    with pytest.raises(ValidationError):
        PROMPTS.validate_json(text)
