"""Pydantic models describing the program's input data."""

from typing import Literal

from pydantic import BaseModel, Field

ParameterType = Literal["number", "integer", "string", "boolean"]
"""JSON types a function parameter or return value can have."""


class ParameterSpec(BaseModel):
    """Type description of one parameter or of a return value.

    Attributes:
        type: The JSON type the value must have.
    """

    type: ParameterType


class FunctionDefinition(BaseModel):
    """One function the LLM is allowed to call.

    Attributes:
        name: Unique function name, e.g. ``fn_add_numbers``.
        description: What the function does, shown to the LLM.
        parameters: Argument names mapped to their type description.
        returns: Type description of the return value.
    """

    name: str = Field(min_length=1)
    description: str
    parameters: dict[str, ParameterSpec]
    returns: ParameterSpec


class PromptItem(BaseModel):
    """One natural-language request to translate into a function call.

    Attributes:
        prompt: The request text, e.g. ``"What is the sum of 2 and 3?"``.
    """

    prompt: str


class ParsedInput(BaseModel):
    """Everything read from the input files.

    Attributes:
        functions: The functions the LLM may call.
        prompts: The requests to translate, in file order.
    """

    functions: list[FunctionDefinition]
    prompts: list[PromptItem]
