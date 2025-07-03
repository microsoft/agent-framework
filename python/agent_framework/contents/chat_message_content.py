# Copyright (c) Microsoft. All rights reserved.

from typing import Annotated, Any, ClassVar, Literal, overload

from pydantic import Field

from agent_framework import (
    AuthorRole,
    BaseContent,
    ContentTypes,
    FinishReason,
    FunctionCallContent,
    FunctionResultContent,
    Status,
    TextContent,
    get_logger,
)
from agent_framework.contents.const import (
    CHAT_MESSAGE_CONTENT_TAG,
    DISCRIMINATOR_FIELD,
    FUNCTION_CALL_CONTENT_TAG,
    TEXT_CONTENT_TAG,
)
from agent_framework.contents.hashing import make_hashable

# TODO (dmytrostruk): Add more content types
TAG_CONTENT_MAP = {TEXT_CONTENT_TAG: TextContent, FUNCTION_CALL_CONTENT_TAG: FunctionCallContent}

CMC_ITEM_TYPES = Annotated[TextContent | FunctionCallContent, Field(discriminator=DISCRIMINATOR_FIELD)]

logger = get_logger()


class ChatMessageContent(BaseContent):
    """This is the class for chat message response content.

    All Chat Completion Services should return an instance of this class as response.
    Or they can implement their own subclass of this class and return an instance.

    Args:
        inner_content: Optional[Any] - The inner content of the response,
            this should hold all the information from the response so even
            when not creating a subclass a developer can leverage the full thing.
        ai_model_id: Optional[str] - The id of the AI model that generated this response.
        metadata: Dict[str, Any] - Any metadata that should be attached to the response.
        role: ChatRole - The role of the chat message.
        content: Optional[str] - The text of the response.
        encoding: Optional[str] - The encoding of the text.

    Methods:
        __str__: Returns the content of the response.
    """

    content_type: Literal[ContentTypes.CHAT_MESSAGE_CONTENT] = Field(default=CHAT_MESSAGE_CONTENT_TAG, init=False)  # type: ignore
    tag: ClassVar[str] = CHAT_MESSAGE_CONTENT_TAG
    role: AuthorRole
    name: str | None = None
    items: list[CMC_ITEM_TYPES] = Field(default_factory=list)  # type: ignore
    encoding: str | None = None
    finish_reason: FinishReason | None = None
    status: Status | None = None

    @overload
    def __init__(
        self,
        role: AuthorRole,
        items: list[CMC_ITEM_TYPES],
        name: str | None = None,
        inner_content: Any | None = None,
        encoding: str | None = None,
        finish_reason: FinishReason | None = None,
        status: Status | None = None,
        ai_model_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None: ...

    @overload
    def __init__(
        self,
        role: AuthorRole,
        content: str,
        name: str | None = None,
        inner_content: Any | None = None,
        encoding: str | None = None,
        finish_reason: FinishReason | None = None,
        status: Status | None = None,
        ai_model_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None: ...

    def __init__(  # type: ignore
        self,
        role: AuthorRole,
        items: list[CMC_ITEM_TYPES] | None = None,
        content: str | None = None,
        inner_content: Any | None = None,
        name: str | None = None,
        encoding: str | None = None,
        finish_reason: FinishReason | None = None,
        status: Status | None = None,
        ai_model_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ):
        """Create a ChatMessageContent instance.

        Args:
            role: AuthorRole - The role of the chat message.
            items: list[TextContent, StreamingTextContent, FunctionCallContent, FunctionResultContent, ImageContent]
                 - The content.
            content: str - The text of the response.
            inner_content: Optional[Any] - The inner content of the response,
                this should hold all the information from the response so even
                when not creating a subclass a developer can leverage the full thing.
            name: Optional[str] - The name of the response.
            encoding: Optional[str] - The encoding of the text.
            finish_reason: Optional[FinishReason] - The reason the response was finished.
            status: Optional[Status] - The status of the response for the Responses API.
            ai_model_id: Optional[str] - The id of the AI model that generated this response.
            metadata: Dict[str, Any] - Any metadata that should be attached to the response.
            **kwargs: Any - Any additional fields to set on the instance.
        """
        kwargs["role"] = role
        if encoding:
            kwargs["encoding"] = encoding
        if finish_reason:
            kwargs["finish_reason"] = finish_reason
        if status:
            kwargs["status"] = status
        if name:
            kwargs["name"] = name
        if content:
            item = TextContent(
                ai_model_id=ai_model_id,
                inner_content=inner_content,
                metadata=metadata or {},
                text=content,
                encoding=encoding,
            )
            if items:
                items.append(item)
            else:
                items = [item]
        if items:
            kwargs["items"] = items
        if inner_content:
            kwargs["inner_content"] = inner_content
        if metadata:
            kwargs["metadata"] = metadata
        if ai_model_id:
            kwargs["ai_model_id"] = ai_model_id
        super().__init__(
            **kwargs,
        )

    @property
    def content(self) -> str:
        """Get the content of the response, will find the first TextContent's text."""
        for item in self.items:
            if isinstance(item, TextContent):
                return item.text
        return ""

    @content.setter
    def content(self, value: str) -> None:
        """Set the content of the response."""
        if not value:
            logger.warning(
                "Setting empty content on ChatMessageContent does not work, "
                "you can do this through the underlying items if needed, ignoring."
            )
            return
        for item in self.items:
            if isinstance(item, TextContent):
                item.text = value
                item.encoding = self.encoding
                return
        self.items.append(
            TextContent(
                ai_model_id=self.ai_model_id,
                inner_content=self.inner_content,
                metadata=self.metadata,
                text=value,
                encoding=self.encoding,
            )
        )

    def __str__(self) -> str:
        """Get the content of the response as a string."""
        return self.content or ""

    def to_dict(self, role_key: str = "role", content_key: str = "content") -> dict[str, Any]:
        """Serialize the ChatMessageContent to a dictionary.

        Returns:
            dict - The dictionary representing the ChatMessageContent.
        """
        ret: dict[str, Any] = {
            role_key: self.role.value,
        }
        if self.role == AuthorRole.ASSISTANT and any(isinstance(item, FunctionCallContent) for item in self.items):
            ret["tool_calls"] = [item.to_dict() for item in self.items if isinstance(item, FunctionCallContent)]
        else:
            ret[content_key] = self._parse_items()
        if self.role == AuthorRole.TOOL:
            assert isinstance(self.items[0], FunctionResultContent)  # noqa: S101
            ret["tool_call_id"] = self.items[0].id or ""
        if self.role != AuthorRole.TOOL and self.name:
            ret["name"] = self.name
        return ret

    def _parse_items(self) -> str | list[dict[str, Any]]:
        """Parse the items of the ChatMessageContent.

        Returns:
            str | list of dicts - The parsed items.
        """
        if len(self.items) == 1 and isinstance(self.items[0], TextContent):
            return self.items[0].text
        if len(self.items) == 1 and isinstance(self.items[0], FunctionResultContent):
            return str(self.items[0].result)
        return [item.to_dict() for item in self.items]

    def __hash__(self) -> int:
        """Return the hash of the chat message content."""
        hashable_items = [make_hashable(item) for item in self.items] if self.items else []
        return hash((self.tag, self.role, self.content, self.encoding, self.finish_reason, *hashable_items))
