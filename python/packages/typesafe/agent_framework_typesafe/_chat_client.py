# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import json
from collections.abc import Awaitable, Mapping, Sequence
from types import TracebackType
from typing import Any, ClassVar, Literal, NoReturn, cast, overload
from uuid import uuid4

import httpx2
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
    JudgeVerdict,
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
    ChoiceAnswer,
    Noul,
    Questions,
    ScoreAnswer,
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

_TYPESAFE_DEFAULT_BASE_URL = "https://api.typesafe.ai"
_TYPESAFE_SYSTEM_ONE_PATH = "/v1/systemone"
_JUDGE_QUESTION_ID = "__af_judge__.answered"
_JUDGE_ANSWERED_THRESHOLD = 0.5


class _ApiKeyTransport(httpx2.AsyncBaseTransport):
    """Restore the API key after the TypeSafe SDK prepares its redacted wire headers."""

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key
        self._transport = httpx2.AsyncHTTPTransport()

    @override
    async def handle_async_request(self, request: httpx2.Request) -> httpx2.Response:
        request.headers["Authorization"] = self._api_key
        return await self._transport.handle_async_request(request)

    @override
    async def aclose(self) -> None:
        await self._transport.aclose()


class TypeSafeSettings(TypedDict, total=False):
    """TypeSafe settings resolved from explicit values, .env files, or the environment."""

    api_key: SecretString | None
    default_model: str | None
    base_url: str | None


class TypeSafeChatOptions(ChatOptions[SystemOneResponse], total=False):
    """TypeSafe-specific chat options.

    Keys:
        response_format: TypeSafe Questions mapping. The connector forwards it as
            the TypeSafe questions parameter and returns SystemOneResponse. It may
            be omitted when the client was created with default_questions.
        model: Optional TypeSafe model override.
        instructions: Optional Agent instructions included in the structured state.
    """

    pass


