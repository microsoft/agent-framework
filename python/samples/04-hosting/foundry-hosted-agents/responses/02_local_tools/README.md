# Basic example of hosting an agent with the `responses` API and local tools

This agent is equipped with a function tool and a local shell tool.

> We recommend deploying this sample on a local container or to Foundry Hosting because the agent has access to a local shell tool, which can run arbitrary commands on the machine.

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
curl -X POST http://localhost:8088/responses -H "Content-Type: application/json" -d '{"input": "What is the weather in Seattle?"}'

curl -X POST http://localhost:8088/responses -H "Content-Type: application/json" -d '{"input": "List the files in the current directory."}'
```
