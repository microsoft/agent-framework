---
status: proposed
contact: eavanvalkenburg
date: 2025-11-18
deciders: markwallace-microsoft, dmytrostruk, sphenry, alliscode
consulted: taochenosu, moonbox3, giles17
---

# Python Client Constructors

## Context and Problem Statement

We have multiple Chat Client implementations that can be used with different servers, the most important example is OpenAI, where we have a separate client for OpenAI and for Azure OpenAI. The constructors for the underlying OpenAI client has now enabled both, so it might make sense to have a single Chat Client for both, the same also applies to other Chat Clients, such as Anthropic, which has a Anthropic client, but also AnthropicBedrock and AnthropicVertex, currently we don't support creating a AF AnthropicClient with those by default, but if you pass them in as a parameter, it will work. This is not the case for OpenAI, where we have a separate client for Azure OpenAI and OpenAI, the OpenAI clients still accept any OpenAI Client (or a subclass thereof) as a parameter, so it can already be used with different servers, including Azure OpenAI, but it is not the default.

We have a preference of creating clients inside of our code because then we can add a user-agent string to allow us to track usage of our clients with different services. This is most useful for Azure, but could also be a strong signal for other vendors to invest in first party support for Agent Framework. And we also make sure to not alter clients that are passed in, as that is often meant for a specific use case, such as setting up httpx clients with proxies, or other customizations that are not relevant for the Agent Framework.

There is likely not a single best solution, the goal here is consistency across clients, and with that ease of use for users of Agent Framework.

### Background on current provider setups:

| Provider | Backend | Parameter Name | Parameter Type | Env Var | Default |
|---|---|---|---|---|---|
| OpenAI | OpenAI | api_key | `str \| Callable[[], Awaitable[str]] \| None` | OPENAI_API_KEY | |
| | | organization | `str \| None` | OPENAI_ORG_ID | |
| | | project | `str \| None` | OPENAI_PROJECT_ID | |
| | | webhook_secret | `str \| None` | OPENAI_WEBHOOK_SECRET | |
| | | base_url | `str \| Url \| None` | | |
| | | websocket_base_url | `str \| Url \| None` | | |
| | | | | | |
| OpenAI | Azure | api_version | `str \| None` | OPENAI_API_VERSION | |
| | | endpoint | `str \| None` | | |
| | | deployment | `str \| None` | | |
| | | api_key | `str \| Callable[[], Awaitable[str]] \| None` | AZURE_OPENAI_API_KEY | |
| | | ad_token | `str \| None` | AZURE_OPENAI_AD_TOKEN | |
| | | ad_token_provider | `AsyncAzureADTokenProvider \| None` | | |
| | | organization | `str \| None` | OPENAI_ORG_ID | |
| | | project | `str \| None` | OPENAI_PROJECT_ID | |
| | | webhook_secret | `str \| None` | OPENAI_WEBHOOK_SECRET | |
| | | websocket_base_url | `str \| Url \| None` | | |
| | | base_url | `str \| Url \| None` | | |
| | | | | | |
| Anthropic | Anthropic | api_key | `str \| None` | ANTHROPIC_API_KEY | |
| | | auth_token | `str \| None` | ANTHROPIC_AUTH_TOKEN | |
| | | base_url | `str \| Url \| None` | ANTHROPIC_BASE_URL | |
| | | | | | |
| Anthropic | Foundry | resource | `str \| None` | ANTHROPIC_FOUNDRY_RESOURCE | |
| | | api_key | `str \| None` | ANTHROPIC_FOUNDRY_API_KEY | |
| | | ad_token_provider | `AzureADTokenProvider \| None` | | |
| | | base_url | `str \| None` | ANTHROPIC_FOUNDRY_BASE_URL | |
| | | | | | |
| Anthropic | Vertex | region | `str \| None` | CLOUD_ML_REGION | |
| | | project_id | `str \| None` | | |
| | | access_token | `str \| None` | | |
| | | credentials | `google.auth.credentials.Credentials \| None` | | |
| | | base_url | `str \| None` | ANTHROPIC_VERTEX_BASE_URL | `https://aiplatform.googleapis.com/v1` or `https://us-aiplatform.googleapis.com/v1` (based on region) |
| | | | | | |
| Anthropic | Bedrock | aws_secret_key | `str \| None` | | |
| | | aws_access_key | `str \| None` | | |
| | | aws_region | `str \| None` | | |
| | | aws_profile | `str \| None` | | |
| | | aws_session_token | `str \| None` | | |
| | | base_url | `str \| None` | ANTHROPIC_BEDROCK_BASE_URL | |


