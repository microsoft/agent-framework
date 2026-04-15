![Microsoft Agent Framework](docs/assets/readme-banner.png)

# Welcome to Microsoft Agent Framework!

[![Microsoft Foundry Discord](https://dcbadge.limes.pink/api/server/b5zjErwbQM?style=flat)](https://discord.gg/b5zjErwbQM)
[![MS Learn Documentation](https://img.shields.io/badge/MS%20Learn-Documentation-blue)](https://learn.microsoft.com/en-us/agent-framework/)
[![PyPI](https://img.shields.io/pypi/v/agent-framework)](https://pypi.org/project/agent-framework/)
[![NuGet](https://img.shields.io/nuget/v/Microsoft.Agents.AI)](https://www.nuget.org/profiles/MicrosoftAgentFramework/)

Welcome to Microsoft's comprehensive multi-language framework for building, orchestrating, and deploying AI agents with support for both .NET and Python implementations. This framework provides everything from simple chat agents to complex multi-agent workflows with graph-based orchestration.

<p align="center">
  <a href="https://www.youtube.com/watch?v=AAgdMhftj8w" title="Watch the full Agent Framework introduction (30 min)">
    <img src="https://img.youtube.com/vi/AAgdMhftj8w/hqdefault.jpg"
         alt="Watch the full Agent Framework introduction (30 min)" width="480">
  </a>
</p>
<p align="center">
  <a href="https://www.youtube.com/watch?v=AAgdMhftj8w">
    Watch the full Agent Framework introduction (30 min)
  </a>
</p>

## 📋 Getting Started

### 📦 Installation

Python

```bash
pip install agent-framework
# This will install all sub-packages, see `python/packages` for individual packages.
# It may take a minute on first install on Windows.
```

.NET

```bash
dotnet add package Microsoft.Agents.AI
```

### 📚 Documentation

- **[Overview](https://learn.microsoft.com/agent-framework/overview/agent-framework-overview)** - High level overview of the framework
- **[Quick Start](https://learn.microsoft.com/agent-framework/tutorials/quick-start)** - Get started with a simple agent
- **[Tutorials](https://learn.microsoft.com/agent-framework/tutorials/overview)** - Step by step tutorials
- **[User Guide](https://learn.microsoft.com/en-us/agent-framework/user-guide/overview)** - In-depth user guide for building agents and workflows
- **[Migration from Semantic Kernel](https://learn.microsoft.com/en-us/agent-framework/migration-guide/from-semantic-kernel)** - Guide to migrate from Semantic Kernel
- **[Migration from AutoGen](https://learn.microsoft.com/en-us/agent-framework/migration-guide/from-autogen)** - Guide to migrate from AutoGen

Still have questions? Join our [weekly office hours](./COMMUNITY.md#public-community-office-hours) or ask questions in our [Discord channel](https://discord.gg/b5zjErwbQM) to get help from the team and other users.

### ✨ **Highlights**

- **Graph-based Workflows**: Connect agents and deterministic functions using data flows with streaming, checkpointing, human-in-the-loop, and time-travel capabilities
  - [Python workflows](./python/samples/03-workflows/) | [.NET workflows](./dotnet/samples/03-workflows/)
- **AF Labs**: Experimental packages for cutting-edge features including benchmarking, reinforcement learning, and research initiatives
  - [Labs directory](./python/packages/lab/)
- **DevUI**: Interactive developer UI for agent development, testing, and debugging workflows
  - [DevUI package](./python/packages/devui/)

<p align="center">
  <a href="https://www.youtube.com/watch?v=mOAaGY4WPvc">
    <img src="https://img.youtube.com/vi/mOAaGY4WPvc/hqdefault.jpg" alt="See the DevUI in action" width="480">
  </a>
</p>
<p align="center">
  <a href="https://www.youtube.com/watch?v=mOAaGY4WPvc">
    See the DevUI in action (1 min)
  </a>
</p>

- **Python and C#/.NET Support**: Full framework support for both Python and C#/.NET implementations with consistent APIs
  - [Python packages](./python/packages/) | [.NET source](./dotnet/src/)
- **Observability**: Built-in OpenTelemetry integration for distributed tracing, monitoring, and debugging
  - [Python observability](./python/samples/02-agents/observability/) | [.NET telemetry](./dotnet/samples/02-agents/AgentOpenTelemetry/)
- **Multiple Agent Provider Support**: Support for various LLM providers with more being added continuously
  - [Python examples](./python/samples/02-agents/providers/) | [.NET examples](./dotnet/samples/02-agents/AgentProviders/)
- **Middleware**: Flexible middleware system for request/response processing, exception handling, and custom pipelines
  - [Python middleware](./python/samples/02-agents/middleware/) | [.NET middleware](./dotnet/samples/02-agents/Agents/Agent_Step11_Middleware/)

### 💬 **We want your feedback!**

- For bugs, please file a [GitHub issue](https://github.com/microsoft/agent-framework/issues).

## Quickstart

### Basic Agent - Python

Create a simple Azure Responses Agent that writes a haiku about the Microsoft Agent Framework

```python
# pip install agent-framework
# Use `az login` to authenticate with Azure CLI
import os
import asyncio
from agent_framework import Agent
from agent_framework.foundry import FoundryChatClient
from azure.identity import AzureCliCredential


async def main():
    # Initialize a chat agent with Microsoft Foundry
    # the endpoint, deployment name, and api version can be set via environment variables
    # or they can be passed in directly to the FoundryChatClient constructor
    agent = Agent(
      client=FoundryChatClient(
          credential=AzureCliCredential(),
          # project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
          # model=os.environ["FOUNDRY_MODEL_DEPLOYMENT_NAME"],
      ),
      name="HaikuBot",
      instructions="You are an upbeat assistant that writes beautifully.",
    )

    print(await agent.run("Write a haiku about Microsoft Agent Framework."))

if __name__ == "__main__":
    asyncio.run(main())
```

### Basic Agent - .NET
Create a simple Agent, using Microsoft Foundry with token-based auth, that writes a haiku about the Microsoft Agent Framework

```c#
// dotnet add package Microsoft.Agents.AI.Foundry
// Use `az login` to authenticate with Azure CLI
using Azure.AI.Projects;
using Azure.Identity;
using System;
using Azure.AI.Projects;
using Azure.Identity;

var endpoint = Environment.GetEnvironmentVariable("AZURE_AI_PROJECT_ENDPOINT") ?? throw new InvalidOperationException("AZURE_AI_PROJECT_ENDPOINT is not set.");
var deploymentName = Environment.GetEnvironmentVariable("AZURE_AI_MODEL_DEPLOYMENT_NAME") ?? "gpt-5.4-mini";

var agent = new AIProjectClient(new Uri(endpoint), new DefaultAzureCredential())
    .AsAIAgent(model: deploymentName, name: "HaikuBot", instructions: "You are an upbeat assistant that writes beautifully.");

Console.WriteLine(await agent.RunAsync("Write a haiku about Microsoft Agent Framework."));
```

Create a simple Agent, using OpenAI Responses, that writes a haiku about the Microsoft Agent Framework

```c#
// dotnet add package Microsoft.Agents.AI.OpenAI
using System;
using OpenAI;
using OpenAI.Responses;

// Replace the <apikey> with your OpenAI API key.
var agent = new OpenAIClient("<apikey>")
    .GetResponsesClient()
    .AsAIAgent(model: "gpt-5.4-mini", name: "HaikuBot", instructions: "You are an upbeat assistant that writes beautifully.");

Console.WriteLine(await agent.RunAsync("Write a haiku about Microsoft Agent Framework."));
```

## More Examples & Samples

### Python

- [Getting Started](./python/samples/01-get-started): progressive tutorial from hello-world to hosting
- [Agent Concepts](./python/samples/02-agents): deep-dive samples by topic (tools, middleware, providers, etc.)
- [Workflows](./python/samples/03-workflows): workflow creation and integration with agents
- [Hosting](./python/samples/04-hosting): A2A, Azure Functions, Durable Task hosting
- [End-to-End](./python/samples/05-end-to-end): full applications, evaluation, and demos

### .NET

- [Getting Started](./dotnet/samples/01-get-started): progressive tutorial from hello agent to hosting
- [Agent Concepts](./dotnet/samples/02-agents/Agents): basic agent creation and tool usage
- [Agent Providers](./dotnet/samples/02-agents/AgentProviders): samples showing different agent providers
- [Workflows](./dotnet/samples/03-workflows): advanced multi-agent patterns and workflow orchestration
- [Hosting](./dotnet/samples/04-hosting): A2A, Durable Agents, Durable Workflows
- [End-to-End](./dotnet/samples/05-end-to-end): full applications and demos

## Troubleshooting

### Authentication

| Problem | Cause | Fix |
|---------|-------|-----|
| Authentication errors when using Azure credentials | Not signed in to Azure CLI | Run `az login` before starting your app |
| API key errors | Wrong or missing API key | Verify the key and ensure it's for the correct resource/provider |

> **Tip:** `DefaultAzureCredential` is convenient for development but in production, consider using a specific credential (e.g., `ManagedIdentityCredential`) to avoid latency issues, unintended credential probing, and potential security risks from fallback mechanisms.

### Environment Variables

The samples typically read configuration from environment variables. Common required variables:

| Variable | Used by | Purpose |
|----------|---------|---------|
| `AZURE_OPENAI_ENDPOINT` | Azure OpenAI samples | Your Azure OpenAI resource URL |
| `AZURE_OPENAI_DEPLOYMENT_NAME` | Azure OpenAI samples | Model deployment name (e.g. `gpt-4o-mini`) |
| `AZURE_AI_PROJECT_ENDPOINT` | Microsoft Foundry samples | Your Microsoft Foundry project endpoint |
| `AZURE_AI_MODEL_DEPLOYMENT_NAME` | Microsoft Foundry samples | Model deployment name |
| `OPENAI_API_KEY` | OpenAI (non-Azure) samples | Your OpenAI platform API key |

## Contributor Resources

- [Contributing Guide](./CONTRIBUTING.md)
- [Python Development Guide](./python/DEV_SETUP.md)
- [Design Documents](./docs/design)
- [Architectural Decision Records](./docs/decisions)

## Important Notes

> [!IMPORTANT]
> If you use Microsoft Agent Framework to build applications that operate with any third-party servers, agents, code, or non-Azure Direct models (“Third-Party Systems”), you do so at your own risk. Third-Party Systems are Non-Microsoft Products under the Microsoft Product Terms and are governed by their own third-party license terms. You are responsible for any usage and associated costs.
>
>We recommend reviewing all data being shared with and received from Third-Party Systems and being cognizant of third-party practices for handling, sharing, retention and location of data. It is your responsibility to manage whether your data will flow outside of your organization’s Azure compliance and geographic boundaries and any related implications, and that appropriate permissions, boundaries and approvals are provisioned.
> 
>You are responsible for carefully reviewing and testing applications you build using Microsoft Agent Framework in the context of your specific use cases, and making all appropriate decisions and customizations. This includes implementing your own responsible AI mitigations such as metaprompt, content filters, or other safety systems, and ensuring your applications meet appropriate quality, reliability, security, and trustworthiness standards. See also: [Transparency FAQ](./TRANSPARENCY_FAQ.md)
