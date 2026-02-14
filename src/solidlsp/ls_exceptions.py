"""
This module contains the exceptions raised by the framework.
"""

from solidlsp.ls_config import Language


class SolidLSPException(Exception):
    def __init__(self, message: str, cause: Exception | None = None) -> None:
        """
        Initializes the exception with the given message.

        :param message: the message describing the exception
        :param cause: the original exception that caused this exception, if any.
            For exceptions raised during request handling, this is typically
                * an LSPError for errors returned by the LSP server
                * LanguageServerTerminatedException for errors due to the language server having terminated.
        """
        self.cause = cause
        super().__init__(message)

    def is_language_server_terminated(self) -> bool:
        """
        :return: True if the exception is caused by the language server having terminated as indicated
            by the causing exception being an instance of LanguageServerTerminatedException.
        """
        from .ls_process import LanguageServerTerminatedException

        return isinstance(self.cause, LanguageServerTerminatedException)

    def get_affected_language(self) -> Language | None:
        """
        :return: the affected language for the case where the exception is caused by the language server having terminated
        """
        from .ls_process import LanguageServerTerminatedException

        if isinstance(self.cause, LanguageServerTerminatedException):
            return self.cause.language
        return None

    def __str__(self) -> str:
        """
        Returns a string representation of the exception.
        """
        s = super().__str__()
        if self.cause:
            if "\n" in s:
                s += "\n"
            else:
                s += " "
            s += f"(caused by {self.cause})"
        return s


class MetalsStaleLockError(SolidLSPException):
    """
    Raised when a stale Metals H2 database lock is detected and the user
    has configured fail-on-stale-lock behavior.

    A stale lock occurs when a previous Metals process crashed without
    cleaning up its lock file, which can prevent proper AUTO_SERVER
    coordination with new instances.
    """

    def __init__(self, lock_path: str, message: str | None = None) -> None:
        self.lock_path = lock_path
        if message is None:
            message = (
                f"Stale Metals lock file detected at {lock_path}. "
                "A previous Metals process may have crashed. "
                "To resolve: remove the lock file manually, or set "
                "on_stale_lock='auto-clean' in ls_specific_settings.scala."
            )
        super().__init__(message)
