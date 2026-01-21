# Copyright (c) Microsoft. All rights reserved.

import sys
from typing import Any, ClassVar, Generic

from agent_framework import ChatOptions, use_chat_middleware, use_function_invocation
from agent_framework._pydantic import AFBaseSettings
from agent_framework.exceptions import ServiceInitializationError
from agent_framework.observability import use_instrumentation
from agent_framework.openai._chat_client import OpenAIBaseChatClient
from foundry_local import FoundryLocalManager
from foundry_local.models import DeviceType
from openai import AsyncOpenAI
from pydantic import BaseModel

if sys.version_info >= (3, 13):
    from typing import TypeVar  # type: ignore # pragma: no cover
else:
    from typing_extensions import TypeVar  # type: ignore # pragma: no cover
if sys.version_info >= (3, 11):
    from typing import TypedDict  # type: ignore # pragma: no cover
else:
    from typing_extensions import TypedDict  # type: ignore # pragma: no cover

__all__ = [
    "FoundryLocalChatOptions",
    "FoundryLocalClient",
    "FoundryLocalSettings",
]

TResponseModel = TypeVar("TResponseModel", bound=BaseModel | None, default=None)


# region Foundry Local Chat Options TypedDict


class FoundryLocalChatOptions(ChatOptions[TResponseModel], Generic[TResponseModel], total=False):
    """Azure Foundry Local (local model deployment) chat options dict.

    Extends base ChatOptions for local model inference via Foundry Local.
    Foundry Local provides an OpenAI-compatible API, so most standard
    OpenAI chat completion options are supported.

    See: https://github.com/Azure/azure-ai-foundry-model-inference

    Keys:
        # Inherited from ChatOptions (supported via OpenAI-compatible API):
        model_id: The model identifier or alias (e.g., 'phi-4-mini').
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


FOUNDRY_LOCAL_OPTION_TRANSLATIONS: dict[str, str] = {
    "model_id": "model",
}
"""Maps ChatOptions keys to OpenAI API parameter names (for compatibility)."""

TFoundryLocalChatOptions = TypeVar(
    "TFoundryLocalChatOptions",
    bound=TypedDict,  # type: ignore[valid-type]
    default="FoundryLocalChatOptions",
    covariant=True,
)


# endregion


class FoundryLocalSettings(AFBaseSettings):
    """Foundry local model settings.

    The settings are first loaded from environment variables with the prefix 'FOUNDRY_LOCAL_'.
    If the environment variables are not found, the settings can be loaded from a .env file
    with the encoding 'utf-8'. If the settings are not found in the .env file, the settings
    are ignored; however, validation will fail alerting that the settings are missing.

    Attributes:
        model_id: The name of the model deployment to use.
            (Env var FOUNDRY_LOCAL_MODEL_ID)
    Parameters:
        env_file_path: If provided, the .env settings are read from this file path location.
        env_file_encoding: The encoding of the .env file, defaults to 'utf-8'.
    """

    env_prefix: ClassVar[str] = "FOUNDRY_LOCAL_"

    model_id: str


@use_function_invocation
@use_instrumentation
@use_chat_middleware
class FoundryLocalClient(OpenAIBaseChatClient[TFoundryLocalChatOptions], Generic[TFoundryLocalChatOptions]):
    """Foundry Local Chat completion class."""

    def __init__(
        self,
        model_id: str | None = None,
        *,
        bootstrap: bool = True,
        timeout: float | None = None,
        prepare_model: bool = True,
        device: DeviceType | None = None,
        env_file_path: str | None = None,
        env_file_encoding: str = "utf-8",
        **kwargs: Any,
    ) -> None:
        """Initialize a FoundryLocalClient.

        Keyword Args:
            model_id: The Foundry Local model ID or alias to use. If not provided,
                it will be loaded from the FoundryLocalSettings.
            bootstrap: Whether to start the Foundry Local service if not already running.
                Default is True.
            timeout: Optional timeout for requests to Foundry Local.
                This timeout is applied to any call to the Foundry Local service.
            prepare_model: Whether to download the model into the cache, and load the model into
                the inferencing service upon initialization. Default is True.
                If false, the first call to generate a completion will load the model,
                and might take a long time.
            device: The device type to use for model inference.
                The device is used to select the appropriate model variant.
                If not provided, the default device for your system will be used.
                The values are in the foundry_local.models.DeviceType enum.
            env_file_path: If provided, the .env settings are read from this file path location.
            env_file_encoding: The encoding of the .env file, defaults to 'utf-8'.
            kwargs: Additional keyword arguments, are passed to the OpenAIBaseChatClient.
                This can include middleware and additional properties.

        Examples:

            .. code-block:: python

                # Create a FoundryLocalClient with a specific model ID:
                from agent_framework_foundry_local import FoundryLocalClient

                client = FoundryLocalClient(model_id="phi-4-mini")

                agent = client.as_agent(
                    name="LocalAgent",
                    instructions="You are a helpful agent.",
                    tools=get_weather,
                )
                response = await agent.run("What's the weather like in Seattle?")

                # Or you can set the model id in the environment:
                os.environ["FOUNDRY_LOCAL_MODEL_ID"] = "phi-4-mini"
                client = FoundryLocalClient()

                # A FoundryLocalManager is created and if set, the service is started.
                # The FoundryLocalManager is available via the `manager` property.
                # For instance to find out which models are available:
                for model in client.manager.list_catalog_models():
                    print(f"- {model.alias} for {model.task} - id={model.id}")

                # Other options include specifying the device type:
                from foundry_local.models import DeviceType

                client = FoundryLocalClient(
                    model_id="phi-4-mini",
                    device=DeviceType.GPU,
                )
                # and choosing if the model should be prepared on initialization:
                client = FoundryLocalClient(
                    model_id="phi-4-mini",
                    prepare_model=False,
                )
                # Beware, in this case the first request to generate a completion
                # will take a long time as the model is loaded then.
                # Alternatively, you could call the `download_model` and `load_model` methods
                # on the `manager` property manually.
                client.manager.download_model(alias_or_model_id="phi-4-mini", device=DeviceType.CPU)
                client.manager.load_model(alias_or_model_id="phi-4-mini", device=DeviceType.CPU)

                # You can also use the CLI:
                `foundry model load phi-4-mini --device Auto`

                # Using custom ChatOptions with type safety:
                from typing import TypedDict
                from agent_framework_foundry_local import FoundryLocalChatOptions

                class MyOptions(FoundryLocalChatOptions, total=False):
                    my_custom_option: str

                client: FoundryLocalClient[MyOptions] = FoundryLocalClient(model_id="phi-4-mini")
                response = await client.get_response("Hello", options={"my_custom_option": "value"})

        Raises:
            ServiceInitializationError: If the specified model ID or alias is not found.
                Sometimes a model might be available but if you have specified a device
                type that is not supported by the model, it will not be found.

        """
        settings = FoundryLocalSettings(
            model_id=model_id,  # type: ignore
            env_file_path=env_file_path,
            env_file_encoding=env_file_encoding,
        )
        manager = FoundryLocalManager(bootstrap=bootstrap, timeout=timeout)
        model_info = manager.get_model_info(
            alias_or_model_id=settings.model_id,
            device=device,
        )
        if model_info is None:
            message = (
                f"Model with ID or alias '{settings.model_id}:{device.value}' not found in Foundry Local."
                if device
                else f"Model with ID or alias '{settings.model_id}' for your current device not found in Foundry Local."
            )
            raise ServiceInitializationError(message)
        if prepare_model:
            manager.download_model(alias_or_model_id=model_info.id, device=device)
            manager.load_model(alias_or_model_id=model_info.id, device=device)

        super().__init__(
            model_id=model_info.id,
            client=AsyncOpenAI(base_url=manager.endpoint, api_key=manager.api_key),
            **kwargs,
        )
        self.manager = manager
