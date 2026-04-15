# Basic example of hosting an agent with the `responses` API and local tools

This agent is equipped with with a function tool and a local shell tool.

> We recommend deploying this sample on a local container or to Foundry Hosting because the agent has access to a local shell tool, which can run arbitrary commands on the machine.

## Interacting with the agent

Send a POST request to the server with a JSON body containing a "message" field to interact with the agent. For example:

```bash
curl -X POST http://localhost:8088/responses -H "Content-Type: application/json" -d '{"input": "What is the weather in Seattle?"}'

curl -X POST http://localhost:8088/responses -H "Content-Type: application/json" -d '{"input": "List the files in the current directory."}'
```

Invoke with `azd`:

```bash
azd ai agent invoke --local "What is the weather in Seattle?"

azd ai agent invoke --local "List the files in the current directory."
```
