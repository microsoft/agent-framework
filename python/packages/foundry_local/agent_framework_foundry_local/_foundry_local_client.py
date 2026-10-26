# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import sys
import threading
from collections.abc import Awaitable, Callable, Mapping, Sequence
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
from foundry_local_sdk import Configuration, DeviceType, FoundryLocalManager, IModel
from openai import AsyncOpenAI
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

# The v2 SDK identifies the host application in native logs and telemetry.
_APP_NAME = "agent-framework"
# The built-in web service performs no authentication; the OpenAI SDK still requires a value.
_WEB_SERVICE_API_KEY = "none"

# Guards first-use initialization: without it, two threads can both observe an
# uninitialized singleton and the SDK rejects the second `initialize()` call.
_MANAGER_LOCK = threading.Lock()


def _resolve_foundry_local_manager() -> FoundryLocalManager:
    """Return the process-wide Foundry Local manager, initializing it on first use.

    The v2 SDK owns a single native manager per process and raises when a second one
    is constructed, so every client shares one manager, catalog, and web service.
    """
    manager = FoundryLocalManager.instance
    if manager is not None:
        return manager
    with _MANAGER_LOCK:
        # Re-check under the lock: another thread may have initialized while we waited.
        manager = FoundryLocalManager.instance
        if manager is None:
            FoundryLocalManager.initialize(Configuration(app_name=_APP_NAME))
            manager = FoundryLocalManager.instance
            if manager is None:  # pragma: no cover - initialize() sets the singleton
                raise RuntimeError("Foundry Local manager could not be initialized.")
    return manager


def _resolve_model(
    manager: FoundryLocalManager,
    model_setting: str,
    *,
    device: DeviceType | None = None,
) -> IModel:
    """Resolve a model alias (or a full model ID) to a catalog model.

    Args:
        manager: The Foundry Local manager owning the catalog.
        model_setting: A model alias such as ``phi-4-mini``, or a full model ID.
        device: When set, select the variant optimized for that device.

    Returns:
        The catalog model, with the requested variant selected when ``device`` is set.

    Raises:
        ValueError: If no model matches, or no variant matches ``device``.
    """
    model = manager.catalog.get_model(model_setting)
    if model is None:
        # An alias lookup misses for full model IDs; the variant lookup covers those.
        model = manager.catalog.get_model_variant(model_setting)
    not_found = (
        f"Model with ID or alias '{model_setting}:{device.value}' not found in Foundry Local."
        if device
        else (f"Model with ID or alias '{model_setting}' for your current device not found in Foundry Local.")
    )
    if model is None:
        raise ValueError(not_found)
    if device is not None:
        variant = next(
            (
                candidate
                for candidate in model.variants
                if candidate.info is not None
                and candidate.info.runtime is not None
                and candidate.info.runtime.device_type == device
            ),
            None,
        )
        if variant is None:
            raise ValueError(not_found)
        model.select_variant(variant)
    return model


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
        device: DeviceType | None = None,
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
            bootstrap: Whether to start the Foundry Local web service if it is not already
                running. Default is True. The client talks to Foundry Local over the
                web service's OpenAI-compatible endpoint, so it needs to be running.
                Pass False only when something else has already started it.
                This also downloads and registers the execution providers that
                accelerated (GPU/NPU) model variants need, unless `device` is CPU.
            timeout: Optional timeout for requests to Foundry Local.
                This timeout is applied to any call to the Foundry Local service.
            prepare_model: Whether to download the model into the cache, and load the model into
                the inferencing service upon initialization. Default is True.
                If false, the first call to generate a completion will load the model,
                and might take a long time.
            device: The device type to use for model inference.
                The device is used to select the appropriate model variant.
                If not provided, the default device for your system will be used.
                The values are in the foundry_local_sdk.DeviceType enum.
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

                agent = client.as_agent(
                    name="LocalAgent",
                    instructions="You are a helpful agent.",
                    tools=get_weather,
                )
                response = await agent.run("What's the weather like in Seattle?")

                # Or you can set the model id in the environment:
                os.environ["FOUNDRY_LOCAL_MODEL"] = "phi-4-mini"
                client = FoundryLocalClient()

                # A process-wide FoundryLocalManager is created on first use and, when
                # bootstrap is set, the web service is started.
                # The FoundryLocalManager is available via the `manager` property.
                # For instance to find out which models are available:
                for model in client.manager.catalog.list_models():
                    print(f"- {model.alias} - id={model.id}")

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
                # Alternatively, you could download and load the model yourself.
                model = client.manager.catalog.get_model("phi-4-mini")
                model.download()
                model.load()

                # You can also use the CLI:
                `foundry model load phi-4-mini --device Auto`

                # Using custom ChatOptions with type safety:
                from typing import TypedDict
                from agent_framework.foundry import FoundryLocalChatOptions

                class MyOptions(FoundryLocalChatOptions, total=False):
                    my_custom_option: str

                client: FoundryLocalClient[MyOptions] = FoundryLocalClient(model="phi-4-mini")
                response = await client.get_response("Hello", options={"my_custom_option": "value"})

        Raises:
            ValueError: If the specified model ID or alias is not found.
                Sometimes a model might be available but if you have specified a device
                type that is not supported by the model, it will not be found.

        """
        settings = load_settings(
            FoundryLocalSettings,
            env_prefix="FOUNDRY_LOCAL_",
            required_fields=["model"],
            model=model,
            env_file_path=env_file_path,
            env_file_encoding=env_file_encoding,
        )
        model_setting: str = settings["model"]  # type: ignore[assignment]

        manager = _resolve_foundry_local_manager()
        if bootstrap and device is not DeviceType.CPU:
            # A variant is only listed in the catalog once its execution provider has been
            # downloaded and registered, so on a fresh installation asking for GPU or NPU
            # (or letting the SDK auto-select) would otherwise report "not found" or
            # silently fall back to CPU. This is a no-op when the providers are registered.
            manager.download_and_register_eps()
        # The v2 SDK runs inference in-process; the optional built-in web service is what
        # exposes the OpenAI-compatible REST endpoint this client talks to.
        if bootstrap and not manager.urls:
            manager.start_web_service()
        if not manager.urls:
            raise ValueError(
                "The Foundry Local web service is not running, so there is no OpenAI-compatible endpoint to call. "
                "Pass bootstrap=True (the default) to start it, or start it on the manager first."
            )
        base_url = f"{manager.urls[0]}/v1"

        model_info = _resolve_model(manager, model_setting, device=device)
        if prepare_model:
            model_info.download()
            model_info.load()

        super().__init__(
            model=model_info.id,
            async_client=AsyncOpenAI(base_url=base_url, api_key=_WEB_SERVICE_API_KEY, timeout=timeout),
            additional_properties=additional_properties,
            middleware=middleware,
            function_invocation_configuration=function_invocation_configuration,
        )
        self.manager = manager
