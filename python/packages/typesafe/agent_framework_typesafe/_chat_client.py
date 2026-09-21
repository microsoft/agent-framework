# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

from collections.abc import Awaitable, Mapping, Sequence
from types import TracebackType
from typing import Any, ClassVar, NoReturn, cast
from uuid import uuid4

from agent_framework import (
    BaseChatClient,
    ChatAndFunctionMiddlewareTypes,
    ChatMiddlewareLayer,
    ChatOptions,
    ChatResponse,
    ChatResponseUpdate,
    CompactionStrategy,
    Content,
    FunctionInvocationConfiguration,
    FunctionInvocationLayer,
    FunctionTool,
    Message,
    ResponseStream,
    TokenizerProtocol,
    UsageDetails,
    validate_tool_mode,
)
from agent_framework._settings import SecretString, load_settings
from agent_framework._telemetry import get_user_agent
from agent_framework.exceptions import (
    ChatClientException,
    ChatClientInvalidAuthException,
    ChatClientInvalidRequestException,
    ChatClientInvalidResponseException,
)
from agent_framework.observability import ChatTelemetryLayer
from typesafe_sdk import (
    AsyncTypeSafeClient,
    Questions,
    SystemOneResponse,
    TypeSafeAPIConnectionError,
    TypeSafeAPIError,
    TypeSafeAPIResponseValidationError,
    TypeSafeAuthenticationError,
    TypeSafeBadRequestError,
    TypeSafeError,
    TypeSafeNotFoundError,
    TypeSafePermissionDeniedError,
    TypeSafeUnprocessableEntityError,
)
from typing_extensions import Self, TypedDict, override

from ._tool_calls import compile_tool_call_plan

_TYPESAFE_SERVICE_URL = "https://api.typesafe.ai/v1/systemone"


class TypeSafeSettings(TypedDict, total=False):
    """TypeSafe settings resolved from explicit values, .env files, or the environment."""

    api_key: SecretString | None
    default_model: str | None


class TypeSafeChatOptions(ChatOptions[SystemOneResponse], total=False):
    """TypeSafe-specific chat options.

    Keys:
        response_format: Required TypeSafe Questions mapping. The connector forwards
            it as the TypeSafe questions parameter and returns SystemOneResponse.
        model: Optional TypeSafe model override.
        instructions: Optional Agent instructions included in the structured state.
    """

    pass


