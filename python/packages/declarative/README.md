# Declarative Agent YAML Specification

This document provides a comprehensive guide for defining agents using YAML configuration files in the Declarative Agents framework. Declarative agents allow you to configure AI agents through human-readable YAML files rather than code, making agent creation more accessible and maintainable.

## Table of Contents

- [Basic Structure](#basic-structure)
- [Model Configuration](#model-configuration)
  - [Supported Providers](#supported-providers)
  - [Connection Types](#connection-types)
  - [Model Options](#model-options)
- [Tools](#tools)
  - [Tool Types](#tool-types)
  - [MCP Tools](#mcp-tools)
- [Instructions](#instructions)
- [Handoff Configuration](#handoff-configuration)
- [PowerFx Expressions](#powerfx-expressions)
- [Using AgentFactory](#using-agentfactory)
  - [Extending with Custom Providers](#extending-with-custom-providers)
- [Common Errors](#common-errors)
- [Complete Examples](#complete-examples)
- [References](#references)
- [Version Information](#version-information)

## Basic Structure

A declarative agent YAML file defines an agent's configuration in a structured format:

```yaml
# Required: Agent kind (currently only PromptAgent supported)
kind: PromptAgent

# Required: Agent name
name: my_agent

# Required: Model configuration
model:
  provider: OpenAI
  apiType: Chat
  id: gpt-4o
  # ... additional provider-specific settings

# Optional: Agent instructions
instructions: |
  You are a helpful assistant...

# Optional: Tools the agent can use
tools:
  - kind: code_interpreter
  - kind: mcp
    # ... tool configuration

# Optional: Handoff configuration for multi-agent scenarios
handoff:
  - agent: other_agent
    description: Transfer to specialist
```

## Model Configuration

### Supported Providers

The declarative agents framework supports **10 built-in providers**. Each provider has specific configuration requirements:

| Provider | API Type | Package | Class | Model ID Field |
|----------|----------|---------|-------|----------------|
| `OpenAI` | `Chat` | `agent_framework.openai` | `OpenAIChatClient` | `id` (maps to `model_id`) |
| `OpenAI` | `Assistants` | `agent_framework.openai` | `OpenAIAssistantsClient` | `id` (maps to `model_id`) |
| `OpenAI` | `Responses` | `agent_framework.openai` | `OpenAIResponsesClient` | `id` (maps to `model_id`) |
| `AzureOpenAI` | `Chat` | `agent_framework.azure` | `AzureOpenAIChatClient` | `id` (maps to `deployment_name`) |
| `AzureOpenAI` | `Assistants` | `agent_framework.azure` | `AzureOpenAIAssistantsClient` | `id` (maps to `deployment_name`) |
| `AzureOpenAI` | `Responses` | `agent_framework.azure` | `AzureOpenAIResponsesClient` | `id` (maps to `deployment_name`) |
| `AzureAIClient` | - | `agent_framework.azure` | `AzureAIClient` | `id` (maps to `model_deployment_name`) |
| `AzureAIAgentClient` | - | `agent_framework.azure` | `AzureAIAgentClient` | `id` (maps to `model_deployment_name`) |
| `AzureAI` | `ProjectProvider` | `agent_framework_azure_ai` | `AzureAIProjectAgentProvider` | `id` (maps to `model`) |
| `Anthropic` | `Chat` | `agent_framework.anthropic` | `AnthropicChatClient` | `id` (maps to `model_id`) |

> **Note:** Google Gemini and Amazon Bedrock are available as separate packages but are NOT included in the default provider mapping. See [Extending with Custom Providers](#extending-with-custom-providers) to add them.

#### OpenAI Chat
Direct OpenAI API integration for chat models.

```yaml
model:
  provider: OpenAI
  apiType: Chat
  id: gpt-4o
  connection:
    kind: apiKey
    secretKey: ${Env.OPENAI_API_KEY}
```

#### OpenAI Responses
OpenAI's Responses API for structured outputs.

```yaml
model:
  provider: OpenAI
  apiType: Responses
  id: gpt-4o
  connection:
    kind: apiKey
    secretKey: ${Env.OPENAI_API_KEY}
```

#### OpenAI Assistants
OpenAI's Assistants API.

```yaml
model:
  provider: OpenAI
  apiType: Assistants
  id: gpt-4o
  connection:
    kind: apiKey
    secretKey: ${Env.OPENAI_API_KEY}
```

#### AzureOpenAI Chat
Azure-hosted OpenAI models for chat.

```yaml
model:
  provider: AzureOpenAI
  apiType: Chat
  id: my-gpt4-deployment
  connection:
    kind: apiKey
    endpoint: https://my-resource.openai.azure.com
    secretKey: ${Env.AZURE_OPENAI_API_KEY}
    apiVersion: "2024-02-15-preview"
```

#### AzureOpenAI Responses
Azure-hosted OpenAI with Responses API.

```yaml
model:
  provider: AzureOpenAI
  apiType: Responses
  id: my-gpt4-deployment
  connection:
    kind: apiKey
    endpoint: https://my-resource.openai.azure.com
    secretKey: ${Env.AZURE_OPENAI_API_KEY}
    apiVersion: "2024-02-15-preview"
```

#### AzureOpenAI Assistants
Azure-hosted OpenAI Assistants.

```yaml
model:
  provider: AzureOpenAI
  apiType: Assistants
  id: my-gpt4-deployment
  connection:
    kind: apiKey
    endpoint: https://my-resource.openai.azure.com
    secretKey: ${Env.AZURE_OPENAI_API_KEY}
    apiVersion: "2024-02-15-preview"
```

#### AzureAIClient
Azure AI Model Inference client (default provider).

```yaml
model:
  provider: AzureAIClient
  id: gpt-4o
  connection:
    kind: apiKey
    endpoint: https://my-endpoint.services.ai.azure.com/models
    secretKey: ${Env.AZURE_AI_API_KEY}
```

#### AzureAIAgentClient
Azure AI Agent Service for managed agent deployments.

```yaml
model:
  provider: AzureAIAgentClient
  id: my-agent-deployment
  connection:
    kind: apiKey
    endpoint: https://my-project.services.ai.azure.com
    secretKey: ${Env.AZURE_AI_AGENT_KEY}
```

#### AzureAI ProjectProvider
Azure AI Project-based agent provider.

```yaml
model:
  provider: AzureAI
  apiType: ProjectProvider
  id: my-model
  connection:
    kind: apiKey
    endpoint: https://my-project.services.ai.azure.com
    secretKey: ${Env.AZURE_AI_KEY}
```

#### Anthropic Chat
Anthropic Claude models integration.

```yaml
model:
  provider: Anthropic
  apiType: Chat
  id: claude-sonnet-4-20250514
  connection:
    kind: apiKey
    secretKey: ${Env.ANTHROPIC_API_KEY}
```

### Connection Types

Connections define how to authenticate with model providers:

#### API Key Connection
API key authentication (most common):

```yaml
connection:
  kind: apiKey
  secretKey: ${Env.API_KEY}
  # Optional for Azure services:
  endpoint: https://my-resource.openai.azure.com
  apiVersion: "2024-02-15-preview"
```

#### Remote Connection
For server-to-server connections with explicit configuration:

```yaml
connection:
  kind: remote
  name: my-connection
  endpoint: https://api.example.com
```

#### Reference Connection
Reference to a pre-configured connection by name:

```yaml
connection:
  kind: reference
  name: my-preconfigured-connection
  target: connection-target-id
```

#### Anonymous Connection
No authentication required (for local services like Ollama):

```yaml
connection:
  kind: anonymous
  endpoint: http://localhost:11434
```

### Model Options

Configure model behavior with options. Note the correct field names:

```yaml
model:
  provider: OpenAI
  apiType: Chat
  id: gpt-4o
  connection:
    kind: apiKey
    secretKey: ${Env.OPENAI_API_KEY}
  options:
    temperature: 0.7              # 0.0 to 2.0
    topP: 0.95                    # 0.0 to 1.0
    maxOutputTokens: 4096         # Maximum output tokens (NOT maxTokens)
    frequencyPenalty: 0.0         # -2.0 to 2.0
    presencePenalty: 0.0          # -2.0 to 2.0
    seed: 42                      # For reproducibility
    stop:                         # Stop sequences
      - "\n\n"
      - "END"
```

> **Important:** Use `maxOutputTokens` (not `maxTokens`). The `ModelOptions` class maps this to the underlying `max_tokens` parameter.

### Environment Variable Substitution

Use `${Env.VARIABLE_NAME}` syntax to reference environment variables:

```yaml
connection:
  kind: apiKey
  secretKey: ${Env.OPENAI_API_KEY}
  endpoint: ${Env.AZURE_ENDPOINT}
```

## Tools

Tools extend agent capabilities beyond conversation. The framework supports various tool types for different use cases.

### Tool Types

#### Code Interpreter
Enables the agent to execute Python code:

```yaml
tools:
  - kind: code_interpreter
```

#### File Search
Enables searching through uploaded files:

```yaml
tools:
  - kind: file_search
    vector_store_ids:
      - vs_abc123
```

#### Bing Grounding
Enables web search via Bing (Azure AI Agent only):

```yaml
tools:
  - kind: bing_grounding
    connection:
      kind: apiKey
      secretKey: ${Env.BING_API_KEY}
```

#### Microsoft Fabric
Enables data integration with Microsoft Fabric (Azure AI Agent only):

```yaml
tools:
  - kind: microsoft_fabric
    connection:
      kind: apiKey
      secretKey: ${Env.FABRIC_API_KEY}
```

#### SharePoint Grounding
Enables searching SharePoint content (Azure AI Agent only):

```yaml
tools:
  - kind: sharepoint_grounding
    connection:
      kind: apiKey
      secretKey: ${Env.SHAREPOINT_API_KEY}
```

#### Azure AI Search
Enables Azure AI Search integration (Azure AI Agent only):

```yaml
tools:
  - kind: azure_ai_search
    connection:
      kind: apiKey
      endpoint: ${Env.SEARCH_ENDPOINT}
      secretKey: ${Env.SEARCH_API_KEY}
    index_name: my-search-index
    query_type: semantic  # simple, full, semantic, vector, hybrid
    top_k: 5
```

#### Azure Functions
Enables calling Azure Functions:

```yaml
tools:
  - kind: azure_function
    name: my_function
    description: Processes data
    input_queue:
      storage_service_endpoint: ${Env.STORAGE_ENDPOINT}
      queue_name: input-queue
    output_queue:
      storage_service_endpoint: ${Env.STORAGE_ENDPOINT}
      queue_name: output-queue
    parameters:
      type: object
      properties:
        input:
          type: string
          description: Input data
```

#### OpenAPI
Enables calling external APIs via OpenAPI specification:

```yaml
tools:
  - kind: openapi
    name: weather_api
    description: Get weather information
    specification: https://api.weather.com/openapi.json
```

### MCP Tools

[Model Context Protocol (MCP)](https://modelcontextprotocol.io/) tools provide a standardized way to extend agent capabilities:

#### Basic MCP Configuration

```yaml
tools:
  - kind: mcp
    serverName: filesystem
    serverDescription: File system operations
    command: npx
    args:
      - "-y"
      - "@anthropic/mcp-filesystem"
      - "/allowed/path"
```

#### MCP with Environment Variables

```yaml
tools:
  - kind: mcp
    serverName: github
    serverDescription: GitHub operations
    command: npx
    args:
      - "-y"
      - "@anthropic/mcp-github"
    env:
      GITHUB_TOKEN: ${Env.GITHUB_TOKEN}
```

#### MCP Tool Approval Modes

Control how tools are executed with different approval modes:

##### Automatic Approval
Tools execute without user confirmation:

```yaml
tools:
  - kind: mcp
    serverName: calculator
    approvalMode: automatic
    command: python
    args: ["-m", "mcp_calculator"]
```

##### Manual Approval
Requires explicit user approval for each tool call:

```yaml
tools:
  - kind: mcp
    serverName: file_writer
    approvalMode: manual
    command: npx
    args: ["-y", "@anthropic/mcp-filesystem"]
```

##### Accept List Approval
Automatically approve only specific tools, require manual approval for others:

```yaml
tools:
  - kind: mcp
    serverName: mixed_tools
    approvalMode:
      mode: acceptList
      tools:
        - safe_read_operation
        - another_safe_tool
    command: python
    args: ["-m", "mcp_server"]
```

##### Deny List Approval
Automatically approve all tools except specific ones:

```yaml
tools:
  - kind: mcp
    serverName: mostly_safe
    approvalMode:
      mode: denyList
      tools:
        - dangerous_delete_operation
        - risky_write_operation
    command: python
    args: ["-m", "mcp_server"]
```

#### Remote MCP Server (SSE)

Connect to remote MCP servers over Server-Sent Events (SSE):

```yaml
tools:
  - kind: mcp
    serverName: remote_tools
    serverDescription: Remote MCP server tools
    url: https://mcp-server.example.com/sse
    headers:
      Authorization: Bearer ${Env.MCP_TOKEN}
```

## Instructions

Instructions define the agent's behavior and personality. They can be provided inline or loaded from external files.

### Inline Instructions

```yaml
instructions: |
  You are a helpful customer service agent for Acme Corporation.
  
  ## Guidelines
  - Always be polite and professional
  - If you don't know the answer, say so
  - Escalate complex issues to human agents
  
  ## Knowledge
  - Our return policy is 30 days
  - Business hours are 9 AM - 5 PM EST
```

### File-based Instructions

```yaml
instructions: ${file:prompts/customer_service.md}
```

### Dynamic Instructions with PowerFx

```yaml
instructions: |
  You are assisting ${context.user_name}.
  Current date: =Now()
  User tier: ${context.subscription_tier}
```

## Handoff Configuration

Handoffs enable multi-agent orchestration by allowing agents to transfer control to other agents.

### Basic Handoff

```yaml
handoff:
  - agent: specialist_agent
    description: Transfer to technical specialist for complex issues
```

### Handoff with Multiple Agents

```yaml
handoff:
  - agent: billing_agent
    description: Transfer to billing department
  - agent: technical_agent
    description: Transfer to technical support
  - agent: sales_agent
    description: Transfer to sales team
```

### Handoff with Agent References

```yaml
# main_agent.yaml
kind: PromptAgent
name: main_agent
model:
  provider: OpenAI
  apiType: Chat
  id: gpt-4o
  connection:
    kind: apiKey
    secretKey: ${Env.OPENAI_API_KEY}
instructions: Route customer inquiries to appropriate specialists.
handoff:
  - agent: ${file:agents/billing_agent.yaml}
    description: Handle billing inquiries
  - agent: ${file:agents/tech_agent.yaml}
    description: Handle technical issues
```

## PowerFx Expressions

The framework supports [PowerFx](https://learn.microsoft.com/en-us/power-platform/power-fx/overview) expressions for dynamic configuration values. PowerFx expressions are prefixed with `=`.

### Supported Fields

PowerFx expressions are evaluated on **specific fields only**, not all string values. The following fields support PowerFx:

| Component | Fields with PowerFx Support |
|-----------|----------------------------|
| **AgentDefinition** | `kind`, `name`, `displayName`, `description` |
| **PromptAgent** | `instructions`, `additionalInstructions` |
| **Model** | `id`, `provider`, `apiType` |
| **Connection** | `authenticationMode`, `usageDescription`, `endpoint`, `apiKey`, `name`, `target` |
| **Tool** | `name`, `kind`, `description` |
| **McpTool** | `serverName`, `serverDescription`, `url` |
| **OpenApiTool** | `specification` |
| **Resource** | `name`, `kind` |
| **ModelResource** | `id` |
| **Property** | `name`, `kind`, `description` |
| **Binding** | `name`, `input` |

> **Note:** Model options (temperature, seed, topK, etc.) do NOT support PowerFx expressions at YAML load time.

### Environment Variables

Access environment variables with `Env.VARIABLE_NAME`:

```yaml
model:
  id: =Env.MODEL_DEPLOYMENT_NAME
  connection:
    kind: apiKey
    endpoint: =Env.AZURE_ENDPOINT
    secretKey: =Env.AZURE_API_KEY
```

### Supported PowerFx Functions

- `Concatenate()`: Concatenate strings
- `Now()`: Current datetime
- `Today()`: Current date
- `Text()`: Format values as text
- Arithmetic operators: `+`, `-`, `*`, `/`
- Logical operators: `And()`, `Or()`, `Not()`
- And more according to [PowerFx specification](https://learn.microsoft.com/en-us/power-platform/power-fx/overview)

### Context Variables

Access context data passed at runtime:

```yaml
instructions: |
  User: ${context.user_name}
  Session ID: ${context.session_id}
  Priority: ${context.priority_level}
```

## Using AgentFactory

The `AgentFactory` class provides the primary interface for loading and instantiating declarative agents.

### Basic Usage

```python
from agent_framework_declarative import AgentFactory
import asyncio

async def main():
    factory = AgentFactory()
    
    # Load agent from YAML file
    agent = await factory.create_agent_from_yaml_path_async("path/to/agent.yaml")
    
    # Use the agent
    response = await agent.run("Hello, how can you help me?")
    print(response)

asyncio.run(main())
```

### With Runtime Context

```python
from agent_framework_declarative import AgentFactory
import asyncio

async def main():
    context = {
        "user_name": "John",
        "session_id": "abc123",
        "subscription_tier": "premium"
    }
    
    factory = AgentFactory()
    agent = await factory.create_agent_from_yaml_path_async(
        "path/to/agent.yaml",
        context=context
    )
    
    response = await agent.run("What services do I have access to?")
    print(response)

asyncio.run(main())
```

### AgentFactory Constructor

```python
AgentFactory(
    chat_client=None,              # Optional: Pre-configured chat client
    bindings=None,                 # Optional: Dict of function bindings
    connections=None,              # Optional: Dict of connection objects
    client_kwargs=None,            # Optional: Kwargs for client creation
    additional_mappings=None,      # Optional: Additional provider mappings
    default_provider="AzureAIClient",  # Default provider type
    safe_mode=True,                # Enable safe mode for PowerFx
    env_file_path=None,            # Path to .env file
    env_file_encoding=None,        # Encoding for .env file
)
```

### Available Methods

| Method | Description |
|--------|-------------|
| `create_agent_from_yaml_path(yaml_path)` | Create agent from YAML file (sync) |
| `create_agent_from_yaml(yaml_str)` | Create agent from YAML string (sync) |
| `create_agent_from_dict(agent_def)` | Create agent from dictionary (sync) |
| `create_agent_from_yaml_path_async(yaml_path)` | Create agent from YAML file (async) |
| `create_agent_from_yaml_async(yaml_str)` | Create agent from YAML string (async) |
| `create_agent_from_dict_async(agent_def)` | Create agent from dictionary (async) |

### Extending with Custom Providers

The built-in provider mapping includes 10 providers. To use additional providers like **Amazon Bedrock** or **Google Gemini**, use the `additional_mappings` parameter:

#### Adding Amazon Bedrock Support

```python
from agent_framework_declarative import AgentFactory

factory = AgentFactory(
    additional_mappings={
        "Bedrock.Chat": {
            "package": "agent_framework_bedrock",
            "name": "BedrockChatClient",
            "model_id_field": "model_id",
        },
    },
)

# Now you can use in YAML:
# model:
#   provider: Bedrock
#   apiType: Chat
#   id: anthropic.claude-3-sonnet-20240229-v1:0
```

#### Adding Google Gemini Support

```python
from agent_framework_declarative import AgentFactory

factory = AgentFactory(
    additional_mappings={
        "Google.Gemini": {
            "package": "agent_framework_google",
            "name": "GoogleGeminiChatClient",
            "model_id_field": "model_id",
        },
    },
)

# Now you can use in YAML:
# model:
#   provider: Google
#   apiType: Gemini
#   id: gemini-1.5-pro
```

> **Note:** Ensure you have the corresponding packages installed (`agent-framework-bedrock`, `agent-framework-google`, etc.).

### Custom Tool Approval Handler

```python
from agent_framework_declarative import AgentFactory
import asyncio

async def approval_handler(tool_name: str, tool_args: dict) -> bool:
    """Custom approval logic for tool execution."""
    dangerous_tools = ["delete_file", "execute_command"]
    if tool_name in dangerous_tools:
        user_input = input(f"Allow {tool_name} with args {tool_args}? (y/n): ")
        return user_input.lower() == 'y'
    return True

async def main():
    factory = AgentFactory()
    agent = await factory.create_agent_from_yaml_path_async(
        "path/to/agent.yaml",
        tool_approval_handler=approval_handler
    )
    
    response = await agent.run("Delete the temporary files")
    print(response)

asyncio.run(main())
```

## Common Errors

### 1. ProviderLookupError
Invalid or unsupported provider configuration:
```
ProviderLookupError: Provider 'InvalidProvider' not found in mapping
```

**Solution:** Check the [Supported Providers](#supported-providers) table or add custom mappings.

### 2. DeclarativeLoaderError
Validation failures during agent creation:
```
DeclarativeLoaderError: Only definitions for a PromptAgent are supported for agent creation.
DeclarativeLoaderError: ChatClient must be provided or connection must be configured.
```

**Common causes:**
- Missing required `kind: PromptAgent` field
- Missing `model.id` or `model.connection` configuration
- Invalid YAML structure

### 3. PowerFx Evaluation Errors
Errors in PowerFx expressions:
```
PowerFxError: Unable to evaluate expression: =InvalidFunction()
```

**Solution:** Verify the expression syntax and ensure environment variables exist.

### 4. Connection Errors
Authentication or endpoint issues:
```
AuthenticationError: Invalid API key provided
ConnectionError: Unable to reach endpoint
```

**Solution:** Verify credentials and endpoint URLs in your environment variables.

## Complete Examples

### Customer Service Agent

```yaml
kind: PromptAgent
name: customer_service_agent
description: Handles customer inquiries and support requests

model:
  provider: OpenAI
  apiType: Chat
  id: gpt-4o
  connection:
    kind: apiKey
    secretKey: ${Env.OPENAI_API_KEY}
  options:
    temperature: 0.7

instructions: |
  You are a customer service representative for TechCorp.
  
  ## Your Role
  - Answer product questions
  - Help with order status inquiries
  - Process simple returns and exchanges
  - Escalate complex issues to specialists
  
  ## Guidelines
  - Be friendly and professional
  - Ask clarifying questions when needed
  - Always verify customer identity before discussing orders
  
  Customer name: ${context.customer_name}

tools:
  - kind: openapi
    name: order_api
    description: Look up order information
    specification: https://api.techcorp.com/orders/openapi.json

handoff:
  - agent: billing_specialist
    description: Transfer to billing for payment issues
  - agent: technical_support
    description: Transfer to tech support for product issues
```

### Research Assistant with MCP

```yaml
kind: PromptAgent
name: research_assistant
description: Helps with research tasks using various tools

model:
  provider: Anthropic
  apiType: Chat
  id: claude-sonnet-4-20250514
  connection:
    kind: apiKey
    secretKey: ${Env.ANTHROPIC_API_KEY}
  options:
    maxOutputTokens: 4096

instructions: |
  You are a research assistant with access to file system and web search tools.
  
  ## Capabilities
  - Search the web for information
  - Read and analyze local documents
  - Summarize findings
  - Create reports
  
  ## Guidelines
  - Cite your sources
  - Be thorough but concise
  - Ask for clarification on ambiguous queries

tools:
  - kind: mcp
    serverName: filesystem
    serverDescription: Read local documents
    approvalMode: automatic
    command: npx
    args:
      - "-y"
      - "@anthropic/mcp-filesystem"
      - "${context.allowed_path}"
  
  - kind: mcp
    serverName: web_search
    serverDescription: Search the web
    approvalMode:
      mode: acceptList
      tools:
        - search
        - fetch_page
    command: npx
    args:
      - "-y"
      - "@anthropic/mcp-web-search"
    env:
      SEARCH_API_KEY: ${Env.SEARCH_API_KEY}
```

### Multi-Agent Orchestrator

```yaml
kind: PromptAgent
name: orchestrator
description: Routes requests to specialized agents

model:
  provider: AzureOpenAI
  apiType: Chat
  id: gpt-4o
  connection:
    kind: apiKey
    endpoint: ${Env.AZURE_OPENAI_ENDPOINT}
    secretKey: ${Env.AZURE_OPENAI_KEY}
    apiVersion: "2024-02-15-preview"

instructions: |
  You are an orchestrator agent. Your job is to understand user requests
  and route them to the appropriate specialist agent.
  
  ## Available Specialists
  - **Data Analyst**: For data analysis, charts, and statistics
  - **Code Assistant**: For programming help and code review
  - **Writer**: For content creation and editing
  
  Analyze each request and transfer to the most appropriate specialist.

handoff:
  - agent: ${file:agents/data_analyst.yaml}
    description: Handles data analysis, visualization, and statistical questions
  - agent: ${file:agents/code_assistant.yaml}
    description: Helps with coding, debugging, and code review
  - agent: ${file:agents/writer.yaml}
    description: Assists with writing, editing, and content creation
```

### Azure AI Agent with Enterprise Tools

```yaml
kind: PromptAgent
name: azure_enterprise_agent
description: Enterprise agent with Azure AI capabilities

model:
  provider: AzureAIAgentClient
  id: ${Env.AZURE_AGENT_DEPLOYMENT}
  connection:
    kind: apiKey
    endpoint: ${Env.AZURE_AI_ENDPOINT}
    secretKey: ${Env.AZURE_AI_KEY}

instructions: |
  You are an enterprise assistant with access to company data.
  Use available tools to answer questions about company information.

tools:
  - kind: azure_ai_search
    connection:
      kind: apiKey
      endpoint: ${Env.SEARCH_ENDPOINT}
      secretKey: ${Env.SEARCH_KEY}
    index_name: company-knowledge-base
    query_type: semantic
    top_k: 10

  - kind: bing_grounding
    connection:
      kind: apiKey
      secretKey: ${Env.BING_KEY}

  - kind: code_interpreter
```

## References

- [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) - Standard protocol for extending AI model capabilities
- [Microsoft Learn MCP Server](https://learn.microsoft.com/en-us/training/support/mcp) - Information about Microsoft Learn's MCP server implementation
- [PowerFx Documentation](https://learn.microsoft.com/en-us/power-platform/power-fx/overview) - PowerFx expression language reference
- [Azure OpenAI Service](https://learn.microsoft.com/en-us/azure/ai-services/openai/) - Azure OpenAI documentation
- [Azure AI Foundry](https://learn.microsoft.com/en-us/azure/ai-studio/) - Azure AI Foundry (formerly AI Studio) documentation
- [Anthropic Claude](https://docs.anthropic.com/) - Anthropic Claude model documentation
- [OpenAI API](https://platform.openai.com/docs/) - OpenAI API documentation

---

## Version Information

This documentation was created based on analysis of the `agent-framework` repository.

| Component | Details |
|-----------|---------|
| **Documentation Version** | 1.0 |
| **Analysis Date** | February 2026 |
| **Repository** | [microsoft/agent-framework](https://github.com/microsoft/agent-framework) |
| **Package** | `agent-framework-declarative` |
| **Source Files Analyzed** | `_loader.py`, `_models.py`, `agent_schema.py` |
| **Provider Count** | 10 built-in providers |

### Changelog

- **v1.0 (Feb 2026)**: Initial comprehensive documentation
  - Documented all 10 built-in providers from `PROVIDER_TYPE_OBJECT_MAPPING`
  - Documented PowerFx-supported fields based on `_try_powerfx_eval` usage in `_models.py`
  - Documented `AgentFactory` API from `_loader.py`
  - Added custom provider extension patterns for Bedrock/Google
  - Corrected `maxOutputTokens` field name per `ModelOptions` class

> **Maintenance Note:** When updating this documentation, verify against the current source code in `python/packages/declarative/agent_framework_declarative/` as the API may evolve.

For the latest updates and additional examples, see the [agent-framework repository](https://github.com/microsoft/agent-framework).
