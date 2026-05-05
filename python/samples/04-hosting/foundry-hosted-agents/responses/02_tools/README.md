# What this sample demonstrates

An [Agent Framework](https://github.com/microsoft/agent-framework) agent with **locally-defined Python tools** hosted using the **Responses protocol**. It shows how to define custom tools with the `@tool` decorator and register them with the agent so the model can call them during a conversation.

## How It Works

### Model Integration

The agent uses `FoundryChatClient` from the Agent Framework to create a Responses client from the project endpoint and model deployment. The agent supports both streaming (SSE events) and non-streaming (JSON) response modes.

See [main.py](main.py) for the full implementation.

### Tools

Local tools are Python functions decorated with the Agent Framework's `@tool` decorator and registered with the agent. When the model chooses to call a tool during a conversation, the agent executes the corresponding function and returns the result to the model.

Each tool can be configured with one of two approval modes: **always_require** or **never_require**. With **always_require**, the agent requests explicit user approval before every invocation; with **never_require**, the agent invokes the tool automatically. To illustrate both behaviors, this sample defines two tools—one using `always_require` and the other using `never_require`.

When a tool is set to `always_require`, the agent host emits an `mcp_approval_request` output containing the approval request ID and details of the pending tool call. The client must reply with an `mcp_approval_response` indicating the same request ID and whether the user approved or denied the call before the agent will proceed.

> IMPORTANT: We are temporarily reusing the **mcp_approval_request** and **mcp_approval_response** message types defined in the [AzureAI AgentServer SDK](https://github.com/Azure/azure-sdk-for-python/blob/main/sdk/agentserver/azure-ai-agentserver-responses/docs/handler-implementation-guide.md#other-tool-call-types) because they map closely to this approval flow. They will likely be superseded by a more formal tool-approval content type in the Responses protocol in the future.

### Agent Hosting

The agent is hosted using the [Agent Framework](https://github.com/microsoft/agent-framework) with the `ResponsesHostServer`, which provisions a REST API endpoint compatible with the OpenAI Responses protocol.

## Running the Agent Host

Follow the instructions in the [Running the Agent Host Locally](../../README.md#running-the-agent-host-locally) section of the README in the parent directory to run the agent host.

## Interacting with the agent

> Depending on how you run the agent host, you can invoke the agent using `curl` (`Invoke-WebRequest` in PowerShell) or `azd`. Please refer to the [parent README](../../README.md) for more details. Use this README for sample queries you can send to the agent.

Send a POST request to the server with a JSON body containing an `"input"` field to interact with the agent. For example:

```bash
curl -X POST http://localhost:8088/responses -H "Content-Type: application/json" -d '{"input": "What is the weather in Seattle?"}'
```

Send a POST request that triggers a tool call configured with `always_require` to see the approval flow in action:

```bash
curl -X POST http://localhost:8088/responses -H "Content-Type: application/json" -d '{"input": "List all the files in the current directory."}'
```

Sample output:

```bash
{"id":"caresp_3b6cba8c972b1d2f00bXmjpUGzfgSFsmgjtlgqUwqvROwl5lyG","object":"response","output":[{"type":"function_call","id":"fc_3b6cba8c972b1d2f00JIAQktGC1upcB6Dgxp1AVVLp0MoyRTX4","call_id":"call_hWwwZ8lqVQCAuo8ZyY4LXIya","name":"run_bash","arguments":"{\"command\":\"ls -la\"}","status":"completed","response_id":"caresp_3b6cba8c972b1d2f00bXmjpUGzfgSFsmgjtlgqUwqvROwl5lyG","agent_reference":null},{"type":"mcp_approval_request","id":"mcpr_3b6cba8c972b1d2f00IdqsjB6iidFmtsuYp6oI1AoAtUKQZxje","server_label":"agent_framework","name":"run_bash","arguments":"{\"command\":\"ls -la\"}","response_id":"caresp_3b6cba8c972b1d2f00bXmjpUGzfgSFsmgjtlgqUwqvROwl5lyG","agent_reference":null}],"created_at":1778021855,"model":"","status":"completed","completed_at":1778021865,"response_id":"caresp_3b6cba8c972b1d2f00bXmjpUGzfgSFsmgjtlgqUwqvROwl5lyG","agent_reference":{"type":"agent_reference"},"agent_session_id":"8caaaa19598306a1f2fb6d8939ef06874c52c63a83b57681ea4e4b75cf6a179","background":false}
```

To approve:

```bash
curl -X POST http://localhost:8088/responses -H "Content-Type: application/json" -d '{"input": [{"type": "mcp_approval_response", "approval_request_id": "mcpr_3b6cba8c972b1d2f00IdqsjB6iidFmtsuYp6oI1AoAtUKQZxje", "approve": true}], "previous_response_id": "caresp_3b6cba8c972b1d2f00bXmjpUGzfgSFsmgjtlgqUwqvROwl5lyG"}'
```

## Deploying the Agent to Foundry

To host the agent on Foundry, follow the instructions in the [Deploying the Agent to Foundry](../../README.md#deploying-the-agent-to-foundry) section of the README in the parent directory.
