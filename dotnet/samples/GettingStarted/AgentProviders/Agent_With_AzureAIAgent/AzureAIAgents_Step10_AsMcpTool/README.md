This sample demonstrates how to expose an existing AI agent as an MCP tool.

## Run the sample

To run the sample, please use one of the following MCP clients: https://modelcontextprotocol.io/clients

Alternatively, use the QuickstartClient sample from this repository: https://github.com/modelcontextprotocol/csharp-sdk/tree/main/samples/QuickstartClient

## Run the sample using MCP Inspector

To use the [MCP Inspector](https://modelcontextprotocol.io/docs/tools/inspector), follow these steps:

1. Open a terminal in the Agent_Step10_AsMcpTool project directory.
1. Run the `npx @modelcontextprotocol/inspector dotnet run` command to start the MCP Inspector. Make sure you have [node.js](https://nodejs.org/en/download/) and npm installed.
   ```bash
   npx @modelcontextprotocol/inspector dotnet run
   ```
1. When the inspector is running, it will display a URL in the terminal, like this:
   ```
   MCP Inspector is up and running at http://127.0.0.1:6274
   ```
1. Open a web browser and navigate to the URL displayed in the terminal. If not opened automatically, this will open the MCP Inspector interface.
1. In the MCP Inspector interface, add the following environment variables to allow your MCP server to access Azure AI Foundry Project to create and run the agent:
    - AZURE_FOUNDRY_PROJECT_ENDPOINT = https://your-resource.openai.azure.com/ # Replace with your Azure AI Foundry Project endpoint
    - AZURE_FOUNDRY_PROJECT_DEPLOYMENT_NAME = gpt-4o-mini # Replace with your model deployment name
1. Find and click the `Connect` button in the MCP Inspector interface to connect to the MCP server.
1. As soon as the connection is established, open the `Tools` tab in the MCP Inspector interface and select the `Joker` tool from the list.
1. Specify your prompt as a value for the `query` argument, for example: `Tell me a joke about a pirate` and click the `Run Tool` button to run the tool.
1. The agent will process the request and return a response in accordance with the provided instructions that instruct it to always start each joke with 'Aye aye, captain!'.