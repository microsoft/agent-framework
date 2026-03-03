# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import json
import re
import sys
from collections.abc import Awaitable, Callable, Mapping, Sequence
from typing import TYPE_CHECKING, Any, Generic, Literal, cast
from urllib.parse import urljoin, urlparse

from azure.ai.projects.aio import AIProjectClient
from openai import AsyncOpenAI

from .._middleware import ChatMiddlewareLayer
from .._settings import load_settings
from .._telemetry import AGENT_FRAMEWORK_USER_AGENT
from .._tools import FunctionInvocationConfiguration, FunctionInvocationLayer
from .._types import (
    Annotation,
    ChatResponse,
    ChatResponseUpdate,
    Content,
    Message,
    ResponseStream,
    TextSpanRegion,
)
from ..observability import ChatTelemetryLayer
from ..openai._responses_client import RawOpenAIResponsesClient
from ._entra_id_authentication import AzureCredentialTypes, AzureTokenProvider
from ._shared import (
    AzureOpenAIConfigMixin,
    AzureOpenAISettings,
    _apply_azure_defaults,
    create_a2a_tool,
    create_azure_ai_search_tool,
    create_bing_tool,
    create_browser_automation_tool,
    create_code_interpreter_tool,
    create_fabric_data_agent_tool,
    create_file_search_tool,
    create_image_generation_tool,
    create_mcp_tool,
    create_openapi_tool,
    create_sharepoint_grounding_tool,
    create_web_search_tool,
)

if sys.version_info >= (3, 13):
    from typing import TypeVar  # type: ignore # pragma: no cover
else:
    from typing_extensions import TypeVar  # type: ignore # pragma: no cover
if sys.version_info >= (3, 12):
    from typing import override  # type: ignore # pragma: no cover
else:
    from typing_extensions import override  # type: ignore # pragma: no cover
if sys.version_info >= (3, 11):
    from typing import TypedDict  # type: ignore # pragma: no cover
else:
    from typing_extensions import TypedDict  # type: ignore # pragma: no cover

if TYPE_CHECKING:
    from .._middleware import MiddlewareTypes
    from ..openai._responses_client import OpenAIResponsesOptions


AzureOpenAIResponsesOptionsT = TypeVar(
    "AzureOpenAIResponsesOptionsT",
    bound=TypedDict,  # type: ignore[valid-type]
    default="OpenAIResponsesOptions",
    covariant=True,
)


class _AzureAIProjectSettings(TypedDict, total=False):
    project_endpoint: str | None
    model_deployment_name: str | None


_DOC_INDEX_PATTERN = re.compile(r"doc_(\d+)")


