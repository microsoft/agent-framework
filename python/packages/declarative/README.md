# Declarative Agent YAML Specification

This document provides a comprehensive guide for defining agents using YAML configuration files in the Declarative Agents framework. Declarative agents allow you to configure AI agents through human-readable YAML files rather than code, making agent creation more accessible and maintainable.

## Table of Contents

- [Basic Structure](#basic-structure)
- [Model Configuration](#model-configuration)
  - [Supported Providers](#supported-providers)
  - [Connection Types](#connection-types)
- [Tools](#tools)
  - [Tool Types](#tool-types)
  - [MCP Tools](#mcp-tools)
- [Instructions](#instructions)
- [Handoff Configuration](#handoff-configuration)
- [PowerFx Expressions](#powerfx-expressions)
- [Using AgentFactory](#using-agentfactory)
- [Complete Examples](#complete-examples)
- [References](#references)

## Basic Structure

A declarative agent YAML file defines an agent's configuration in a structured format:

```yaml
# Required: Agent name
name: my_agent

# Required: Model configuration
model:
  provider: OpenAI.Chat
  model_id: gpt-4o
  # ... additional provider-specific settings

# Optional: Agent instructions
instructions: |
  You are a helpful assistant...

# Optional: Tools the agent can use
tools:
  - type: code_interpreter
  - type: mcp
    # ... tool configuration

# Optional: Handoff configuration for multi-agent scenarios
handoff:
  - agent: other_agent
    description: Transfer to specialist
```

## Model Configuration

### Supported Providers

The declarative agents framework supports multiple model providers. Each provider has specific configuration requirements:

#### OpenAI.Chat
Direct OpenAI API integration for chat models.

```yaml
model:
  provider: OpenAI.Chat
  model_id: gpt-4o
  connection:
    type: key
    key: ${env:OPENAI_API_KEY}
  # Optional parameters
  temperature: 0.7
  top_p: 1.0
  max_tokens: 4096
  frequency_penalty: 0.0
  presence_penalty: 0.0
  stop: ["\n\n"]
  seed: 42
```

#### OpenAI.Responses
OpenAI's Responses API for structured outputs.

```yaml
model:
  provider: OpenAI.Responses
  model_id: gpt-4o
  connection:
    type: key
    key: ${env:OPENAI_API_KEY}
```

#### AzureOpenAI.Chat
Azure-hosted OpenAI models for chat.

```yaml
model:
  provider: AzureOpenAI.Chat
  deployment_name: my-gpt4-deployment
  connection:
    type: key
    endpoint: https://my-resource.openai.azure.com
    key: ${env:AZURE_OPENAI_API_KEY}
    api_version: "2024-02-15-preview"
```

#### AzureOpenAI.Responses
Azure-hosted OpenAI with Responses API.

```yaml
model:
  provider: AzureOpenAI.Responses
  deployment_name: my-gpt4-deployment
  connection:
    type: key
    endpoint: https://my-resource.openai.azure.com
    key: ${env:AZURE_OPENAI_API_KEY}
    api_version: "2024-02-15-preview"
```

#### AzureAIInference.Chat
Azure AI Model Inference for chat models.

```yaml
model:
  provider: AzureAIInference.Chat
  model_id: DeepSeek-R1
  connection:
    type: key
    endpoint: https://my-endpoint.services.ai.azure.com/models
    key: ${env:AZURE_AI_API_KEY}
```

#### AzureAIFoundry.Chat
Azure AI Foundry (formerly Azure AI Studio) integration.

```yaml
model:
  provider: AzureAIFoundry.Chat
  model_id: gpt-4o
  connection:
    type: key
    endpoint: https://my-project.services.ai.azure.com
    key: ${env:AZURE_AI_FOUNDRY_KEY}
```

#### AzureAIAgent
Azure AI Agent Service for managed agent deployments.

```yaml
model:
  provider: AzureAIAgent
  agent_id: my-agent-id
  connection:
    type: key
    endpoint: https://my-project.services.ai.azure.com
    key: ${env:AZURE_AI_AGENT_KEY}
```

#### Anthropic.Chat
Anthropic Claude models integration.

```yaml
model:
  provider: Anthropic.Chat
  model_id: claude-sonnet-4-20250514
  connection:
    type: key
    key: ${env:ANTHROPIC_API_KEY}
  # Optional parameters
  temperature: 0.7
  max_tokens: 4096
  top_p: 1.0
  top_k: 40
```

#### Ollama.Chat
Local Ollama models for self-hosted inference.

```yaml
model:
  provider: Ollama.Chat
  model_id: llama3.2
  connection:
    type: anonymous
    host: http://localhost:11434
```

#### GitHub.Chat
GitHub Models integration.

```yaml
model:
  provider: GitHub.Chat
  model_id: openai/gpt-4o
  connection:
    type: key
    key: ${env:GITHUB_TOKEN}
```

### Connection Types

Connections define how to authenticate with model providers:

#### Remote Connection
For server-to-server connections with explicit configuration:

```yaml
connection:
  type: remote
  endpoint: https://api.example.com
  # Additional provider-specific settings
```

#### Key-based Connection
API key authentication:

```yaml
connection:
  type: key
  key: ${env:API_KEY}
  # Optional: endpoint for Azure services
  endpoint: https://my-resource.openai.azure.com
  api_version: "2024-02-15-preview"
```

#### Reference Connection
Reference to a pre-configured connection by name:

```yaml
connection:
  type: reference
  name: my-preconfigured-connection
```

#### Anonymous Connection
No authentication required (for local services):

```yaml
connection:
  type: anonymous
  host: http://localhost:11434
```

### Environment Variable Substitution

Use `${env:VARIABLE_NAME}` syntax to reference environment variables:

```yaml
connection:
  type: key
  key: ${env:OPENAI_API_KEY}
  endpoint: ${env:AZURE_ENDPOINT}
```

## Tools

Tools extend agent capabilities beyond conversation. The framework supports various tool types for different use cases.

### Tool Types

#### Code Interpreter
Enables the agent to execute Python code:

```yaml
tools:
  - type: code_interpreter
```

#### File Search
Enables searching through uploaded files:

```yaml
tools:
  - type: file_search
    vector_store_ids:
      - vs_abc123
```

#### Bing Grounding
Enables web search via Bing (Azure AI Agent only):

```yaml
tools:
  - type: bing_grounding
    connection:
      type: key
      key: ${env:BING_API_KEY}
```

#### Microsoft Fabric
Enables data integration with Microsoft Fabric (Azure AI Agent only):

```yaml
tools:
  - type: microsoft_fabric
    connection:
      type: key
      key: ${env:FABRIC_API_KEY}
```

#### SharePoint Grounding
Enables searching SharePoint content (Azure AI Agent only):

```yaml
tools:
  - type: sharepoint_grounding
    connection:
      type: key
      key: ${env:SHAREPOINT_API_KEY}
```

#### Azure AI Search
Enables Azure AI Search integration (Azure AI Agent only):

```yaml
tools:
  - type: azure_ai_search
    connection:
      type: key
      endpoint: ${env:SEARCH_ENDPOINT}
      key: ${env:SEARCH_API_KEY}
    index_name: my-search-index
    # Optional settings
    query_type: semantic  # simple, full, semantic, vector, hybrid
    top_k: 5
```

#### Azure Functions
Enables calling Azure Functions:

```yaml
tools:
  - type: azure_function
    name: my_function
    description: Processes data
    input_queue:
      storage_service_endpoint: ${env:STORAGE_ENDPOINT}
      queue_name: input-queue
    output_queue:
      storage_service_endpoint: ${env:STORAGE_ENDPOINT}
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
  - type: openapi
    name: weather_api
    description: Get weather information
    spec_url: https://api.weather.com/openapi.json
    # Or inline spec
    spec:
      openapi: "3.0.0"
      info:
        title: Weather API
        version: "1.0"
      paths:
        /weather:
          get:
            operationId: getWeather
            parameters:
              - name: city
                in: query
                required: true
                schema:
                  type: string
```

### MCP Tools

[Model Context Protocol (MCP)](https://modelcontextprotocol.io/) tools provide a standardized way to extend agent capabilities:

#### Basic MCP Configuration

```yaml
tools:
  - type: mcp
    name: filesystem
    description: File system operations
    command: npx
    args:
      - "-y"
      - "@anthropic/mcp-filesystem"
      - "/allowed/path"
```

#### MCP with Environment Variables

```yaml
tools:
  - type: mcp
    name: github
    description: GitHub operations
    command: npx
    args:
      - "-y"
      - "@anthropic/mcp-github"
    env:
      GITHUB_TOKEN: ${env:GITHUB_TOKEN}
```

#### MCP Tool Approval Modes

Control how tools are executed with different approval modes:

##### Automatic Approval
Tools execute without user confirmation:

```yaml
tools:
  - type: mcp
    name: calculator
    approval_mode: automatic
    command: python
    args: ["-m", "mcp_calculator"]
```

##### Manual Approval
Requires explicit user approval for each tool call:

```yaml
tools:
  - type: mcp
    name: file_writer
    approval_mode: manual
    command: npx
    args: ["-y", "@anthropic/mcp-filesystem"]
```

##### Accept List Approval
Automatically approve only specific tools, require manual approval for others:

```yaml
tools:
  - type: mcp
    name: mixed_tools
    approval_mode:
      mode: accept_list
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
  - type: mcp
    name: mostly_safe
    approval_mode:
      mode: deny_list
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
  - type: mcp
    name: remote_tools
    description: Remote MCP server tools
    url: https://mcp-server.example.com/sse
    headers:
      Authorization: Bearer ${env:MCP_TOKEN}
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
  Current date: ${Now()}
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

### Handoff with Conditions

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
name: main_agent
model:
  provider: OpenAI.Chat
  model_id: gpt-4o
  connection:
    type: key
    key: ${env:OPENAI_API_KEY}
instructions: Route customer inquiries to appropriate specialists.
handoff:
  - agent: ${file:agents/billing_agent.yaml}
    description: Handle billing inquiries
  - agent: ${file:agents/tech_agent.yaml}
    description: Handle technical issues
```

## PowerFx Expressions

The framework supports [PowerFx](https://learn.microsoft.com/en-us/power-platform/power-fx/overview) expressions for dynamic configuration values.

### Basic Expressions

```yaml
instructions: |
  Current timestamp: ${Now()}
  Today's date: ${Today()}
  Formatted date: ${Text(Today(), "yyyy-mm-dd")}
```

### Context Variables

Access context data passed at runtime:

```yaml
instructions: |
  User: ${context.user_name}
  Session ID: ${context.session_id}
  Priority: ${context.priority_level}
```

### Conditional Logic

```yaml
instructions: |
  ${If(context.is_premium, "You are a premium customer with priority support.", "Welcome! Consider upgrading to premium for faster support.")}
```

### String Operations

```yaml
instructions: |
  Greeting: ${Concatenate("Hello, ", context.user_name, "!")}
  Uppercase name: ${Upper(context.user_name)}
  Name length: ${Len(context.user_name)}
```

## Using AgentFactory

The `AgentFactory` class provides the primary interface for loading and instantiating declarative agents.

### Basic Usage

```python
from declarative_agents import AgentFactory
import asyncio

async def main():
    # Load agent from YAML file
    agent = await AgentFactory.create_agent("path/to/agent.yaml")
    
    # Use the agent
    response = await agent.run("Hello, how can you help me?")
    print(response)

asyncio.run(main())
```

### With Runtime Context

```python
from declarative_agents import AgentFactory
import asyncio

async def main():
    context = {
        "user_name": "John",
        "session_id": "abc123",
        "subscription_tier": "premium"
    }
    
    agent = await AgentFactory.create_agent(
        "path/to/agent.yaml",
        context=context
    )
    
    response = await agent.run("What services do I have access to?")
    print(response)

asyncio.run(main())
```

### AgentFactory Parameters

The `AgentFactory.create_agent()` method accepts the following parameters:

| Parameter | Type | Description |
|-----------|------|-------------|
| `path` | `str` | Path to the YAML agent definition file |
| `context` | `dict` | Runtime context variables for PowerFx expressions |
| `tool_approval_handler` | `callable` | Custom handler for MCP tool approval |
| `connections` | `dict` | Pre-configured connection references |

### Custom Tool Approval Handler

```python
from declarative_agents import AgentFactory
import asyncio

async def approval_handler(tool_name: str, tool_args: dict) -> bool:
    """Custom approval logic for tool execution."""
    dangerous_tools = ["delete_file", "execute_command"]
    if tool_name in dangerous_tools:
        user_input = input(f"Allow {tool_name} with args {tool_args}? (y/n): ")
        return user_input.lower() == 'y'
    return True

async def main():
    agent = await AgentFactory.create_agent(
        "path/to/agent.yaml",
        tool_approval_handler=approval_handler
    )
    
    response = await agent.run("Delete the temporary files")
    print(response)

asyncio.run(main())
```

## Complete Examples

### Customer Service Agent

```yaml
name: customer_service_agent
description: Handles customer inquiries and support requests

model:
  provider: OpenAI.Chat
  model_id: gpt-4o
  connection:
    type: key
    key: ${env:OPENAI_API_KEY}
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
  
  Current time: ${Now()}
  Customer name: ${context.customer_name}

tools:
  - type: openapi
    name: order_api
    description: Look up order information
    spec_url: https://api.techcorp.com/orders/openapi.json

handoff:
  - agent: billing_specialist
    description: Transfer to billing for payment issues
  - agent: technical_support
    description: Transfer to tech support for product issues
```

### Research Assistant with MCP

```yaml
name: research_assistant
description: Helps with research tasks using various tools

model:
  provider: Anthropic.Chat
  model_id: claude-sonnet-4-20250514
  connection:
    type: key
    key: ${env:ANTHROPIC_API_KEY}
  max_tokens: 4096

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
  - type: mcp
    name: filesystem
    description: Read local documents
    approval_mode: automatic
    command: npx
    args:
      - "-y"
      - "@anthropic/mcp-filesystem"
      - "${context.allowed_path}"
  
  - type: mcp
    name: web_search
    description: Search the web
    approval_mode:
      mode: accept_list
      tools:
        - search
        - fetch_page
    command: npx
    args:
      - "-y"
      - "@anthropic/mcp-web-search"
    env:
      SEARCH_API_KEY: ${env:SEARCH_API_KEY}
```

### Multi-Agent Orchestrator

```yaml
name: orchestrator
description: Routes requests to specialized agents

model:
  provider: AzureOpenAI.Chat
  deployment_name: gpt-4o
  connection:
    type: key
    endpoint: ${env:AZURE_OPENAI_ENDPOINT}
    key: ${env:AZURE_OPENAI_KEY}
    api_version: "2024-02-15-preview"

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

### Azure AI Agent with Tools

```yaml
name: azure_enterprise_agent
description: Enterprise agent with Azure AI capabilities

model:
  provider: AzureAIAgent
  agent_id: ${env:AZURE_AGENT_ID}
  connection:
    type: key
    endpoint: ${env:AZURE_AI_ENDPOINT}
    key: ${env:AZURE_AI_KEY}

instructions: |
  You are an enterprise assistant with access to company data.
  Use available tools to answer questions about company information.

tools:
  - type: azure_ai_search
    connection:
      type: key
      endpoint: ${env:SEARCH_ENDPOINT}
      key: ${env:SEARCH_KEY}
    index_name: company-knowledge-base
    query_type: semantic
    top_k: 10

  - type: bing_grounding
    connection:
      type: key
      key: ${env:BING_KEY}

  - type: code_interpreter
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

## Schema Version

This specification is for declarative agents schema version 1.0.

For the latest updates and additional examples, see the [agent-framework repository](https://github.com/microsoft/agent-framework).
