# Declarative Agent Samples

This folder contains sample code demonstrating how to use the **Microsoft Agent Framework Declarative** package to create agents from YAML specifications. The declarative approach allows you to define your agents in a structured, configuration-driven way, separating agent behavior from implementation details.

## Installation

Install the declarative package via pip:

```bash
pip install agent-framework-declarative --pre
```

## What is Declarative Agent Framework?

The declarative package provides support for building agents based on YAML specifications. This approach offers several benefits:

- **Cross-Platform Compatibility**: Write one YAML definition and create agents in both Python and .NET - the same agent configuration works across both platforms
- **Separation of Concerns**: Define agent behavior in YAML files separate from your implementation code
- **Reusability**: Share and version agent configurations independently across projects and languages
- **Flexibility**: Easily swap between different LLM providers and configurations
- **Maintainability**: Update agent instructions and settings without modifying code

## Samples in This Folder

### 1. **Get Weather Agent** ([`get_weather_agent.py`](./get_weather_agent.py))

Demonstrates how to create an agent with custom function tools using the declarative approach.

- Uses Azure OpenAI Responses client
- Shows how to bind Python functions to the agent using the `bindings` parameter
- Loads agent configuration from `agent-samples/chatclient/GetWeather.yaml`
- Implements a simple weather lookup function tool

**Key concepts**: Function binding, Azure OpenAI integration, tool usage

### 2. **Microsoft Learn Agent** ([`microsoft_learn_agent.py`](./microsoft_learn_agent.py))

Shows how to create an agent that can search and retrieve information from Microsoft Learn documentation using the Model Context Protocol (MCP).

- Uses Azure AI Foundry client with MCP server integration
- Demonstrates async context managers for proper resource cleanup
- Loads agent configuration from `agent-samples/foundry/MicrosoftLearnAgent.yaml`
- Uses Azure CLI credentials for authentication
- Leverages MCP to access Microsoft documentation tools

**Requirements**: `pip install agent-framework-azure-ai --pre`

**Key concepts**: Azure AI Foundry integration, MCP server usage, async patterns, resource management

### 3. **Inline YAML Agent** ([`inline_yaml.py`](./inline_yaml.py))

Shows how to create an agent using an inline YAML string rather than a file.

- Uses Azure AI Foundry v2 Client with instructions.

**Requirements**: `pip install agent-framework-azure-ai --pre`

**Key concepts**: Inline YAML definition.

### 4. **Azure OpenAI Responses Agent** ([`azure_openai_responses_agent.py`](./azure_openai_responses_agent.py))

Illustrates a basic agent using Azure OpenAI with structured responses.

- Uses Azure OpenAI Responses client
- Shows how to pass credentials via `client_kwargs`
- Loads agent configuration from `agent-samples/azure/AzureOpenAIResponses.yaml`
- Demonstrates accessing structured response data

**Key concepts**: Azure OpenAI integration, credential management, structured outputs

### 5. **OpenAI Responses Agent** ([`openai_responses_agent.py`](./openai_responses_agent.py))

Demonstrates the simplest possible agent using OpenAI directly.

- Uses OpenAI API (requires `OPENAI_API_KEY` environment variable)
- Shows minimal configuration needed for basic agent creation
- Loads agent configuration from `agent-samples/openai/OpenAIResponses.yaml`

**Key concepts**: OpenAI integration, minimal setup, environment-based configuration

## Agent Samples Repository

All the YAML configuration files referenced in these samples are located in the [`agent-samples`](../../../../agent-samples/) folder at the repository root. This folder contains declarative agent specifications organized by provider:

- **`agent-samples/azure/`** - Azure OpenAI agent configurations
- **`agent-samples/chatclient/`** - Chat client agent configurations with tools
- **`agent-samples/foundry/`** - Azure AI Foundry agent configurations
- **`agent-samples/openai/`** - OpenAI agent configurations

**Important**: These YAML files are **platform-agnostic** and work with both Python and .NET implementations of the Agent Framework. You can use the exact same YAML definition to create agents in either language, making it easy to share agent configurations across different technology stacks.

These YAML files define:
- Agent instructions and system prompts
- Model selection and parameters
- Tool and function configurations
- Provider-specific settings
- MCP server integrations (where applicable)

## Common Patterns

### Creating an Agent from YAML String

```python
from agent_framework.declarative import AgentFactory

with open("agent.yaml", "r") as f:
    yaml_str = f.read()

agent = AgentFactory().create_agent_from_yaml(yaml_str)
# response = await agent.run("Your query here")
```

### Creating an Agent from YAML Path

```python
from pathlib import Path
from agent_framework.declarative import AgentFactory

yaml_path = Path("agent.yaml")
agent = AgentFactory().create_agent_from_yaml_path(yaml_path)
# response = await agent.run("Your query here")
```

### Binding Custom Functions