class RawTypeSafeChatClient(BaseChatClient[TypeSafeChatOptions]):
    """Raw Agent Framework chat client for TypeSafe AI System One models.

    The client maps text messages and Agent instructions to TypeSafe structured
    state. The response_format option supplies the TypeSafe Questions mapping,
    while every response is returned as SystemOneResponse. The raw client can
    emit constrained function calls but does not execute them; TypeSafeChatClient
    adds the function-invocation layer. Free-form generation, streaming, and
    non-text message content are not supported.

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
        base_url: str | None = None,
        async_client: AsyncTypeSafeClient | None = None,
        default_questions: Questions | None = None,
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
            base_url: Optional TypeSafe API root. Defaults to TYPESAFE_BASE_URL
                or https://api.typesafe.ai for connector-owned SDK clients.
            async_client: Optional preconfigured TypeSafe SDK client. It remains caller-owned.
            default_questions: Questions used when a request omits response_format.
                This is useful for framework integrations that invoke a chat client
                with a fixed task contract, such as SecureAgentConfig quarantine calls.
            compaction_strategy: Optional compaction strategy applied before requests.
            tokenizer: Optional tokenizer used by token-aware compaction strategies.
            additional_properties: Additional properties stored on the client.
            env_file_path: Path to a .env file used for settings resolution.
            env_file_encoding: Encoding used to read the .env file.
        """
        self._owns_client = async_client is None
        self.default_questions = (
            self._validate_questions_mapping(default_questions, setting_name="default_questions")
            if default_questions is not None
            else None
        )

        if async_client is not None:
            self.client = async_client
            self.model = model
            self.base_url = None
            self._service_url = "Unknown"
        else:
            settings = load_settings(
                TypeSafeSettings,
                env_prefix="TYPESAFE_",
                required_fields=["api_key"],
                api_key=api_key,
                default_model=model,
                base_url=base_url,
                env_file_path=env_file_path,
                env_file_encoding=env_file_encoding,
            )
            self.model = settings.get("default_model")
            self.base_url = settings.get("base_url") or _TYPESAFE_DEFAULT_BASE_URL
            self._service_url = f"{self.base_url.rstrip('/')}{_TYPESAFE_SYSTEM_ONE_PATH}"
            api_key_secret = cast(SecretString, settings.get("api_key"))
            api_key_value = api_key_secret.get_secret_value()
            self.client = AsyncTypeSafeClient(
                api_key=api_key_value,
                model=self.model,
                base_url=self.base_url,
                headers={"User-Agent": get_user_agent()},
                transport=_ApiKeyTransport(api_key_value),
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
        return self._service_url

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
        unexpected_kwargs = set(kwargs) - {"tool_choice"}
        if unexpected_kwargs:
            raise ChatClientInvalidRequestException(
                f"TypeSafe does not support client-specific arguments: {', '.join(sorted(unexpected_kwargs))}."
            )
        request_options = dict(options)
        if "tool_choice" in kwargs:
            request_options.setdefault("tool_choice", kwargs["tool_choice"])

        async def _get_response() -> ChatResponse[Any]:
            normalized_options = await self._validate_options(request_options)
            self._validate_supported_options(normalized_options)

            model = normalized_options.get("model", self.model)
            if model is not None and not isinstance(model, str):
                raise ChatClientInvalidRequestException("TypeSafe model must be a string.")

            response_format = normalized_options.get("response_format")
            is_judge_request = response_format is JudgeVerdict
            user_questions = (
                cast(
                    Questions,
                    {
                        _JUDGE_QUESTION_ID: Noul(
                            instructions=("Has the agent fully addressed the original request and all stated criteria?")
                        )
                    },
                )
                if is_judge_request
                else self._get_questions(normalized_options)
            )
            tools = self._get_function_tools(normalized_options)
            tool_mode = validate_tool_mode(normalized_options.get("tool_choice"))
            tool_plan = compile_tool_call_plan(
                tools,
                tool_mode=tool_mode,
                user_question_ids=set(user_questions),
                previous_calls=self._get_current_turn_function_calls(messages),
            )
            questions = dict(user_questions)
            if tool_plan is not None:
                questions.update(tool_plan.questions)

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

            if is_judge_request:
                return self._build_judge_response(response, usage_details)

            response = self._filter_internal_answers(response, set(user_questions))
            terminal_text = self._build_terminal_text(messages, response)
            return ChatResponse(
                messages=[Message(role="assistant", contents=[terminal_text])],
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

    def _get_questions(self, options: Mapping[str, Any]) -> Questions:
        response_format = options.get("response_format")
        if response_format is None and self.default_questions is not None:
            return self.default_questions
        return self._validate_questions_mapping(response_format, setting_name="response_format")

    @staticmethod
    def _validate_questions_mapping(value: Any, *, setting_name: str) -> Questions:
        if not isinstance(value, Mapping) or not value:
            raise ChatClientInvalidRequestException(
                f"TypeSafe {setting_name} must be a non-empty typesafe_sdk.Questions mapping."
            )
        question_ids: list[Any] = list(cast(Mapping[Any, Any], value))
        invalid_question_ids = [question_id for question_id in question_ids if not isinstance(question_id, str)]
        if invalid_question_ids:
            raise ChatClientInvalidRequestException(f"TypeSafe {setting_name} question IDs must be strings.")
        return cast(Questions, value)

    @staticmethod
    def _get_function_tools(options: Mapping[str, Any]) -> list[FunctionTool]:
        tools = options.get("tools")
        if tools is None:
            return []
        if isinstance(tools, Sequence) and not isinstance(tools, (str, bytes)):
            return [cast(FunctionTool, tool) for tool in cast(Sequence[Any], tools)]
        return [cast(FunctionTool, tools)]

    @staticmethod
    def _get_current_turn_function_calls(messages: Sequence[Message]) -> dict[str, list[dict[str, Any]]]:
        calls: dict[str, list[dict[str, Any]]] = {}
        for message in reversed(messages):
            if message.role == "user":
                break
            for content in reversed(message.contents):
                if content.type == "function_call" and content.name:
                    calls.setdefault(content.name, []).append(content.parse_arguments() or {})
        for function_calls in calls.values():
            function_calls.reverse()
        return calls

    @staticmethod
    def _build_state(messages: Sequence[Message], *, instructions: Any) -> dict[str, Any]:
        if instructions is not None and not isinstance(instructions, str):
            raise ChatClientInvalidRequestException("TypeSafe instructions must be a string.")

        state_messages: list[dict[str, Any]] = []
        for index, message in enumerate(messages):
            unsupported_content_types = sorted({
                content.type
                for content in message.contents
                if content.type not in {"text", "text_reasoning", "function_call", "function_result"}
            })
            if unsupported_content_types:
                raise ChatClientInvalidRequestException(
                    f"TypeSafe only supports text, reasoning summaries, and function call/result content; "
                    f"message {index} contains: "
                    f"{', '.join(unsupported_content_types)}."
                )

            contents: list[dict[str, Any]] = []
            for content in message.contents:
                if content.type == "text" and content.text:
                    contents.append({"type": "text", "text": content.text})
                elif content.type == "text_reasoning" and content.text:
                    contents.append({"type": "text_reasoning", "text": content.text})
                elif content.type == "function_call":
                    contents.append({
                        "type": "function_call",
                        "call_id": content.call_id,
                        "name": content.name,
                        "arguments": content.parse_arguments(),
                    })
                elif content.type == "function_result":
                    contents.append(RawTypeSafeChatClient._serialize_function_result(content))
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
    def _serialize_function_result(content: Content) -> dict[str, Any]:
        items: list[dict[str, str]] = []
        for item in content.items or ():
            if item.type != "text":
                raise ChatClientInvalidRequestException(
                    f"TypeSafe function results support text items only; received unsupported {item.type!r} content."
                )
            items.append({"type": "text", "text": item.text or ""})
        return {
            "type": "function_result",
            "call_id": content.call_id,
            "result": content.result,
            **({"items": items} if items else {}),
        }

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
    def _build_judge_response(response: SystemOneResponse, usage_details: UsageDetails) -> ChatResponse[JudgeVerdict]:
        answer = response.nouls.get(_JUDGE_QUESTION_ID)
        if answer is None:
            raise ChatClientInvalidResponseException("TypeSafe response is missing the AgentLoop judge verdict.")
        verdict = JudgeVerdict(
            answered=answer.noul > _JUDGE_ANSWERED_THRESHOLD,
            reasoning=f"Jev P(answered)={answer.noul:.3f}",
        )
        return ChatResponse(
            messages=[Message(role="assistant", contents=[verdict.model_dump_json()])],
            response_id=response.request_id,
            model=response.model,
            finish_reason="stop",
            usage_details=usage_details or None,
            value=verdict,
            response_format=JudgeVerdict,
            raw_representation=response,
        )

    @staticmethod
    def _build_terminal_text(messages: Sequence[Message], response: SystemOneResponse) -> str:
        tool_results = RawTypeSafeChatClient._get_current_turn_function_result_texts(messages)
        if not tool_results:
            return response.model_dump_json()

        decision_lines = [
            f"{question_id}: {answer.choice}"
            if isinstance(answer, ChoiceAnswer)
            else f"{question_id}: {answer.score:g}"
            for question_id, answer in response.answers.items()
            if isinstance(answer, (ChoiceAnswer, ScoreAnswer))
        ]
        return "\n".join([*tool_results, *decision_lines])

    @staticmethod
    def _get_current_turn_function_result_texts(messages: Sequence[Message]) -> list[str]:
        results: list[str] = []
        for message in reversed(messages):
            if message.role == "user":
                break
            for content in reversed(message.contents):
                if content.type == "function_result" and isinstance(content.result, str):
                    results.append(RawTypeSafeChatClient._unwrap_function_result_text(content.result))
        results.reverse()
        return results

    @staticmethod
    def _unwrap_function_result_text(result: str) -> str:
        try:
            decoded: Any = json.loads(result)
        except json.JSONDecodeError:
            return result
        if isinstance(decoded, dict):
            decoded_result = cast(dict[str, Any], decoded)
            if set(decoded_result) == {"result"} and isinstance(decoded_result["result"], str):
                return decoded_result["result"]
        return result

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

    @overload
    def get_response(
        self,
        messages: Sequence[Message],
        *,
        stream: Literal[False] = ...,
        options: TypeSafeChatOptions | ChatOptions[Any] | None = None,
        middleware: Sequence[ChatAndFunctionMiddlewareTypes] | None = None,
        compaction_strategy: CompactionStrategy | None = None,
        tokenizer: TokenizerProtocol | None = None,
        function_invocation_kwargs: Mapping[str, Any] | None = None,
        client_kwargs: Mapping[str, Any] | None = None,
    ) -> Awaitable[ChatResponse[Any]]: ...

    @overload
    def get_response(
        self,
        messages: Sequence[Message],
        *,
        stream: Literal[True],
        options: TypeSafeChatOptions | ChatOptions[Any] | None = None,
        middleware: Sequence[ChatAndFunctionMiddlewareTypes] | None = None,
        compaction_strategy: CompactionStrategy | None = None,
        tokenizer: TokenizerProtocol | None = None,
        function_invocation_kwargs: Mapping[str, Any] | None = None,
        client_kwargs: Mapping[str, Any] | None = None,
    ) -> ResponseStream[ChatResponseUpdate, ChatResponse[Any]]: ...

    @override
    def get_response(
        self,
        messages: Sequence[Message],
        *,
        stream: bool = False,
        options: TypeSafeChatOptions | ChatOptions[Any] | None = None,
        middleware: Sequence[ChatAndFunctionMiddlewareTypes] | None = None,
        compaction_strategy: CompactionStrategy | None = None,
        tokenizer: TokenizerProtocol | None = None,
        function_invocation_kwargs: Mapping[str, Any] | None = None,
        client_kwargs: Mapping[str, Any] | None = None,
    ) -> Awaitable[ChatResponse[Any]] | ResponseStream[ChatResponseUpdate, ChatResponse[Any]]:
        """Reject streaming before the function-invocation layer can execute tools."""
        if stream:

            async def _reject_streaming() -> ResponseStream[ChatResponseUpdate, ChatResponse[Any]]:  # ruff: ignore[unused-async]
                raise ChatClientInvalidRequestException("TypeSafe System One does not support streaming responses.")

            return ResponseStream.from_awaitable(  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
                _reject_streaming()
            )

        return super().get_response(
            messages,
            stream=False,
            options=options,
            middleware=middleware,
            compaction_strategy=compaction_strategy,
            tokenizer=tokenizer,
            function_invocation_kwargs=function_invocation_kwargs,
            client_kwargs=client_kwargs,
        )

    def __init__(
        self,
        *,
        api_key: str | SecretString | None = None,
        model: str | None = None,
        base_url: str | None = None,
        async_client: AsyncTypeSafeClient | None = None,
        default_questions: Questions | None = None,
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
            base_url: Optional TypeSafe API root for connector-owned SDK clients.
            async_client: Optional preconfigured TypeSafe SDK client. It remains caller-owned.
            default_questions: Questions used when a request omits response_format.
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
        invocation_configuration.setdefault("max_function_calls", 1)
        super().__init__(
            api_key=api_key,
            model=model,
            base_url=base_url,
            async_client=async_client,
            default_questions=default_questions,
            middleware=middleware,
            function_invocation_configuration=cast(FunctionInvocationConfiguration, invocation_configuration),
            compaction_strategy=compaction_strategy,
            tokenizer=tokenizer,
            additional_properties=additional_properties,
            env_file_path=env_file_path,
            env_file_encoding=env_file_encoding,
        )
