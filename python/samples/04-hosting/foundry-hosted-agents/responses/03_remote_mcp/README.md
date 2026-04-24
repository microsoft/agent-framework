# Basic example of hosting an agent with the `responses` API and a remote MCP

This agent is equipped with a GitHub MCP server and a Foundry Toolbox, which are both remote MCPs.

> Note that there are other ways to interact with Foundry toolboxes. Using it as a MCP is just one of the options.

## Running the server locally

### Environment setup

Follow the instructions in the [Environment setup](../../README.md#environment-setup) section of the README in the parent directory to set up your environment and install dependencies.

Run the following command to start the server:

```bash
python main.py
```

## Interacting with the agent

Send a POST request to the server with a JSON body containing a "input" field to interact with the agent. For example:

```bash
curl -X POST http://localhost:8088/responses -H "Content-Type: application/json" -d '{"input": "List all the repositories I own on GitHub."}'
```