## Decision Drivers

- Reduce client sprawl and different clients that only have one or more different parameters.
- Make client creation inside our classes the default and cover as many backends as possible.
- Make clients easy to use and discover, so that users can easily find the right client for their use case.
- Allow client creation based on environment variables, so that users can easily configure their clients without having to pass in parameters.
- A breaking glass scenario should always be possible, so that users can pass in their own clients if needed, and it should also be easy to figure out how to do that.

## Considered Options

1. Separate clients for each backend, such as OpenAI and Azure OpenAI, Anthropic and AnthropicBedrock, etc.
1. Separate parameter set per backend with a single client, such as OpenAIClient with parameters, for endpoint/base_url, api_key, and entra auth.
1. Single client with a explicit parameter for the backend to use, such as OpenAIClient(backend="azure") or AnthropicClient(backend="vertex").
1. Single client with a customized `__new__` method that can create the right client based on the parameters passed in, such as OpenAIClient(api_key="...", backend="azure") which returns a AzureOpenAIClient.
1. Map clients to underlying SDK clients, OpenAI's SDK client allows both OpenAI and Azure OpenAI, so would be a single client, while Anthropic's SDK has explicit clients for Bedrock and Vertex, so would be a separate client for AnthropicBedrock and AnthropicVertex.

## Pros and Cons of the Options

### 1. Separate clients for each backend, such as OpenAI and Azure OpenAI, Anthropic and AnthropicBedrock, etc.
This option would entail potentially a large number of clients, and keeping track of additional backend implementation being created by vendors.
- Good, because it is clear which client is used
- Good, because we can easily have aliases of parameters, that are then mapped internally, such as `deployment_name` for Azure OpenAI mapping to `model_id` internally
- Good, because it is easy to map environment variables to the right client
- Good, because any customization of the behavior can be done in the subclass
- Good, because we can expose the classes in different places, currently the `AzureOpenAIClient` is exposed in the `azure` module, while the `OpenAIClient` is exposed in the `openai` module, the same could be done with Anthropic, exposed from `anthropic`, while `AnthropicBedrock` would be exposed from `agent_framework.amazon`.
- Good, stable clients per backend, as changes to one client do not affect the other clients.
- Bad, because it creates a lot of clients that are very similar (even if they subclass from one base client class)
- Bad, because it is hard to keep track of all the clients and their parameters
- Bad, because it is hard to discover the right client for a specific use case

Example code:
```python
from agent_framework.openai import OpenAIClient # using a fictional OpenAIClient, to illustrate the point
from agent_framework.azure import AzureOpenAIClient

openai_client = OpenAIClient(model_id="...", api_key="...")
azure_client = AzureOpenAIClient(api_key="...", deployment_name="...", ad_token_provider="...", credential=AzureCliCredential())
```

### 2. Separate parameter set per backend with a single client, such as OpenAIClient with parameters, for endpoint/base_url, api_key, and entra auth.
This option would entail a single client that can be used with different backends, but requires the user to pass in the right parameters.
- Good, because it reduces the number of clients and makes it easier to discover the right client with the right parameters
- Good, because it allows for a single client to be used with different backends and additional backends can be added easily
- Good, because the user does not have to worry about which client to use, they can just use the `OpenAIClient` or `AnthropicClient` and pass in the right parameters, and we create the right client for them, if that client changes, then we do that in the code, without any changes to the api.
- Good, because in many cases, the differences between the backends are just a few parameters, such as endpoint/base_url and authentication method.
- Good, because client resolution logic could be encapsulated in a factory method, making it easier to maintain and even extend by users.
- Neutral, this would be a one-time breaking change for users of the existing clients, but would make it easier to use in the long run.
- Bad, because it requires the user to know which parameters to pass in for the specific backend and when using environment variables, it is not always clear which parameters are used for which backend, or what the order of precedence is.
- Bad, because it can lead to confusion if the user passes in the wrong parameters for the specific backend
- Bad, because the name for a parameter that is similar but not the same between backends can be confusing, such as `deployment_name` for Azure OpenAI and `model_id` for OpenAI, would we then only have `model_id` for both, or have both parameters?
- Bad, because it can lead to a lot of parameters that are not used for a specific backend, such as `entra_auth` for Azure OpenAI, but not for OpenAI
- Bad, less stable per client, as changes to the parameter change all clients.
- Bad, because customized behavior per backend is harder to implement, as it requires more conditional logic in the client code.

