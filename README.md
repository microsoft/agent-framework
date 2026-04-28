![Microsoft Agent Framework](docs/assets/readme-banner.png)

# Welcome to Microsoft Agent Framework!

[![Microsoft Foundry Discord](https://dcbadge.limes.pink/api/server/b5zjErwbQM?style=flat)](https://discord.gg/b5zjErwbQM)
[![MS Learn Documentation](https://img.shields.io/badge/MS%20Learn-Documentation-blue)](https://learn.microsoft.com/en-us/agent-framework/)
[![PyPI](https://img.shields.io/pypi/v/agent-framework)](https://pypi.org/project/agent-framework/)
[![NuGet](https://img.shields.io/nuget/v/Microsoft.Agents.AI)](https://www.nuget.org/profiles/MicrosoftAgentFramework/)
[![GitHub stars](https://img.shields.io/github/stars/microsoft/agent-framework?style=social)](https://github.com/microsoft/agent-framework/stargazers)


Microsoft Agent Framework (MAF) is an open, multi-language framework for building **production-grade AI agents and multi-agent workflows** in **.NET and Python**.

It is designed for teams moving beyond prototypes who need:
- a consistent agent programming model with tools, middleware, and provider flexibility,
- graph-based workflows with checkpointing, streaming, human-in-the-loop, and time-travel,
- durable and restartable execution for long-running, stateful orchestration,
- interoperable architectures through MCP and Agent-to-Agent (A2A) communication,
- built-in observability and tracing with OpenTelemetry,
- and practical paths to test, host, and operate agents in real production systems.

MAF supports a broad ecosystem including Azure AI Foundry, Azure OpenAI, OpenAI, and GitHub Copilot SDK, with samples and hosting patterns for both local development and cloud deployment.


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

## Is this the right framework for you?

✅ MAF is a strong fit if you:
- are building agents and workflows you expect to run in production,
- need orchestration beyond a single prompt or stateless chat loop,
- want graph-based patterns such as sequential, concurrent, handoff, and group collaboration,
- care about durability, restartability, observability, governance, or human-in-the-loop control,
- need provider flexibility so your architecture can evolve without major rewrites.

💡 If your scope is limited to experimentation or simple single-prompt chatbots,
MAF may be more than what you need today. It is intentionally designed for systems where agent behavior, reliability, and operational needs grow over time.

## ✨ Key Features
- **Python and C#/.NET Support**: Full framework support for both Python and C#/.NET implementations with consistent APIs
  - [Python packages](./python/packages/) | [.NET source](./dotnet/src/)
- **Multiple Agent Provider Support**: Support for various LLM providers with more being added continuously
  - [Python examples](./python/samples/02-agents/providers/) | [.NET examples](./dotnet/samples/02-agents/AgentProviders/)
- **Middleware**: Flexible middleware system for request/response processing, exception handling, and custom pipelines
  - [Python middleware](./python/samples/02-agents/middleware/) | [.NET middleware](./dotnet/samples/02-agents/Agents/Agent_Step11_Middleware/)
- **Orchestration Patterns & Workflows**: Build multi-agent systems with graph-based workflows supporting sequential, concurrent, handoff, and group collaboration patterns; includes checkpointing, streaming, human-in-the-loop, and time-travel
  - [Python workflows](./python/samples/03-workflows/) | [.NET workflows](./dotnet/samples/03-workflows/)
- **Foundry Hosted Agents (new)**: Deploy and host your agents to Foundry-hosted infrastructure with just 2 additional lines of code
  - [Python samples](./python/samples/04-hosting/foundry-hosted-agents/) | [.NET samples](./dotnet/samples/04-hosting/FoundryHostedAgents/)
- **Observability**: Built-in OpenTelemetry integration for distributed tracing, monitoring, and debugging
  - [Python observability](./python/samples/02-agents/observability/) | [.NET telemetry](./dotnet/samples/02-agents/AgentOpenTelemetry/)
- **Declarative Agents**: Define agents using YAML for faster setup and versioning
  - [Declarative agent samples](./declarative-agents/)
- **Agent Skills**: Build domain-specific knowledge bases from multiple sources—files, inline code, class libraries—for agents to discover and use
  - [Skills design](./docs/decisions/0021-agent-skills-design.md)
- **AF Labs**: Experimental packages for cutting-edge features including benchmarking, reinforcement learning, and research initiatives
  - [Labs directory](./python/packages/lab/)
- **DevUI**: Interactive developer UI for agent development, testing, and debugging workflows
  - [See the DevUI in action](https://www.youtube.com/watch?v=mOAaGY4WPvc)

## 📖 Table of Contents

- [Getting Started](#-getting-started)
  - [Installation](#-installation)
  - [Learning Resources](#-learning-resources)
  - [Quickstart](#quickstart)
    - [Basic Agent - Python](#basic-agent---python)
    - [Basic Agent - .NET](#basic-agent---net)
- [More Examples & Samples](#more-examples--samples)
- [Community & Feedback](#-community--feedback)
- [Troubleshooting](#troubleshooting)
- [Contributor Resources](#contributor-resources)

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
# For Foundry integration (used in the .NET quickstart below):
dotnet add package Microsoft.Agents.AI.Foundry
dotnet add package Azure.AI.Projects
dotnet add package Azure.Identity
```

### 📚 Learning Resources

- **[Overview](https://learn.microsoft.com/agent-framework/overview/agent-framework-overview)** - High level overview of the framework
- **[Quick Start](https://learn.microsoft.com/agent-framework/tutorials/quick-start)** - Get started with a simple agent
- **[Tutorials](https://learn.microsoft.com/agent-framework/tutorials/overview)** - Step by step tutorials
- **[User Guide](https://learn.microsoft.com/en-us/agent-framework/user-guide/overview)** - In-depth user guide for building agents and workflows
- **[Migration from Semantic Kernel](https://learn.microsoft.com/en-us/agent-framework/migration-guide/from-semantic-kernel)** - Guide to migrate from Semantic Kernel
- **[Migration from AutoGen](https://learn.microsoft.com/en-us/agent-framework/migration-guide/from-autogen)** - Guide to migrate from AutoGen

### Quickstart

#### Basic Agent - Python

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
      name="HaikuAgent",
      instructions="You are an upbeat assistant that writes beautifully.",
    )

    print(await agent.run("Write a haiku about Microsoft Agent Framework."))

if __name__ == "__main__":
    asyncio.run(main())
```

#### Basic Agent - .NET
Create a simple Agent, using Microsoft Foundry that writes a haiku about the Microsoft Agent Framework

```c#
// This sample shows how to create and run a basic agent with AIProjectClient.AsAIAgent(...).

using Azure.AI.Projects;
using Azure.Identity;
using Microsoft.Agents.AI;

string endpoint = Environment.GetEnvironmentVariable("AZURE_AI_PROJECT_ENDPOINT") ?? throw new InvalidOperationException("AZURE_AI_PROJECT_ENDPOINT is not set.");
string deploymentName = Environment.GetEnvironmentVariable("AZURE_AI_MODEL_DEPLOYMENT_NAME") ?? "gpt-5.4-mini";

AIAgent agent =
    new AIProjectClient(new Uri(endpoint), new DefaultAzureCredential())
    .AsAIAgent(model: deploymentName, instructions: "You are an upbeat assistant that writes beautifully.", name: "HaikuAgent");

// Once you have the agent, you can invoke it like any other AIAgent.
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

## 💬 Community & Feedback

- **Found a bug?** File a [GitHub issue](https://github.com/microsoft/agent-framework/issues) to help us improve.
- **Enjoying MAF?** [![GitHub stars](https://img.shields.io/badge/⭐-Star%20us%20on%20GitHub-yellow)](https://github.com/microsoft/agent-framework) to show your support and help others discover the project.
- **Have questions?** Join our [Discord](https://discord.gg/b5zjErwbQM) or visit [weekly office hours](./COMMUNITY.md#public-community-office-hours).

## Troubleshooting

### Authentication

| Problem | Cause | Fix |
|---------|-------|-----|
| Authentication errors when using Azure credentials | Not signed in to Azure CLI | Run `az login` before starting your app |
| API key errors | Wrong or missing API key | Verify the key and ensure it's for the correct resource/provider |

> **Tip:** `DefaultAzureCredential` is convenient for development but in production, consider using a specific credential (e.g., `ManagedIdentityCredential`) to avoid latency issues, unintended credential probing, and potential security risks from fallback mechanisms.

### Environment Variables
For environment variable configuration specific to each sample, refer to the README in the sample directory ([Python samples](./python/samples/) | [.NET samples](./dotnet/samples/)).

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
