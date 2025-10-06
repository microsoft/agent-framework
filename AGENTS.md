# Microsoft Agent Framework - Developer Usage Guide

A comprehensive guide for engineers new to the Microsoft Agent Framework for Python.

## Table of Contents

- [Overview](#overview)
- [Architecture and Key Concepts](#architecture-and-key-concepts)
- [Developer Environment Setup](#developer-environment-setup)
- [Quick Start Guide](#quick-start-guide)
- [Core Concepts](#core-concepts)
  - [Agents](#agents)
  - [Chat Clients](#chat-clients)
  - [Tools and Functions](#tools-and-functions)
  - [Workflows](#workflows)
- [Installation and Configuration](#installation-and-configuration)
- [Creating Your First Agent](#creating-your-first-agent)
- [Working with Chat Clients](#working-with-chat-clients)
- [Using Tools and Functions](#using-tools-and-functions)
- [Building Workflows](#building-workflows)
- [Multi-Agent Orchestration](#multi-agent-orchestration)
- [Middleware and Context Providers](#middleware-and-context-providers)
- [Thread Management](#thread-management)
- [DevUI for Testing and Debugging](#devui-for-testing-and-debugging)
- [Common Examples and Usage Scenarios](#common-examples-and-usage-scenarios)
- [Troubleshooting Guide](#troubleshooting-guide)
- [Additional Resources](#additional-resources)

---

## Overview

The Microsoft Agent Framework is a flexible, production-ready framework for building, orchestrating, and deploying AI agents and multi-agent systems. It provides a consistent programming model across Python and .NET, enabling developers to create sophisticated AI applications with ease.

### Python Folder Structure

```
python/
├── packages/              # Core and integration packages
│   ├── core/             # Main agent-framework-core package
│   ├── azure-ai/         # Azure AI Foundry integration
│   ├── copilotstudio/    # Microsoft Copilot Studio integration
│   ├── devui/            # Development UI for testing agents
│   ├── a2a/              # Agent-to-Agent communication
│   ├── mem0/             # Memory integration
│   └── redis/            # Redis backend support
├── samples/              # Working code examples
│   └── getting_started/  # Categorized samples by feature
│       ├── agents/       # Agent examples by provider
│       ├── chat_client/  # Direct chat client usage
│       ├── workflows/    # Workflow orchestration patterns
│       ├── middleware/   # Middleware examples
│       ├── context_providers/  # Context provider patterns
│       ├── threads/      # Thread management
│       ├── multimodal_input/   # Image and multimodal examples
│       └── observability/      # Telemetry and monitoring
├── tests/                # Unit and integration tests
├── docs/                 # Additional documentation
├── README.md             # Quick start guide
└── DEV_SETUP.md          # Developer setup instructions
```

### Documentation Structure

- **README.md**: Quick start guide with installation and basic examples
- **DEV_SETUP.md**: Comprehensive developer setup and tooling guide
- **packages/core/README.md**: Core package documentation with API overview
- **packages/devui/README.md**: DevUI sample app documentation
- **samples/**: Organized examples with individual README files per category
- **docs/**: Design documents, specifications, and architectural decision records

### Key Highlights

- **Flexible Agent Framework**: Build, orchestrate, and deploy AI agents and multi-agent systems
- **Multi-Agent Orchestration**: Group chat, sequential, concurrent, and handoff patterns
- **Plugin Ecosystem**: Extend with native functions, OpenAPI, Model Context Protocol (MCP), and more
- **LLM Support**: OpenAI, Azure OpenAI, Azure AI Foundry, Anthropic, Ollama, and more
- **Runtime Support**: In-process and distributed agent execution
- **Multimodal**: Text, vision, and function calling
- **Cross-Platform**: Python (3.10+) and .NET implementations
- **Production-Ready**: Comprehensive observability, middleware, and error handling

---

## Architecture and Key Concepts

### Framework Architecture

The Agent Framework follows a layered architecture:

```
┌─────────────────────────────────────────────────────────────┐
│                    Application Layer                         │
│  (Your agents, workflows, and business logic)                │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│                 Agent Framework Core                         │
│  • ChatAgent         • Workflows        • Middleware         │
│  • Tools/Functions   • Context Providers • Observability     │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│                   Chat Client Layer                          │
│  • OpenAI            • Azure OpenAI     • Azure AI           │
│  • Anthropic         • Ollama           • Custom Clients     │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│                   LLM Services                               │
│  (OpenAI API, Azure OpenAI, Azure AI Foundry, etc.)         │
└─────────────────────────────────────────────────────────────┘
```

### Core Components

**1. Agents**
- `ChatAgent`: Primary agent implementation for conversational AI
- Supports tools, context providers, middleware, streaming responses
- Configurable instructions, model parameters, and response formats

**2. Chat Clients**
- Protocol-based interface for LLM communication
- Built-in clients: OpenAI, Azure OpenAI, Azure AI, Anthropic, Ollama
- Support for assistants API, chat completions, structured responses

**3. Tools and Functions**
- Python functions decorated with type hints become agent tools
- Automatic schema generation from function signatures
- Support for async functions and streaming responses

**4. Workflows**
- Directed graph-based orchestration of agents and executors
- Sequential, concurrent, and conditional execution patterns
- Checkpointing, human-in-the-loop, and sub-workflow composition

**5. Middleware**
- Intercept and modify agent runs, function calls, and chat requests
- Function-based or class-based implementations
- Use cases: logging, security, validation, result transformation

**6. Context Providers**
- Inject dynamic context into agent conversations
- Memory integration (Mem0), custom context sources
- Automatic context refresh and management

### Key Design Principles

1. **Protocol-Driven**: Uses Python protocols for extensibility without tight coupling
2. **Async-First**: Built on asyncio for efficient concurrent operations
3. **Type-Safe**: Leverages Pydantic for validation and serialization
4. **Observable**: OpenTelemetry integration for traces, logs, and metrics
5. **Modular**: Install only what you need with selective package installation
6. **Developer-Friendly**: Intuitive APIs with comprehensive examples

---

## Developer Environment Setup

### System Requirements

- **Python**: 3.10 or higher
- **Operating Systems**: Windows, macOS, Linux (including WSL)
- **Package Manager**: pip or uv (recommended for development)

### Installation of Development Tools

#### Using uv (Recommended for Contributors)

[uv](https://github.com/astral-sh/uv) is a fast Python package manager that simplifies dependency management.

**Windows (PowerShell):**
```powershell
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```

**macOS/Linux:**
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

**Setup Development Environment:**
```bash
# Navigate to python directory
cd python

# Install Python versions (for testing across versions)
uv python install 3.10 3.11 3.12 3.13

# Create virtual environment and install dependencies
uv run poe setup -p 3.10  # or 3.11, 3.12, 3.13

# Install pre-commit hooks
uv run poe pre-commit-install
```

#### Using pip (For Regular Usage)

```bash
# Create virtual environment
python -m venv .venv

# Activate virtual environment
# On Windows:
.venv\Scripts\activate
# On macOS/Linux:
source .venv/bin/activate

# Install Agent Framework
pip install agent-framework --pre
```

### VSCode Setup

1. Install the [Python extension](https://marketplace.visualstudio.com/items?itemName=ms-python.python)
2. Open the `python` folder as your workspace root
3. Select the virtual environment (`.venv`) as your Python interpreter
   - Press `Ctrl+Shift+P` → "Python: Select Interpreter"
4. Configure `.env` file for API keys (see Configuration section)

### WSL Users

- Clone repository to your WSL home directory (e.g., `~/workspace`)
- Avoid `/mnt/c/` paths for better performance
- Install WSL extension for VSCode

### Development Tools

The framework uses:
- **[poethepoet](https://github.com/nat-n/poethepoet)**: Task runner (commands via `uv run poe`)
- **[ruff](https://github.com/astral-sh/ruff)**: Linting and formatting
- **[pytest](https://pytest.org/)**: Testing framework
- **[pyright](https://github.com/microsoft/pyright)**: Type checking
- **[pre-commit](https://pre-commit.com/)**: Git hooks for code quality

### Development Commands

```bash
# Format code
uv run poe fmt

# Run linters
uv run poe lint

# Type checking
uv run poe pyright

# Run tests with coverage
uv run poe test

# Run all checks (before committing)
uv run poe check

# Build documentation
uv run poe docs-build

# Serve docs locally
uv run poe docs-serve
```

---

## Quick Start Guide

### 1. Install the Framework

```bash
# Full installation (includes all integrations)
pip install agent-framework --pre

# Core only (lightweight, includes OpenAI/Azure OpenAI)
pip install agent-framework-core --pre

# Core + specific integrations
pip install agent-framework-azure-ai --pre
pip install agent-framework-copilotstudio --pre
```

### 2. Set Up API Keys

Create a `.env` file in your project root:

```bash
# OpenAI
OPENAI_API_KEY=sk-...
OPENAI_CHAT_MODEL_ID=gpt-4o

# Azure OpenAI
AZURE_OPENAI_API_KEY=...
AZURE_OPENAI_ENDPOINT=https://...
AZURE_OPENAI_CHAT_DEPLOYMENT_NAME=gpt-4o

# Azure AI Foundry
AZURE_AI_PROJECT_ENDPOINT=https://...
AZURE_AI_MODEL_DEPLOYMENT_NAME=gpt-4o
```

### 3. Create Your First Agent

```python
import asyncio
from agent_framework import ChatAgent
from agent_framework.openai import OpenAIChatClient

async def main():
    agent = ChatAgent(
        chat_client=OpenAIChatClient(),
        instructions="You are a helpful assistant."
    )
    
    result = await agent.run("Hello! What can you help me with?")
    print(result)

asyncio.run(main())
```

### 4. Run with DevUI (Optional)

Test your agents interactively:

```bash
# Install DevUI
pip install agent-framework-devui --pre

# Launch programmatically
python
>>> from agent_framework.devui import serve
>>> from agent_framework import ChatAgent
>>> from agent_framework.openai import OpenAIChatClient
>>> 
>>> agent = ChatAgent(chat_client=OpenAIChatClient(), name="MyAgent")
>>> serve(entities=[agent], auto_open=True)
```

---

## Core Concepts

### Agents

An **Agent** is an autonomous entity that can interact with language models, use tools, maintain conversation state, and coordinate with other agents.

#### ChatAgent

The primary agent implementation in the framework:

```python
from agent_framework import ChatAgent
from agent_framework.openai import OpenAIChatClient

agent = ChatAgent(
    chat_client=OpenAIChatClient(),
    name="MyAgent",
    description="A helpful assistant",
    instructions="You are a helpful AI assistant. Be concise and friendly.",
    tools=[],                    # List of functions/tools
    context_providers=[],        # Dynamic context injection
    middleware=[],               # Request/response interceptors
    temperature=0.7,
    max_tokens=1000,
    response_format=None,        # For structured outputs
)

# Run the agent
result = await agent.run("Your message here")
print(result.text)

# Stream responses
async for event in agent.run_stream("Your message here"):
    if hasattr(event, 'text'):
        print(event.text, end='', flush=True)
```

#### Agent Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `chat_client` | ChatClientProtocol | The LLM client to use (required) |
| `instructions` | str | System instructions for the agent |
| `name` | str | Agent name (for identification) |
| `description` | str | Brief description of agent's purpose |
| `tools` | list | Functions/tools the agent can use |
| `context_providers` | list | Dynamic context injection |
| `middleware` | list | Request/response interceptors |
| `temperature` | float | Randomness (0.0-2.0) |
| `max_tokens` | int | Maximum response length |
| `top_p` | float | Nucleus sampling parameter |
| `frequency_penalty` | float | Repetition penalty |
| `presence_penalty` | float | Topic diversity penalty |
| `response_format` | type[BaseModel] | Pydantic model for structured output |

#### Agent Lifecycle

```python
# 1. Initialize agent with chat client
agent = ChatAgent(chat_client=OpenAIChatClient())

# 2. Run agent (single invocation)
result = await agent.run("Hello")

# 3. Continue conversation (maintains history)
result2 = await agent.run("Tell me more")

# 4. Stream responses for real-time output
async for event in agent.run_stream("Explain quantum computing"):
    # Process streaming events
    pass
```

---

### Chat Clients

Chat clients provide the interface between agents and language model services.

#### Built-in Chat Clients

**OpenAI:**
```python
from agent_framework.openai import (
    OpenAIChatClient,        # Chat completions
    OpenAIResponsesClient,   # Structured responses
    OpenAIAssistantsClient,  # Assistants API
)

# Basic usage
client = OpenAIChatClient(
    model="gpt-4o",
    api_key="sk-...",  # Optional: uses OPENAI_API_KEY env var
)

# With explicit configuration
client = OpenAIChatClient(
    model="gpt-4o",
    api_key="your-key",
    organization="your-org",
    timeout=30.0,
)
```

**Azure OpenAI:**
```python
from agent_framework.azure import (
    AzureOpenAIChatClient,
    AzureOpenAIResponsesClient,
    AzureOpenAIAssistantsClient,
)

client = AzureOpenAIChatClient(
    deployment_name="gpt-4o",
    endpoint="https://your-resource.openai.azure.com",
    api_key="your-key",
    api_version="2024-02-15-preview",
)
```

**Azure AI Foundry:**
```python
from agent_framework.azure_ai import AzureAIChatClient

client = AzureAIChatClient(
    endpoint="https://your-project.cognitiveservices.azure.com",
    deployment_name="gpt-4o",
    # Uses Azure default credentials
)
```

**Anthropic (via OpenAI-compatible API):**
```python
from agent_framework.openai import OpenAIChatClient

client = OpenAIChatClient(
    model="claude-3-5-sonnet-20241022",
    api_key="your-anthropic-key",
    base_url="https://api.anthropic.com/v1",
)
```

#### Direct Chat Client Usage

You can use chat clients directly without agents:

```python
from agent_framework import ChatMessage, Role
from agent_framework.openai import OpenAIChatClient

client = OpenAIChatClient()

messages = [
    ChatMessage(role=Role.SYSTEM, text="You are a helpful assistant."),
    ChatMessage(role=Role.USER, text="Write a haiku about Python."),
]

response = await client.get_response(messages)
print(response.messages[0].text)
```

#### Creating Custom Chat Clients

Implement the `ChatClientProtocol`:

```python
from typing import Any, AsyncIterator
from agent_framework import (
    ChatClientProtocol,
    ChatMessage,
    ChatResponse,
    ChatOptions,
)

class CustomChatClient:
    """Custom chat client implementation."""
    
    async def get_response(
        self,
        messages: list[ChatMessage],
        options: ChatOptions | None = None,
        **kwargs: Any,
    ) -> ChatResponse:
        """Get a chat response."""
        # Your implementation
        pass
    
    async def get_response_stream(
        self,
        messages: list[ChatMessage],
        options: ChatOptions | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[ChatResponse]:
        """Get a streaming chat response."""
        # Your implementation
        pass
```

---

### Tools and Functions

Tools enable agents to interact with external systems and perform actions.

#### Basic Function Tools

Any Python function can become a tool:

```python
from typing import Annotated
from pydantic import Field

def get_weather(
    location: Annotated[str, Field(description="City name or coordinates")],
    unit: Annotated[str, Field(description="Temperature unit (celsius/fahrenheit)")] = "celsius",
) -> str:
    """Get the current weather for a location."""
    # Implementation
    return f"Weather in {location}: 22°C, sunny"

# Add to agent
agent = ChatAgent(
    chat_client=OpenAIChatClient(),
    tools=[get_weather],
)
```

#### Async Function Tools

```python
async def search_database(query: Annotated[str, "Search query"]) -> list[dict]:
    """Search the database."""
    # Async implementation
    await asyncio.sleep(0.1)  # Simulate DB query
    return [{"id": 1, "title": "Result"}]

agent = ChatAgent(
    chat_client=OpenAIChatClient(),
    tools=[search_database],
)
```

#### Type Hints and Documentation

The framework automatically generates tool schemas from:
- Function docstrings (description)
- Type hints (parameter types)
- `Annotated` metadata (parameter descriptions)
- Default values (optional parameters)

```python
from typing import Annotated
from pydantic import Field

def send_email(
    to: Annotated[str, Field(description="Recipient email address")],
    subject: Annotated[str, Field(description="Email subject")],
    body: Annotated[str, Field(description="Email body content")],
    cc: Annotated[list[str] | None, Field(description="CC recipients")] = None,
) -> str:
    """Send an email to the specified recipient.
    
    This function sends an email using the configured email service.
    Returns a confirmation message.
    """
    # Implementation
    return f"Email sent to {to}"
```

#### Complex Return Types

Tools can return structured data:

```python
from pydantic import BaseModel
from datetime import datetime

class SearchResult(BaseModel):
    title: str
    url: str
    snippet: str
    timestamp: datetime

def web_search(query: str) -> list[SearchResult]:
    """Search the web and return results."""
    return [
        SearchResult(
            title="Example Result",
            url="https://example.com",
            snippet="Sample snippet...",
            timestamp=datetime.now(),
        )
    ]
```

#### Tool Choice Control

```python
# Let the model decide when to use tools
result = await agent.run("What's the weather?", tool_choice="auto")

# Force tool usage
result = await agent.run("What's the weather?", tool_choice="required")

# Disable tools for this run
result = await agent.run("Just chat with me", tool_choice="none")
```

---

### Workflows

Workflows orchestrate multiple agents and executors in complex patterns.

#### Basic Workflow Structure

```python
from agent_framework.workflows import WorkflowBuilder, Executor

# Define executors
@Executor
async def process_input(data: str) -> str:
    return f"Processed: {data}"

@Executor
async def format_output(data: str) -> str:
    return f"Formatted: {data}"

# Build workflow
workflow = (
    WorkflowBuilder()
    .add_edge(process_input, format_output)
    .build()
)

# Run workflow
result = await workflow.run("input data")
```

#### Sequential Execution

```python
from agent_framework import ChatAgent
from agent_framework.workflows import SequentialBuilder

# Create specialized agents
writer = ChatAgent(
    chat_client=OpenAIChatClient(),
    name="Writer",
    instructions="Generate creative content",
)

editor = ChatAgent(
    chat_client=OpenAIChatClient(),
    name="Editor",
    instructions="Review and improve content",
)

# Sequential workflow
workflow = (
    SequentialBuilder()
    .add_agent(writer)
    .add_agent(editor)
    .build()
)

result = await workflow.run("Write a blog post about AI")
```

#### Concurrent Execution

```python
from agent_framework.workflows import ConcurrentBuilder

# Create specialized agents
researcher = ChatAgent(name="Researcher", ...)
analyst = ChatAgent(name="Analyst", ...)
summarizer = ChatAgent(name="Summarizer", ...)

# Concurrent workflow
workflow = (
    ConcurrentBuilder()
    .add_agent(researcher)
    .add_agent(analyst)
    .add_agent(summarizer)
    .build()
)

# All agents run in parallel
results = await workflow.run("Analyze market trends")
```

#### Conditional Routing

```python
from agent_framework.workflows import WorkflowBuilder, EdgeCondition

async def classify_content(text: str) -> str:
    # Classification logic
    return "spam" if "buy now" in text.lower() else "ham"

async def handle_spam(text: str) -> str:
    return "Blocked spam message"

async def handle_ham(text: str) -> str:
    return "Processing legitimate message"

workflow = (
    WorkflowBuilder()
    .add_edge(
        classify_content,
        handle_spam,
        condition=lambda result: result == "spam"
    )
    .add_edge(
        classify_content,
        handle_ham,
        condition=lambda result: result == "ham"
    )
    .build()
)
```

#### Workflow Events and Streaming

```python
# Stream workflow events
async for event in workflow.run_stream("input"):
    if isinstance(event, ExecutorInvokeEvent):
        print(f"Starting: {event.executor_name}")
    elif isinstance(event, ExecutorCompletedEvent):
        print(f"Completed: {event.executor_name}")
    elif isinstance(event, WorkflowOutputEvent):
        print(f"Final result: {event.result}")
```

---

## Installation and Configuration

### Package Installation Options

#### Option 1: Full Installation (Recommended for Getting Started)

Install everything with a single command:

```bash
pip install agent-framework --pre
```

This includes:
- Core framework
- OpenAI and Azure OpenAI support
- Azure AI Foundry integration
- Microsoft Copilot Studio integration
- Workflows and orchestration
- DevUI for testing

#### Option 2: Selective Installation (Recommended for Production)

Install only what you need:

```bash
# Core only (includes OpenAI/Azure OpenAI)
pip install agent-framework-core --pre

# Core + Azure AI
pip install agent-framework-azure-ai --pre

# Core + Copilot Studio
pip install agent-framework-copilotstudio --pre

# Core + Redis backend
pip install agent-framework-redis --pre

# Core + Mem0 memory integration
pip install agent-framework-mem0 --pre

# DevUI for testing
pip install agent-framework-devui --pre
```

#### Option 3: Development Installation

For contributing to the framework:

```bash
# Clone repository
git clone https://github.com/microsoft/agent-framework.git
cd agent-framework/python

# Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# Setup development environment
uv run poe setup -p 3.10

# Install pre-commit hooks
uv run poe pre-commit-install
```

### Configuration Methods

#### Method 1: Environment Variables

Create a `.env` file in your project root:

```bash
# OpenAI Configuration
OPENAI_API_KEY=sk-...
OPENAI_CHAT_MODEL_ID=gpt-4o
OPENAI_RESPONSES_MODEL_ID=gpt-4o

# Azure OpenAI Configuration
AZURE_OPENAI_API_KEY=...
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com
AZURE_OPENAI_CHAT_DEPLOYMENT_NAME=gpt-4o
AZURE_OPENAI_RESPONSES_DEPLOYMENT_NAME=gpt-4o
AZURE_OPENAI_API_VERSION=2024-02-15-preview

# Azure AI Foundry Configuration
AZURE_AI_PROJECT_ENDPOINT=https://your-project.cognitiveservices.azure.com
AZURE_AI_MODEL_DEPLOYMENT_NAME=gpt-4o

# Observability (Optional)
ENABLE_OTEL=true
ENABLE_SENSITIVE_DATA=false  # Don't enable in production
OTLP_ENDPOINT=http://localhost:4317
APPLICATIONINSIGHTS_CONNECTION_STRING=...
```

The framework automatically loads `.env` files using pydantic-settings.

#### Method 2: Explicit Configuration

Pass configuration directly to chat clients:

```python
from agent_framework.azure import AzureOpenAIChatClient

client = AzureOpenAIChatClient(
    deployment_name="gpt-4o",
    endpoint="https://your-resource.openai.azure.com",
    api_key="your-api-key",
    api_version="2024-02-15-preview",
)
```

#### Method 3: Custom .env File Path

Load configuration from a specific file:

```python
from agent_framework.openai import OpenAIChatClient

client = OpenAIChatClient(env_file_path="config/production.env")
```

### Azure Authentication

#### Using API Keys

```python
from agent_framework.azure import AzureOpenAIChatClient

client = AzureOpenAIChatClient(
    deployment_name="gpt-4o",
    endpoint="https://your-resource.openai.azure.com",
    api_key="your-api-key",
)
```

#### Using Azure Default Credentials (Recommended)

```bash
# Install Azure Identity
pip install azure-identity
```

```python
from azure.identity import DefaultAzureCredential
from agent_framework.azure_ai import AzureAIChatClient

# Uses DefaultAzureCredential automatically
client = AzureAIChatClient(
    endpoint="https://your-project.cognitiveservices.azure.com",
    deployment_name="gpt-4o",
    # credential is optional; uses DefaultAzureCredential if not provided
)
```

---

## Creating Your First Agent

### Step-by-Step Tutorial

#### 1. Install Required Package

```bash
pip install agent-framework --pre
```

#### 2. Create Configuration File

Create `.env`:

```bash
OPENAI_API_KEY=sk-...
OPENAI_CHAT_MODEL_ID=gpt-4o
```

#### 3. Create Your Agent Script

Create `my_first_agent.py`:

```python
import asyncio
from agent_framework import ChatAgent
from agent_framework.openai import OpenAIChatClient

async def main():
    # Create a chat client
    chat_client = OpenAIChatClient()
    
    # Create an agent
    agent = ChatAgent(
        chat_client=chat_client,
        name="AssistantBot",
        description="A helpful AI assistant",
        instructions="""
        You are a friendly and helpful AI assistant.
        Provide clear, concise, and accurate responses.
        If you're unsure about something, admit it.
        """,
    )
    
    # Run the agent
    result = await agent.run("Hello! Can you help me understand AI agents?")
    print(result.text)

# Run the async function
if __name__ == "__main__":
    asyncio.run(main())
```

#### 4. Run Your Agent

```bash
python my_first_agent.py
```

### Adding Conversation History

Agents maintain conversation context automatically:

```python
async def main():
    agent = ChatAgent(
        chat_client=OpenAIChatClient(),
        instructions="You are a helpful assistant.",
    )
    
    # First message
    result1 = await agent.run("My name is Alice.")
    print(result1.text)
    # Output: "Hello Alice! How can I help you today?"
    
    # Follow-up (agent remembers context)
    result2 = await agent.run("What's my name?")
    print(result2.text)
    # Output: "Your name is Alice."
```

### Streaming Responses

Get real-time streaming output:

```python
async def main():
    agent = ChatAgent(
        chat_client=OpenAIChatClient(),
        instructions="You are a helpful assistant.",
    )
    
    # Stream response
    print("Agent: ", end='', flush=True)
    async for event in agent.run_stream("Write a short poem about Python"):
        if hasattr(event, 'text') and event.text:
            print(event.text, end='', flush=True)
    print()  # New line after streaming completes
```

### Error Handling

```python
async def main():
    agent = ChatAgent(
        chat_client=OpenAIChatClient(),
        instructions="You are a helpful assistant.",
    )
    
    try:
        result = await agent.run("Your message")
        print(result.text)
    except Exception as e:
        print(f"Error: {e}")
        # Handle error appropriately
```

---

## Working with Chat Clients

### OpenAI Chat Client

#### Basic Usage

```python
from agent_framework.openai import OpenAIChatClient

# Using environment variables
client = OpenAIChatClient()

# With explicit configuration
client = OpenAIChatClient(
    model="gpt-4o",
    api_key="sk-...",
    organization="org-...",
)

# Create agent
agent = ChatAgent(chat_client=client)
```

#### Structured Outputs

```python
from pydantic import BaseModel
from agent_framework.openai import OpenAIResponsesClient

class WeatherInfo(BaseModel):
    location: str
    temperature: float
    conditions: str
    humidity: int

client = OpenAIResponsesClient(model="gpt-4o")
agent = ChatAgent(
    chat_client=client,
    response_format=WeatherInfo,
)

result = await agent.run("What's the weather in Seattle?")
weather = result.parsed  # WeatherInfo instance
print(f"{weather.location}: {weather.temperature}°C, {weather.conditions}")
```

#### Assistants API

```python
from agent_framework.openai import OpenAIAssistantsClient

client = OpenAIAssistantsClient(
    model="gpt-4o",
    assistant_id="asst_...",  # Optional: use existing assistant
)

agent = ChatAgent(
    chat_client=client,
    instructions="You are a code expert.",
    tools=[],  # Assistants API supports built-in tools
)
```

### Azure OpenAI Chat Client

```python
from agent_framework.azure import AzureOpenAIChatClient

client = AzureOpenAIChatClient(
    deployment_name="gpt-4o",
    endpoint="https://your-resource.openai.azure.com",
    api_key="your-key",
    api_version="2024-02-15-preview",
)

agent = ChatAgent(chat_client=client)
```

### Azure AI Foundry Chat Client

```python
from agent_framework.azure_ai import AzureAIChatClient

client = AzureAIChatClient(
    endpoint="https://your-project.cognitiveservices.azure.com",
    deployment_name="gpt-4o",
    # Uses Azure Default Credentials
)

agent = ChatAgent(chat_client=client)
```

### Multi-Model Support

Use different models in the same application:

```python
# GPT-4 for complex reasoning
gpt4_client = OpenAIChatClient(model="gpt-4o")
reasoning_agent = ChatAgent(
    chat_client=gpt4_client,
    name="ReasoningAgent",
    instructions="Provide detailed, step-by-step analysis.",
)

# GPT-3.5 for simple tasks
gpt35_client = OpenAIChatClient(model="gpt-3.5-turbo")
simple_agent = ChatAgent(
    chat_client=gpt35_client,
    name="SimpleAgent",
    instructions="Provide quick, concise answers.",
)
```

---

## Using Tools and Functions

### Creating Tool Functions

#### Simple Tools

```python
def get_current_time() -> str:
    """Get the current time."""
    from datetime import datetime
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

agent = ChatAgent(
    chat_client=OpenAIChatClient(),
    tools=[get_current_time],
)
```

#### Tools with Parameters

```python
from typing import Annotated
from pydantic import Field

def calculate_discount(
    price: Annotated[float, Field(description="Original price", gt=0)],
    discount_percent: Annotated[int, Field(description="Discount percentage", ge=0, le=100)],
) -> dict:
    """Calculate the discounted price.
    
    Returns both the discount amount and final price.
    """
    discount_amount = price * (discount_percent / 100)
    final_price = price - discount_amount
    return {
        "original_price": price,
        "discount_percent": discount_percent,
        "discount_amount": discount_amount,
        "final_price": final_price,
    }

agent = ChatAgent(
    chat_client=OpenAIChatClient(),
    tools=[calculate_discount],
)

result = await agent.run("What's 20% off of $100?")
```

#### Async Tools

```python
import httpx

async def fetch_url(url: Annotated[str, "URL to fetch"]) -> str:
    """Fetch content from a URL."""
    async with httpx.AsyncClient() as client:
        response = await client.get(url)
        return response.text[:500]  # Return first 500 chars

agent = ChatAgent(
    chat_client=OpenAIChatClient(),
    tools=[fetch_url],
)
```

### Tool Examples by Category

#### Data Retrieval Tools

```python
async def search_database(
    query: Annotated[str, "Search query"],
    limit: Annotated[int, "Maximum results"] = 10,
) -> list[dict]:
    """Search the product database."""
    # Your database query logic
    return [
        {"id": 1, "name": "Product A", "price": 29.99},
        {"id": 2, "name": "Product B", "price": 49.99},
    ]
```

#### External API Tools

```python
import httpx

async def get_weather(
    location: Annotated[str, "City name or coordinates"],
) -> dict:
    """Get weather information for a location."""
    api_key = os.getenv("WEATHER_API_KEY")
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"https://api.weather.com/v1/current",
            params={"location": location, "key": api_key}
        )
        return response.json()
```

#### Calculation Tools

```python
import math

def calculate_mortgage(
    principal: Annotated[float, Field(description="Loan amount", gt=0)],
    annual_rate: Annotated[float, Field(description="Annual interest rate (%)", ge=0)],
    years: Annotated[int, Field(description="Loan term in years", gt=0)],
) -> dict:
    """Calculate monthly mortgage payment."""
    monthly_rate = (annual_rate / 100) / 12
    num_payments = years * 12
    
    if monthly_rate == 0:
        monthly_payment = principal / num_payments
    else:
        monthly_payment = principal * (
            monthly_rate * (1 + monthly_rate) ** num_payments
        ) / ((1 + monthly_rate) ** num_payments - 1)
    
    return {
        "monthly_payment": round(monthly_payment, 2),
        "total_paid": round(monthly_payment * num_payments, 2),
        "total_interest": round(monthly_payment * num_payments - principal, 2),
    }
```

### Tool Best Practices

1. **Clear Documentation**: Write descriptive docstrings and use `Field()` descriptions
2. **Type Hints**: Use proper type hints for parameters and return values
3. **Error Handling**: Handle errors gracefully and return user-friendly messages
4. **Validation**: Use Pydantic's `Field()` constraints for input validation
5. **Async When Needed**: Use async functions for I/O-bound operations
6. **Stateless Design**: Tools should be stateless and deterministic when possible
7. **Security**: Validate and sanitize all inputs, especially for external APIs

---

## Building Workflows

Workflows enable complex orchestration of agents and executors in directed graphs.

### Workflow Fundamentals

#### Basic Workflow Pattern

```python
from agent_framework.workflows import WorkflowBuilder, Executor

@Executor
async def step1(data: str) -> str:
    """First processing step."""
    return f"Step1: {data}"

@Executor
async def step2(data: str) -> str:
    """Second processing step."""
    return f"Step2: {data}"

# Build workflow
workflow = (
    WorkflowBuilder()
    .add_edge(step1, step2)
    .build()
)

# Execute
result = await workflow.run("input")
print(result)  # "Step2: Step1: input"
```

#### Adding Agents to Workflows

```python
from agent_framework import ChatAgent
from agent_framework.openai import OpenAIChatClient
from agent_framework.workflows import WorkflowBuilder

# Create agents
analyzer = ChatAgent(
    chat_client=OpenAIChatClient(),
    name="Analyzer",
    instructions="Analyze the input and extract key points.",
)

summarizer = ChatAgent(
    chat_client=OpenAIChatClient(),
    name="Summarizer",
    instructions="Create a concise summary.",
)

# Build workflow
workflow = (
    WorkflowBuilder()
    .add_edge(analyzer, summarizer)
    .build()
)

result = await workflow.run("Long article text here...")
```

### Sequential Workflows

Execute agents in sequence with shared conversation context:

```python
from agent_framework.workflows import SequentialBuilder

researcher = ChatAgent(
    chat_client=OpenAIChatClient(),
    name="Researcher",
    instructions="Research the topic and gather information.",
)

writer = ChatAgent(
    chat_client=OpenAIChatClient(),
    name="Writer",
    instructions="Write a detailed article based on research.",
)

editor = ChatAgent(
    chat_client=OpenAIChatClient(),
    name="Editor",
    instructions="Edit and improve the article.",
)

# Sequential workflow
workflow = (
    SequentialBuilder()
    .add_agent(researcher)
    .add_agent(writer)
    .add_agent(editor)
    .build()
)

result = await workflow.run("Write an article about quantum computing")
```

### Concurrent Workflows

Execute multiple agents in parallel:

```python
from agent_framework.workflows import ConcurrentBuilder

# Create specialized agents
agent1 = ChatAgent(name="Agent1", chat_client=OpenAIChatClient(), ...)
agent2 = ChatAgent(name="Agent2", chat_client=OpenAIChatClient(), ...)
agent3 = ChatAgent(name="Agent3", chat_client=OpenAIChatClient(), ...)

# Concurrent execution
workflow = (
    ConcurrentBuilder()
    .add_agent(agent1)
    .add_agent(agent2)
    .add_agent(agent3)
    .build()
)

# All agents run in parallel
results = await workflow.run("Analyze this from multiple perspectives")
```

### Custom Aggregation

Combine concurrent results with custom logic:

```python
from agent_framework.workflows import ConcurrentBuilder

async def custom_aggregator(results: list) -> str:
    """Combine and summarize all results."""
    combined = "\n\n".join(str(r) for r in results)
    
    # Use an agent to create final summary
    summarizer = ChatAgent(
        chat_client=OpenAIChatClient(),
        instructions="Synthesize multiple analyses into one coherent summary.",
    )
    final = await summarizer.run(combined)
    return final.text

workflow = (
    ConcurrentBuilder()
    .add_agent(agent1)
    .add_agent(agent2)
    .add_agent(agent3)
    .set_aggregator(custom_aggregator)
    .build()
)
```

### Conditional Routing

Route workflow execution based on conditions:

```python
from agent_framework.workflows import WorkflowBuilder

@Executor
async def classify(text: str) -> str:
    """Classify input type."""
    if "urgent" in text.lower():
        return "urgent"
    elif "question" in text.lower():
        return "question"
    else:
        return "general"

@Executor
async def handle_urgent(text: str) -> str:
    return f"[URGENT] {text}"

@Executor
async def handle_question(text: str) -> str:
    return f"[Q&A] {text}"

@Executor
async def handle_general(text: str) -> str:
    return f"[General] {text}"

workflow = (
    WorkflowBuilder()
    .add_edge(classify, handle_urgent, condition=lambda r: r == "urgent")
    .add_edge(classify, handle_question, condition=lambda r: r == "question")
    .add_edge(classify, handle_general, condition=lambda r: r == "general")
    .build()
)
```

### Loops and Iteration

Create feedback loops in workflows:

```python
from agent_framework.workflows import WorkflowBuilder

@Executor
async def generate_content(prompt: str) -> str:
    agent = ChatAgent(chat_client=OpenAIChatClient())
    result = await agent.run(prompt)
    return result.text

@Executor
async def review_quality(content: str) -> dict:
    """Review content and decide if it needs improvement."""
    # Simplified quality check
    quality_score = len(content.split())  # More words = higher quality (simplified)
    return {
        "content": content,
        "score": quality_score,
        "needs_improvement": quality_score < 50,
    }

@Executor
async def refine_content(review: dict) -> str:
    if review["needs_improvement"]:
        # Send back for improvement
        return f"Expand on: {review['content']}"
    return review["content"]

workflow = (
    WorkflowBuilder()
    .add_edge("start", generate_content)
    .add_edge(generate_content, review_quality)
    .add_edge(
        review_quality,
        generate_content,  # Loop back
        condition=lambda r: r["needs_improvement"]
    )
    .add_edge(
        review_quality,
        refine_content,  # Exit loop
        condition=lambda r: not r["needs_improvement"]
    )
    .build()
)
```

### Sub-Workflows

Compose workflows within workflows:

```python
from agent_framework.workflows import WorkflowBuilder, WorkflowExecutor

# Define sub-workflow
sub_workflow = (
    WorkflowBuilder()
    .add_edge(step1, step2)
    .build()
)

# Wrap as executor
sub_executor = WorkflowExecutor(sub_workflow)

# Use in main workflow
main_workflow = (
    WorkflowBuilder()
    .add_edge(preprocessing, sub_executor)
    .add_edge(sub_executor, postprocessing)
    .build()
)
```

### Checkpointing and Resume

Save and resume workflow state:

```python
from agent_framework.workflows import WorkflowBuilder, Checkpoint

workflow = WorkflowBuilder().add_edge(...).build()

# Run with checkpointing
checkpoint = Checkpoint()
try:
    result = await workflow.run("input", checkpoint=checkpoint)
except Exception as e:
    # Save checkpoint
    checkpoint.save("workflow_state.json")
    
# Later, resume from checkpoint
checkpoint = Checkpoint.load("workflow_state.json")
result = await workflow.run("input", checkpoint=checkpoint)
```

### Human-in-the-Loop

Pause workflow for human input:

```python
from agent_framework.workflows import WorkflowBuilder, HumanInputRequest

@Executor
async def request_approval(content: str) -> HumanInputRequest:
    """Request human approval."""
    return HumanInputRequest(
        prompt=f"Approve this content?\n{content}",
        options=["approve", "reject", "revise"],
    )

@Executor
async def handle_response(response: str) -> str:
    if response == "approve":
        return "Content approved!"
    elif response == "reject":
        return "Content rejected."
    else:
        return "Please revise the content."

workflow = (
    WorkflowBuilder()
    .add_edge(generate_content, request_approval)
    .add_edge(request_approval, handle_response)
    .build()
)

# Run workflow
async for event in workflow.run_stream("input"):
    if isinstance(event, HumanInputRequest):
        # Pause and wait for human input
        user_response = input(event.prompt)
        await event.respond(user_response)
```

### Workflow Streaming

Monitor workflow execution in real-time:

```python
from agent_framework.workflows import (
    ExecutorInvokeEvent,
    ExecutorCompletedEvent,
    WorkflowOutputEvent,
)

async for event in workflow.run_stream("input"):
    if isinstance(event, ExecutorInvokeEvent):
        print(f"Starting: {event.executor_name}")
    elif isinstance(event, ExecutorCompletedEvent):
        print(f"Completed: {event.executor_name} -> {event.result}")
    elif isinstance(event, WorkflowOutputEvent):
        print(f"Final output: {event.result}")
```

---

## Multi-Agent Orchestration

### Sequential Collaboration

Agents work in sequence, building on each other's output:

```python
from agent_framework import ChatAgent
from agent_framework.openai import OpenAIChatClient

async def sequential_collaboration():
    # Agent 1: Research
    researcher = ChatAgent(
        chat_client=OpenAIChatClient(),
        name="Researcher",
        instructions="""
        Research the given topic thoroughly.
        Provide facts, statistics, and key insights.
        Format your output as bullet points.
        """,
    )
    
    # Agent 2: Writer
    writer = ChatAgent(
        chat_client=OpenAIChatClient(),
        name="Writer",
        instructions="""
        Transform the research into an engaging article.
        Use a conversational tone.
        Include an introduction, body, and conclusion.
        """,
    )
    
    # Agent 3: Editor
    editor = ChatAgent(
        chat_client=OpenAIChatClient(),
        name="Editor",
        instructions="""
        Review and improve the article.
        Fix grammar and style issues.
        Ensure clarity and flow.
        """,
    )
    
    # Execute sequence
    task = "Write about the benefits of exercise"
    
    # Step 1: Research
    research = await researcher.run(task)
    print(f"Research completed:\n{research.text}\n")
    
    # Step 2: Write
    article = await writer.run(f"Write an article based on this research:\n{research.text}")
    print(f"Article draft:\n{article.text}\n")
    
    # Step 3: Edit
    final = await editor.run(f"Edit this article:\n{article.text}")
    print(f"Final article:\n{final.text}")
    
    return final.text

# Run
import asyncio
result = asyncio.run(sequential_collaboration())
```

### Parallel Processing

Multiple agents analyze the same input simultaneously:

```python
async def parallel_analysis():
    # Create specialized agents
    technical_analyst = ChatAgent(
        chat_client=OpenAIChatClient(),
        name="TechnicalAnalyst",
        instructions="Analyze from a technical perspective.",
    )
    
    business_analyst = ChatAgent(
        chat_client=OpenAIChatClient(),
        name="BusinessAnalyst",
        instructions="Analyze from a business perspective.",
    )
    
    user_experience_analyst = ChatAgent(
        chat_client=OpenAIChatClient(),
        name="UXAnalyst",
        instructions="Analyze from a user experience perspective.",
    )
    
    # Input
    product_description = "New mobile app for task management"
    
    # Run all analyses in parallel
    results = await asyncio.gather(
        technical_analyst.run(f"Analyze: {product_description}"),
        business_analyst.run(f"Analyze: {product_description}"),
        user_experience_analyst.run(f"Analyze: {product_description}"),
    )
    
    # Combine results
    combined_analysis = "\n\n".join([
        f"Technical Analysis:\n{results[0].text}",
        f"Business Analysis:\n{results[1].text}",
        f"UX Analysis:\n{results[2].text}",
    ])
    
    # Final synthesis
    synthesizer = ChatAgent(
        chat_client=OpenAIChatClient(),
        instructions="Synthesize multiple analyses into actionable recommendations.",
    )
    
    final = await synthesizer.run(f"Synthesize these analyses:\n{combined_analysis}")
    return final.text
```

### Hierarchical Teams

Manager agent coordinates specialist agents:

```python
async def hierarchical_team():
    # Specialist agents
    def research_tool(topic: str) -> str:
        """Research a topic."""
        return f"Research results for: {topic}"
    
    def code_tool(task: str) -> str:
        """Generate code."""
        return f"Code for: {task}"
    
    researcher = ChatAgent(
        chat_client=OpenAIChatClient(),
        name="Researcher",
        tools=[research_tool],
        instructions="Research topics thoroughly.",
    )
    
    developer = ChatAgent(
        chat_client=OpenAIChatClient(),
        name="Developer",
        tools=[code_tool],
        instructions="Write clean, efficient code.",
    )
    
    # Manager agent
    manager = ChatAgent(
        chat_client=OpenAIChatClient(),
        name="Manager",
        instructions="""
        You coordinate a team of specialists:
        - Researcher: Handles research tasks
        - Developer: Handles coding tasks
        
        Analyze the user's request and delegate to appropriate team members.
        Synthesize their outputs into a coherent response.
        """,
    )
    
    # Simulated delegation (in practice, you'd use function calling)
    task = "Build a web scraper for news articles"
    
    # Manager analyzes task
    plan = await manager.run(f"Create a plan for: {task}")
    
    # Delegate to specialists
    research_result = await researcher.run("Research web scraping best practices")
    code_result = await developer.run("Create a web scraper implementation")
    
    # Manager synthesizes
    final = await manager.run(
        f"Synthesize these results:\n"
        f"Plan: {plan.text}\n"
        f"Research: {research_result.text}\n"
        f"Code: {code_result.text}"
    )
    
    return final.text
```

### Debate Pattern

Agents debate to reach better conclusions:

```python
async def debate_pattern():
    # Create opposing viewpoints
    advocate = ChatAgent(
        chat_client=OpenAIChatClient(),
        name="Advocate",
        instructions="""
        Argue in favor of the given proposition.
        Provide strong, logical arguments and evidence.
        """,
    )
    
    critic = ChatAgent(
        chat_client=OpenAIChatClient(),
        name="Critic",
        instructions="""
        Argue against the given proposition.
        Identify weaknesses and provide counterarguments.
        """,
    )
    
    judge = ChatAgent(
        chat_client=OpenAIChatClient(),
        name="Judge",
        instructions="""
        Review both arguments objectively.
        Provide a balanced conclusion.
        Identify strengths and weaknesses of each position.
        """,
    )
    
    # Topic
    topic = "Remote work is more productive than office work"
    
    # Round 1
    advocate_arg = await advocate.run(f"Argue for: {topic}")
    critic_arg = await critic.run(f"Argue against: {topic}")
    
    # Round 2: Rebuttals
    advocate_rebuttal = await advocate.run(
        f"Respond to this criticism: {critic_arg.text}"
    )
    critic_rebuttal = await critic.run(
        f"Respond to this argument: {advocate_arg.text}"
    )
    
    # Judge evaluates
    final = await judge.run(
        f"Evaluate this debate:\n"
        f"Advocate: {advocate_arg.text}\n"
        f"Critic: {critic_arg.text}\n"
        f"Advocate Rebuttal: {advocate_rebuttal.text}\n"
        f"Critic Rebuttal: {critic_rebuttal.text}"
    )
    
    return final.text
```

### Consensus Building

Multiple agents vote or reach consensus:

```python
async def consensus_pattern():
    # Create voting agents
    agents = [
        ChatAgent(
            chat_client=OpenAIChatClient(),
            name=f"Expert{i}",
            instructions=f"You are expert {i}. Provide your opinion.",
        )
        for i in range(5)
    ]
    
    question = "Should we implement feature X?"
    
    # Collect votes
    votes = []
    for agent in agents:
        response = await agent.run(
            f"{question} Answer with YES or NO and brief reasoning."
        )
        votes.append({
            "agent": agent.name,
            "response": response.text,
        })
    
    # Tally and synthesize
    synthesizer = ChatAgent(
        chat_client=OpenAIChatClient(),
        instructions="Analyze votes and reach a consensus decision.",
    )
    
    vote_summary = "\n".join([
        f"{v['agent']}: {v['response']}" for v in votes
    ])
    
    consensus = await synthesizer.run(
        f"Analyze these votes and make a final decision:\n{vote_summary}"
    )
    
    return consensus.text
```

---

## Middleware and Context Providers

### Middleware

Middleware intercepts and modifies agent runs, function calls, and chat requests.

#### Agent Middleware

Intercepts agent execution:

```python
from agent_framework import agent_middleware, AgentRunContext, ChatAgent
from agent_framework.openai import OpenAIChatClient

@agent_middleware
async def logging_middleware(context: AgentRunContext, next):
    """Log agent execution."""
    print(f"Agent {context.agent.name} starting...")
    print(f"Input: {context.messages[-1].text if context.messages else 'N/A'}")
    
    # Call next middleware or agent
    await next(context)
    
    print(f"Agent {context.agent.name} completed")
    print(f"Output: {context.result.text if context.result else 'N/A'}")

# Use with agent
agent = ChatAgent(
    chat_client=OpenAIChatClient(),
    middleware=[logging_middleware],
)
```

#### Function Middleware

Intercepts function/tool calls:

```python
from agent_framework import function_middleware, FunctionInvocationContext

@function_middleware
async def timing_middleware(context: FunctionInvocationContext, next):
    """Time function execution."""
    import time
    start = time.time()
    
    print(f"Calling {context.function.__name__}...")
    await next(context)
    
    elapsed = time.time() - start
    print(f"Function took {elapsed:.2f}s")

def my_tool(query: str) -> str:
    """Example tool."""
    return f"Result for: {query}"

agent = ChatAgent(
    chat_client=OpenAIChatClient(),
    tools=[my_tool],
    middleware=[timing_middleware],
)
```

#### Chat Middleware

Intercepts chat client requests:

```python
from agent_framework import chat_middleware, ChatContext

@chat_middleware
async def message_filter_middleware(context: ChatContext, next):
    """Filter sensitive information from messages."""
    # Modify messages before sending to LLM
    for msg in context.messages:
        if "password" in msg.text.lower():
            msg.text = msg.text.replace("password", "[REDACTED]")
    
    await next(context)
    
    # Can also modify response
    if context.result and "sensitive" in context.result.text.lower():
        context.result.text = "Response filtered for security."

agent = ChatAgent(
    chat_client=OpenAIChatClient(),
    middleware=[message_filter_middleware],
)
```

#### Class-Based Middleware

For complex, stateful middleware:

```python
from agent_framework import AgentMiddleware, AgentRunContext

class SecurityMiddleware(AgentMiddleware):
    """Check for security violations."""
    
    def __init__(self, blocked_terms: list[str]):
        self.blocked_terms = blocked_terms
    
    async def invoke(self, context: AgentRunContext, next):
        """Check input for blocked terms."""
        last_message = context.messages[-1].text if context.messages else ""
        
        for term in self.blocked_terms:
            if term.lower() in last_message.lower():
                # Terminate execution
                context.terminate = True
                context.result = AgentRunResult(
                    text="Request blocked: contains prohibited content",
                    messages=[],
                )
                return
        
        await next(context)

# Use with agent
security = SecurityMiddleware(blocked_terms=["hack", "exploit"])
agent = ChatAgent(
    chat_client=OpenAIChatClient(),
    middleware=[security],
)
```

#### Middleware Use Cases

**Logging and Monitoring:**
```python
@agent_middleware
async def monitoring_middleware(context: AgentRunContext, next):
    """Monitor agent performance."""
    import time
    start = time.time()
    
    await next(context)
    
    elapsed = time.time() - start
    # Send to monitoring system
    print(f"Agent: {context.agent.name}, Duration: {elapsed}s")
```

**Caching:**
```python
from functools import lru_cache

@function_middleware
async def cache_middleware(context: FunctionInvocationContext, next):
    """Cache function results."""
    cache_key = f"{context.function.__name__}:{str(context.args)}:{str(context.kwargs)}"
    
    # Check cache (simplified)
    cached = get_from_cache(cache_key)
    if cached:
        context.result = cached
        return
    
    await next(context)
    
    # Store in cache
    set_in_cache(cache_key, context.result)
```

**Rate Limiting:**
```python
import asyncio
from collections import defaultdict

class RateLimitMiddleware(AgentMiddleware):
    """Limit agent invocations."""
    
    def __init__(self, max_per_minute: int = 10):
        self.max_per_minute = max_per_minute
        self.calls = defaultdict(list)
    
    async def invoke(self, context: AgentRunContext, next):
        import time
        now = time.time()
        agent_id = context.agent.id
        
        # Clean old calls
        self.calls[agent_id] = [
            t for t in self.calls[agent_id]
            if now - t < 60
        ]
        
        # Check limit
        if len(self.calls[agent_id]) >= self.max_per_minute:
            await asyncio.sleep(1)  # Wait and retry
        
        self.calls[agent_id].append(now)
        await next(context)
```

### Context Providers

Context providers inject dynamic information into conversations.

#### Simple Context Provider

```python
from agent_framework import ContextProvider, ChatAgent
from datetime import datetime

class TimeContextProvider(ContextProvider):
    """Provide current time context."""
    
    async def get_context(self) -> str:
        now = datetime.now()
        return f"Current time: {now.strftime('%Y-%m-%d %H:%M:%S')}"

# Use with agent
agent = ChatAgent(
    chat_client=OpenAIChatClient(),
    context_providers=[TimeContextProvider()],
)
```

#### Database Context Provider

```python
class UserContextProvider(ContextProvider):
    """Provide user-specific context."""
    
    def __init__(self, user_id: str):
        self.user_id = user_id
    
    async def get_context(self) -> str:
        # Fetch user data from database
        user = await fetch_user_from_db(self.user_id)
        return f"""
        User Profile:
        - Name: {user.name}
        - Preferences: {user.preferences}
        - History: {user.recent_activity}
        """

agent = ChatAgent(
    chat_client=OpenAIChatClient(),
    context_providers=[UserContextProvider(user_id="123")],
)
```

#### Memory Context Provider (Mem0)

```python
from agent_framework.mem0 import Mem0ContextProvider

# Create memory-enabled agent
memory_provider = Mem0ContextProvider(
    user_id="user123",
    mem0_api_key="your-key",
)

agent = ChatAgent(
    chat_client=OpenAIChatClient(),
    context_providers=[memory_provider],
    instructions="You remember past conversations.",
)

# Agent will automatically retrieve relevant memories
result = await agent.run("What did we discuss last time?")
```

#### Multiple Context Providers

```python
agent = ChatAgent(
    chat_client=OpenAIChatClient(),
    context_providers=[
        TimeContextProvider(),
        UserContextProvider(user_id="123"),
        WeatherContextProvider(location="Seattle"),
    ],
)
```

---

## Thread Management

Manage conversation persistence and multi-user sessions.

### In-Memory Threads (Default)

By default, agents maintain conversation history in memory:

```python
agent = ChatAgent(chat_client=OpenAIChatClient())

# First message
await agent.run("My name is Alice")

# Second message (agent remembers)
result = await agent.run("What's my name?")
# Output: "Your name is Alice"
```

### Custom Chat Message Store

Implement custom storage:

```python
from agent_framework import ChatMessageStoreProtocol, ChatMessage
from typing import MutableSequence

class CustomChatMessageStore(ChatMessageStoreProtocol):
    """Custom message storage implementation."""
    
    def __init__(self):
        self._messages: list[ChatMessage] = []
    
    def get_messages(self) -> MutableSequence[ChatMessage]:
        return self._messages
    
    def add_message(self, message: ChatMessage) -> None:
        self._messages.append(message)
        # Save to database, file, etc.
        self._save_to_storage()
    
    def clear(self) -> None:
        self._messages.clear()
    
    def _save_to_storage(self):
        # Implement persistence
        pass

# Use custom store
def create_custom_store():
    return CustomChatMessageStore()

agent = ChatAgent(
    chat_client=OpenAIChatClient(),
    chat_message_store_factory=create_custom_store,
)
```

### Redis-Backed Threads

For production multi-user applications:

```bash
pip install agent-framework-redis --pre
```

```python
from agent_framework.redis import RedisChatMessageStore

# Create Redis-backed store
store_factory = lambda: RedisChatMessageStore(
    redis_url="redis://localhost:6379",
    session_id="user123_conversation1",
)

agent = ChatAgent(
    chat_client=OpenAIChatClient(),
    chat_message_store_factory=store_factory,
)

# Messages are persisted to Redis
await agent.run("Hello")
await agent.run("How are you?")

# Can resume conversation later
# Messages are automatically loaded from Redis
```

### Service-Managed Threads (Assistants API)

Use backend-managed threads:

```python
from agent_framework.openai import OpenAIAssistantsClient

# Create client with thread support
client = OpenAIAssistantsClient(model="gpt-4o")

agent = ChatAgent(
    chat_client=client,
    conversation_id="thread_abc123",  # Reuse existing thread
)

# Or let framework create new thread
agent = ChatAgent(chat_client=client)
# Framework creates thread automatically
```

### Thread Management Examples

**Multiple Users:**
```python
def create_agent_for_user(user_id: str):
    """Create user-specific agent."""
    store_factory = lambda: RedisChatMessageStore(
        redis_url="redis://localhost:6379",
        session_id=f"user_{user_id}",
    )
    
    return ChatAgent(
        chat_client=OpenAIChatClient(),
        chat_message_store_factory=store_factory,
    )

# Each user gets isolated conversation
alice_agent = create_agent_for_user("alice")
bob_agent = create_agent_for_user("bob")
```

**Session Management:**
```python
class SessionManager:
    """Manage conversation sessions."""
    
    def __init__(self):
        self.sessions = {}
    
    def get_agent(self, session_id: str) -> ChatAgent:
        if session_id not in self.sessions:
            self.sessions[session_id] = ChatAgent(
                chat_client=OpenAIChatClient(),
                chat_message_store_factory=lambda: RedisChatMessageStore(
                    redis_url="redis://localhost:6379",
                    session_id=session_id,
                ),
            )
        return self.sessions[session_id]
    
    def clear_session(self, session_id: str):
        if session_id in self.sessions:
            del self.sessions[session_id]

# Usage
manager = SessionManager()
agent = manager.get_agent("session_123")
```

---

## DevUI for Testing and Debugging

DevUI provides a web interface for testing agents and workflows.

### Installation

```bash
pip install agent-framework-devui --pre
```

### Quick Start

#### Programmatic Launch

```python
from agent_framework import ChatAgent
from agent_framework.openai import OpenAIChatClient
from agent_framework.devui import serve

def get_weather(location: str) -> str:
    """Get weather for a location."""
    return f"Weather in {location}: 72°F and sunny"

# Create agent
agent = ChatAgent(
    name="WeatherAgent",
    chat_client=OpenAIChatClient(),
    tools=[get_weather],
)

# Launch DevUI
serve(entities=[agent], auto_open=True)
# Opens browser to http://localhost:8080
```

#### CLI Launch

Organize agents in a directory structure:

```
agents/
├── weather_agent/
│   ├── __init__.py      # Must export: agent = ChatAgent(...)
│   ├── agent.py
│   └── .env             # Optional: API keys
├── support_agent/
│   ├── __init__.py
│   └── agent.py
└── .env                 # Shared environment variables
```

**agents/weather_agent/__init__.py:**
```python
from agent_framework import ChatAgent
from agent_framework.openai import OpenAIChatClient

def get_weather(location: str) -> str:
    return f"Weather in {location}: sunny"

agent = ChatAgent(
    name="WeatherAgent",
    chat_client=OpenAIChatClient(),
    tools=[get_weather],
)
```

Launch DevUI:
```bash
devui ./agents --port 8080
# → Web UI: http://localhost:8080
# → API: http://localhost:8080/v1/*
```

### Features

**1. Interactive Chat Interface:**
- Test agents with a chat UI
- View streaming responses in real-time
- Inspect message history

**2. Multi-Agent Support:**
- Switch between different agents/workflows
- Compare agent behaviors
- Test multi-agent interactions

**3. Tool Inspection:**
- View available tools for each agent
- See tool call arguments and results
- Debug tool execution

**4. Workflow Visualization:**
- Visual graph of workflow structure
- Real-time execution status
- Event stream monitoring

**5. Trace Viewer:**
- OpenTelemetry trace visualization
- Detailed span information
- Performance analysis

### Configuration Options

```bash
devui [directory] [options]

Options:
  --port, -p      Port (default: 8080)
  --host          Host (default: 127.0.0.1)
  --headless      API only, no UI
  --config        YAML config file
  --tracing       none|framework|workflow|all
  --reload        Enable auto-reload
```

### OpenAI-Compatible API

DevUI exposes an OpenAI-compatible API:

```bash
curl -X POST http://localhost:8080/v1/responses \
  -H "Content-Type: application/json" \
  -d '{
    "model": "agent-framework",
    "input": "Hello world",
    "extra_body": {"entity_id": "weather_agent"}
  }'
```

### Observability Integration

Enable tracing to view in DevUI:

```bash
# Start DevUI with tracing
devui ./agents --tracing framework

# In your code, traces are automatically collected
# View them in the "Traces" tab of DevUI
```

---

## Common Examples and Usage Scenarios

### Customer Support Agent

```python
from agent_framework import ChatAgent
from agent_framework.openai import OpenAIChatClient
from typing import Annotated

def check_order_status(order_id: Annotated[str, "Order ID"]) -> dict:
    """Check the status of an order."""
    # Simulated database lookup
    return {
        "order_id": order_id,
        "status": "shipped",
        "tracking": "1Z999AA10123456784",
        "estimated_delivery": "2024-01-15",
    }

def initiate_return(order_id: Annotated[str, "Order ID"]) -> str:
    """Initiate a return for an order."""
    return f"Return initiated for order {order_id}. Label will be emailed."

support_agent = ChatAgent(
    chat_client=OpenAIChatClient(),
    name="SupportAgent",
    instructions="""
    You are a helpful customer support agent.
    Be friendly, empathetic, and professional.
    Use the available tools to help customers with:
    - Order status inquiries
    - Return requests
    Always confirm details before taking actions.
    """,
    tools=[check_order_status, initiate_return],
)

# Usage
result = await support_agent.run("Where is my order #12345?")
```

### Code Review Assistant

```python
def analyze_code(code: Annotated[str, "Code to analyze"]) -> dict:
    """Analyze code for issues."""
    # Use static analysis tools
    return {
        "issues": [
            {"line": 5, "severity": "warning", "message": "Variable not used"},
            {"line": 12, "severity": "error", "message": "Syntax error"},
        ],
        "suggestions": ["Add type hints", "Use f-strings"],
    }

code_reviewer = ChatAgent(
    chat_client=OpenAIChatClient(),
    name="CodeReviewer",
    instructions="""
    You are an expert code reviewer.
    Review code for:
    - Best practices
    - Performance issues
    - Security vulnerabilities
    - Code style
    Provide constructive feedback with examples.
    """,
    tools=[analyze_code],
)

# Usage
code = """
def calculate(x, y):
    result = x + y
    return result
"""
result = await code_reviewer.run(f"Review this code:\n```python\n{code}\n```")
```

### Data Analysis Assistant

```python
import pandas as pd

def query_database(sql: Annotated[str, "SQL query"]) -> str:
    """Execute SQL query and return results."""
    # Execute query (simplified)
    return "Query results: 150 rows returned"

def generate_chart(data_desc: Annotated[str, "Data description"]) -> str:
    """Generate a chart visualization."""
    return f"Chart generated for: {data_desc}"

analyst_agent = ChatAgent(
    chat_client=OpenAIChatClient(),
    name="DataAnalyst",
    instructions="""
    You are a data analysis expert.
    Help users:
    - Query databases
    - Analyze data patterns
    - Generate visualizations
    - Provide insights and recommendations
    Explain your analysis in clear terms.
    """,
    tools=[query_database, generate_chart],
)

# Usage
result = await analyst_agent.run(
    "Show me sales trends for the last quarter"
)
```

### Content Moderation System

```python
from agent_framework.workflows import WorkflowBuilder

# Create specialized agents
spam_detector = ChatAgent(
    chat_client=OpenAIChatClient(),
    name="SpamDetector",
    instructions="Classify content as SPAM or HAM. Output only SPAM or HAM.",
)

toxicity_checker = ChatAgent(
    chat_client=OpenAIChatClient(),
    name="ToxicityChecker",
    instructions="Rate toxicity 0-10. Output only the number.",
)

# Build moderation workflow
@Executor
async def moderate(content: str) -> dict:
    spam_result = await spam_detector.run(content)
    toxicity_result = await toxicity_checker.run(content)
    
    return {
        "content": content,
        "is_spam": "SPAM" in spam_result.text,
        "toxicity": int(toxicity_result.text.strip()),
        "approved": "SPAM" not in spam_result.text and int(toxicity_result.text.strip()) < 5,
    }

# Usage
result = await moderate("Check this user content")
```

### Document Processing Pipeline

```python
# Sequential workflow for document processing
extractor = ChatAgent(
    chat_client=OpenAIChatClient(),
    name="Extractor",
    instructions="Extract key information from documents.",
)

classifier = ChatAgent(
    chat_client=OpenAIChatClient(),
    name="Classifier",
    instructions="Classify document type and urgency.",
)

summarizer = ChatAgent(
    chat_client=OpenAIChatClient(),
    name="Summarizer",
    instructions="Create concise summaries.",
)

from agent_framework.workflows import SequentialBuilder

doc_pipeline = (
    SequentialBuilder()
    .add_agent(extractor)
    .add_agent(classifier)
    .add_agent(summarizer)
    .build()
)

# Usage
result = await doc_pipeline.run("Process this document: [document text]")
```

### Personal AI Assistant

```python
from datetime import datetime

def get_calendar(date: str) -> list[dict]:
    """Get calendar events."""
    return [{"time": "10:00", "event": "Team meeting"}]

def send_email(to: str, subject: str, body: str) -> str:
    """Send an email."""
    return f"Email sent to {to}"

def set_reminder(time: str, message: str) -> str:
    """Set a reminder."""
    return f"Reminder set for {time}: {message}"

assistant = ChatAgent(
    chat_client=OpenAIChatClient(),
    name="PersonalAssistant",
    instructions="""
    You are a helpful personal assistant.
    Help with:
    - Schedule management
    - Email composition
    - Reminders
    - Information lookup
    Be proactive and anticipate user needs.
    """,
    tools=[get_calendar, send_email, set_reminder],
    context_providers=[
        TimeContextProvider(),
        UserContextProvider(user_id="user123"),
    ],
)

# Usage
result = await assistant.run("What's on my schedule today?")
```

---

## Troubleshooting Guide

### Common Issues and Solutions

#### 1. API Key Not Found

**Error:**
```
OpenAIError: The api_key client option must be set
```

**Solutions:**
- Check `.env` file exists in project root
- Verify environment variable name: `OPENAI_API_KEY=sk-...`
- Explicitly pass API key: `OpenAIChatClient(api_key="sk-...")`
- Ensure `.env` file is loaded: `from dotenv import load_dotenv; load_dotenv()`

#### 2. Model Not Found

**Error:**
```
InvalidRequestError: The model 'gpt-4' does not exist
```

**Solutions:**
- Use correct model name: `gpt-4o`, `gpt-4o-mini`, `gpt-3.5-turbo`
- For Azure: Verify deployment name matches
- Check model availability in your account

#### 3. Import Errors

**Error:**
```
ImportError: cannot import name 'ChatAgent' from 'agent_framework'
```

**Solutions:**
- Install package: `pip install agent-framework --pre`
- Check Python version: 3.10+
- Verify installation: `pip show agent-framework`
- Try reinstalling: `pip install --upgrade --force-reinstall agent-framework --pre`

#### 4. Async/Await Issues

**Error:**
```
RuntimeError: asyncio.run() cannot be called from a running event loop
```

**Solutions:**
- Use `asyncio.run()` only in non-async contexts
- In Jupyter notebooks: Use `await` directly or `nest_asyncio`
  ```python
  import nest_asyncio
  nest_asyncio.apply()
  ```
- In async functions: Use `await` directly

#### 5. Rate Limiting

**Error:**
```
RateLimitError: Rate limit exceeded
```

**Solutions:**
- Add retry logic with exponential backoff
- Use middleware for rate limiting (see Middleware section)
- Upgrade API plan
- Reduce request frequency

#### 6. Context Length Exceeded

**Error:**
```
InvalidRequestError: This model's maximum context length is 4096 tokens
```

**Solutions:**
- Reduce conversation history
- Use message truncation
- Implement custom message store with trimming
- Switch to model with larger context (e.g., `gpt-4o` with 128K)

```python
def create_trimming_store():
    store = InMemoryChatMessageStore()
    # Keep only last 10 messages
    original_add = store.add_message
    def add_with_trim(msg):
        original_add(msg)
        messages = store.get_messages()
        if len(messages) > 10:
            messages[:] = messages[-10:]
    store.add_message = add_with_trim
    return store
```

#### 7. Tool Call Failures

**Issue:** Agent doesn't call tools when expected

**Solutions:**
- Verify tool function signatures have type hints
- Add descriptive docstrings
- Use `Annotated` with `Field()` for parameter descriptions
- Check `tool_choice` parameter: use `"auto"` or `"required"`
- Ensure tools return serializable types

#### 8. Azure Authentication Issues

**Error:**
```
ClientAuthenticationError: Authentication failed
```

**Solutions:**
- For API key: Verify `AZURE_OPENAI_API_KEY`
- For managed identity: Ensure proper RBAC roles
- Check endpoint URL format: `https://<resource>.openai.azure.com`
- Verify API version: `2024-02-15-preview` or later

#### 9. DevUI Not Starting

**Issue:** DevUI fails to start or shows errors

**Solutions:**
- Check port availability: `lsof -i :8080` (Mac/Linux)
- Verify agent exports: `agent = ChatAgent(...)` in `__init__.py`
- Check `.env` files are present and valid
- View logs for specific errors: `devui ./agents --verbose`

#### 10. Streaming Not Working

**Issue:** `run_stream()` doesn't produce events

**Solutions:**
- Verify chat client supports streaming
- Check for blocking operations in async code
- Use `async for` correctly:
  ```python
  async for event in agent.run_stream("message"):
      print(event)
  ```
- Ensure proper event handling

### Debugging Tips

**1. Enable Logging:**
```python
import logging
logging.basicConfig(level=logging.DEBUG)

from agent_framework import get_logger
logger = get_logger()
logger.setLevel(logging.DEBUG)
```

**2. Enable Observability:**
```bash
# .env
ENABLE_OTEL=true
ENABLE_SENSITIVE_DATA=true  # Development only
OTLP_ENDPOINT=http://localhost:4317
```

**3. Use DevUI:**
```python
from agent_framework.devui import serve
serve(entities=[agent], auto_open=True)
```

**4. Print Context:**
```python
@agent_middleware
async def debug_middleware(context: AgentRunContext, next):
    print(f"Messages: {context.messages}")
    await next(context)
    print(f"Result: {context.result}")

agent = ChatAgent(
    chat_client=OpenAIChatClient(),
    middleware=[debug_middleware],
)
```

**5. Test Components Independently:**
```python
# Test chat client directly
client = OpenAIChatClient()
messages = [ChatMessage(role=Role.USER, text="Test")]
response = await client.get_response(messages)
print(response.messages[0].text)

# Test tools directly
result = my_tool("test input")
print(result)
```

### Performance Optimization

**1. Use Async Properly:**
- Don't mix sync and async inappropriately
- Use `asyncio.gather()` for concurrent operations
- Avoid blocking operations in async functions

**2. Connection Pooling:**
```python
# Reuse clients
client = OpenAIChatClient()
agent1 = ChatAgent(chat_client=client)
agent2 = ChatAgent(chat_client=client)  # Shares connection pool
```

**3. Caching:**
- Implement caching middleware for repeated requests
- Cache tool results when appropriate
- Use Redis for distributed caching

**4. Message Trimming:**
- Limit conversation history size
- Implement smart truncation strategies
- Remove old, less relevant messages

---

## Additional Resources

### Official Documentation

- **[Agent Framework Repository](https://github.com/microsoft/agent-framework)**: Main repository with source code
- **[Python Package Documentation](https://github.com/microsoft/agent-framework/tree/main/python)**: Python-specific docs
- **[Design Documents](https://github.com/microsoft/agent-framework/tree/main/docs/design)**: Architecture and design decisions
- **[API Reference](https://microsoft.github.io/agent-framework)**: Detailed API documentation (coming soon)

### Sample Code

- **[Getting Started Samples](https://github.com/microsoft/agent-framework/tree/main/python/samples/getting_started)**: Comprehensive examples
  - [Agents](https://github.com/microsoft/agent-framework/tree/main/python/samples/getting_started/agents): Basic to advanced agent patterns
  - [Chat Clients](https://github.com/microsoft/agent-framework/tree/main/python/samples/getting_started/chat_client): Client usage examples
  - [Workflows](https://github.com/microsoft/agent-framework/tree/main/python/samples/getting_started/workflows): Orchestration patterns
  - [Middleware](https://github.com/microsoft/agent-framework/tree/main/python/samples/getting_started/middleware): Middleware examples
  - [Observability](https://github.com/microsoft/agent-framework/tree/main/python/samples/getting_started/observability): Monitoring setup

### Community and Support

- **[GitHub Issues](https://github.com/microsoft/agent-framework/issues)**: Report bugs and request features
- **[GitHub Discussions](https://github.com/microsoft/agent-framework/discussions)**: Ask questions and share ideas
- **[Contributing Guide](https://github.com/microsoft/agent-framework/blob/main/CONTRIBUTING.md)**: How to contribute

### Related Technologies

- **[OpenAI API Documentation](https://platform.openai.com/docs/api-reference)**: OpenAI API reference
- **[Azure OpenAI Documentation](https://learn.microsoft.com/azure/ai-services/openai/)**: Azure OpenAI service docs
- **[Azure AI Foundry](https://learn.microsoft.com/azure/ai-studio/)**: Azure AI platform docs
- **[OpenTelemetry Python](https://opentelemetry.io/docs/languages/python/)**: Observability framework
- **[Pydantic Documentation](https://docs.pydantic.dev/)**: Data validation library

### Development Resources

- **[Python DEV_SETUP.md](https://github.com/microsoft/agent-framework/blob/main/python/DEV_SETUP.md)**: Development environment setup
- **[Code of Conduct](https://github.com/microsoft/agent-framework/blob/main/CODE_OF_CONDUCT.md)**: Community guidelines
- **[Security Policy](https://github.com/microsoft/agent-framework/blob/main/SECURITY.md)**: Security reporting

### Learning Paths

**For Beginners:**
1. Read the Quick Start Guide (above)
2. Follow [Getting Started Samples](https://github.com/microsoft/agent-framework/tree/main/python/samples/getting_started)
3. Try building a simple chatbot
4. Experiment with DevUI

**For Intermediate Users:**
1. Explore middleware patterns
2. Build multi-agent workflows
3. Implement custom tools
4. Add observability to your agents

**For Advanced Users:**
1. Create custom chat clients
2. Build complex workflow orchestrations
3. Implement distributed agent systems
4. Contribute to the framework

### Best Practices Summary

1. **Code Organization:**
   - Separate agent definitions, tools, and business logic
   - Use proper project structure with packages
   - Keep configuration in `.env` files

2. **Error Handling:**
   - Always handle exceptions in agent code
   - Provide meaningful error messages
   - Use middleware for centralized error handling

3. **Security:**
   - Never hardcode API keys
   - Validate all user inputs
   - Filter sensitive data with middleware
   - Use environment-specific configurations

4. **Performance:**
   - Reuse chat clients when possible
   - Implement caching for expensive operations
   - Use async/await properly
   - Monitor and optimize with observability

5. **Testing:**
   - Test agents with DevUI
   - Write unit tests for tools
   - Test workflows end-to-end
   - Use mocks for external dependencies

6. **Production Deployment:**
   - Use Azure managed identity for authentication
   - Implement proper logging and monitoring
   - Set up alerts for failures and anomalies
   - Use Redis for distributed state management
   - Implement rate limiting and retries

---

## Conclusion

The Microsoft Agent Framework provides a powerful, flexible foundation for building AI agents and multi-agent systems. This guide has covered:

- ✅ Framework architecture and core concepts
- ✅ Development environment setup
- ✅ Creating and configuring agents
- ✅ Working with different chat clients
- ✅ Building tools and functions
- ✅ Orchestrating workflows
- ✅ Implementing middleware and context providers
- ✅ Managing conversation threads
- ✅ Testing with DevUI
- ✅ Common patterns and troubleshooting

### Next Steps

1. **Set up your development environment** following the setup guide
2. **Create your first agent** using the Quick Start
3. **Explore the samples** in the repository
4. **Join the community** on GitHub Discussions
5. **Build something amazing!**

### Getting Help

- **Documentation Issues**: Open an issue on [GitHub](https://github.com/microsoft/agent-framework/issues)
- **Questions**: Use [GitHub Discussions](https://github.com/microsoft/agent-framework/discussions)
- **Bugs**: Report on [GitHub Issues](https://github.com/microsoft/agent-framework/issues)
- **Security Issues**: Follow the [Security Policy](https://github.com/microsoft/agent-framework/blob/main/SECURITY.md)

### Feedback

We welcome your feedback on this documentation! Please open an issue or discussion on GitHub to share your thoughts, suggestions, or report any errors.

---

**Document Version:** 1.0
**Last Updated:** 2024
**Framework Version:** Preview (Python 3.10+)

For the latest updates and changes, always refer to the [official repository](https://github.com/microsoft/agent-framework).
