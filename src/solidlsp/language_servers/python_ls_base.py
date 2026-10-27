"""
Provides the base class shared by all Python language server implementations.
"""
# SPDX-License-Identifier: MIT

from solidlsp.ls import SolidLanguageServer


class PythonLanguageServerBase(SolidLanguageServer):
    """
    Base class for Python language servers, which holds behaviour common to all implementations.
    """