```python
from pathlib import Path
from agent_framework.declarative import AgentFactory

def my_function(param: str) -> str:
    return f"Result: {param}"

agent_factory = AgentFactory(bindings={"my_function": my_function})
agent = agent_factory.create_agent_from_yaml_path(Path("agent_with_tool.yaml"))
```

### Using Credentials

```python
from pathlib import Path
from agent_framework.declarative import AgentFactory
from azure.identity import AzureCliCredential

agent = AgentFactory(
    client_kwargs={"credential": AzureCliCredential()}
).create_agent_from_yaml_path(Path("azure_agent.yaml"))
```

### Adding Custom Provider Mappings

```python
from pathlib import Path
from agent_framework.declarative import AgentFactory
# from my_custom_module import MyCustomChatClient

# Register a custom provider mapping
agent_factory = AgentFactory(
    additional_mappings={
        "MyProvider": {
            "package": "my_custom_module",
            "name": "MyCustomChatClient",
            "model_id_field": "model_id",
        }
    }
)

# Now you can reference "MyProvider" in your YAML
# Example YAML snippet:
# model:
#   provider: MyProvider
#   id: my-model-name

agent = agent_factory.create_agent_from_yaml_path(Path("custom_provider.yaml"))
```

This allows you to extend the declarative framework with custom chat client implementations. The mapping requires:
- **package**: The Python package/module to import from
- **name**: The class name of your ChatClientProtocol implementation
- **model_id_field**: The constructor parameter name that accepts the value of the `model.id` field from the YAML

You can reference your custom provider using either `Provider.ApiType` format or just `Provider` in your YAML configuration, as long as it matches the registered mapping.

### Using PowerFx Formulas in YAML

The declarative framework supports PowerFx formulas in YAML values, enabling dynamic configuration based on environment variables and conditional logic. Prefix any value with `=` to evaluate it as a PowerFx expression.

#### Environment Variable Lookup

Access environment variables using the `Env.<variable_name>` syntax:

```yaml
model:
  connection:
    kind: key
    apiKey: =Env.OPENAI_API_KEY
    endpoint: =Env.BASE_URL & "/v1"  # String concatenation with &

  options:
    temperature: 0.7
    maxOutputTokens: =Env.MAX_TOKENS  # Will be converted to appropriate type
```

#### Conditional Logic

Use PowerFx operators for conditional configuration. This is particularly useful for adjusting parameters based on which model is being used:

```yaml
model:
  id: =Env.MODEL_NAME
  options:
    # Set max tokens based on model - using conditional logic
    maxOutputTokens: =If(Env.MODEL_NAME = "gpt-5", 8000, 4000)

    # Adjust temperature for different environments
    temperature: =If(Env.ENVIRONMENT = "production", 0.3, 0.7)

    # Use logical operators for complex conditions
    seed: =If(Env.ENVIRONMENT = "production" And Env.DETERMINISTIC = "true", 42, Blank())
```

#### Supported PowerFx Features

- **String operations**: Concatenation (`&`), comparison (`=`, `<>`), substring testing (`in`, `exactin`)
- **Logical operators**: `And`, `Or`, `Not` (also `&&`, `||`, `!`)
- **Arithmetic**: Basic math operations (`+`, `-`, `*`, `/`)
- **Conditional**: `If(condition, true_value, false_value)`
- **Environment access**: `Env.<VARIABLE_NAME>`

Example with multiple features:

```yaml
instructions: =If(
  Env.USE_EXPERT_MODE = "true",
  "You are an expert AI assistant with advanced capabilities. " & Env.CUSTOM_INSTRUCTIONS,
  "You are a helpful AI assistant."
)

model:
  options:
    stopSequences: =If("gpt-4" in Env.MODEL_NAME, ["END", "STOP"], ["END"])
```

**Note**: PowerFx evaluation happens when the YAML is loaded, not at runtime. Use environment variables (via `.env` file or `env_file` parameter) to make configurations flexible across environments.

## Running the Samples

Each sample can be run independently. Make sure you have the required environment variables set:

- For Azure samples: Ensure you're logged in via Azure CLI (`az login`)
- For OpenAI samples: Set `OPENAI_API_KEY` environment variable

```bash
# Run a specific sample
python get_weather_agent.py
python microsoft_learn_agent.py
python inline_yaml.py
python azure_openai_responses_agent.py
python openai_responses_agent.py
```

## Learn More

- [Agent Framework Declarative Package](../../../packages/declarative/) - Main declarative package documentation
- [Agent Samples](../../../../agent-samples/) - Additional declarative agent YAML specifications
- [Agent Framework Core](../../../packages/core/) - Core agent framework documentation

## Next Steps

1. Explore the YAML files in the `agent-samples` folder to understand the configuration format
2. Try modifying the samples to use different models or instructions
3. Create your own declarative agent configurations
4. Build custom function tools and bind them to your agents
