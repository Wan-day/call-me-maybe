"""Pydantic models describing the program's input data."""

import re
from typing import Annotated, Literal

from pydantic import BaseModel, Field, field_validator

ParameterType = Literal["number", "integer", "string", "boolean"]
"""JSON types a function parameter or return value can have."""

ParameterName = Annotated[str, Field(min_length=1)]
"""A parameter name: any text except the empty string."""

_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


class ParameterSpec(BaseModel):
    """Type description of one parameter or of a return value.

    Attributes:
        type: The JSON type the value must have.
    """

    type: ParameterType


class FunctionDefinition(BaseModel):
    """One function the LLM is allowed to call.

    Attributes:
        name: Unique function name, e.g. ``fn_add_numbers``. Only ASCII
            letters, digits and underscores, not starting with a digit.
        description: What the function does, shown to the LLM.
        parameters: Argument names (never empty) mapped to their type
            description.
        returns: Type description of the return value.
    """

    name: str
    description: str
    parameters: dict[ParameterName, ParameterSpec]
    returns: ParameterSpec

    @field_validator("name")
    @classmethod
    def _check_name(cls, name: str) -> str:
        """Reject names that are not identifier-style.

        Args:
            name: The function name from the input file.

        Returns:
            The name, unchanged.

        Raises:
            ValueError: If the name is empty or contains other characters
                than ASCII letters, digits and underscores, or starts
                with a digit.
        """
        if not _IDENTIFIER.fullmatch(name):
            raise ValueError(
                "must contain only letters, digits and underscores, "
                "and must not start with a digit"
            )
        return name


class PromptItem(BaseModel):
    """One natural-language request to translate into a function call.

    Attributes:
        prompt: The request text, e.g. ``"What is the sum of 2 and 3?"``.
            Never empty or only whitespace.
    """

    prompt: str

    @field_validator("prompt")
    @classmethod
    def _check_prompt(cls, prompt: str) -> str:
        """Reject prompts with nothing to translate.

        Args:
            prompt: The prompt text from the input file.

        Returns:
            The prompt, unchanged.

        Raises:
            ValueError: If the prompt is empty or only whitespace.
        """
        if not prompt.strip():
            raise ValueError("must not be empty or only whitespace")
        return prompt


class ParsedInput(BaseModel):
    """Everything read from the input files.

    Attributes:
        functions: The functions the LLM may call.
        prompts: The requests to translate, in file order.
    """

    functions: list[FunctionDefinition]
    prompts: list[PromptItem]
