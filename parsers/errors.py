"""Shared parser exceptions."""


class HeaderNotFoundError(Exception):
    """Raised when a parser cannot locate a required column header.

    Signals that the file structure has drifted from what the parser expects —
    probably an insurer template change. main.py catches this and quarantines
    the file with the exception message surfaced in the email report.
    """
