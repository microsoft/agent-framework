# Copyright (c) Microsoft. All rights reserved.

import logging
from typing import Annotated, Any, Literal

from pydantic import Field

from agent_framework import PromptExecutionSettings

logger = logging.getLogger(__name__)


class OpenAIEmbeddingPromptExecutionSettings(PromptExecutionSettings):
    """Specific settings for the text embedding endpoint."""

    input: str | list[str] | list[int] | list[list[int]] | None = None
    ai_model_id: Annotated[str | None, Field(serialization_alias="model")] = None
    encoding_format: Literal["float", "base64"] | None = None
    user: str | None = None
    extra_headers: dict[str, Any] | None = None
    extra_query: dict[str, Any] | None = None
    extra_body: dict[str, Any] | None = None
    timeout: float | None = None
    dimensions: Annotated[int | None, Field(gt=0, le=3072)] = None
