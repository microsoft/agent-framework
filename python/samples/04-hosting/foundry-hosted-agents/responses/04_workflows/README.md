# Basic example of hosting an agent with the `responses` API and a workflow

This sample demonstrates how to host a workflow using the `responses` API.

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
curl -X POST http://localhost:8088/responses -H "Content-Type: application/json" -d '{"input": "Create a slogan for a new electric SUV that is affordable and fun to drive."}'
```