Example code:
```python
from agent_framework.openai import OpenAIClient
openai_client = OpenAIClient(
    model_id="...",
    api_key="...",
    base_url="...",
)
azure_client = OpenAIClient(
    api_key=str | Callable[[], Awaitable[str] | str] | None = None,
    deployment_name="...",
    endpoint="...",
    # base_url="...",
    ad_token_provider=...,
)
```



### 3. Single client with a explicit parameter for the backend to use, such as OpenAIClient(backend="azure") or AnthropicClient(backend="vertex").
This option would entail a single client that can be used with different backends, but requires the user to pass in the right backend as a parameter.
- Same list as the option above, and:
- Good, because it is explicit about which backend to try and target, including for environment variables
- Bad, because adding a new backend would require a change to the client (the backend param would change from i.e. `Literal["openai", "azure"]` to `Literal["openai", "azure", "newbackend"]`)


Example code:
```python
from agent_framework.openai import OpenAIClient
openai_client = OpenAIClient(
    backend="openai", # probably optional, since this would be the default
    model_id="...",
    api_key="...",
)
azure_client = OpenAIClient(
    backend="azure",
    deployment_name="...", # could also become `model_id` to make it a bit simpler
    ad_token_provider=...,
)
```

### 4. Single client with a customized `__new__` method that can create the right client based on the parameters passed in, such as OpenAIClient(backend="azure") which returns a AzureOpenAIClient.
This option would entail a single client that can be used with different backends, and the right client is created based on the parameters passed in.
- Good, because the entry point for a user is very clear
- Good, because it allows for customization of the client based on the parameters passed in
- Bad, because it still needs all the extra client classes for the different backends
- Bad, because there might be confusion between using the subclasses or the main class with the customized `__new__` method
- Bad, because adding a new backend is still work that is required to be built

Example code:
```python
from agent_framework.openai import OpenAIClient
openai_client = OpenAIClient(
    backend="openai", # probably optional, since this would be the default
    model_id="...",
    api_key="...",
)
azure_client = OpenAIClient(
    backend="azure",
    model_id="...",
    ad_token_provider=...,
)
print(type(openai_client))  # OpenAIClient
print(type(azure_client))  # AzureOpenAIClient
```

### 5. Map clients to underlying SDK clients, OpenAI's SDK client allows both OpenAI and Azure OpenAI, so would be a single client, while Anthropic's SDK has explicit clients for Bedrock and Vertex, so would be a separate client for AnthropicBedrock and AnthropicVertex.
This option would entail a mix of the above options, depending on the underlying SDK clients.
- Good, because it aligns with the underlying SDK clients and their capabilities
- Good, because it reduces the number of clients where possible
- Bad, because it can lead to inconsistency between clients, some being separate per backend, while others are combined
- Bad, because it can lead to confusion for users if they expect a consistent approach across all clients
- Bad, because changes to the underlying SDK clients can lead to changes in our clients, which can lead to instability.

Example code:
```python
from agent_framework.anthropic import AnthropicClient, AnthropicBedrockClient
from agent_framework.openai import OpenAIClient
openai_client = OpenAIClient(
    model_id="...",
    api_key="...",
)
azure_client = OpenAIClient(
    model_id="...",
    api_key=lambda: get_azure_ad_token(...),
)
anthropic_client = AnthropicClient(
    model_id="...",
    api_key="...",
)
anthropic_bedrock_client = AnthropicBedrockClient(
    model_id="...",
    aws_secret_key="...",
    aws_access_key="...",
    base_url="...",
)
```

## Decision Outcome

