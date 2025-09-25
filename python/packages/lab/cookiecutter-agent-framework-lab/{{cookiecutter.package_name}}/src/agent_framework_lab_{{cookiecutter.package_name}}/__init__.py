# Copyright (c) Microsoft. All rights reserved.

"""
{{ cookiecutter.package_description }}
"""

import importlib.metadata

# Import your main exports here
# from .main_module import MainClass, main_function

try:
    __version__ = importlib.metadata.version(__name__)
except importlib.metadata.PackageNotFoundError:
    __version__ = "0.0.0"  # Fallback for development mode

__all__ = [
    # List your exports here
    # "MainClass",
    # "main_function",
]
