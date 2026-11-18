"""Entry point of ``python -m src``: read options, load inputs, run."""

import argparse
import sys
from pathlib import Path

from src.errors import InputFileError
from src.parser import Parser

DEFAULT_FUNCTIONS = Path("data/input/functions_definition.json")
DEFAULT_INPUT = Path("data/input/function_calling_tests.json")
DEFAULT_OUTPUT = Path("data/output/function_calling_results.json")

CRITICAL_PREFIX = "[CRITICAL ERROR] "
ERROR_PREFIX = "[ERROR] "


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Read the command-line options.

    Accepts --functions_definition, --input and --output. An option that
    is not given falls back to DEFAULT_FUNCTIONS, DEFAULT_INPUT or
    DEFAULT_OUTPUT. The files are not checked here; Parser does that.

    Args:
        argv: Arguments without the program name, for example
            ["--input", "x.json"]. None reads them from sys.argv.

    Returns:
        A namespace with three Path attributes: functions_definition,
        input and output.

    Raises:
        SystemExit: Raised by argparse. Status 0 after printing the help
            for -h/--help, status 2 after printing a usage error for an
            unknown option or a missing value.
    """
    cli = argparse.ArgumentParser(
        prog="python -m src",
        description="Translate natural-language prompts into function calls.",
    )
    cli.add_argument(
        "--functions_definition",
        type=Path,
        default=DEFAULT_FUNCTIONS,
        help=f"JSON file with the callable functions "
        f"(default: {DEFAULT_FUNCTIONS})",
    )
    cli.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_INPUT,
        help=f"JSON file with the prompts (default: {DEFAULT_INPUT})",
    )
    cli.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"where to write the results (default: {DEFAULT_OUTPUT})",
    )
    return cli.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Run the program and turn every failure into a message and a status.

    Steps:
        1. Read the options with parse_args.
        2. Load the input files with Parser. Parser checks that the files
           exist and contain valid JSON in the expected form; main only
           catches the errors it raises.
        3. Not implemented yet: pass the loaded input to the LLM and get
           the function calls back.
        4. Not implemented yet: write the function calls to the output
           JSON file.

    Errors are printed to stderr. A message that spans several lines
    (for example several schema problems in one file) gets the prefix on
    every line. There are two kinds:
        - Critical errors stop the run, for example an input file that is
          missing or invalid (InputFileError). main prints the message
          with the prefix "[CRITICAL ERROR] " and returns 1.
        - Non-critical errors let the run continue, for example one
          prompt that could not be processed. main prints the message
          with the prefix "[ERROR] ", keeps going, and still returns 0
          at the end.

    Args:
        argv: Arguments without the program name, for example
            ["--input", "x.json"]. None reads them from sys.argv.

    Returns:
        0 if the run finished, even with non-critical errors.
        1 if a critical error stopped the run.

    Raises:
        SystemExit: From parse_args, which exits through argparse with
            status 0 for -h/--help and status 2 for invalid command-line
            usage. main does not catch it.
    """
    args = parse_args(argv)
    parser = Parser(
        functions_path=args.functions_definition,
        prompts_path=args.input
    )
    try:
        parser.load()
    except InputFileError as error:
        print_error(str(error), CRITICAL_PREFIX)
        return 1
    return 0


def print_error(message: str, prefix: str) -> None:
    """Print a message to stderr with the prefix on every line.

    Args:
        message: The text to print; may span several lines.
        prefix: CRITICAL_PREFIX or ERROR_PREFIX.
    """
    for line in message.splitlines():
        print(prefix + line, file=sys.stderr)


if __name__ == "__main__":
    sys.exit(main())