We will move to a single client per provider, where the supplied backends are handled through parameters. This means that for OpenAI we will have a single `OpenAIClient` that can be used with both OpenAI and Azure OpenAI, while for Anthropic we will have a single `AnthropicClient` that can be used with Anthropic, AnthropicFoundry, AnthropicBedrock and AnthropicVertex. This allows us to always add user_agents, and give a single way of creating clients per provider, while still allowing for customization through parameters.

The following mapping will be done, between clients, parameters and environment variables:

| AF Client | Backend | Parameter | Env Var | Precedence |
|---|---|---|---|---|
| OpenAIChatClient | OpenAI | api_key | OPENAI_API_KEY | 1 |
| | | organization | OPENAI_ORG_ID | |
| | | project | OPENAI_PROJECT_ID | |
| | | base_url | OPENAI_BASE_URL | |
| | | model_id | OPENAI_CHAT_MODEL_ID | | |
| | | | | |
| OpenAIChatClient | Azure | api_key | AZURE_OPENAI_API_KEY | 2 |
| | | ad_token | AZURE_OPENAI_AD_TOKEN | 2 |
| | | ad_token_provider | | 2 |
| | | endpoint | AZURE_OPENAI_ENDPOINT | |
| | | base_url | AZURE_OPENAI_BASE_URL | |
| | | deployment_name | AZURE_OPENAI_CHAT_DEPLOYMENT_NAME | |
| | | api_version | OPENAI_API_VERSION | |
| | | | | |
| OpenAIResponsesClient | OpenAI | api_key | OPENAI_API_KEY | 1 |
| | | organization | OPENAI_ORG_ID | |
| | | project | OPENAI_PROJECT_ID | |
| | | base_url | OPENAI_BASE_URL | |
| | | model_id | OPENAI_RESPONSES_MODEL_ID | |
| | | | | |
| OpenAIResponsesClient | Azure | api_key | AZURE_OPENAI_API_KEY | 2 |
| | | ad_token | AZURE_OPENAI_AD_TOKEN | 2 |
| | | ad_token_provider | | 2 |
| | | endpoint | AZURE_OPENAI_ENDPOINT | |
| | | base_url | AZURE_OPENAI_BASE_URL | |
| | | deployment_name | AZURE_OPENAI_RESPONSES_DEPLOYMENT_NAME | |
| | | api_version | OPENAI_API_VERSION | |
| | | | | |
| OpenAIAssistantsClient | OpenAI | api_key | OPENAI_API_KEY | 1 |
| | | organization | OPENAI_ORG_ID | |
| | | project | OPENAI_PROJECT_ID | |
| | | base_url | OPENAI_BASE_URL | |
| | | model_id | OPENAI_CHAT_MODEL_ID | |
| | | | | |
| OpenAIAssistantsClient | Azure | api_key | AZURE_OPENAI_API_KEY | 2 |
| | | ad_token | AZURE_OPENAI_AD_TOKEN | 2 |
| | | ad_token_provider | | 2 |
| | | endpoint | AZURE_OPENAI_ENDPOINT | |
| | | base_url | AZURE_OPENAI_BASE_URL | |
| | | deployment_name | AZURE_OPENAI_CHAT_DEPLOYMENT_NAME | |
| | | api_version | OPENAI_API_VERSION | |
| | | | | |
| AnthropicChatClient | Anthropic | api_key | ANTHROPIC_API_KEY | 1 |
| | | base_url | ANTHROPIC_BASE_URL | |
| | | | | |
| AnthropicChatClient | Foundry | api_key | ANTHROPIC_FOUNDRY_API_KEY | 2 |
| | | ad_token_provider | | 2 |
| | | resource | ANTHROPIC_FOUNDRY_RESOURCE | |
| | | base_url | ANTHROPIC_FOUNDRY_BASE_URL | |
| | | | | |
| AnthropicChatClient | Vertex | access_token | ANTHROPIC_VERTEX_ACCESS_TOKEN | 3 |
| | | google_credentials | | 3 |
| | | region | CLOUD_ML_REGION | |
| | | project_id | ANTHROPIC_VERTEX_PROJECT_ID | |
| | | base_url | ANTHROPIC_VERTEX_BASE_URL | |
| | | | | |
| AnthropicChatClient | Bedrock | aws_access_key | ANTHROPIC_AWS_ACCESS_KEY_ID | 4 |
| | | aws_secret_key | ANTHROPIC_AWS_SECRET_ACCESS_KEY | |
| | | aws_session_token | ANTHROPIC_AWS_SESSION_TOKEN | |
| | | aws_profile | ANTHROPIC_AWS_PROFILE | 4 |
| | | aws_region | ANTHROPIC_AWS_REGION | |
| | | base_url | ANTHROPIC_BEDROCK_BASE_URL | |

