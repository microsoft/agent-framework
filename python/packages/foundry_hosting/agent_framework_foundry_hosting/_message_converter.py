# Copyright (c) Microsoft. All rights reserved.

from agent_framework import Content, Message
from azure.ai.agentserver.responses.models import (
    ComputerScreenshotContent,
    FunctionCallOutputItemParam,
    MessageContent,
    MessageContentInputFileContent,
    MessageContentInputImageContent,
    MessageContentInputTextContent,
    MessageContentOutputTextContent,
    MessageContentReasoningTextContent,
    MessageContentRefusalContent,
    OutputItem,
    OutputItemFunctionToolCall,
    OutputItemMessage,
    OutputItemOutputMessage,
    OutputItemReasoningItem,
    OutputMessageContent,
    OutputMessageContentOutputTextContent,
    OutputMessageContentRefusalContent,
    SummaryTextContent,
    TextContent,
)
from typing_extensions import Sequence, cast


def to_messages(history: Sequence[OutputItem]) -> list[Message]:
    """Converts a sequence of OutputItem objects to a list of Message objects.

    Args:
        history (Sequence[OutputItem]): The sequence of OutputItem objects to convert.

    Returns:
        list[Message]: The list of Message objects.
    """
    messages: list[Message] = []
    for item in history:
        messages.append(_to_message(item))
    return messages


def _to_message(item: OutputItem) -> Message:
    """Converts an OutputItem to a Message.

    Args:
        item (OutputItem): The OutputItem to convert.

    Returns:
        Message: The converted Message.

    Raises:
        ValueError: If the OutputItem type is not supported.
    """
    if item.type == "output_message":
        msg = cast(OutputItemOutputMessage, item)
        contents = [_convert_output_message_content(part) for part in msg.content]
        return Message(role=msg.role, contents=contents)

    if item.type == "message":
        msg = cast(OutputItemMessage, item)
        contents = [_convert_message_content(part) for part in msg.content]
        return Message(role=msg.role, contents=contents)

    if item.type == "function_call":
        fc = cast(OutputItemFunctionToolCall, item)
        return Message(
            role="assistant",
            contents=[Content.from_function_call(fc.call_id, fc.name, arguments=fc.arguments)],
        )

    if item.type == "function_call_output":
        fco = cast(FunctionCallOutputItemParam, item)
        output = fco.output if isinstance(fco.output, str) else str(fco.output)
        return Message(
            role="tool",
            contents=[Content.from_function_result(fco.call_id, result=output)],
        )

    if item.type == "reasoning":
        reasoning = cast(OutputItemReasoningItem, item)
        contents: list[Content] = []
        if reasoning.summary:
            for summary in reasoning.summary:
                contents.append(Content.from_text(summary.text))
        return Message(role="assistant", contents=contents)

    raise ValueError(f"Unsupported OutputItem type: {item.type}")


def _convert_output_message_content(content: OutputMessageContent) -> Content:
    """Converts an OutputMessageContent to a Content object.

    Args:
        content (OutputMessageContent): The OutputMessageContent to convert.

    Returns:
        Content: The converted Content object.

    Raises:
        ValueError: If the OutputMessageContent type is not supported.
    """
    if content.type == "output_text":
        text_content = cast(OutputMessageContentOutputTextContent, content)
        return Content.from_text(text_content.text)
    if content.type == "refusal":
        refusal_content = cast(OutputMessageContentRefusalContent, content)
        return Content.from_text(refusal_content.refusal)

    raise ValueError(f"Unsupported OutputMessageContent type: {content.type}")


def _convert_message_content(content: MessageContent) -> Content:
    """Converts a MessageContent to a Content object.

    Args:
        content (MessageContent): The MessageContent to convert.

    Returns:
        Content: The converted Content object.

    Raises:
        ValueError: If the MessageContent type is not supported.
    """
    if content.type == "input_text":
        input_text = cast(MessageContentInputTextContent, content)
        return Content.from_text(input_text.text)
    if content.type == "output_text":
        output_text = cast(MessageContentOutputTextContent, content)
        return Content.from_text(output_text.text)
    if content.type == "text":
        text = cast(TextContent, content)
        return Content.from_text(text.text)
    if content.type == "summary_text":
        summary = cast(SummaryTextContent, content)
        return Content.from_text(summary.text)
    if content.type == "refusal":
        refusal = cast(MessageContentRefusalContent, content)
        return Content.from_text(refusal.refusal)
    if content.type == "reasoning_text":
        reasoning = cast(MessageContentReasoningTextContent, content)
        return Content.from_text_reasoning(text=reasoning.text)
    if content.type == "input_image":
        image = cast(MessageContentInputImageContent, content)
        if image.image_url:
            return Content.from_uri(image.image_url)
        if image.file_id:
            return Content.from_hosted_file(image.file_id)
    if content.type == "input_file":
        file = cast(MessageContentInputFileContent, content)
        if file.file_url:
            return Content.from_uri(file.file_url)
        if file.file_id:
            return Content.from_hosted_file(file.file_id, name=file.filename)
    if content.type == "computer_screenshot":
        screenshot = cast(ComputerScreenshotContent, content)
        return Content.from_uri(screenshot.image_url)

    raise ValueError(f"Unsupported MessageContent type: {content.type}")