class RawAzureOpenAIResponsesClient(
    RawOpenAIResponsesClient[AzureOpenAIResponsesOptionsT],
    Generic[AzureOpenAIResponsesOptionsT],
):
    """Raw Azure OpenAI responses client with Foundry and Azure AI parse adaptations."""

    @staticmethod
    def _parse_foundry_tool_output(value: Any) -> Any:
        """Parse Foundry tool output payloads when represented as JSON strings."""
        if not isinstance(value, str):
            return value

        stripped = value.strip()
        if not stripped:
            return None

        try:
            return json.loads(stripped)
        except json.JSONDecodeError:
            return value

    def _parse_foundry_preview_item(self, item: Any) -> list[Content]:
        """Parse Foundry preview tool output items into function call/result content."""
        item_type = getattr(item, "type", None)
        if not isinstance(item_type, str):
            return []

        if item_type.endswith("_preview_call"):
            call_id = getattr(item, "call_id", None) or getattr(item, "id", None)
            if not call_id:
                return []

            tool_name = item_type.removesuffix("_call")
            additional_properties: dict[str, Any] = {
                "tool_type": item_type,
                "tool_name": tool_name,
                "item_id": getattr(item, "id", None),
                "status": getattr(item, "status", None),
            }
            arguments = getattr(item, "arguments", None)
            return [
                Content.from_function_call(
                    call_id=call_id,
                    name=tool_name,
                    arguments=arguments if arguments is not None else "",
                    additional_properties={
                        k: v for k, v in additional_properties.items() if v is not None
                    },
                    raw_representation=item,
                )
            ]

        if item_type.endswith("_preview_call_output"):
            call_id = getattr(item, "call_id", None) or getattr(item, "id", None)
            if not call_id:
                return []

            tool_name = item_type.removesuffix("_call_output")
            output: Any = getattr(item, "output", None)
            if output is None:
                output = getattr(item, "result", None)
            if output is None:
                output = getattr(item, "outputs", None)

            additional_properties = {
                "tool_type": item_type,
                "tool_name": tool_name,
                "item_id": getattr(item, "id", None),
                "status": getattr(item, "status", None),
            }
            return [
                Content.from_function_result(
                    call_id=call_id,
                    result=self._parse_foundry_tool_output(output),
                    additional_properties={
                        k: v for k, v in additional_properties.items() if v is not None
                    },
                    raw_representation=item,
                )
            ]

        return []

    @override
    def _parse_response_from_openai(
        self, response: Any, options: dict[str, Any]
    ) -> ChatResponse:
        parsed_response = super()._parse_response_from_openai(
            response=response, options=options
        )

        foundry_contents: list[Content] = []
        for item in getattr(response, "output", []) or []:
            foundry_contents.extend(self._parse_foundry_preview_item(item))

        if not foundry_contents:
            return parsed_response

        if parsed_response.messages:
            existing_contents = list(parsed_response.messages[0].contents or [])
            parsed_response.messages[0].contents = [
                *foundry_contents,
                *existing_contents,
            ]
        else:
            parsed_response.messages = [
                Message(role="assistant", contents=foundry_contents)
            ]

        return parsed_response

    @override
    def _parse_chunk_from_openai(
        self,
        event: Any,
        options: dict[str, Any],
        function_call_ids: dict[int, tuple[str, str]],
    ) -> ChatResponseUpdate:
        update = super()._parse_chunk_from_openai(
            event=event,
            options=options,
            function_call_ids=function_call_ids,
        )
        if getattr(event, "type", None) != "response.output_item.done":
            return update

        foundry_contents = self._parse_foundry_preview_item(
            getattr(event, "item", None)
        )
        if foundry_contents:
            update.contents = [*list(update.contents or []), *foundry_contents]
        return update

    def _extract_azure_search_urls(self, output_items: Any) -> list[str]:
        """Extract document URLs from azure_ai_search_call_output items."""
        get_urls: list[str] = []
        for item in output_items:
            if item.type != "azure_ai_search_call_output":
                continue
            output = item.output
            if isinstance(output, str):
                try:
                    output = json.loads(output)
                except (json.JSONDecodeError, TypeError):
                    continue
            if isinstance(output, list):
                continue
            if output is not None:
                urls = (
                    output.get("get_urls")
                    if isinstance(output, dict)
                    else output.get_urls
                )
                if urls and isinstance(urls, list):
                    get_urls.extend(urls)
        return get_urls

    def _get_search_doc_url(
        self, citation_title: str | None, get_urls: list[str]
    ) -> str | None:
        """Map a citation title like ``doc_0`` to its corresponding get_url."""
        if not citation_title or not get_urls:
            return None
        match = _DOC_INDEX_PATTERN.search(citation_title)
        if not match:
            return None
        doc_index = int(match.group(1))
        if 0 <= doc_index < len(get_urls):
            return str(get_urls[doc_index])
        return None

    def _enrich_annotations_with_search_urls(
        self, contents: list[Content], get_urls: list[str]
    ) -> None:
        """Enrich citation annotations in contents with real document URLs from Azure AI Search."""
        if not get_urls:
            return
        for content in contents:
            if not content.annotations:
                continue
            for annotation in content.annotations:
                if not isinstance(annotation, dict):
                    continue
                if annotation.get("type") != "citation":
                    continue
                title = annotation.get("title")
                doc_url = self._get_search_doc_url(title, get_urls)
                if doc_url:
                    annotation.setdefault("additional_properties", {})["get_url"] = (
                        doc_url
                    )

    def _build_url_citation_content(
        self,
        annotation_data: dict[str, Any],
        get_urls: list[str],
        raw_event: Any,
    ) -> Content:
        """Build a citation ``Content`` from a ``url_citation`` streaming annotation event."""
        ann_title = str(annotation_data.get("title") or "")
        ann_url = str(annotation_data.get("url") or "")
        ann_start = annotation_data.get("start_index")
        ann_end = annotation_data.get("end_index")

        additional_props: dict[str, Any] = {
            "annotation_index": getattr(raw_event, "annotation_index", None),
        }
        doc_url = self._get_search_doc_url(ann_title, get_urls)
        if doc_url:
            additional_props["get_url"] = doc_url

        annotation_obj = Annotation(
            type="citation",
            title=ann_title,
            url=ann_url,
            additional_properties={
                k: v for k, v in additional_props.items() if v is not None
            },
            raw_representation=annotation_data,
        )
        if ann_start is not None and ann_end is not None:
            annotation_obj["annotated_regions"] = [
                TextSpanRegion(
                    type="text_span", start_index=ann_start, end_index=ann_end
                )
            ]

        return Content.from_text(
            text="", annotations=[annotation_obj], raw_representation=raw_event
        )

    @override
    def _inner_get_response(
        self,
        *,
        messages: Sequence[Message],
        options: Mapping[str, Any],
        stream: bool = False,
        **kwargs: Any,
    ) -> Awaitable[ChatResponse] | ResponseStream[ChatResponseUpdate, ChatResponse]:
        """Wrap base response to enrich Azure AI Search citation annotations."""
        if not stream:

            async def _enrich_response() -> ChatResponse:
                response = await super(
                    RawAzureOpenAIResponsesClient, self
                )._inner_get_response(
                    messages=messages, options=options, stream=False, **kwargs
                )
                parsed_response = cast("ChatResponse", response)
                raw_output = getattr(parsed_response.raw_representation, "output", None)
                if raw_output:
                    get_urls = self._extract_azure_search_urls(raw_output)
                    if get_urls:
                        for msg in parsed_response.messages:
                            self._enrich_annotations_with_search_urls(
                                list(msg.contents or []), get_urls
                            )
                return parsed_response

            return _enrich_response()

        stream_result = super()._inner_get_response(  # type: ignore[assignment]
            messages=messages, options=options, stream=True, **kwargs
        )
        search_get_urls: list[str] = []

        def _enrich_update(update: ChatResponseUpdate) -> ChatResponseUpdate:
            raw = update.raw_representation
            if raw is None:
                return update
            event_type = raw.type

            if event_type in (
                "response.output_item.added",
                "response.output_item.done",
            ):
                urls = self._extract_azure_search_urls([raw.item])
                if urls:
                    search_get_urls.extend(urls)

            if event_type == "response.output_text.annotation.added":
                ann = raw.annotation
                if isinstance(ann, dict) and ann.get("type") == "url_citation":
                    citation_content = self._build_url_citation_content(
                        ann, search_get_urls, raw
                    )
                    update.contents = [*list(update.contents or []), citation_content]

            if update.contents and search_get_urls:
                self._enrich_annotations_with_search_urls(
                    list(update.contents), search_get_urls
                )

            return update

        stream_result.with_transform_hook(_enrich_update)  # type: ignore[union-attr]
        return stream_result