The Precedence column indicates the order of precedence when multiple environment variables are set, for example if both `OPENAI_API_KEY` and `AZURE_OPENAI_API_KEY` are set, the `OPENAI_API_KEY` will be used and we assume a OpenAI Backend is wanted. If a `api_key` is passed as a parameter in that case, then we will look at the rest of the environment variables to determine the backend, so if `chat_deployment_name` is set and `chat_model_id` is not, we assume Azure OpenAI is wanted, otherwise OpenAI. As part of this change we will also remove the Pydantic Settings usage, in favor of self-built environment variable resolution, as that gives us more control over the precedence and mapping of environment variables to parameters. Including the notion of precedence between environment variables for different backends.

### Explicit Backend Selection

To handle scenarios where multiple sets of credentials are present and the user wants to override the default precedence, an optional `backend` parameter is added. This parameter has no default value and maps to an environment variable per client:

| AF Client | Env Var |
|---|---|
| OpenAIChatClient | OPENAI_CHAT_CLIENT_BACKEND |
| OpenAIResponsesClient | OPENAI_RESPONSES_CLIENT_BACKEND |
| OpenAIAssistantsClient | OPENAI_ASSISTANTS_CLIENT_BACKEND |
| AnthropicChatClient | ANTHROPIC_CHAT_CLIENT_BACKEND |

The `backend` parameter accepts the following values:

| AF Client | Backend Values |
|---|---|
| OpenAI* | `Literal["openai", "azure"]` |
| AnthropicChatClient | `Literal["anthropic", "foundry", "vertex", "bedrock"]` |

**Resolution logic:**
1. If `backend` parameter is explicitly passed, use that backend and only resolve environment variables for that backend.
2. If `backend` parameter is not passed, check the corresponding `*_BACKEND` environment variable.
3. If neither is set, fall back to the precedence rules.

**Example usage:**
```python
# User has both OPENAI_API_KEY and AZURE_OPENAI_ENDPOINT set
# Without backend param, precedence would select OpenAI

# Explicitly select Azure backend - only AZURE_* env vars are used
client = OpenAIResponsesClient(backend="azure")

# Or set via environment variable
# export OPENAI_RESPONSES_CLIENT_BACKEND=azure
client = OpenAIResponsesClient()  # Will use Azure backend
```

This approach ensures that when users have credentials for multiple backends configured (e.g., in a shared development environment), they can explicitly control which backend is used without needing to modify or unset environment variables.

Example init code:
```python

class OpenAIChatClient(BaseChatClient):
    @overload
    def __init__(
        self,
        *,
        backend: Literal["openai"],
        api_key: str | Callable[[], Awaitable[str]],
        organization: str | None = None,
        project: str | None = None,
        base_url: str | Url | None = None,
        model_id: str | None = None,
        # Common parameters
        default_headers: Mapping[str, str] | None = None,
        client: AsyncOpenAI | None = None,
        instruction_role: str | None = None,
        env_file_path: str | None = None,
        env_file_encoding: str | None = None,
        **kwargs: Any,
    ):
        """OpenAI backend."""
        ...

    @overload
    def __init__(
        self,
        *,
        backend: Literal["azure"],
        api_key: str | Callable[[], Awaitable[str]] | None = None,
        deployment_name: str | None = None,
        endpoint: str | None = None,
        ad_token: str | None = None,
        ad_token_provider: AsyncAzureADTokenProvider | None = None,
        api_version: str | None = None,
        base_url: str | Url | None = None,
        # Common parameters
        default_headers: Mapping[str, str] | None = None,
        client: AsyncOpenAI | None = None,
        instruction_role: str | None = None,
        env_file_path: str | None = None,
        env_file_encoding: str | None = None,
        **kwargs: Any,
    ):
        """Azure OpenAI backend."""
        ...

    def __init__(
        self,
        *,
        backend: Literal["openai", "azure"] | None = None,
        api_key: str | Callable[[], Awaitable[str]] | None = None,
        organization: str | None = None,
        project: str | None = None,
        base_url: str | Url | None = None,
        model_id: str | None = None,
        # Azure specific parameters
        deployment_name: str | None = None,
        endpoint: str | None = None,
        ad_token: str | None = None,
        ad_token_provider: AsyncAzureADTokenProvider | None = None,
        api_version: str | None = None,
        # Common parameters
        default_headers: Mapping[str, str] | None = None,
        client: AsyncOpenAI | None = None,
        instruction_role: str | None = None,
        env_file_path: str | None = None,
        env_file_encoding: str | None = None,
        **kwargs: Any,
    ):
        ...
```

