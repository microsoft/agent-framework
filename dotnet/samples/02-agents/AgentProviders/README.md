# Creating an AIAgent with various providers

These samples show how to create an AIAgent instance using various providers,
organized by provider. This is not an exhaustive list, but shows a variety of
the more popular options.

For other samples that demonstrate how to use AIAgent instances,
see the [Getting Started With Agents](../Agents/README.md) samples.

## Prerequisites

See the README.md for each sample for the prerequisites for that sample.

## Providers

### [A2A](./a2a/)

| Sample | Description |
| --- | --- |
| [Agent with A2A](./a2a/Agent_With_A2A/) | Create an AIAgent for an existing A2A agent |

### [Anthropic](./anthropic/)

| Sample | Description |
| --- | --- |
| [Agent with Anthropic](./anthropic/Agent_With_Anthropic/) | Create an AIAgent using Anthropic Claude models |
| [Running](./anthropic/Agent_Anthropic_Step01_Running/) | Basic Anthropic agent usage |
| [Reasoning](./anthropic/Agent_Anthropic_Step02_Reasoning/) | Using Anthropic reasoning capabilities |
| [Function Tools](./anthropic/Agent_Anthropic_Step03_UsingFunctionTools/) | Using function tools with Anthropic |
| [Skills](./anthropic/Agent_Anthropic_Step04_UsingSkills/) | Using skills with Anthropic agents |

### [Azure](./azure/)

| Sample | Description |
| --- | --- |
| [Azure AI Project](./azure/Agent_With_AzureAIProject/) | Create a Foundry Project agent using the Azure.AI.Project SDK |
| [Azure Foundry Model](./azure/Agent_With_AzureFoundryModel/) | Use any model deployed to Microsoft Foundry |
| [Azure OpenAI ChatCompletion](./azure/Agent_With_AzureOpenAIChatCompletion/) | Create an AIAgent using Azure OpenAI ChatCompletion |
| [Azure OpenAI Responses](./azure/Agent_With_AzureOpenAIResponses/) | Create an AIAgent using Azure OpenAI Responses |

### [Custom](./custom/)

| Sample | Description |
| --- | --- |
| [Custom Implementation](./custom/Agent_With_CustomImplementation/) | Create an AIAgent with a custom implementation |

### [Foundry](./foundry/)

See [foundry/README.md](./foundry/README.md) for the full list of Foundry agent samples,
covering basics, function tools, structured output, middleware, MCP, code interpreter, and more.

### [GitHub Copilot](./github-copilot/)

| Sample | Description |
| --- | --- |
| [GitHub Copilot](./github-copilot/Agent_With_GitHubCopilot/) | Create an AIAgent using GitHub Copilot SDK |

### [Google Gemini](./google-gemini/)

| Sample | Description |
| --- | --- |
| [Google Gemini](./google-gemini/Agent_With_GoogleGemini/) | Create an AIAgent using Google Gemini |

### [Ollama](./ollama/)

| Sample | Description |
| --- | --- |
| [Ollama](./ollama/Agent_With_Ollama/) | Create an AIAgent using Ollama |

### [ONNX](./onnx/)

| Sample | Description |
| --- | --- |
| [ONNX](./onnx/Agent_With_ONNX/) | Create an AIAgent using ONNX Runtime |

### [OpenAI](./openai/)

| Sample | Description |
| --- | --- |
| [OpenAI ChatCompletion](./openai/Agent_With_OpenAIChatCompletion/) | Create an AIAgent using OpenAI ChatCompletion |
| [OpenAI Responses](./openai/Agent_With_OpenAIResponses/) | Create an AIAgent using OpenAI Responses |
| [Running](./openai/Agent_OpenAI_Step01_Running/) | Basic OpenAI agent usage |
| [Reasoning](./openai/Agent_OpenAI_Step02_Reasoning/) | Using OpenAI reasoning capabilities |
| [Create from ChatClient](./openai/Agent_OpenAI_Step03_CreateFromChatClient/) | Create agent from IChatClient |
| [Create from Response Client](./openai/Agent_OpenAI_Step04_CreateFromOpenAIResponseClient/) | Create agent from OpenAI Response client |
| [Conversation](./openai/Agent_OpenAI_Step05_Conversation/) | Multi-turn conversations with OpenAI |
| [Code Interpreter](./openai/Agent_OpenAI_Step06_CodeInterpreterFileDownload/) | Code interpreter with file downloads |

## Running the samples

Navigate to a sample directory and run:

```powershell
dotnet run
```

Set the required environment variables as documented in each sample's README.
If the variables are not set, you will be prompted for the values when running the samples.
