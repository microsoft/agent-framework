# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import sys
from collections.abc import Awaitable, Callable, Mapping, Sequence
from threading import Lock
from typing import Any, ClassVar, Generic, Literal, cast, overload

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
from agent_framework.observability import ChatTelemetryLayer
from agent_framework_openai._chat_completion_client import RawOpenAIChatCompletionClient
from foundry_local_sdk import Configuration, DeviceType, FoundryLocalManager
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
        metadata: Not applicable for local inference.

        # Foundry Local-specific options:
        extra_body: Additional request body parameters to pass to the model.
            Can be used for model-specific options not covered by standard API.

    Note:
        The actual options supported depend on the specific model being used.
        Some models (like Phi-4) may not support all OpenAI API features.
        Options not supported by the model will typically be ignored.
    """

    # Foundry Local-specific options
    extra_body: dict[str, Any]
    """Additional request body parameters for model-specific options."""

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
    FunctionInvocationLayer[FoundryLocalChatOptionsT],
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
        options: ChatOptions[ResponseModelT],
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
        options: FoundryLocalChatOptionsT | ChatOptions[None] | None = None,
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
        options: FoundryLocalChatOptionsT | ChatOptions[Any] | None = None,
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
        options: FoundryLocalChatOptionsT | ChatOptions[Any] | None = None,
        compaction_strategy: CompactionStrategy | None = None,
        tokenizer: TokenizerProtocol | None = None,
        function_invocation_kwargs: Mapping[str, Any] | None = None,
        client_kwargs: Mapping[str, Any] | None = None,
        middleware: Sequence[ChatAndFunctionMiddlewareTypes] | None = None,
    ) -> Awaitable[ChatResponse[Any]] | ResponseStream[ChatResponseUpdate, ChatResponse[Any]]:
        """Get a response from the Foundry Local chat client with all standard layers enabled."""
        super_get_response = cast(
            "Callable[..., Awaitable[ChatResponse[Any]] | ResponseStream[ChatResponseUpdate, ChatResponse[Any]]]",
            super().get_response,
        )
        effective_client_kwargs = dict(client_kwargs) if client_kwargs is not None else {}
        if middleware is not None:
            effective_client_kwargs["middleware"] = middleware
        return super_get_response(
            messages=messages,
            stream=stream,
            options=options,
            compaction_strategy=compaction_strategy,
            tokenizer=tokenizer,
            function_invocation_kwargs=function_invocation_kwargs,
            client_kwargs=effective_client_kwargs,
        )

    def __init__(
        self,
        model: str | None = None,
        *,
        bootstrap: bool = True,
        timeout: float | None = None,
        prepare_model: bool = True,
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
                If false, the first call to generate a completion will load the model,
                and might take a long time.
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
                # Beware, in this case the first request to generate a completion
                # will take a long time as the model is loaded then.
                # Alternatively, prepare the exact resolved variant manually.
                model = client.manager.catalog.get_model_variant(client.model)
                if model is not None:
                    model.download()
                    model.load()

                # Using custom ChatOptions with type safety:
                from typing import TypedDict
                from agent_framework.foundry import FoundryLocalChatOptions


                class MyOptions(FoundryLocalChatOptions, total=False):
                    my_custom_option: str


                client: FoundryLocalClient[MyOptions] = FoundryLocalClient(model="phi-4-mini")
                response = await client.get_response("Hello", options={"my_custom_option": "value"})

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
        model_setting = cast(str, settings.get("model"))
        device_type = DeviceType(device) if device is not None else None

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
            try:
                if not manager.urls:
                    if not bootstrap:
                        raise ValueError("bootstrap=False requires a running Foundry Local web service.")
                    manager.start_web_service()
                if not manager.urls:
                    raise ValueError("Foundry Local web service did not provide a bound URL.")

                is_variant_id = ":" in model_setting
                model_handle = (
                    manager.catalog.get_model_variant(model_setting)
                    if is_variant_id
                    else manager.catalog.get_model(model_setting)
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
                    model_handle = manager.catalog.get_model_variant(model_handle.id)
                if model_handle is None:
                    target = f"{model_setting}:{device_type.value}" if device_type is not None else model_setting
                    raise ValueError(f"Model with ID or alias '{target}' not found in Foundry Local.")

                model_id = model_handle.id
                if prepare_model:
                    model_handle.download()
                    model_handle.load()

                super().__init__(
                    model=model_id,
                    async_client=AsyncOpenAI(
                        base_url=f"{manager.urls[0].rstrip('/')}/v1",
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