class RawTypeSafeChatClient(BaseChatClient[TypeSafeChatOptions]):
    """Raw Agent Framework chat client for TypeSafe AI System One models.

    The client maps text messages and Agent instructions to TypeSafe structured
    state. The response_format option supplies the TypeSafe Questions mapping,
    while every response is returned as SystemOneResponse. Free-form generation,
    streaming, tools, and non-text message content are not supported.

    Use TypeSafeChatClient for the standard middleware and telemetry layers.
    """

    OTEL_PROVIDER_NAME: ClassVar[str] = "typesafe.ai"
    _SUPPORTED_OPTIONS: ClassVar[frozenset[str]] = frozenset({
        "allow_multiple_tool_calls",
        "instructions",
        "model",
        "response_format",
        "tool_choice",
        "tools",
    })

    def __init__(
        self,
        *,
        api_key: str | SecretString | None = None,
        model: str | None = None,
        async_client: AsyncTypeSafeClient | None = None,
        compaction_strategy: CompactionStrategy | None = None,
        tokenizer: TokenizerProtocol | None = None,
        additional_properties: dict[str, Any] | None = None,
        env_file_path: str | None = None,
        env_file_encoding: str | None = None,
    ) -> None:
        """Create a raw TypeSafe AI chat client.

        Keyword Args:
            api_key: TypeSafe API key. Defaults to the TYPESAFE_API_KEY environment variable.
            model: Default TypeSafe model. The SDK defaults to jev-latest.
            async_client: Optional preconfigured TypeSafe SDK client. It remains caller-owned.
            compaction_strategy: Optional compaction strategy applied before requests.
            tokenizer: Optional tokenizer used by token-aware compaction strategies.
            additional_properties: Additional properties stored on the client.
            env_file_path: Path to a .env file used for settings resolution.
            env_file_encoding: Encoding used to read the .env file.
        """
        settings = load_settings(
            TypeSafeSettings,
            env_prefix="TYPESAFE_",
            required_fields=[] if async_client is not None else ["api_key"],
            api_key=api_key,
            default_model=model,
            env_file_path=env_file_path,
            env_file_encoding=env_file_encoding,
        )

        self.model = settings.get("default_model")
        self._owns_client = async_client is None

        if async_client is not None:
            self.client = async_client
        else:
            api_key_secret = cast(SecretString, settings.get("api_key"))
            self.client = AsyncTypeSafeClient(
                api_key=api_key_secret.get_secret_value(),
                model=self.model,
                headers={"User-Agent": get_user_agent()},
            )
        super().__init__(
            compaction_strategy=compaction_strategy,
            tokenizer=tokenizer,
            additional_properties=additional_properties,
        )

    async def __aenter__(self) -> Self:
        """Enter the client context."""
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Close connector-owned resources."""
        await self.close()

    async def close(self) -> None:
        """Close the internally created TypeSafe SDK client."""
        if self._owns_client:
            await self.client.aclose()

    @override
    def service_url(self) -> str:
        """Return the TypeSafe System One endpoint."""
        return _TYPESAFE_SERVICE_URL

    @override
    def _inner_get_response(
        self,
        *,
        messages: Sequence[Message],
        stream: bool,
        options: Mapping[str, Any],
        **kwargs: Any,
    ) -> Awaitable[ChatResponse[Any]] | ResponseStream[ChatResponseUpdate, ChatResponse[Any]]:
        """Evaluate messages with TypeSafe and return structured answers."""
        if stream:
            raise ChatClientInvalidRequestException("TypeSafe System One does not support streaming responses.")
        if kwargs:
            raise ChatClientInvalidRequestException(
                f"TypeSafe does not support client-specific arguments: {', '.join(sorted(kwargs))}."
            )

        async def _get_response() -> ChatResponse[Any]:
            normalized_options = await self._validate_options(options)
            self._validate_supported_options(normalized_options)

            user_questions = self._get_questions(normalized_options)
            tools = self._get_function_tools(normalized_options)
            tool_mode = validate_tool_mode(normalized_options.get("tool_choice"))
            tool_plan = compile_tool_call_plan(
                tools,
                tool_mode=tool_mode,
                user_question_ids=set(user_questions),
            )
            questions = dict(user_questions)
            if tool_plan is not None:
                questions.update(tool_plan.questions)
            model = normalized_options.get("model", self.model)
            if model is not None and not isinstance(model, str):
                raise ChatClientInvalidRequestException("TypeSafe model must be a string.")

            state = self._build_state(
                messages,
                instructions=normalized_options.get("instructions"),
            )

            try:
                response = await self.client.system_one(  # pyright: ignore[reportUnknownMemberType]
                    state=state,
                    questions=questions,
                    model=model,
                    response_model=SystemOneResponse,
                )
            except TypeSafeError as exc:
                self._raise_sdk_error(exc)
            except Exception as exc:
                raise ChatClientException(
                    f"TypeSafe request failed: {exc}",
                    inner_exception=exc,
                ) from exc

            if not isinstance(response, SystemOneResponse):
                raise ChatClientInvalidResponseException(
                    "TypeSafe returned a response that does not match SystemOneResponse."
                )

            input_tokens = response.usage.input_tokens
            output_tokens = response.usage.output_tokens
            usage_details = self._build_usage_details(input_tokens, output_tokens)

            if tool_plan is not None and (tool_call := tool_plan.decode(response)) is not None:
                function, arguments = tool_call
                return ChatResponse(
                    messages=[
                        Message(
                            role="assistant",
                            contents=[
                                Content.from_function_call(
                                    call_id=f"typesafe-{uuid4().hex}",
                                    name=function.name,
                                    arguments=arguments,
                                )
                            ],
                        )
                    ],
                    response_id=response.request_id,
                    model=response.model,
                    finish_reason="tool_calls",
                    usage_details=usage_details or None,
                )

            response = self._filter_internal_answers(response, set(user_questions))
            return ChatResponse(
                messages=[Message(role="assistant", contents=[response.model_dump_json()])],
                response_id=response.request_id,
                model=response.model,
                finish_reason="stop",
                usage_details=usage_details or None,
                value=response,
                response_format=SystemOneResponse,
                raw_representation=response,
            )

        return _get_response()

    @override
    async def _validate_options(self, options: Mapping[str, Any]) -> dict[str, Any]:
        raw_options = dict(options)
        raw_tools = raw_options.pop("tools", None)
        validated = await super()._validate_options(raw_options)
        if raw_tools is None:
            return validated
        tool_items: list[Any] = (
            list(cast(Sequence[Any], raw_tools))
            if isinstance(raw_tools, Sequence) and not isinstance(raw_tools, (str, bytes))
            else [raw_tools]
        )
        if not all(isinstance(tool, FunctionTool) for tool in tool_items):
            raise ChatClientInvalidRequestException(
                "TypeSafe raw tool routing requires FunctionTool instances. "
                "Pass MCPTool objects through Agent.run so Agent Framework can connect and expand them first."
            )
        validated["tools"] = list(tool_items)
        return validated

    @classmethod
    def _validate_supported_options(cls, options: Mapping[str, Any]) -> None:
        unsupported = sorted(
            key for key, value in options.items() if key not in cls._SUPPORTED_OPTIONS and value is not None
        )
        if unsupported:
            raise ChatClientInvalidRequestException(
                "TypeSafe does not support these chat options: "
                f"{', '.join(unsupported)}. Use response_format to define structured judgments."
            )

        if options.get("allow_multiple_tool_calls"):
            raise ChatClientInvalidRequestException("TypeSafe supports one tool call per agent run.")

    @staticmethod
    def _get_questions(options: Mapping[str, Any]) -> Questions:
        response_format = options.get("response_format")
        if not isinstance(response_format, Mapping) or not response_format:
            raise ChatClientInvalidRequestException(
                "TypeSafe response_format must be a non-empty typesafe_sdk.Questions mapping."
            )
        return cast(Questions, response_format)

    @staticmethod
    def _get_function_tools(options: Mapping[str, Any]) -> list[FunctionTool]:
        tools = options.get("tools")
        if tools is None:
            return []
        if isinstance(tools, Sequence) and not isinstance(tools, (str, bytes)):
            return [cast(FunctionTool, tool) for tool in cast(Sequence[Any], tools)]
        return [cast(FunctionTool, tools)]

    @staticmethod
    def _build_state(messages: Sequence[Message], *, instructions: Any) -> dict[str, Any]:
        if instructions is not None and not isinstance(instructions, str):
            raise ChatClientInvalidRequestException("TypeSafe instructions must be a string.")

        state_messages: list[dict[str, Any]] = []
        for index, message in enumerate(messages):
            unsupported_content_types = sorted({
                content.type
                for content in message.contents
                if content.type not in {"text", "function_call", "function_result"}
            })
            if unsupported_content_types:
                raise ChatClientInvalidRequestException(
                    f"TypeSafe only supports text and function call/result content; message {index} contains: "
                    f"{', '.join(unsupported_content_types)}."
                )

            contents: list[dict[str, Any]] = []
            for content in message.contents:
                if content.type == "text" and content.text:
                    contents.append({"type": "text", "text": content.text})
                elif content.type == "function_call":
                    contents.append({
                        "type": "function_call",
                        "call_id": content.call_id,
                        "name": content.name,
                        "arguments": content.parse_arguments(),
                    })
                elif content.type == "function_result":
                    contents.append({
                        "type": "function_result",
                        "call_id": content.call_id,
                        "result": content.result,
                    })
            if contents:
                state_messages.append({
                    "role": str(message.role),
                    "contents": contents,
                })

        if not state_messages:
            raise ChatClientInvalidRequestException("TypeSafe requires at least one non-empty text message.")

        state: dict[str, Any] = {"messages": state_messages}
        if instructions:
            state["instructions"] = instructions
        return state

    @staticmethod
    def _build_usage_details(input_tokens: int | None, output_tokens: int | None) -> UsageDetails:
        return UsageDetails(
            **({"input_token_count": input_tokens} if input_tokens is not None else {}),
            **({"output_token_count": output_tokens} if output_tokens is not None else {}),
            **(
                {"total_token_count": input_tokens + output_tokens}
                if input_tokens is not None and output_tokens is not None
                else {}
            ),
        )

    @staticmethod
    def _filter_internal_answers(response: SystemOneResponse, question_ids: set[str]) -> SystemOneResponse:
        missing = sorted(question_id for question_id in question_ids if question_id not in response.answers)
        if missing:
            raise ChatClientInvalidResponseException(
                f"TypeSafe response is missing configured answers: {', '.join(missing)}."
            )
        if set(response.answers) == question_ids:
            return response
        filtered = response.model_copy(
            update={"answers": {question_id: response.answers[question_id] for question_id in question_ids}}
        )
        filtered.__dict__.pop("_raw", None)  # pyright: ignore[reportAttributeAccessIssue, reportUnknownMemberType]
        return filtered

    @staticmethod
    def _raise_sdk_error(exc: TypeSafeError) -> NoReturn:
        if isinstance(exc, TypeSafeAPIResponseValidationError):
            raise ChatClientInvalidResponseException(
                f"TypeSafe returned an invalid response: {exc}",
                inner_exception=exc,
            ) from exc
        if isinstance(exc, (TypeSafeAuthenticationError, TypeSafePermissionDeniedError)):
            raise ChatClientInvalidAuthException(
                f"TypeSafe authentication failed: {exc}",
                inner_exception=exc,
            ) from exc
        if isinstance(exc, (TypeSafeBadRequestError, TypeSafeNotFoundError, TypeSafeUnprocessableEntityError)):
            raise ChatClientInvalidRequestException(
                f"Invalid TypeSafe request: {exc}",
                inner_exception=exc,
            ) from exc
        if isinstance(exc, (TypeSafeAPIConnectionError, TypeSafeAPIError)):
            raise ChatClientException(
                f"TypeSafe request failed: {exc}",
                inner_exception=exc,
            ) from exc
        raise ChatClientInvalidRequestException(
            f"Invalid TypeSafe request: {exc}",
            inner_exception=exc,
        ) from exc


class TypeSafeChatClient(
    FunctionInvocationLayer[TypeSafeChatOptions],
    ChatMiddlewareLayer[TypeSafeChatOptions],
    ChatTelemetryLayer[TypeSafeChatOptions],
    RawTypeSafeChatClient,
):
    """TypeSafe AI chat client with function invocation, middleware, and telemetry support.

    This is the recommended client for most uses. Use RawTypeSafeChatClient
    when composing a custom layer stack or opting out of telemetry.
    """

    def __init__(
        self,
        *,
        api_key: str | SecretString | None = None,
        model: str | None = None,
        async_client: AsyncTypeSafeClient | None = None,
        middleware: Sequence[ChatAndFunctionMiddlewareTypes] | None = None,
        function_invocation_configuration: FunctionInvocationConfiguration | None = None,
        compaction_strategy: CompactionStrategy | None = None,
        tokenizer: TokenizerProtocol | None = None,
        additional_properties: dict[str, Any] | None = None,
        env_file_path: str | None = None,
        env_file_encoding: str | None = None,
    ) -> None:
        """Create a layered TypeSafe AI chat client.

        Keyword Args:
            api_key: TypeSafe API key. Defaults to the TYPESAFE_API_KEY environment variable.
            model: Default TypeSafe model. The SDK defaults to jev-latest.
            async_client: Optional preconfigured TypeSafe SDK client. It remains caller-owned.
            middleware: Chat and function middleware to apply around requests and tool calls.
            function_invocation_configuration: Function invocation settings. TypeSafe limits
                each run to one executed tool call.
            compaction_strategy: Optional compaction strategy applied before requests.
            tokenizer: Optional tokenizer used by token-aware compaction strategies.
            additional_properties: Additional properties stored on the client.
            env_file_path: Path to a .env file used for settings resolution.
            env_file_encoding: Encoding used to read the .env file.
        """
        invocation_configuration = dict(function_invocation_configuration or {})
        invocation_configuration["max_function_calls"] = 1
        super().__init__(
            api_key=api_key,
            model=model,
            async_client=async_client,
            middleware=middleware,
            function_invocation_configuration=cast(FunctionInvocationConfiguration, invocation_configuration),
            compaction_strategy=compaction_strategy,
            tokenizer=tokenizer,
            additional_properties=additional_properties,
            env_file_path=env_file_path,
            env_file_encoding=env_file_encoding,
        )
