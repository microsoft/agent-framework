**IMPORTANT!** All samples and other resources made available in this GitHub repository are designed to assist in accelerating development of agents, solutions, and agent workflows for various scenarios. Review all provided resources and carefully test output behavior in the context of your use case. AI responses may be inaccurate and AI actions should be monitored with human oversight. Learn more in the transparency documents for [Agent Service](https://learn.microsoft.com/en-us/azure/ai-foundry/responsible-ai/agents/transparency-note) and [Agent Framework](https://github.com/microsoft/agent-framework/blob/main/TRANSPARENCY_FAQ.md).
 
Agents, solutions, or other output you create may be subject to legal and regulatory requirements, may require licenses, or may not be suitable for all industries, scenarios, or use cases. By using any sample, you are acknowledging that any output created using those samples are solely your responsibility, and that you will comply with all applicable laws, regulations, and relevant safety standards, terms of service, and codes of conduct.
 
Third-party samples contained in this folder are subject to their own designated terms, and they have not been tested or verified by Microsoft or its affiliates.
 
Microsoft has no responsibility to you or others with respect to any of these samples or any resulting output.

# What this sample demonstrates

This sample demonstrates how to use a Hosted Model Context Protocol (MCP) server with a 
[Microsoft Agent Framework](https://learn.microsoft.com/en-us/agent-framework/overview/agent-framework-overview#ai-agents) AI agent and
host it using [Azure AI AgentServer SDK](https://learn.microsoft.com/en-us/dotnet/api/overview/azure/ai.agentserver.agentframework-readme) and 
deploy it to Microsoft Foundry using the Azure Developer CLI [ai agent](https://aka.ms/azdaiagent/docs) extension.

## How It Works

### MCP Integration

This sample uses a Hosted Model Context Protocol (MCP) server to provide external tools to the agent. The MCP workflow operates as follows:

1. The agent is configured with a `HostedMcpServerTool` pointing to `https://learn.microsoft.com/api/mcp`
2. Only the `microsoft_docs_search` tool is enabled from the available MCP tools
3. Approval mode is set to `NeverRequire`, allowing automatic tool execution without user confirmation
4. When you ask questions, the Azure OpenAI Responses service automatically invokes the MCP tool to search Microsoft Learn documentation
5. The agent returns answers based on the retrieved Microsoft Learn content

**Note**: In this configuration, the Azure OpenAI Responses service manages tool invocation directly - the Agent Framework does not handle MCP tool calls.

### Agent Hosting

The agent is hosted using the [Azure AI AgentServer SDK](https://learn.microsoft.com/en-us/dotnet/api/overview/azure/ai.agentserver.agentframework-readme),
which provisions a REST API endpoint compatible with the OpenAI Responses protocol. This allows interaction with the agent using OpenAI Responses compatible clients.

### Agent Deployment

The hosted agent can be seamlessly deployed to Microsoft Foundry using the Azure Developer CLI [ai agent](https://aka.ms/azdaiagent/docs) extension.
The extension builds a container image for the agent, deploys it to Azure Container Instances (ACI), and creates a hosted agent version and deployment on Foundry Agent Service.

## Running the Agent Locally

### Prerequisites

Before running this sample, ensure you have:

1. An Azure OpenAI endpoint configured
2. A deployment of a chat model (e.g., `gpt-4o-mini`)
3. Azure CLI installed and authenticated (`az login`)
4. .NET 10 SDK or later installed

### Environment Variables

Set the following environment variables:

- `AZURE_OPENAI_ENDPOINT` - Your Azure OpenAI endpoint URL (required)
- `AZURE_OPENAI_DEPLOYMENT_NAME` - The deployment name for your chat model (optional, defaults to `gpt-4o-mini`)

**PowerShell:**
```powershell
# Replace with your Azure OpenAI endpoint
$env:AZURE_OPENAI_ENDPOINT="https://your-openai-resource.openai.azure.com/"

# Optional, defaults to gpt-4o-mini
$env:AZURE_OPENAI_DEPLOYMENT_NAME="gpt-4o-mini"
```

### Running the Sample

To run the agent, execute the following command in your terminal:

```powershell
dotnet run
```

This will start the hosted agent locally on `http://localhost:8080/`.

### Interacting with the Agent

You can interact with the agent using:

- The `run-requests.http` file in this directory to test and prompt the agent
- Any OpenAI Responses compatible client by sending requests to `http://localhost:8080/`

Try asking questions about Microsoft documentation and technologies to see the MCP tool in action.

### Deploying the Agent to Microsoft Foundry

To deploy your agent to Microsoft Foundry, follow the comprehensive deployment guide at https://aka.ms/azdaiagent/docs