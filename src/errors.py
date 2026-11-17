"""Exceptions raised by the program's modules."""


class InputFileError(Exception):
    """An input file is missing, unreadable, or does not match its schema.

    The message is meant to be shown to the user as is.
    """
