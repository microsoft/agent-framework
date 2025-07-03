# Copyright (c) Microsoft. All rights reserved.

from typing import Any, ClassVar, Literal, TypeVar
from xml.etree.ElementTree import Element  # noqa: S405

from pydantic import Field, field_serializer

from agent_framework import BaseContent, ContentTypes, TextContent
from agent_framework.contents.const import (
    DEFAULT_FULLY_QUALIFIED_NAME_SEPARATOR,
    FUNCTION_RESULT_CONTENT_TAG,
    TEXT_CONTENT_TAG,
)
from agent_framework.contents.hashing import make_hashable
from agent_framework.exceptions import (
    ContentInitializationError,
)

TAG_CONTENT_MAP = {
    TEXT_CONTENT_TAG: TextContent,
}

_T = TypeVar("_T", bound="FunctionResultContent")


class FunctionResultContent(BaseContent):
    """This class represents function result content."""

    content_type: Literal[ContentTypes.FUNCTION_RESULT_CONTENT] = Field(FUNCTION_RESULT_CONTENT_TAG, init=False)  # type: ignore
    tag: ClassVar[str] = FUNCTION_RESULT_CONTENT_TAG
    id: str | None = None
    call_id: str | None = None
    result: Any
    name: str | None = None
    function_name: str
    plugin_name: str | None = None
    encoding: str | None = None

    def __init__(
        self,
        inner_content: Any | None = None,
        ai_model_id: str | None = None,
        id: str | None = None,
        call_id: str | None = None,
        name: str | None = None,
        function_name: str | None = None,
        plugin_name: str | None = None,
        result: Any | None = None,
        encoding: str | None = None,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        """Create function result content.

        Args:
            inner_content (Any | None): The inner content.
            ai_model_id (str | None): The id of the AI model.
            id (str | None): The id of the function call that the result relates to.
            call_id (str | None): The call id of the function call from the Responses API.
            name (str | None): The name of the function.
                When not supplied function_name and plugin_name should be supplied.
            function_name (str | None): The function name.
                Not used when 'name' is supplied.
            plugin_name (str | None): The plugin name.
                Not used when 'name' is supplied.
            result (Any | None): The result of the function.
            encoding (str | None): The encoding of the result.
            metadata (dict[str, Any] | None): The metadata of the function call.
            kwargs (Any): Additional arguments.
        """
        if function_name and plugin_name and not name:
            name = f"{plugin_name}{DEFAULT_FULLY_QUALIFIED_NAME_SEPARATOR}{function_name}"
        if name and not function_name and not plugin_name:
            if DEFAULT_FULLY_QUALIFIED_NAME_SEPARATOR in name:
                plugin_name, function_name = name.split(DEFAULT_FULLY_QUALIFIED_NAME_SEPARATOR, maxsplit=1)
            else:
                function_name = name
        args = {
            "inner_content": inner_content,
            "ai_model_id": ai_model_id,
            "id": id,
            "name": name,
            "function_name": function_name or "",
            "plugin_name": plugin_name,
            "result": result,
            "encoding": encoding,
        }
        if call_id:
            args["call_id"] = call_id
        if metadata:
            args["metadata"] = metadata

        # TODO (dmytrostruk): Resolve type error
        super().__init__(**args)  # type: ignore

    def __str__(self) -> str:
        """Return the text of the response."""
        return str(self.result)

    def to_element(self) -> Element:
        """Convert the instance to an Element."""
        element = Element(self.tag)
        if self.id:
            element.set("id", self.id)
        if self.name:
            element.set("name", self.name)
        element.text = str(self.result)
        return element

    @classmethod
    def from_element(cls: type[_T], element: Element) -> _T:
        """Create an instance from an Element."""
        if element.tag != cls.tag:
            raise ContentInitializationError(f"Element tag is not {cls.tag}")  # pragma: no cover
        return cls(id=element.get("id", ""), result=element.text, name=element.get("name", None))

    def to_dict(self) -> dict[str, str | Any]:
        """Convert the instance to a dictionary."""
        return {
            "tool_call_id": self.id,
            "content": self.result,
        }

    def custom_fully_qualified_name(self, separator: str) -> str:
        """Get the fully qualified name of the function with a custom separator.

        Args:
            separator (str): The custom separator.

        Returns:
            The fully qualified name of the function with a custom separator.
        """
        return f"{self.plugin_name}{separator}{self.function_name}" if self.plugin_name else self.function_name

    @field_serializer("result")
    def serialize_result(self, value: Any) -> str:
        """Serialize the result."""
        return str(value)

    def __hash__(self) -> int:
        """Return the hash of the function result content."""
        hashable_result = make_hashable(self.result)
        return hash((
            self.tag,
            self.id,
            hashable_result,
            self.name,
            self.function_name,
            self.plugin_name,
            self.encoding,
        ))
