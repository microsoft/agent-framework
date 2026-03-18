# Workflow as MCP Tool Sample

This sample demonstrates how to expose durable workflows as [MCP (Model Context Protocol)](https://modelcontextprotocol.io/) tools, enabling MCP-compatible clients to invoke workflows directly.

## Key Concepts Demonstrated

- **Workflow as MCP Tool**: Expose workflows as callable MCP tools using `exposeMcpToolTrigger: true`
- **MCP Server Hosting**: The Azure Functions host automatically generates a remote MCP endpoint at `/runtime/webhooks/mcp`
- **String and POCO Results**: Shows workflows returning both plain strings and structured JSON objects

## Sample Architecture

The sample creates two workflows exposed as MCP tools:

### Translate Workflow (returns a string)

| Executor | Input | Output | Description |
|----------|-------|--------|-------------|
| **TranslateText** | `string` | `TranslationResult` | Converts input text to uppercase |
| **FormatOutput** | `TranslationResult` | `string` | Formats the result into a readable string |

### OrderLookup Workflow (returns a POCO)

| Executor | Input | Output | Description |
|----------|-------|--------|-------------|
| **LookupOrder** | `string` | `OrderInfo` | Looks up an order by ID |
| **EnrichOrder** | `OrderInfo` | `OrderSummary` | Adds computed fields (total price, status) |

## Environment Setup

See the [README.md](../../README.md) file in the parent directory for complete setup instructions, including:

- Prerequisites installation
- Durable Task Scheduler setup
- Storage emulator configuration

For this sample, you'll also need [Node.js](https://nodejs.org/en/download) to use the [MCP Inspector](https://modelcontextprotocol.io/docs/tools/inspector).

## Running the Sample

1. **Start the Function App**:

   ```bash
   cd dotnet/samples/04-hosting/DurableWorkflows/AzureFunctions/04_WorkflowMcpTool
   func start
   ```

2. **Note the MCP Server Endpoint**: When the app starts, you'll see the MCP server endpoint in the terminal output:

   ```text
   MCP server endpoint:  http://localhost:7071/runtime/webhooks/mcp
   ```

## Invoking Workflows via MCP Inspector

1. Install and run the [MCP Inspector](https://modelcontextprotocol.io/docs/tools/inspector):

   ```bash
   npx @modelcontextprotocol/inspector
   ```

2. Connect to the MCP server endpoint:
   - For **Transport Type**, select **"Streamable HTTP"**
   - For **URL**, enter `http://localhost:7071/runtime/webhooks/mcp`
   - Click the **Connect** button

3. Click the **List Tools** button. You should see two tools: `Translate` and `OrderLookup`.

4. Test the **Translate** tool (returns a plain string):
   - Select the `Translate` tool
   - Set `hello world` as the `input` parameter
   - Click **Run Tool**
   - Expected result: `Original: hello world => Translated: HELLO WORLD`

5. Test the **OrderLookup** tool (returns a JSON object):
   - Select the `OrderLookup` tool
   - Set `ORD-2025-42` as the `input` parameter
   - Click **Run Tool**
   - Expected result: A JSON object containing order details such as `OrderId`, `CustomerName`, `Product`, `TotalPrice`, and `Status`

You'll see the workflow executor activities logged in the terminal where you ran `func start`.
