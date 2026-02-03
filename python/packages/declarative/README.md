# Microsoft Agent Framework - Declarative YAML Schema

Complete YAML schema documentation for defining agents declaratively in Microsoft Agent Framework.

**Based on official source code:**
- [`_models.py`](https://github.com/microsoft/agent-framework/blob/main/python/packages/declarative/agent_framework_declarative/_models.py) - Pydantic models
- [`_loader.py`](https://github.com/microsoft/agent-framework/blob/main/python/packages/declarative/agent_framework_declarative/_loader.py) - AgentFactory and provider mappings

---

## Get Started with Microsoft Agent Framework Declarative

Please install this package via pip:

```bash
pip install agent-framework-declarative --pre
```

---

## 📑 Table of Contents

- [Main Structure](#main-structure)
- [PromptAgent Definition](#promptagent-definition)
  - [Main Fields](#main-fields)
  - [Example](#example)
- [Model Section](#model-section)
  - [Complete Structure](#complete-structure)
  - [Supported Providers](#supported-providers)
  - [Example with Provider](#example-with-provider)
- [Connection Types](#connection-types)
  - [1. RemoteConnection](#1-remoteconnection)
  - [2. ApiKeyConnection](#2-apikeyconnection)
  - [3. ReferenceConnection](#3-referenceconnection)
  - [4. AnonymousConnection](#4-anonymousconnection)
- [ModelOptions](#modeloptions)
  - [Complete Structure](#complete-structure-1)
  - [Example](#example-1)
- [Tools Section](#tools-section)
  - [1. FunctionTool](#1-functiontool)
  - [2. WebSearchTool](#2-websearchtool)
  - [3. FileSearchTool](#3-filesearchtool)
  - [4. CodeInterpreterTool](#4-codeinterpretertool)
  - [5. McpTool (Model Context Protocol)](#5-mcptool-model-context-protocol)
  - [6. OpenApiTool](#6-openapitool)
  - [7. CustomTool](#7-customtool)
- [Input/Output Schemas](#inputoutput-schemas)
  - [PropertySchema](#propertyschema)
  - [Property Types](#property-types)
  - [Complete Example](#complete-example)
- [PowerFx Expressions](#powerfx-expressions)
  - [Syntax](#syntax)
  - [Environment Variables](#environment-variables)
  - [Supported PowerFx Functions](#supported-powerfx-functions)
- [Complete Examples](#complete-examples)
  - [Example 1: Simple Agent with Azure OpenAI](#example-1-simple-agent-with-azure-openai)
  - [Example 2: Agent with Azure AI Client](#example-2-agent-with-azure-ai-client)
  - [Example 3: Agent with MCP Tool](#example-3-agent-with-mcp-tool)
  - [Example 4: Agent with Multiple Tools](#example-4-agent-with-multiple-tools)
  - [Example 5: Agent with Input/Output Schema](#example-5-agent-with-inputoutput-schema)
- [Python Usage](#python-usage)
  - [Create Agent from YAML](#create-agent-from-yaml)
  - [With Bindings (Python Functions)](#with-bindings-python-functions)
  - [With Connections](#with-connections)
  - [AgentFactory Parameters](#agentfactory-parameters)
- [Validation and Errors](#validation-and-errors)
  - [Common Errors](#common-errors)
  - [Required Fields](#required-fields)
- [References](#references)

---

## Main Structure

Every YAML file must start with a `kind` field that defines the agent type:

```yaml
kind: Prompt  # or "Agent" - both create a PromptAgent
```

[↑ Back to top](#-table-of-contents)

---

## PromptAgent Definition

### Main Fields

```yaml
kind: Prompt                    # REQUIRED: "Prompt" or "Agent"
name: string                    # REQUIRED: Agent name
description: string             # OPTIONAL: Agent description
instructions: string            # OPTIONAL: System instructions (system prompt)
additionalInstructions: string  # OPTIONAL: Additional instructions
model: Model                    # OPTIONAL: Model configuration
tools: list[Tool]               # OPTIONAL: List of tools
template: Template              # OPTIONAL: Template configuration
outputSchema: PropertySchema    # OPTIONAL: Output schema
```

### Example

```yaml
kind: Prompt
name: MyAssistant
description: A helpful AI assistant
instructions: You are a helpful assistant that answers questions concisely.
model:
  id: gpt-4
  connection:
    kind: remote
    endpoint: https://myendpoint.com
```

[↑ Back to top](#-table-of-contents)

---

## Model Section

Defines the LLM model to use and how to connect to it.

### Complete Structure

```yaml
model:
  id: string                    # REQUIRED: Model ID/deployment name
  provider: string              # OPTIONAL: Provider (default: "AzureAIClient")
  apiType: string               # OPTIONAL: API type
  connection: Connection        # OPTIONAL: Connection configuration
  options: ModelOptions         # OPTIONAL: Model options
```

### Supported Providers

The loader looks up providers in `PROVIDER_TYPE_OBJECT_MAPPING` ([source](https://github.com/microsoft/agent-framework/blob/main/python/packages/declarative/agent_framework_declarative/_loader.py)):

| Provider | Package | Class | Model ID Field |
|----------|---------|-------|----------------|
| `AzureOpenAI.Chat` | `agent_framework.azure` | `AzureOpenAIChatClient` | `deployment_name` |
| `AzureOpenAI.Assistants` | `agent_framework.azure` | `AzureOpenAIAssistantsClient` | `deployment_name` |
| `AzureOpenAI.Responses` | `agent_framework.azure` | `AzureOpenAIResponsesClient` | `deployment_name` |
| `OpenAI.Chat` | `agent_framework.openai` | `OpenAIChatClient` | `model_id` |
| `OpenAI.Assistants` | `agent_framework.openai` | `OpenAIAssistantsClient` | `model_id` |
| `OpenAI.Responses` | `agent_framework.openai` | `OpenAIResponsesClient` | `model_id` |
| `AzureAIAgentClient` | `agent_framework.azure` | `AzureAIAgentClient` | `model_deployment_name` |
| `AzureAIClient` | `agent_framework.azure` | `AzureAIClient` | `model_deployment_name` |
| `AzureAI.ProjectProvider` | `agent_framework.azure` | `AzureAIProjectAgentProvider` | `model` |
| `Anthropic.Chat` | `agent_framework.anthropic` | `AnthropicChatClient` | `model_id` |

> **Default:** If `provider` is not specified, uses `"AzureAIClient"`.

### Example with Provider

```yaml
model:
  id: gpt-4
  provider: AzureOpenAI.Chat
  connection:
    kind: remote
    endpoint: https://myresource.openai.azure.com
```

[↑ Back to top](#-table-of-contents)

---

## Connection Types

Defines how to authenticate and connect to the model service.

### 1. RemoteConnection

Connection to a remote endpoint (most common with Azure AI).

```yaml
connection:
  kind: remote                  # REQUIRED
  endpoint: string              # OPTIONAL: Endpoint URL
  name: string                  # OPTIONAL: Connection name
  authenticationMode: string    # OPTIONAL
  usageDescription: string      # OPTIONAL
```

**Example:**
```yaml
model:
  id: gpt-4.1
  connection:
    kind: remote
    endpoint: =Env.AZURE_PROJECT_ENDPOINT
```

[↑ Back to Connections](#connection-types)

### 2. ApiKeyConnection

Connection with API Key.

```yaml
connection:
  kind: key                     # REQUIRED
  apiKey: string                # OPTIONAL (or use 'key')
  key: string                   # OPTIONAL: Alternative to 'apiKey' (takes precedence)
  endpoint: string              # OPTIONAL
  authenticationMode: string    # OPTIONAL
  usageDescription: string      # OPTIONAL
```

> **Note:** If both `apiKey` and `key` are provided, `key` takes precedence.

**Example:**
```yaml
model:
  id: gpt-4
  provider: OpenAI.Chat
  connection:
    kind: key
    apiKey: =Env.OPENAI_API_KEY
    endpoint: https://api.openai.com/v1
```

[↑ Back to Connections](#connection-types)

### 3. ReferenceConnection

Reference to an externally defined connection.

```yaml
connection:
  kind: reference               # REQUIRED
  name: string                  # OPTIONAL: Connection name
  target: string                # OPTIONAL
  authenticationMode: string    # OPTIONAL
  usageDescription: string      # OPTIONAL
```

**Usage in Python:**
```python
factory = AgentFactory(
    connections={"my_connection": credential_object}
)
```

**Example:**
```yaml
model:
  id: gpt-4
  connection:
    kind: reference
    name: my_azure_connection
```

[↑ Back to Connections](#connection-types)

### 4. AnonymousConnection

Anonymous connection without authentication.

```yaml
connection:
  kind: anonymous               # REQUIRED
  endpoint: string              # OPTIONAL
  authenticationMode: string    # OPTIONAL
  usageDescription: string      # OPTIONAL
```

**Example:**
```yaml
model:
  id: llama-2
  connection:
    kind: anonymous
    endpoint: https://public-llm-api.com/v1
```

[↑ Back to Connections](#connection-types) | [↑ Back to top](#-table-of-contents)

---

## ModelOptions

LLM model configuration options.

### Complete Structure

```yaml
model:
  options:
    temperature: float                # OPTIONAL: 0.0 to 2.0
    topP: float                       # OPTIONAL: 0.0 to 1.0
    maxTokens: int                    # OPTIONAL: Maximum output tokens
    # Additional options supported by the model
```

### Example

```yaml
model:
  id: gpt-4
  options:
    temperature: 0.7
    maxTokens: 2000
    topP: 0.95
```

[↑ Back to top](#-table-of-contents)

---

## Tools Section

List of tools available to the agent.

**Available Tool Types:**
1. [FunctionTool](#1-functiontool) - Custom functions
2. [WebSearchTool](#2-websearchtool) - Web search
3. [FileSearchTool](#3-filesearchtool) - File/vector search
4. [CodeInterpreterTool](#4-codeinterpretertool) - Code interpreter
5. [McpTool](#5-mcptool-model-context-protocol) - Model Context Protocol
6. [OpenApiTool](#6-openapitool) - OpenAPI-based APIs
7. [CustomTool](#7-customtool) - Custom tools

### 1. FunctionTool

Defines a function that the agent can call.

```yaml
tools:
  - kind: function              # REQUIRED
    name: string                # OPTIONAL
    description: string         # OPTIONAL
    parameters: PropertySchema  # OPTIONAL: Parameter schema
    strict: bool                # OPTIONAL: Strict mode (default: false)
    bindings: list[Binding]     # OPTIONAL: Bindings to Python functions
```

**Example:**
```yaml
tools:
  - kind: function
    name: get_weather
    description: Get current weather for a location
    parameters:
      properties:
        - name: location
          kind: string
          description: City name
          required: true
        - name: units
          kind: string
          description: Temperature units
          enum: [celsius, fahrenheit]
          default: celsius
    bindings:
      - name: get_weather_func
        input: location
```

**Usage with bindings in Python:**
```python
def my_weather_function(location: str, units: str = "celsius") -> str:
    return f"Weather in {location}: 25°{units[0].upper()}"

factory = AgentFactory(
    bindings={"get_weather_func": my_weather_function}
)
```

[↑ Back to Tools](#tools-section)

### 2. WebSearchTool

Hosted web search tool.

```yaml
tools:
  - kind: web_search            # REQUIRED
    name: string                # OPTIONAL
    description: string         # OPTIONAL
    connection: Connection      # OPTIONAL
    options: dict               # OPTIONAL: Additional properties
```

**Example:**
```yaml
tools:
  - kind: web_search
    description: Search the web for current information
```

[↑ Back to Tools](#tools-section)

### 3. FileSearchTool

Search in stored vectors/files.

```yaml
tools:
  - kind: file_search           # REQUIRED
    name: string                # OPTIONAL
    description: string         # OPTIONAL
    connection: Connection      # OPTIONAL
    vectorStoreIds: list[string] # OPTIONAL: Vector store IDs
    maximumResultCount: int     # OPTIONAL: Maximum results
    ranker: string              # OPTIONAL: Ranker type
    scoreThreshold: float       # OPTIONAL: Score threshold
    filters: dict               # OPTIONAL: Search filters
```

**Example:**
```yaml
tools:
  - kind: file_search
    description: Search company documentation
    vectorStoreIds:
      - vs_abc123
      - vs_def456
    maximumResultCount: 10
    scoreThreshold: 0.75
    ranker: semantic
```

[↑ Back to Tools](#tools-section)

### 4. CodeInterpreterTool

Hosted Python code interpreter.

```yaml
tools:
  - kind: code_interpreter      # REQUIRED
    name: string                # OPTIONAL
    description: string         # OPTIONAL
    fileIds: list[string]       # OPTIONAL: Available file IDs
```

**Example:**
```yaml
tools:
  - kind: code_interpreter
    description: Execute Python code to analyze data
    fileIds:
      - file_abc123
      - file_def456
```

[↑ Back to Tools](#tools-section)

### 5. McpTool (Model Context Protocol)

MCP server for external tools.

```yaml
tools:
  - kind: mcp                   # REQUIRED
    name: string                # OPTIONAL
    description: string         # OPTIONAL
    connection: Connection      # OPTIONAL
    serverName: string          # OPTIONAL
    serverDescription: string   # OPTIONAL
    url: string                 # OPTIONAL: MCP server URL
    approvalMode: ApprovalMode  # OPTIONAL: Approval mode
    allowedTools: list[string]  # OPTIONAL: List of allowed tools
```

#### ApprovalMode Types

**Always Require Approval:**
```yaml
approvalMode:
  kind: always
```

**Never Require Approval:**
```yaml
approvalMode:
  kind: never
```

**Specify Per Tool:**
```yaml
approvalMode:
  kind: specify
  alwaysRequireApprovalTools:   # Tools that ALWAYS require approval
    - delete_records
    - truncate_table
  neverRequireApprovalTools:    # Tools that NEVER require approval
    - select_query
    - count_records
```

**Example 1: Microsoft Learn MCP**
```yaml
tools:
  - kind: mcp
    name: microsoft_learn
    description: Search Microsoft Learn documentation
    url: https://learn.microsoft.com/api/mcp
    approvalMode:
      kind: never
    allowedTools:
      - microsoft_docs_search
      - microsoft_docs_fetch
      - microsoft_code_sample_search
```

**Example 2: Selective Approval**
```yaml
tools:
  - kind: mcp
    name: database_tools
    description: Database operations
    url: https://myserver.com/mcp
    approvalMode:
      kind: specify
      alwaysRequireApprovalTools:
        - delete_records
        - truncate_table
      neverRequireApprovalTools:
        - select_query
        - count_records
```

[↑ Back to Tools](#tools-section)

### 6. OpenApiTool

Tool based on OpenAPI specification.

```yaml
tools:
  - kind: openapi               # REQUIRED
    name: string                # OPTIONAL
    description: string         # OPTIONAL
    specification: string       # OPTIONAL: URL or path to OpenAPI spec
    connection: Connection      # OPTIONAL: Connection configuration
```

**Example:**
```yaml
tools:
  - kind: openapi
    name: petstore_api
    description: Interact with the Pet Store API
    specification: https://petstore.swagger.io/v2/swagger.json
    connection:
      kind: key
      apiKey: =Env.PETSTORE_API_KEY
      endpoint: https://petstore.swagger.io/v2
```

[↑ Back to Tools](#tools-section)

### 7. CustomTool

Custom tool with free configuration.

```yaml
tools:
  - kind: custom                # REQUIRED
    name: string                # OPTIONAL
    description: string         # OPTIONAL
    connection: Connection      # OPTIONAL
    options: dict               # OPTIONAL: Custom configuration
```

**Example:**
```yaml
tools:
  - kind: custom
    name: my_special_tool
    description: Custom integration with internal system
    connection:
      kind: reference
      name: internal_api
    options:
      timeout: 30
      retry_count: 3
      custom_header: special-value
```

[↑ Back to Tools](#tools-section) | [↑ Back to top](#-table-of-contents)

---

## Input/Output Schemas

Define the structure of agent input and output.

### PropertySchema

```yaml
outputSchema:  # or use in tool parameters
  strict: bool                  # OPTIONAL: Strict mode (default: false)
  examples: list[dict]          # OPTIONAL: Example values
  properties:
    - name: string              # OPTIONAL
      kind: string              # OPTIONAL: field type
      description: string       # OPTIONAL
      required: bool            # OPTIONAL
      default: any              # OPTIONAL
      example: any              # OPTIONAL
      enum: list[any]           # OPTIONAL: allowed values
```

### Property Types

#### 1. Simple Property

**Supported kinds:** `string`, `number`, `boolean`

```yaml
- name: user_name
  kind: string
  description: Name of the user
  required: true
```

#### 2. ArrayProperty

```yaml
- name: tags
  kind: array
  description: List of tags
  items:
    name: tag
    kind: string
```

#### 3. ObjectProperty

```yaml
- name: address
  kind: object
  description: User address
  properties:
    - name: street
      kind: string
    - name: city
      kind: string
    - name: zip
      kind: string
```

### Complete Example

```yaml
outputSchema:
  properties:
    - name: results
      kind: array
      description: Search results
      items:
        kind: object
        properties:
          - name: title
            kind: string
          - name: url
            kind: string
          - name: snippet
            kind: string
    - name: total_count
      kind: number
```

[↑ Back to top](#-table-of-contents)

---

## PowerFx Expressions

Any string in YAML can use PowerFx expressions prefixed with `=`.

### Syntax

```yaml
field: =PowerFxExpression
```

### Environment Variables

Access environment variables with `Env.VARIABLE_NAME`:

```yaml
model:
  id: =Env.MODEL_DEPLOYMENT_NAME
  connection:
    kind: remote
    endpoint: =Env.AZURE_ENDPOINT
```

### Supported PowerFx Functions

- `Concatenate()`: Concatenate strings
- Arithmetic operators: `+`, `-`, `*`, `/`
- Logical operators: `And()`, `Or()`, `Not()`
- And more according to [PowerFx specification](https://learn.microsoft.com/en-us/power-platform/power-fx/overview)

**Example:**
```yaml
model:
  id: =Concatenate("gpt-", Env.MODEL_VERSION)
  connection:
    kind: remote
    endpoint: =Concatenate("https://", Env.REGION, ".openai.azure.com")
```

> **Note:** PowerFx evaluation requires Python ≤ 3.13 and the `powerfx` package. If not available, expressions are returned as literal strings.

[↑ Back to top](#-table-of-contents)

---

## Complete Examples

### Example 1: Simple Agent with Azure OpenAI

```yaml
kind: Prompt
name: SimpleAssistant
description: A simple AI assistant
instructions: You are a helpful assistant that answers questions concisely.

model:
  id: gpt-4
  provider: AzureOpenAI.Chat
  connection:
    kind: remote
    endpoint: https://myresource.openai.azure.com
  options:
    temperature: 0.7
    maxTokens: 1000
```

[↑ Back to Examples](#complete-examples)

### Example 2: Agent with Azure AI Client

```yaml
kind: Prompt
name: AzureAIAgent
description: Agent using Azure AI Foundry
instructions: You are an expert assistant.

model:
  id: =Env.AZURE_MODEL_ID
  provider: AzureAIClient
  connection:
    kind: remote
    endpoint: =Env.AZURE_PROJECT_ENDPOINT
  options:
    temperature: 0.8
    maxTokens: 2000
```

[↑ Back to Examples](#complete-examples)

### Example 3: Agent with MCP Tool

```yaml
kind: Prompt
name: MicrosoftLearnAgent
description: Search and retrieve Microsoft Learn documentation
instructions: You answer questions by searching the Microsoft Learn content only.

model:
  id: =Env.AZURE_MODEL_ID
  connection:
    kind: remote
    endpoint: =Env.AZURE_PROJECT_ENDPOINT

tools:
  - kind: mcp
    name: microsoft_learn
    description: Get information from Microsoft Learn
    url: https://learn.microsoft.com/api/mcp
    approvalMode:
      kind: never
    allowedTools:
      - microsoft_docs_search
      - microsoft_docs_fetch
      - microsoft_code_sample_search
```

[↑ Back to Examples](#complete-examples)

### Example 4: Agent with Multiple Tools

```yaml
kind: Prompt
name: MultiToolAgent
description: Agent with multiple capabilities
instructions: You can search the web, analyze code, and call custom functions.

model:
  id: gpt-4
  provider: AzureOpenAI.Chat
  connection:
    kind: key
    apiKey: =Env.AZURE_OPENAI_KEY
    endpoint: =Env.AZURE_OPENAI_ENDPOINT
  options:
    temperature: 0.5

tools:
  - kind: web_search
    description: Search the web for current information

  - kind: code_interpreter
    description: Execute Python code for analysis

  - kind: function
    name: calculate_discount
    description: Calculate discount price
    parameters:
      properties:
        - name: price
          kind: number
          description: Original price
          required: true
        - name: discount_percent
          kind: number
          description: Discount percentage
          required: true
    bindings:
      - name: discount_calculator
```

[↑ Back to Examples](#complete-examples)

### Example 5: Agent with Input/Output Schema

```yaml
kind: Prompt
name: StructuredAgent
description: Agent with structured output
instructions: Process user requests and return structured data.

model:
  id: gpt-4-turbo
  provider: OpenAI.Chat
  connection:
    kind: key
    apiKey: =Env.OPENAI_API_KEY

outputSchema:
  properties:
    - name: result
      kind: string
      description: Processed result
    - name: confidence
      kind: number
      description: Confidence score 0-1
    - name: metadata
      kind: object
      properties:
        - name: processing_time
          kind: number
        - name: word_count
          kind: number
```

[↑ Back to Examples](#complete-examples) | [↑ Back to top](#-table-of-contents)

---

## Python Usage

### Create Agent from YAML

```python
from agent_framework_declarative import AgentFactory
from azure.identity.aio import DefaultAzureCredential
from pathlib import Path
import asyncio
import os

async def main():
    from dotenv import load_dotenv
    load_dotenv()
    
    yaml_path = Path(__file__).parent / "agent.yaml"
    project_endpoint = os.getenv("AZURE_PROJECT_ENDPOINT")
    credential = DefaultAzureCredential()
    
    factory = AgentFactory(
        client_kwargs={
            "async_credential": credential,
            "project_endpoint": project_endpoint
        }
    )
    
    agent = factory.create_agent_from_yaml_path(yaml_path)
    
    async with agent:
        response = await agent.run("Your question here")
        print(response.text)

if __name__ == "__main__":
    asyncio.run(main())
```

[↑ Back to Python Usage](#python-usage)

### With Bindings (Python Functions)

```python
def calculate_discount(price: float, discount_percent: float) -> float:
    """Calculate discounted price."""
    return price * (1 - discount_percent / 100)

def get_weather(location: str) -> str:
    """Get weather for location."""
    return f"Weather in {location}: Sunny, 25°C"

factory = AgentFactory(
    bindings={
        "discount_calculator": calculate_discount,
        "weather_func": get_weather
    },
    client_kwargs={
        "async_credential": credential,
        "project_endpoint": project_endpoint
    }
)

agent = factory.create_agent_from_yaml_path("agent.yaml")
```

[↑ Back to Python Usage](#python-usage)

### With Connections

```python
from azure.identity import DefaultAzureCredential

my_credential = DefaultAzureCredential()

factory = AgentFactory(
    connections={
        "azure_connection": my_credential,
        "custom_api": {"api_key": "secret123"}
    }
)
```

[↑ Back to Python Usage](#python-usage)

### AgentFactory Parameters

```python
AgentFactory(
    chat_client=None,              # Optional: Pre-configured chat client
    bindings=None,                 # Optional: Dict of function bindings
    connections=None,              # Optional: Dict of connection objects
    client_kwargs=None,            # Optional: Kwargs for client creation
    additional_mappings=None,      # Optional: Additional provider mappings
    default_provider="AzureAIClient",  # Default provider type
    safe_mode=True,                # Enable safe mode
    env_file_path=None,            # Path to .env file
    env_file_encoding=None,        # Encoding for .env file
)
```

**Available Methods:**
- `create_agent_from_yaml_path(yaml_path)` - Create agent from YAML file
- `create_agent_from_yaml(yaml_str)` - Create agent from YAML string
- `create_agent_from_dict(agent_def)` - Create agent from dictionary
- `create_agent_from_yaml_path_async(yaml_path)` - Async version
- `create_agent_from_yaml_async(yaml_str)` - Async version
- `create_agent_from_dict_async(agent_def)` - Async version

[↑ Back to Python Usage](#python-usage) | [↑ Back to top](#-table-of-contents)

---

## Validation and Errors

### Common Errors

#### 1. DeclarativeLoaderError
YAML doesn't represent a `PromptAgent`
```
Only yaml definitions for a PromptAgent are supported for agent creation.
```

#### 2. ProviderLookupError
Unknown provider
```
Unsupported provider type: UnknownProvider
```

#### 3. ValueError
Missing required fields
```
Missing required field: model.id
Missing required field: kind
```

[↑ Back to Validation](#validation-and-errors)

### Required Fields

**Agent Level:**
- `kind` - Must be "Prompt" or "Agent"
- `name` - Agent name

**Model Level:**
- `model.id` - Model ID or deployment name

**Connection Level (depends on kind):**
- `remote`: No required fields (endpoint optional)
- `key`: No required fields (apiKey/key optional)
- `reference`: No required fields (name optional)
- `anonymous`: No required fields (endpoint optional)

**Tool Level:**
- All tools: `kind` is required
- Other fields are optional per tool type

[↑ Back to Validation](#validation-and-errors) | [↑ Back to top](#-table-of-contents)

---

## References

### Official Documentation
- [Microsoft Agent Framework](https://github.com/microsoft/agent-framework)
- [Azure AI Foundry Documentation](https://learn.microsoft.com/azure/ai-services/)
- [PowerFx Documentation](https://learn.microsoft.com/en-us/power-platform/power-fx/overview)

### Source Code
- [`_models.py`](https://github.com/microsoft/agent-framework/blob/main/python/packages/declarative/agent_framework_declarative/_models.py) - Pydantic models for YAML schema
- [`_loader.py`](https://github.com/microsoft/agent-framework/blob/main/python/packages/declarative/agent_framework_declarative/_loader.py) - AgentFactory and provider mappings

### Related Packages
- `agent-framework` - Core framework
- `agent-framework-core` - Core models and agents
- `agent-framework-azure-ai` - Azure AI integration
- `agent-framework-declarative` - Declarative YAML support
- `agent-framework-devui` - Development UI for testing agents
- `powerfx` - PowerFx expression evaluation

### Model Context Protocol (MCP)
- [MCP Specification](https://modelcontextprotocol.io/)
- [Microsoft Learn MCP Server](https://learn.microsoft.com/api/mcp)

---

[↑ Back to top](#-table-of-contents)
