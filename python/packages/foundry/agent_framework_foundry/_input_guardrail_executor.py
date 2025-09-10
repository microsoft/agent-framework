# Copyright (c) Microsoft. All rights reserved.

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pydantic import BaseModel

from azure.core.exceptions import HttpResponseError
from azure.ai.contentsafety.models import (
    AnalyzeImageOptions,
    AnalyzeTextOptions,
    AnalyzeImageOutputType,
    AnalyzeTextOutputType,
    ImageCategory,
    TextCategory,
)

from agent_framework import (
    ChatMessage,
    ChatRole,
    DataContent,
    ErrorContent,
    TextContent,
    TextReasoningContent,
)

from agent_framework.workflow import (
    Executor,
    handler,
    WorkflowCompletedEvent,
    WorkflowContext,
)
from ._aacs_client import get_or_create_content_safety_client


class InputGuardrailExecutor(Executor, ABC):
    """built-in executor for reviewing agent messages."""

    def __init__(
        self,
        *,
        image_category_thresholds: dict[ImageCategory, int],
        text_category_thresholds: dict[TextCategory, int],
    ):
        super().__init__()
        self._image_category_thresholds = image_category_thresholds
        self._text_category_thresholds = text_category_thresholds

    @handler
    async def handle_request_str(self, request: str, ctx: WorkflowContext[str]) -> None:
        text_categories = list(self._text_category_thresholds.keys()) if self._text_category_thresholds else []
        text_failure_messages = self._analyze_text(request, text_categories)
        if text_failure_messages:
            await ctx.add_event(WorkflowCompletedEvent("\n".join(text_failure_messages)))
        else:
            await ctx.send_message(message=request)

    @handler
    async def handle_request_messages(self, request: list[ChatMessage], ctx: WorkflowContext[list[ChatMessage]]) -> None:
        aacs_client = get_or_create_content_safety_client()

        text_categories = list(self._text_category_thresholds.keys()) if self._text_category_thresholds else []
        image_categories = list(self._image_category_thresholds.keys()) if self._image_category_thresholds else []

        failure_messages = []

        for message in request.messages:
            if message.role != ChatRole.USER:
                continue

            texts = []
            images = []
            for content in message.contents:
                if isinstance(content, TextContent):
                    texts.append(content.text)
                elif isinstance(content, TextReasoningContent):
                    texts.append(content.text)
                elif isinstance(content, ErrorContent):
                    text = ""
                    if content.details:
                        text = content.details
                    if content.message:
                        text = text + "\n" + content.message
                    texts.append(text)
                elif isinstance(content, DataContent):
                    images.append(content.uri)

            # Analyze text
            try:
                for text in texts:
                    text_failure_messages = self._analyze_text(text, text_categories)
                    failure_messages.extend(text_failure_messages)
            except HttpResponseError as e:
                # TODO: error handling for text analysis failure
                print("Analyze text failed.")

            # TODO: Analyze images in a similar way if needed
            pass

        if failure_messages:
            await ctx.add_event(WorkflowCompletedEvent(failure_messages.join("\n")))
        else:
            await ctx.send_message(message=request)

    def _analyze_text(self, text: str, text_categories: list[TextCategory]) -> list[str]:
        aacs_client = get_or_create_content_safety_client()
        aacs_request = AnalyzeTextOptions(
            text=text,
            categories=text_categories,
            output_type=AnalyzeTextOutputType.FOUR_SEVERITY_LEVELS,
        )
        aacs_response = aacs_client.analyze_text(aacs_request)

        failure_messages = []
        for item in aacs_response.categories_analysis:
            category = item.category
            severity = item.severity
            target_severity = self._text_category_thresholds.get(category, None)
            if target_severity and severity > target_severity:
                # TODO: set error
                print(f"Text content flagged for category {category} with severity {severity}.")
                failure_messages.append(f"Text content flagged for category {category} with severity {severity}.")

        return failure_messages
