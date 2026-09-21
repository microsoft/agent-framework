# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

from collections.abc import Awaitable, Mapping, Sequence
from types import TracebackType
from typing import Any, ClassVar, NoReturn, cast

from agent_framework import (
    BaseChatClient,
    ChatMiddlewareLayer,
    ChatMiddlewareTypes,
    ChatOptions,
    ChatResponse,
    ChatResponseUpdate,
    CompactionStrategy,
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


class TypeSafeChatClient(
    ChatMiddlewareLayer[TypeSafeChatOptions],
    ChatTelemetryLayer[TypeSafeChatOptions],
    BaseChatClient[TypeSafeChatOptions],
):
    """Agent Framework chat client for TypeSafe AI System One models.

    The client maps text messages and Agent instructions to TypeSafe structured
    state. The response_format option supplies the TypeSafe Questions mapping,
    while every response is returned as SystemOneResponse. Free-form generation,
    streaming, tools, and non-text message content are not supported.
    """

    OTEL_PROVIDER_NAME: ClassVar[str] = "typesafe.ai"
    _SUPPORTED_OPTIONS: ClassVar[frozenset[str]] = frozenset({
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
        middleware: Sequence[ChatMiddlewareTypes] | None = None,
        compaction_strategy: CompactionStrategy | None = None,
        tokenizer: TokenizerProtocol | None = None,
        additional_properties: dict[str, Any] | None = None,
        env_file_path: str | None = None,
        env_file_encoding: str | None = None,
    ) -> None:
        """Create a TypeSafe AI chat client.

        Keyword Args:
            api_key: TypeSafe API key. Defaults to the TYPESAFE_API_KEY environment variable.
            model: Default TypeSafe model. The SDK defaults to jev-latest.
            async_client: Optional preconfigured TypeSafe SDK client. It remains caller-owned.
            middleware: Chat middleware to apply around TypeSafe requests.
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
            middleware=middleware,
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

            questions = self._get_questions(normalized_options)
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
            usage_details = UsageDetails(
                **({"input_token_count": input_tokens} if input_tokens is not None else {}),
                **({"output_token_count": output_tokens} if output_tokens is not None else {}),
                **(
                    {"total_token_count": input_tokens + output_tokens}
                    if input_tokens is not None and output_tokens is not None
                    else {}
                ),
            )

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

        if options.get("tools"):
            raise ChatClientInvalidRequestException("TypeSafe System One does not support tools.")

        tool_mode = validate_tool_mode(options.get("tool_choice"))
        if tool_mode is not None and tool_mode.get("mode") not in ("auto", "none"):
            raise ChatClientInvalidRequestException("TypeSafe System One does not support required tool choice.")

    @staticmethod
    def _get_questions(options: Mapping[str, Any]) -> Questions:
        response_format = options.get("response_format")
        if not isinstance(response_format, Mapping) or not response_format:
            raise ChatClientInvalidRequestException(
                "TypeSafe response_format must be a non-empty typesafe_sdk.Questions mapping."
            )
        return cast(Questions, response_format)

    @staticmethod
    def _build_state(messages: Sequence[Message], *, instructions: Any) -> dict[str, Any]:
        if instructions is not None and not isinstance(instructions, str):
            raise ChatClientInvalidRequestException("TypeSafe instructions must be a string.")

        state_messages: list[dict[str, str]] = []
        for index, message in enumerate(messages):
            unsupported_content_types = sorted({content.type for content in message.contents if content.type != "text"})
            if unsupported_content_types:
                raise ChatClientInvalidRequestException(
                    f"TypeSafe only supports text message content; message {index} contains: "
                    f"{', '.join(unsupported_content_types)}."
                )

            if message.text:
                state_messages.append({
                    "role": str(message.role),
                    "content": message.text,
                })

        if not state_messages:
            raise ChatClientInvalidRequestException("TypeSafe requires at least one non-empty text message.")

        state: dict[str, Any] = {"messages": state_messages}
        if instructions:
            state["instructions"] = instructions
        return state

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
