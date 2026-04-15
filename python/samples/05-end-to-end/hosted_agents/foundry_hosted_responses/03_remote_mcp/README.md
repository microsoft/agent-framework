# Basic example of hosting an agent with the `responses` API and a remote MCP

This agent is equipped with a GitHub MCP server and a Foundry Toolbox, which are both remote MCPs.

## Interacting with the agent

Send a POST request to the server with a JSON body containing a "message" field to interact with the agent. For example:

```bash
curl -X POST http://localhost:8088/responses -H "Content-Type: application/json" -d '{"input": "List all the repositories I own on GitHub."}'
```

Invoke with `azd`:

```bash
azd ai agent invoke --local "List all the repositories I own on GitHub."
```