class AzureOpenAIResponsesClient(  # type: ignore[misc]
    AzureOpenAIConfigMixin,
    ChatMiddlewareLayer[AzureOpenAIResponsesOptionsT],
    FunctionInvocationLayer[AzureOpenAIResponsesOptionsT],
    ChatTelemetryLayer[AzureOpenAIResponsesOptionsT],
    RawAzureOpenAIResponsesClient[AzureOpenAIResponsesOptionsT],
    Generic[AzureOpenAIResponsesOptionsT],
):
    """Azure Responses completion class with middleware, telemetry, and function invocation support."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        deployment_name: str | None = None,
        endpoint: str | None = None,
        base_url: str | None = None,
        api_version: str | None = None,
        token_endpoint: str | None = None,
        credential: AzureCredentialTypes | AzureTokenProvider | None = None,
        default_headers: Mapping[str, str] | None = None,
        async_client: AsyncOpenAI | None = None,
        project_client: Any | None = None,
        project_endpoint: str | None = None,
        backend: Literal["azure_openai", "foundry"] | None = None,
        env_file_path: str | None = None,
        env_file_encoding: str | None = None,
        instruction_role: str | None = None,
        middleware: Sequence[MiddlewareTypes] | None = None,
        function_invocation_configuration: FunctionInvocationConfiguration
        | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize an Azure OpenAI Responses client.

        The client can be created in two ways:

        1. **Direct Azure OpenAI** (default): Provide endpoint, api_key, or credential
           to connect directly to an Azure OpenAI deployment.
        2. **Foundry project endpoint**: Provide a ``project_client`` or ``project_endpoint``
           (with ``credential``) to create the client via an Azure AI Foundry project.
           This requires the ``azure-ai-projects`` package to be installed.

        Keyword Args:
            api_key: The API key. If provided, will override the value in the env vars or .env file.
                Can also be set via environment variable AZURE_OPENAI_API_KEY.
            deployment_name: The deployment name. If provided, will override the value
                (responses_deployment_name) in the env vars or .env file.
                Can also be set via environment variable AZURE_OPENAI_RESPONSES_DEPLOYMENT_NAME.
                In project mode, AZURE_AI_MODEL_DEPLOYMENT_NAME is also used as a fallback.
            endpoint: The deployment endpoint. If provided will override the value
                in the env vars or .env file.
                Can also be set via environment variable AZURE_OPENAI_ENDPOINT.
            base_url: The deployment base URL. If provided will override the value
                in the env vars or .env file. Currently, the base_url must end with "/openai/v1/".
                Can also be set via environment variable AZURE_OPENAI_BASE_URL.
            api_version: The deployment API version. If provided will override the value
                in the env vars or .env file. Currently, the api_version must be "preview".
                Can also be set via environment variable AZURE_OPENAI_API_VERSION.
            token_endpoint: The token endpoint to request an Azure token.
                Can also be set via environment variable AZURE_OPENAI_TOKEN_ENDPOINT.
            credential: Azure credential or token provider for authentication. Accepts a
                ``TokenCredential``, ``AsyncTokenCredential``, or a callable that returns a
                bearer token string (sync or async), for example from
                ``azure.identity.get_bearer_token_provider()``.
            default_headers: The default headers mapping of string keys to
                string values for HTTP requests.
            async_client: An existing client to use.
            project_client: An existing ``AIProjectClient`` (from ``azure.ai.projects.aio``) to use.
                The OpenAI client will be obtained via ``project_client.get_openai_client()``.
                Requires the ``azure-ai-projects`` package.
            project_endpoint: The Azure AI Foundry project endpoint URL.
                When provided with ``credential``, an ``AIProjectClient`` will be created
                and used to obtain the OpenAI client. Requires the ``azure-ai-projects`` package.
            backend: Backend mode for settings resolution.
                Use ``"foundry"`` to load only ``AZURE_AI_*`` settings
                (for example, ``AZURE_AI_PROJECT_ENDPOINT`` and ``AZURE_AI_MODEL_DEPLOYMENT_NAME``).
                Use ``"azure_openai"`` to load ``AZURE_OPENAI_*`` settings.
                When ``project_client`` or ``project_endpoint`` is provided, Foundry mode is inferred.
            env_file_path: Use the environment settings file as a fallback to using env vars.
            env_file_encoding: The encoding of the environment settings file, defaults to 'utf-8'.
            instruction_role: The role to use for 'instruction' messages, for example, summarization
                prompts could use `developer` or `system`.
            middleware: Optional sequence of middleware to apply to requests.
            function_invocation_configuration: Optional configuration for function invocation behavior.
            kwargs: Additional keyword arguments.

        Examples:
            .. code-block:: python

                from agent_framework.azure import AzureOpenAIResponsesClient

                # Using environment variables
                # Set AZURE_OPENAI_ENDPOINT=https://your-endpoint.openai.azure.com
                # Set AZURE_OPENAI_RESPONSES_DEPLOYMENT_NAME=gpt-4o
                # Set AZURE_OPENAI_API_KEY=your-key
                client = AzureOpenAIResponsesClient()

                # Or passing parameters directly
                client = AzureOpenAIResponsesClient(
                    endpoint="https://your-endpoint.openai.azure.com", deployment_name="gpt-4o", api_key="your-key"
                )

                # Or loading from a .env file
                client = AzureOpenAIResponsesClient(env_file_path="path/to/.env")

                # Using a Foundry project endpoint
                from azure.identity import DefaultAzureCredential

                client = AzureOpenAIResponsesClient(
                    project_endpoint="https://your-project.services.ai.azure.com",
                    deployment_name="gpt-4o",
                    credential=DefaultAzureCredential(),
                )

                # Or using an existing AIProjectClient
                from azure.ai.projects.aio import AIProjectClient

                project_client = AIProjectClient(
                    endpoint="https://your-project.services.ai.azure.com",
                    credential=DefaultAzureCredential(),
                )
                client = AzureOpenAIResponsesClient(
                    project_client=project_client,
                    deployment_name="gpt-4o",
                )

                # Using custom ChatOptions with type safety:
                from typing import TypedDict
                from agent_framework.azure import AzureOpenAIResponsesOptions


                class MyOptions(AzureOpenAIResponsesOptions, total=False):
                    my_custom_option: str


                client: AzureOpenAIResponsesClient[MyOptions] = AzureOpenAIResponsesClient()
                response = await client.get_response("Hello", options={"my_custom_option": "value"})
        """
        if (model_id := kwargs.pop("model_id", None)) and not deployment_name:
            deployment_name = str(model_id)

        is_foundry_backend = (
            backend == "foundry"
            or project_client is not None
            or project_endpoint is not None
        )
        resolved_project_endpoint = project_endpoint
        azure_openai_settings: AzureOpenAISettings
        if is_foundry_backend:
            azure_ai_project_settings = load_settings(
                _AzureAIProjectSettings,
                env_prefix="AZURE_AI_",
                project_endpoint=project_endpoint,
                model_deployment_name=deployment_name,
                env_file_path=env_file_path,
                env_file_encoding=env_file_encoding,
            )
            resolved_project_endpoint = azure_ai_project_settings.get(
                "project_endpoint"
            )
            azure_openai_settings = {
                "api_key": None,
                "base_url": base_url,
                "endpoint": endpoint,
                "responses_deployment_name": azure_ai_project_settings.get(
                    "model_deployment_name"
                ),
                "api_version": api_version,
                "token_endpoint": token_endpoint,
            }
        else:
            azure_openai_settings = load_settings(
                AzureOpenAISettings,
                env_prefix="AZURE_OPENAI_",
                api_key=api_key,
                base_url=base_url,
                endpoint=endpoint,
                responses_deployment_name=deployment_name,
                api_version=api_version,
                env_file_path=env_file_path,
                env_file_encoding=env_file_encoding,
                token_endpoint=token_endpoint,
            )


        # Project client path: create OpenAI client from an Azure AI Foundry project
        if async_client is None and is_foundry_backend:
            async_client = self._create_client_from_project(
                project_client=project_client,
                project_endpoint=resolved_project_endpoint,
                credential=credential,
            )

        _apply_azure_defaults(azure_openai_settings, default_api_version="preview")
        # TODO(peterychang): This is a temporary hack to ensure that the base_url is set correctly
        # while this feature is in preview.
        # But we should only do this if we're on azure. Private deployments may not need this.
        if (
            not azure_openai_settings.get("base_url")
            and azure_openai_settings.get("endpoint")
            and (hostname := urlparse(str(azure_openai_settings["endpoint"])).hostname)
            and hostname.endswith(".openai.azure.com")
        ):
            azure_openai_settings["base_url"] = urljoin(str(azure_openai_settings["endpoint"]), "/openai/v1/")

        resolved_deployment_name = azure_openai_settings.get("responses_deployment_name")
        if not resolved_deployment_name:
            if is_foundry_backend:
                raise ValueError(
                    "Azure OpenAI deployment name is required. Set via 'deployment_name' parameter "
                    "or 'AZURE_AI_MODEL_DEPLOYMENT_NAME' environment variable."
                )
            raise ValueError(
                "Azure OpenAI deployment name is required. Set via 'deployment_name' parameter "
                "or 'AZURE_OPENAI_RESPONSES_DEPLOYMENT_NAME' environment variable."
            )

        super().__init__(
            deployment_name=resolved_deployment_name,
            endpoint=azure_openai_settings["endpoint"],
            base_url=azure_openai_settings["base_url"],
            api_version=azure_openai_settings["api_version"],  # type: ignore
            api_key=azure_openai_settings["api_key"].get_secret_value() if azure_openai_settings["api_key"] else None,
            token_endpoint=azure_openai_settings["token_endpoint"],
            credential=credential,
            default_headers=default_headers,
            client=async_client,
            instruction_role=instruction_role,
            middleware=middleware,
            function_invocation_configuration=function_invocation_configuration,
        )
        if is_foundry_backend:
            self._attach_project_tool_methods()

    def _attach_project_tool_methods(self) -> None:
        """Attach project-mode hosted tool methods dynamically."""
        tool_methods: dict[str, Callable[..., Any]] = {
            "get_code_interpreter_tool": create_code_interpreter_tool,
            "get_file_search_tool": create_file_search_tool,
            "get_web_search_tool": create_web_search_tool,
            "get_bing_tool": create_bing_tool,
            "get_image_generation_tool": create_image_generation_tool,
            "get_mcp_tool": create_mcp_tool,
            "get_fabric_data_agent_tool": create_fabric_data_agent_tool,
            "get_sharepoint_grounding_tool": create_sharepoint_grounding_tool,
            "get_azure_ai_search_tool": create_azure_ai_search_tool,
            "get_browser_automation_tool": create_browser_automation_tool,
            "get_openapi_tool": create_openapi_tool,
            "get_a2a_tool": create_a2a_tool,
        }
        for method_name, method in tool_methods.items():
            setattr(self, method_name, method)

    @staticmethod
    def _create_client_from_project(
        *,
        project_client: AIProjectClient | None,
        project_endpoint: str | None,
        credential: AzureCredentialTypes | AzureTokenProvider | None,
    ) -> AsyncOpenAI:
        """Create an AsyncOpenAI client from an Azure AI Foundry project.

        Args:
            project_client: An existing AIProjectClient to use.
            project_endpoint: The Azure AI Foundry project endpoint URL.
            credential: Azure credential for authentication.

        Returns:
            An AsyncAzureOpenAI client obtained from the project client.

        Raises:
            ValueError: If required parameters are missing or
                the azure-ai-projects package is not installed.
        """
        if project_client is not None:
            return project_client.get_openai_client()

        if not project_endpoint:
            raise ValueError("Azure AI project endpoint is required when project_client is not provided.")
        if not credential:
            raise ValueError("Azure credential is required when using project_endpoint without a project_client.")
        project_client = AIProjectClient(
            endpoint=project_endpoint,
            credential=credential,  # type: ignore[arg-type]
            user_agent=AGENT_FRAMEWORK_USER_AGENT,
        )
        return project_client.get_openai_client()

    @override
    def _check_model_presence(self, options: dict[str, Any]) -> None:
        if not options.get("model"):
            if not self.model_id:
                raise ValueError("deployment_name must be a non-empty string")
            options["model"] = self.model_id
