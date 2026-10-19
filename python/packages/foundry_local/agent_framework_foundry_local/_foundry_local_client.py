# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import asyncio
import sys
from collections.abc import Awaitable, Callable, Mapping, Sequence
from threading import Event, Lock
from typing import Any, ClassVar, Generic, Literal, overload

from agent_framework import (
    ChatAndFunctionMiddlewareTypes,
    ChatMiddlewareLayer,
    ChatOptions,
    ChatResponse,
    ChatResponseUpdate,
    CompactionStrategy,
    FunctionInvocationConfiguration,
    FunctionInvocationLayer,
    Message,
    ResponseStream,
    TokenizerProtocol,
)
from agent_framework._settings import load_settings
from agent_framework.exceptions import SettingNotFoundError
from agent_framework.observability import ChatTelemetryLayer
from agent_framework_openai._chat_completion_client import RawOpenAIChatCompletionClient
from foundry_local_sdk import Configuration, DeviceType, FoundryLocalManager, IModel
from foundry_local_sdk.catalog import CatalogType
from openai import DEFAULT_TIMEOUT, AsyncOpenAI
from pydantic import BaseModel

from ._feature_usage import FeatureIndex

if sys.version_info >= (3, 13):
    from typing import TypeVar  # pragma: no cover
else:
    from typing_extensions import TypeVar  # pragma: no cover
if sys.version_info >= (3, 11):
    from typing import TypedDict  # pragma: no cover
else:
    from typing_extensions import TypedDict  # pragma: no cover


__all__ = [
    "FoundryLocalChatOptions",
    "FoundryLocalClient",
    "FoundryLocalSettings",
]

ResponseModelT = TypeVar("ResponseModelT", bound=BaseModel | None, default=None)
_MANAGER_SETUP_LOCK = Lock()


# region Foundry Local Chat Options TypedDict


class FoundryLocalChatOptions(ChatOptions[ResponseModelT], Generic[ResponseModelT], total=False):
    """Azure Foundry Local (local model deployment) chat options dict.

    Extends base ChatOptions for local model inference via Foundry Local.
    Foundry Local provides an OpenAI-compatible API, so most standard
    OpenAI chat completion options are supported.

    See: https://github.com/Azure/azure-ai-foundry-model-inference

    Keys:
        # Inherited from ChatOptions (supported via OpenAI-compatible API):
        model: The model identifier or alias (e.g., 'phi-4-mini').
        temperature: Sampling temperature (0-2).
        top_p: Nucleus sampling parameter.
        max_tokens: Maximum tokens to generate.
        stop: Stop sequences.
        tools: List of tools available to the model.
        tool_choice: How the model should use tools.
        frequency_penalty: Frequency penalty (-2.0 to 2.0).
        presence_penalty: Presence penalty (-2.0 to 2.0).
        seed: Random seed for reproducibility.

        # Options with limited support (depends on the model):
        response_format: Response format specification.
            Not all local models support JSON mode.
        logit_bias: Token bias dictionary.
            May not be supported by all models.

        # Options not supported in Foundry Local:
        user: Not used locally.
        store: Not applicable for local inference.
        # Foundry Local-specific options:
        top_k: Number of highest-probability tokens to consider; 0 disables the limit.
        do_sample: Whether to sample instead of using greedy decoding.
        early_stopping: Whether to stop beam search early.
        metadata: Native decoder settings encoded as string-valued metadata.
        extra_body: Additional request body parameters to pass to the model.
            Can be used for model-specific options not covered by standard API.

    Note:
        The actual options supported depend on the specific model being used.
        Some models (like Phi-4) may not support all OpenAI API features.
        Unsupported options may fail the request rather than being ignored.
    """

    # Foundry Local-specific options
    extra_body: dict[str, Any]
    """Additional request body parameters for model-specific options."""

    top_k: int
    """Number of highest-probability tokens to consider; 0 disables the limit."""

    do_sample: bool
    """Whether to sample instead of using greedy decoding."""

    early_stopping: bool
    """Whether to stop beam search early."""

    # ChatOptions fields not applicable for local inference
    user: None  # type: ignore[misc]
    """Not used for local model inference."""

    store: None  # type: ignore[misc]
    """Not applicable for local inference."""


