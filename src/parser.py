"""Read and validate the program's JSON input files."""

import json
from pathlib import Path
from typing import Any, TypeVar

from pydantic import BaseModel, ConfigDict, TypeAdapter, ValidationError

from src.errors import InputFileError
from src.models import FunctionDefinition, ParsedInput, PromptItem

T = TypeVar("T")

_FUNCTIONS = TypeAdapter(list[FunctionDefinition])
_PROMPTS = TypeAdapter(list[PromptItem])


class Parser(BaseModel):
    """Loads the input files and turns them into validated models.

    Every failure is raised as an InputFileError whose message can be
    shown to the user as is.

    Attributes:
        functions_path: JSON file holding an array of function definitions.
        prompts_path: JSON file holding an array of ``{"prompt": ...}``.
    """

    model_config = ConfigDict(frozen=True)

    functions_path: Path
    prompts_path: Path

    def load(self) -> ParsedInput:
        """Load both input files.

        Returns:
            The validated functions and prompts.

        Raises:
            InputFileError: If either file is invalid. The functions file
                is checked first.
        """
        return ParsedInput(
            functions=self.load_function_definitions(),
            prompts=self.load_prompts(),
        )

    def load_function_definitions(self) -> list[FunctionDefinition]:
        """Load the functions the LLM may call from ``functions_path``.

        Returns:
            The validated function definitions, in file order.

        Raises:
            InputFileError: If the file cannot be read, is not valid JSON,
                does not match the schema, is empty, or repeats a function
                name.
        """
        path = self.functions_path
        functions = self._load_json_list(path, _FUNCTIONS)
        if not functions:
            raise InputFileError(f"{path}: no functions defined")
        seen: set[str] = set()
        for function in functions:
            if function.name in seen:
                raise InputFileError(
                    f"{path}: function '{function.name}' is defined twice"
                )
            seen.add(function.name)
        return functions

    def load_prompts(self) -> list[PromptItem]:
        """Load the natural-language prompts from ``prompts_path``.

        Returns:
            The validated prompts, in file order. May be empty.

        Raises:
            InputFileError: If the file cannot be read, is not valid JSON,
                or does not match the schema.
        """
        return self._load_json_list(self.prompts_path, _PROMPTS)

    def _load_json_list(
        self, path: Path, adapter: TypeAdapter[list[T]]
    ) -> list[T]:
        """Read a file and validate its content with a pydantic adapter.

        Args:
            path: File to read, decoded as UTF-8. A leading byte order
                mark (BOM), as some Windows editors write, is skipped.
            adapter: Adapter describing the expected JSON array.

        Returns:
            The validated items.

        Raises:
            InputFileError: If reading or validation fails, or if a JSON
                object repeats a key.
        """
        try:
            with open(path, encoding="utf-8-sig") as file:
                text = file.read()
        except FileNotFoundError:
            raise InputFileError(f"{path}: file not found") from None
        except IsADirectoryError:
            raise InputFileError(f"{path}: is a directory") from None
        except PermissionError:
            raise InputFileError(f"{path}: permission denied") from None
        except UnicodeDecodeError:
            raise InputFileError(f"{path}: not a UTF-8 text file") from None
        except OSError as error:
            raise InputFileError(f"{path}: {error.strerror}") from None

        self._check_duplicate_keys(path, text)
        try:
            return adapter.validate_json(text)
        except ValidationError as error:
            raise InputFileError(self._describe(path, error)) from None

    @staticmethod
    def _check_duplicate_keys(path: Path, text: str) -> None:
        """Reject JSON objects that contain the same key twice.

        Standard JSON parsing keeps only the last value of a repeated key,
        so the duplicate would disappear silently. Text that is not valid
        JSON is left for pydantic to report.

        Args:
            path: File the text comes from, for the error message.
            text: The file content.

        Raises:
            InputFileError: If a key repeats, or if the JSON is nested too
                deeply to read.
        """
        def no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
            result: dict[str, Any] = {}
            for key, value in pairs:
                if key in result:
                    raise InputFileError(
                        f"{path}: key '{key}' appears twice in one object"
                    )
                result[key] = value
            return result

        try:
            json.loads(text, object_pairs_hook=no_duplicates)
        except json.JSONDecodeError:
            pass
        except RecursionError:
            raise InputFileError(f"{path}: JSON nested too deeply") from None

    @staticmethod
    def _describe(path: Path, error: ValidationError) -> str:
        """Turn a pydantic error into a short message, one line per problem.

        Args:
            path: File the error comes from.
            error: The validation error raised by pydantic.

        Returns:
            A message such as ``f.json: [0].returns: Field required``.
        """
        lines = []
        for detail in error.errors():
            location = ""
            for part in detail["loc"]:
                if isinstance(part, int):
                    location += f"[{part}]"
                else:
                    location += f".{part}"
            location = location.lstrip(".")
            prefix = f"{path}: {location}: " if location else f"{path}: "
            # Messages from our own validators start with "Value error, ".
            message = detail["msg"].removeprefix("Value error, ")
            lines.append(prefix + message)
        return "\n".join(lines)
