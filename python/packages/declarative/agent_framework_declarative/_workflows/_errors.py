# Copyright (c) Microsoft. All rights reserved.

"""Error types for declarative workflow executor modules.

This module exists so that executor modules and the builder (e.g.
``_executors_http``, ``_declarative_builder``) can raise declarative-specific
exceptions without importing from ``_factory``. ``_factory`` imports
``_declarative_builder`` which imports the executor modules; pulling
:class:`DeclarativeWorkflowError` from ``_factory`` into an executor or
builder module would therefore introduce a circular import.
"""

from __future__ import annotations

from agent_framework.exceptions import WorkflowException


class DeclarativeWorkflowError(WorkflowException):
    """Raised for build-time / factory-level declarative workflow errors.

    Used for YAML parsing/validation issues, missing configuration (e.g. an
    HTTP request handler not supplied for a workflow that contains an
    ``HttpRequestAction``), and other errors detected before workflow
    execution begins.
    """

    pass


class DeclarativeActionError(WorkflowException):
    """Raised when a declarative action fails at run time.

    Used by executor modules for runtime failures (e.g. transport errors,
    non-2xx responses from :class:`HttpRequestActionExecutor`). Build-time and
    factory-level errors continue to use :class:`DeclarativeWorkflowError`.
    """

    pass