FoundryLocalChatOptionsT = TypeVar(
    "FoundryLocalChatOptionsT",
    bound=TypedDict,  # type: ignore[valid-type]
    default="FoundryLocalChatOptions",
    covariant=True,
)


# endregion


class FoundryLocalSettings(TypedDict, total=False):
    """Foundry local model settings.

    Settings are resolved in this order: explicit keyword arguments, values from an
    explicitly provided .env file, then environment variables with the prefix
    'FOUNDRY_LOCAL_'.

    Keys:
        model: The name of the model deployment to use.
            (Env var FOUNDRY_LOCAL_MODEL)
    """

    model: str | None


class FoundryLocalClient(
    FunctionInvocationLayer[FoundryLocalChatOptionsT | FoundryLocalChatOptions[Any]],
    ChatMiddlewareLayer[FoundryLocalChatOptionsT],
    ChatTelemetryLayer[FoundryLocalChatOptionsT],
    RawOpenAIChatCompletionClient[FoundryLocalChatOptionsT],
    Generic[FoundryLocalChatOptionsT],
):
    """Foundry Local Chat completion class with middleware, telemetry, and function invocation support."""

    _FEATURE_USAGE_INDEX: ClassVar[int | None] = FeatureIndex.FOUNDRY_LOCAL

    @overload
    def get_response(
        self,
        messages: Sequence[Message],
        *,
        stream: Literal[False] = ...,
        options: ChatOptions[ResponseModelT] | FoundryLocalChatOptions[ResponseModelT],
        compaction_strategy: CompactionStrategy | None = None,
        tokenizer: TokenizerProtocol | None = None,
        function_invocation_kwargs: Mapping[str, Any] | None = None,
        client_kwargs: Mapping[str, Any] | None = None,
        middleware: Sequence[ChatAndFunctionMiddlewareTypes] | None = None,
    ) -> Awaitable[ChatResponse[ResponseModelT]]: ...

    @overload
    def get_response(
        self,
        messages: Sequence[Message],
        *,
        stream: Literal[False] = ...,
        options: FoundryLocalChatOptionsT | FoundryLocalChatOptions[Any] | ChatOptions[None] | None = None,
        compaction_strategy: CompactionStrategy | None = None,
        tokenizer: TokenizerProtocol | None = None,
        function_invocation_kwargs: Mapping[str, Any] | None = None,
        client_kwargs: Mapping[str, Any] | None = None,
        middleware: Sequence[ChatAndFunctionMiddlewareTypes] | None = None,
    ) -> Awaitable[ChatResponse[Any]]: ...

    @overload
    def get_response(
        self,
        messages: Sequence[Message],
        *,
        stream: Literal[True],
        options: FoundryLocalChatOptionsT | FoundryLocalChatOptions[Any] | ChatOptions[Any] | None = None,
        compaction_strategy: CompactionStrategy | None = None,
        tokenizer: TokenizerProtocol | None = None,
        function_invocation_kwargs: Mapping[str, Any] | None = None,
        client_kwargs: Mapping[str, Any] | None = None,
        middleware: Sequence[ChatAndFunctionMiddlewareTypes] | None = None,
    ) -> ResponseStream[ChatResponseUpdate, ChatResponse[Any]]: ...

    def get_response(
        self,
        messages: Sequence[Message],
        *,
        stream: bool = False,
        options: FoundryLocalChatOptionsT | FoundryLocalChatOptions[Any] | ChatOptions[Any] | None = None,
        compaction_strategy: CompactionStrategy | None = None,
        tokenizer: TokenizerProtocol | None = None,
        function_invocation_kwargs: Mapping[str, Any] | None = None,
        client_kwargs: Mapping[str, Any] | None = None,
        middleware: Sequence[ChatAndFunctionMiddlewareTypes] | None = None,
    ) -> Awaitable[ChatResponse[Any]] | ResponseStream[ChatResponseUpdate, ChatResponse[Any]]:
        """Get a response from the Foundry Local chat client with all standard layers enabled."""
        effective_client_kwargs = dict(client_kwargs) if client_kwargs is not None else {}
        if middleware is not None:
            effective_client_kwargs["middleware"] = middleware
        if stream:
            return super().get_response(
                messages=messages,
                stream=True,
                options=options,
                compaction_strategy=compaction_strategy,
                tokenizer=tokenizer,
                function_invocation_kwargs=function_invocation_kwargs,
                client_kwargs=effective_client_kwargs,
            )
        return super().get_response(
            messages=messages,
            stream=False,
            options=options,
            compaction_strategy=compaction_strategy,
            tokenizer=tokenizer,
            function_invocation_kwargs=function_invocation_kwargs,
            client_kwargs=effective_client_kwargs,
        )

    def _inner_get_response(
        self,
        *,
        messages: Sequence[Message],
        options: Mapping[str, Any],
        stream: bool = False,
        **kwargs: Any,
    ) -> Awaitable[ChatResponse] | ResponseStream[ChatResponseUpdate, ChatResponse]:
        inner_get_response = super()._inner_get_response
        if not self._prepare_model_on_request or (options.get("model") or self.model) != self._model_handle.id:
            return inner_get_response(messages=messages, options=options, stream=stream, **kwargs)

        if stream:

            async def _get_stream() -> ResponseStream[ChatResponseUpdate, ChatResponse]:
                await asyncio.to_thread(self._ensure_model_loaded)
                response = inner_get_response(messages=messages, options=options, stream=True, **kwargs)
                if not isinstance(response, ResponseStream):
                    raise TypeError("Streaming responses must return a ResponseStream.")
                return response  # type: ignore[reportUnknownVariableType]

            return ResponseStream[ChatResponseUpdate, ChatResponse].from_awaitable(_get_stream())

        async def _get_response() -> ChatResponse:
            await asyncio.to_thread(self._ensure_model_loaded)
            return await inner_get_response(messages=messages, options=options, stream=False, **kwargs)

        return _get_response()

    def _ensure_model_loaded(self) -> None:
        with _MANAGER_SETUP_LOCK:
            if not self._model_handle.is_loaded:
                self._prepare_model()

    def _prepare_model(self) -> None:
        if self._download_progress_callback is None and self._download_cancel_event is None:
            self._model_handle.download()
        else:
            self._model_handle.download(
                progress_callback=self._download_progress_callback, cancel_event=self._download_cancel_event
            )
        self._model_handle.load()

    def _prepare_options(self, messages: Sequence[Message], options: Mapping[str, Any]) -> dict[str, Any]:
        prepared = super()._prepare_options(messages, options)
        native_metadata: dict[str, str] = {}
        for key in ("top_k", "do_sample", "early_stopping"):
            value = prepared.pop(key, None)
            if value is not None:
                native_metadata[key] = str(value).lower() if isinstance(value, bool) else str(value)
        extra_body: Mapping[str, Any] | None = prepared.get("extra_body")
        if extra_body is not None and not isinstance(extra_body, Mapping):
            raise ValueError("extra_body must be a mapping.")
        metadata: Mapping[str, Any] | None = prepared.get("metadata")
        extra_metadata: Mapping[str, Any] | None = extra_body.get("metadata") if extra_body is not None else None
        for name, value in (("metadata", metadata), ("extra_body metadata", extra_metadata)):
            if value is not None and not isinstance(value, Mapping):
                raise ValueError(f"{name} must be a mapping.")
        if native_metadata or (metadata is not None and extra_metadata is not None):
            merged_metadata: dict[str, Any] = {
                **(metadata or {}),
                **(extra_metadata or {}),
                **native_metadata,
            }
            prepared["metadata"] = merged_metadata
            if extra_body is not None and "metadata" in extra_body:
                prepared["extra_body"] = {**extra_body, "metadata": merged_metadata}
        # The HTTP service uses max_tokens and a bare schema, not OpenAI's newer token key or named schema envelope.
        if "max_completion_tokens" in prepared:
            prepared["max_tokens"] = prepared.pop("max_completion_tokens")
        response_format: Mapping[str, Any] | None = prepared.get("response_format")
        if isinstance(response_format, Mapping):
            if response_format.get("type") == "json_schema":
                schema: Mapping[str, Any] | None = response_format.get("json_schema")
                if isinstance(schema, Mapping):
                    prepared["response_format"] = {
                        **response_format,
                        "json_schema": schema.get("schema", schema),
                    }
            elif response_format.get("type") not in ("json_object", "text"):
                # Older OpenAI adapters pass raw JSON schemas through unchanged.
                prepared["response_format"] = {"type": "json_schema", "json_schema": response_format}
        tool_choice: str | Mapping[str, Any] | None = prepared.get("tool_choice")
        if tool_choice == "required" or (isinstance(tool_choice, Mapping) and tool_choice.get("type") == "function"):
            # Native schema grammar overrides forced tools; retain it only for the final reply.
            prepared.pop("response_format", None)
        return prepared

    def __init__(
        self,
        model: str | None = None,
        *,
        bootstrap: bool = True,
        timeout: float | None = None,
        prepare_model: bool = True,
        catalog_type: CatalogType | Literal["public", "local"] = CatalogType.PUBLIC,
        download_progress_callback: Callable[[float], None] | None = None,
        download_cancel_event: Event | None = None,
        device: DeviceType | Literal["CPU", "GPU", "NPU"] | None = None,
        configuration: Configuration | None = None,
        additional_properties: dict[str, Any] | None = None,
        middleware: Sequence[ChatAndFunctionMiddlewareTypes] | None = None,
        function_invocation_configuration: FunctionInvocationConfiguration | None = None,
        env_file_path: str | None = None,
        env_file_encoding: str = "utf-8",
    ) -> None:
        """Initialize a FoundryLocalClient.

        Keyword Args:
            model: The Foundry Local model ID or alias to use. If not provided,
                it will be loaded from the FoundryLocalSettings.
            bootstrap: Whether to initialize the SDK singleton and start its built-in web
                service if needed. Default is True. When False, the manager and web
                service must already be running in this process.
            timeout: Optional timeout for HTTP inference requests. Uses the OpenAI
                client's default when omitted; does not apply to native model preparation.
            prepare_model: Whether to download the model into the cache, and load the model into
                the inferencing service upon initialization. Default is True.
                If False, preparation is deferred until the first inference request for the
                configured model. An already loaded variant is reused. The first request
                may take longer while downloading and loading the model.
            catalog_type: The catalog used for model lookup and HTTP inference.
                Defaults to "public". Use "local" for models already registered through
                the SDK's local catalog. Also accepts foundry_local_sdk.catalog.CatalogType.
                Per-request model overrides remain in the selected catalog.
            download_progress_callback: Optional callback receiving native download progress
                as a percentage from 0 to 100, including deferred preparation.
                Deferred callbacks run on a worker thread.
            download_cancel_event: Optional event that cancels native model download when set.
                Also applies to deferred preparation; does not cancel model loading or inference.
                Cancelling an awaiting request does not interrupt native preparation already in progress.
            device: The device type to use for model inference.
                The device is used to select the appropriate model variant.
                If not provided, the default device for your system will be used.
                Accepts "CPU", "GPU", "NPU", or foundry_local_sdk.DeviceType.
            configuration: SDK configuration used when initializing a new manager.
                Defaults to Configuration(app_name="agent-framework"). To share a manager,
                initialize it before creating clients and omit this parameter.
            additional_properties: Additional properties stored on the client instance.
            middleware: Optional sequence of ChatAndFunctionMiddlewareTypes to apply to requests.
            function_invocation_configuration: Optional configuration for function invocation support.
            env_file_path: If provided, the .env settings are read from this file path location.
            env_file_encoding: The encoding of the .env file, defaults to 'utf-8'.

        Examples:

            .. code-block:: python

                # Create a FoundryLocalClient with a specific model ID:
                from agent_framework.foundry import FoundryLocalClient

                client = FoundryLocalClient(model="phi-4-mini")

                from agent_framework import Agent

                agent = Agent(
                    client=client,
                    name="LocalAgent",
                    instructions="You are a helpful agent.",
                    tools=get_weather,
                )
                response = await agent.run("What's the weather like in Seattle?")

                # Or you can set the model id in the environment:
                os.environ["FOUNDRY_LOCAL_MODEL"] = "phi-4-mini"
                client = FoundryLocalClient()

                # The SDK singleton is shared by all clients in this process.
                # For instance to find out which models are available:
                for model in client.manager.catalog.list_models():
                    print(f"- {model.alias} for {model.info.task} - id={model.id}")

                # Other options include specifying the device type:
                from foundry_local_sdk import DeviceType

                client = FoundryLocalClient(
                    model="phi-4-mini",
                    device=DeviceType.GPU,
                )
                # and choosing if the model should be prepared on initialization:
                client = FoundryLocalClient(
                    model="phi-4-mini",
                    prepare_model=False,
                )
                # The first inference request prepares the exact resolved variant.
                # Alternatively, prepare it manually before inference:
                model = client.manager.catalog.get_model_variant(client.model)
                if model is not None:
                    model.download()
                    model.load()

                # Using native ChatOptions with type safety:
                from agent_framework import Message
                from agent_framework.foundry import FoundryLocalChatOptions

                options: FoundryLocalChatOptions[None] = {"top_k": 40, "max_tokens": 100}
                response = await client.get_response(
                    [Message(role="user", contents=["Hello"])],
                    options=options,
                )

        Raises:
            ValueError: If the model or requested device is unavailable, bootstrap is
                disabled without a running manager/service, or configuration is supplied
                for an already initialized manager.

        """
        settings = load_settings(
            FoundryLocalSettings,
            env_prefix="FOUNDRY_LOCAL_",
            required_fields=["model"],
            model=model,
            env_file_path=env_file_path,
            env_file_encoding=env_file_encoding,
        )
        model_setting = settings.get("model")
        if model_setting is None:
            raise SettingNotFoundError("Required setting 'model' was not provided.")
        device_type = DeviceType(device) if device is not None else None
        catalog_kind = (
            {"public": CatalogType.PUBLIC, "local": CatalogType.LOCAL}.get(catalog_type)
            if isinstance(catalog_type, str)
            else catalog_type
        )
        if not isinstance(catalog_kind, CatalogType):
            raise ValueError("catalog_type must be 'public', 'local', or a CatalogType.")

        with _MANAGER_SETUP_LOCK:
            manager = FoundryLocalManager.instance
            owns_manager = manager is None
            if manager is None:
                if not bootstrap:
                    raise ValueError(
                        "bootstrap=False requires an initialized Foundry Local manager and running web service."
                    )
                FoundryLocalManager.initialize(configuration or Configuration(app_name="agent-framework"))
                manager = FoundryLocalManager.instance
                if manager is None:
                    raise RuntimeError("Foundry Local manager initialization did not create a singleton.")
            elif configuration is not None:
                raise ValueError(
                    "Foundry Local is already initialized; configure the shared manager before creating clients."
                )

            initialized = False
            started_web_service = False
            try:
                if not manager.urls:
                    if not bootstrap:
                        raise ValueError("bootstrap=False requires a running Foundry Local web service.")
                    manager.start_web_service()
                    started_web_service = bool(manager.urls)
                if not manager.urls:
                    raise ValueError("Foundry Local web service did not provide a bound URL.")

                catalog = manager.catalog if catalog_kind == CatalogType.PUBLIC else manager.get_catalog(catalog_kind)
                is_variant_id = ":" in model_setting
                model_handle = (
                    catalog.get_model_variant(model_setting) if is_variant_id else catalog.get_model(model_setting)
                )
                if model_handle is not None and device_type is not None:
                    model_handle = next(
                        (
                            variant
                            for variant in ([model_handle] if is_variant_id else model_handle.variants)
                            if (runtime := variant.info.runtime) is not None and runtime.device_type == device_type
                        ),
                        None,
                    )
                elif model_handle is not None and not is_variant_id:
                    # Pin the alias's chosen variant before download changes the cached preference.
                    model_handle = catalog.get_model_variant(model_handle.id)
                if model_handle is None:
                    target = f"{model_setting}:{device_type.value}" if device_type is not None else model_setting
                    raise ValueError(f"Model with ID or alias '{target}' not found in Foundry Local.")

                model_id = model_handle.id
                self._model_handle: IModel = model_handle
                self._prepare_model_on_request = not prepare_model
                self._download_progress_callback = download_progress_callback
                self._download_cancel_event = download_cancel_event
                if prepare_model:
                    self._prepare_model()

                catalog_path = "/catalogs/local" if catalog_kind == CatalogType.LOCAL else ""
                super().__init__(
                    model=model_id,
                    async_client=AsyncOpenAI(
                        base_url=f"{manager.urls[0].rstrip('/')}{catalog_path}/v1",
                        api_key="foundry-local",
                        timeout=timeout if timeout is not None else DEFAULT_TIMEOUT,
                    ),
                    additional_properties=additional_properties,
                    middleware=middleware,
                    function_invocation_configuration=function_invocation_configuration,
                )
                self.manager = manager
                initialized = True
            finally:
                if owns_manager and not initialized:
                    manager.close()
                elif started_web_service and not initialized:
                    manager.stop_web_service()