And for Anthropic:
```python

class AnthropicChatClient(BaseChatClient):
    @overload
    def __init__(
        self,
        *,
        backend: Literal["anthropic"],
        model_id: str | None = None,
        api_key: str,
        base_url: str | Url | None = None,
        # Common parameters
        client: AsyncAnthropic | None = None,
        additional_beta_flags: list[str] | None = None,
        env_file_path: str | None = None,
        env_file_encoding: str | None = None,
        **kwargs: Any,
    ):
        """Anthropic backend."""
        ...

    @overload
    def __init__(
        self,
        *,
        backend: Literal["foundry"],
        model_id: str | None = None,
        api_key: str | None = None,
        ad_token_provider: AzureADTokenProvider | None = None,
        resource: str | None = None,
        base_url: str | Url | None = None,
        # Common parameters
        client: AsyncAnthropic | None = None,
        additional_beta_flags: list[str] | None = None,
        env_file_path: str | None = None,
        env_file_encoding: str | None = None,
        **kwargs: Any,
    ):
        """Azure AI Foundry backend."""
        ...

    @overload
    def __init__(
        self,
        *,
        backend: Literal["vertex"],
        model_id: str | None = None,
        access_token: str | None = None,
        google_credentials: google.auth.credentials.Credentials | None = None,
        region: str | None = None,
        project_id: str | None = None,
        base_url: str | Url | None = None,
        # Common parameters
        client: AsyncAnthropic | None = None,
        additional_beta_flags: list[str] | None = None,
        env_file_path: str | None = None,
        env_file_encoding: str | None = None,
        **kwargs: Any,
    ):
        """Google Vertex backend."""
        ...

    @overload
    def __init__(
        self,
        *,
        backend: Literal["bedrock"],
        model_id: str | None = None,
        aws_access_key: str | None = None,
        aws_secret_key: str | None = None,
        aws_session_token: str | None = None,
        aws_profile: str | None = None,
        aws_region: str | None = None,
        base_url: str | Url | None = None,
        # Common parameters
        client: AsyncAnthropic | None = None,
        additional_beta_flags: list[str] | None = None,
        env_file_path: str | None = None,
        env_file_encoding: str | None = None,
        **kwargs: Any,
    ):
        """AWS Bedrock backend."""
        ...

    def __init__(
        self,
        *,
        backend: Literal["anthropic", "foundry", "vertex", "bedrock"] | None = None,
        model_id: str | None = None,
        # Anthropic backend parameters
        api_key: str | None = None,
        # Azure AI Foundry backend parameters
        ad_token_provider: AzureADTokenProvider | None = None,
        resource: str | None = None,
        # Google Vertex backend parameters
        access_token: str | None = None,
        google_credentials: google.auth.credentials.Credentials | None = None,
        region: str | None = None,
        project_id: str | None = None,
        # AWS Bedrock backend parameters
        aws_access_key: str | None = None,
        aws_secret_key: str | None = None,
        aws_session_token: str | None = None,
        aws_profile: str | None = None,
        aws_region: str | None = None,
        # Common parameters
        base_url: str | Url | None = None,
        client: AsyncAnthropic | None = None,
        additional_beta_flags: list[str] | None = None,
        env_file_path: str | None = None,
        env_file_encoding: str | None = None,
        **kwargs: Any,
    ):
        ...
```
