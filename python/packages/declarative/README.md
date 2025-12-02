# Microsoft Agent Framework - Declarative YAML Schema

Complete YAML schema documentation for defining agents declaratively in Microsoft Agent Framework.

**Based on official source code:**
- [`_models.py`](https://github.com/microsoft/agent-framework/blob/main/python/packages/declarative/agent_framework_declarative/_models.py)
- [`_loader.py`](https://github.com/microsoft/agent-framework/blob/main/python/packages/declarative/agent_framework_declarative/_loader.py)

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
  - [Mapping to ChatAgent Parameters](#mapping-to-chatagent-parameters)
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
  - [PowerFx Evaluation](#powerfx-evaluation)
- [Complete Examples](#complete-examples)
  - [Example 1: Simple Agent with Azure OpenAI](#example-1-simple-agent-with-azure-openai)
  - [Example 2: Agent with Azure AI Client and PowerFx](#example-2-agent-with-azure-ai-client-and-powerfx)
  - [Example 3: Agent with MCP Tool (Microsoft Learn)](#example-3-agent-with-mcp-tool-microsoft-learn)
  - [Example 4: Agent with Multiple Tools](#example-4-agent-with-multiple-tools)
  - [Example 5: Agent with Input/Output Schema](#example-5-agent-with-inputoutput-schema)
  - [Example 6: Agent with File Search](#example-6-agent-with-file-search)
  - [Example 7: Agent with OpenAPI Tool](#example-7-agent-with-openapi-tool)
- [Python Usage](#python-usage)
  - [Create Agent from YAML](#create-agent-from-yaml)
  - [With Bindings (Python Functions)](#with-bindings-python-functions)
  - [With Connections](#with-connections)
  - [From YAML String](#from-yaml-string)
- [Validation and Errors](#validation-and-errors)
  - [Common Errors](#common-errors)
  - [PowerFx Validation](#powerfx-validation)
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
model: Model                    # OPTIONAL: Model configuration
tools: list[Tool]              # OPTIONAL: List of tools
inputSchema: PropertySchema     # OPTIONAL: Input schema
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

The loader looks up providers in `PROVIDER_TYPE_OBJECT_MAPPING`:

| Provider | Package | Class | Model ID Field |
|----------|---------|-------|---------------|
| `AzureOpenAI.Chat` | `agent_framework.azure` | `AzureOpenAIChatClient` | `deployment_name` |
| `AzureOpenAI.Assistants` | `agent_framework.azure` | `AzureOpenAIAssistantsClient` | `assistant_id` |
| `OpenAI.Chat` | `agent_framework.openai` | `OpenAIChatClient` | `model` |
| `OpenAI.Assistants` | `agent_framework.openai` | `OpenAIAssistantsClient` | `assistant_id` |
| `AzureAIClient` | `agent_framework_azure_ai` | `AzureAIClient` | `model_id` |
| `OpenAICompatible.Chat` | `agent_framework.openai` | `OpenAICompatibleChatClient` | `model` |

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
  endpoint: string              # REQUIRED: Endpoint URL
  authenticationMode: string    # OPTIONAL
  usageDescription: string      # OPTIONAL
  name: string                  # OPTIONAL
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
  apiKey: string                # REQUIRED (or use 'key')
  key: string                   # Alternative to 'apiKey'
  endpoint: string              # OPTIONAL
  authenticationMode: string    # OPTIONAL
  usageDescription: string      # OPTIONAL
  name: string                  # OPTIONAL
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
  name: string                  # REQUIRED: Connection name
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
  endpoint: string              # REQUIRED
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
    frequencyPenalty: float           # OPTIONAL: -2.0 to 2.0
    maxOutputTokens: int              # OPTIONAL: Maximum output tokens
    presencePenalty: float            # OPTIONAL: -2.0 to 2.0
    seed: int                         # OPTIONAL: Seed for reproducibility
    temperature: float                # OPTIONAL: 0.0 to 2.0
    topP: float                       # OPTIONAL: 0.0 to 1.0
    stopSequences: list[string]       # OPTIONAL: Stop sequences
    allowMultipleToolCalls: bool      # OPTIONAL: Allow multiple tool calls
    additionalProperties: dict        # OPTIONAL: Additional properties
```

### Mapping to ChatAgent Parameters

The loader converts `ModelOptions` to `ChatAgent` parameters:

| YAML Field | ChatAgent Parameter |
|-----------|-------------------|
| `frequencyPenalty` | `frequency_penalty` |
| `presencePenalty` | `presence_penalty` |
| `maxOutputTokens` | `max_tokens` |
| `temperature` | `temperature` |
| `topP` | `top_p` |
| `seed` | `seed` |
| `stopSequences` | `stop` |
| `allowMultipleToolCalls` | `allow_multiple_tool_calls` |
| `additionalProperties.chatToolMode` | `tool_choice` |
| `additionalProperties` (rest) | `additional_chat_options` |

### Example

```yaml
model:
  id: gpt-4
  options:
    temperature: 0.7
    maxOutputTokens: 2000
    topP: 0.95
    stopSequences: ["\n\n", "END"]
    allowMultipleToolCalls: true
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
    name: string                # REQUIRED
    description: string         # REQUIRED
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
    vectorStoreIds: list[string] # OPTIONAL: Vector store IDs
    maximumResultCount: int     # OPTIONAL: Maximum results
    ranker: string              # OPTIONAL: Ranker type
    scoreThreshold: float       # OPTIONAL: Score threshold
    filters: dict               # OPTIONAL: Search filters
    connection: Connection      # OPTIONAL: Connection
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
    name: string                # REQUIRED
    description: string         # OPTIONAL
    url: string                 # REQUIRED: MCP server URL
    approvalMode: ApprovalMode  # OPTIONAL: Approval mode
    allowedTools: list[string]  # OPTIONAL: List of allowed tools
```

#### ApprovalMode - Simple Format

```yaml
approvalMode:
  kind: never         # No approval (automatic execution)
  # OR
  kind: always        # Requires approval on EVERY call
  # OR
  kind: onFirstUse    # Requires approval only on first use
```

String format is also accepted:
```yaml
approvalMode: never   # Equivalent to {kind: never}
```

#### ApprovalMode - Advanced Format (ToolSpecify)

```yaml
approvalMode:
  kind: toolSpecify
  alwaysRequireApprovalTools: list[string]  # Tools that ALWAYS require approval
  neverRequireApprovalTools: list[string]   # Tools that NEVER require approval
```

**Conversion in loader:**

| YAML | Python (HostedMCPTool) |
|------|----------------------|
| `kind: never` | `approval_mode="never_require"` |
| `kind: always` | `approval_mode="always_require"` |
| `kind: toolSpecify` | `approval_mode={"always_require_approval": [...], "never_require_approval": [...]}` |

**Example 1: Microsoft Learn**
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
      kind: toolSpecify
      alwaysRequireApprovalTools:
        - delete_records
        - truncate_table
      neverRequireApprovalTools:
        - select_query
        - count_records
    allowedTools:
      - select_query
      - delete_records
      - truncate_table
      - count_records
```

[↑ Back to Tools](#tools-section)

### 6. OpenApiTool

Tool based on OpenAPI specification.

```yaml
tools:
  - kind: openapi               # REQUIRED
    name: string                # REQUIRED
    description: string         # OPTIONAL
    specification: string       # REQUIRED: URL or path to OpenAPI spec
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
    name: string                # REQUIRED
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
inputSchema:  # or outputSchema
  properties:
    - name: string              # REQUIRED
      kind: string              # REQUIRED: field type
      description: string       # OPTIONAL
      required: bool            # OPTIONAL
      default: any              # OPTIONAL
      example: any              # OPTIONAL
      enum: list[any]           # OPTIONAL: allowed values
```

### Property Types

#### 1. Simple Property

**Supported kinds:** `string`, `number`, `boolean`, `array`, `object`

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
inputSchema:
  properties:
    - name: query
      kind: string
      description: User search query
      required: true
    - name: filters
      kind: object
      description: Search filters
      properties:
        - name: category
          kind: string
          enum: [docs, blog, video]
        - name: date_from
          kind: string
    - name: max_results
      kind: number
      default: 10

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
- And more according to PowerFx specification

**Example:**
```yaml
model:
  id: =Concatenate("gpt-", Env.MODEL_VERSION)
  connection:
    kind: remote
    endpoint: =Concatenate("https://", Env.REGION, ".openai.azure.com")
```

### PowerFx Evaluation

**Requirements:**
- Python ≤ 3.13 (PowerFx doesn't support 3.14+)
- `powerfx` package installed

**Behavior:**
- If PowerFx engine is not available, expressions are returned as literal strings
- A warning is logged when this happens
- The agent may fail if the literal value is invalid

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
    maxOutputTokens: 1000
```

[↑ Back to Examples](#complete-examples)

### Example 2: Agent with Azure AI Client and PowerFx

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
    maxOutputTokens: 2000
```

[↑ Back to Examples](#complete-examples)

### Example 3: Agent with MCP Tool (Microsoft Learn)

```yaml
kind: Prompt
name: MicrosoftLearnAgent
description: Search and retrieve Microsoft Learn documentation
instructions: You answer questions by searching the Microsoft Learn content only.

model:
  id: =Env.AZURE_FOUNDRY_PROJECT_MODEL_ID
  connection:
    kind: remote
    endpoint: =Env.AZURE_FOUNDRY_PROJECT_ENDPOINT

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
description: Agent with structured input and output
instructions: Process user requests and return structured data.

model:
  id: gpt-4-turbo
  provider: OpenAI.Chat
  connection:
    kind: key
    apiKey: =Env.OPENAI_API_KEY

inputSchema:
  properties:
    - name: task
      kind: string
      description: Task to perform
      required: true
      enum: [summarize, translate, analyze]
    - name: content
      kind: string
      description: Content to process
      required: true
    - name: language
      kind: string
      description: Target language for translation
      default: en

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

[↑ Back to Examples](#complete-examples)

### Example 6: Agent with File Search

```yaml
kind: Prompt
name: DocumentSearchAgent
description: Search through company documents
instructions: Search and retrieve information from indexed documents. Cite sources.

model:
  id: =Env.MODEL_DEPLOYMENT
  provider: AzureAIClient
  connection:
    kind: remote
    endpoint: =Env.AZURE_AI_ENDPOINT
  options:
    temperature: 0.3
    maxOutputTokens: 4000
    topP: 0.95
    allowMultipleToolCalls: true

tools:
  - kind: file_search
    description: Search company documentation and knowledge base
    vectorStoreIds:
      - =Env.VECTOR_STORE_POLICIES
      - =Env.VECTOR_STORE_PROCEDURES
    maximumResultCount: 20
    scoreThreshold: 0.7
    ranker: semantic
    filters:
      department: engineering
```

[↑ Back to Examples](#complete-examples)

### Example 7: Agent with OpenAPI Tool

```yaml
kind: Prompt
name: APIIntegrationAgent
description: Agent that can call external APIs
instructions: Use the available API to fetch and process data.

model:
  id: gpt-4
  provider: AzureOpenAI.Chat
  connection:
    kind: remote
    endpoint: =Env.AZURE_ENDPOINT

tools:
  - kind: openapi
    name: weather_api
    description: Get weather information
    specification: https://api.weather.com/openapi.json
    connection:
      kind: key
      apiKey: =Env.WEATHER_API_KEY
      endpoint: https://api.weather.com

  - kind: openapi
    name: stock_api
    description: Get stock market data
    specification: =Env.STOCK_API_SPEC_URL
    connection:
      kind: anonymous
      endpoint: https://api.stocks.com/v1
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
    # Load environment variables
    from dotenv import load_dotenv
    load_dotenv()
    
    # YAML path
    yaml_path = Path(__file__).parent / "agent.yaml"
    
    # Configure project endpoint
    project_endpoint = os.getenv("AZURE_PROJECT_ENDPOINT")
    
    # Create credentials
    credential = DefaultAzureCredential()
    
    # Create factory
    factory = AgentFactory(
        client_kwargs={
            "async_credential": credential,
            "project_endpoint": project_endpoint
        }
    )
    
    # Create agent from YAML
    agent = factory.create_agent_from_yaml_path(yaml_path)
    
    # Use the agent
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

### From YAML String

```python
yaml_content = """
kind: Prompt
name: QuickAgent
description: Quick test agent
instructions: Be helpful

model:
  id: gpt-4
  connection:
    kind: remote
    endpoint: https://myendpoint.com
"""

agent = factory.create_agent_from_yaml(yaml_content)
```

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
#### 3. ValueError
Missing required fields
```
Missing required field: model.id
Missing required field: kind
```

#### 4. PowerFx Evaluation Warnings
When PowerFx engine is not available or Python > 3.13:
```
PowerFx engine is not available. PowerFx expressions will be returned as is.
```

[↑ Back to Validation](#validation-and-errors)

### PowerFx Validation

PowerFx expressions are evaluated during agent creation:

1. **Valid Expression:**
   ```yaml
   endpoint: =Env.AZURE_ENDPOINT
   ```
   ✅ Evaluates to value from environment variable

2. **Invalid Expression:**
   ```yaml
   endpoint: =InvalidFunction(Env.VAR)
   ```
   ❌ PowerFx evaluation error

3. **Missing Variable:**
   ```yaml
   endpoint: =Env.NONEXISTENT_VAR
   ```
   ⚠️ Returns empty string or default value

[↑ Back to Validation](#validation-and-errors)

### Required Fields

**Agent Level:**
- `kind` - Must be "Prompt" or "Agent"
- `name` - Agent name

**Model Level:**
- `model.id` - Model ID or deployment name

**Connection Level (depends on kind):**
- `remote`: `endpoint`
- `key`: `apiKey` or `key`
- `reference`: `name`
- `anonymous`: `endpoint`

**Tool Level (depends on kind):**
- `function`: `name`, `description`
- `mcp`: `name`, `url`
- `openapi`: `name`, `specification`
- `custom`: `name`

[↑ Back to Validation](#validation-and-errors) | [↑ Back to top](#-table-of-contents)

---

## References

### Official Documentation
- [Microsoft Agent Framework](https://github.com/microsoft/agent-framework)
- [Azure AI Foundry Documentation](https://learn.microsoft.com/azure/ai-services/)
- [PowerFx Documentation](https://learn.microsoft.com/power-platform/power-fx/)

### Source Code
- [`_models.py`](https://github.com/microsoft/agent-framework/blob/main/python/packages/declarative/agent_framework_declarative/_models.py) - Pydantic models
- [`_loader.py`](https://github.com/microsoft/agent-framework/blob/main/python/packages/declarative/agent_framework_declarative/_loader.py) - YAML loader logic
- [`_factory.py`](https://github.com/microsoft/agent-framework/blob/main/python/packages/declarative/agent_framework_declarative/_factory.py) - AgentFactory implementation

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

## Changelog

**Version 1.0** (December 2, 2025)
- Initial comprehensive documentation
- All agent types, connections, tools documented
- Complete examples for common scenarios
- Python usage patterns
- Validation and error reference
- Based on official source code analysis

---

**Last Updated:** December 2, 2025  
**Framework Version:** agent-framework-declarative 1.0.0b251120

[↑ Back to top](#-table-of-contents)
