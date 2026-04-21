# Basic example of hosting an agent with the `responses` API

This agent only contains an instruction (personal). It's the most basic agent with an LLM and no tools.

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
curl -X POST http://localhost:8088/responses -H "Content-Type: application/json" -d '{"input": "Hi"}'
```

## Multi-turn conversation

To have a multi-turn conversation with the agent, include the previous response id in the request body. For example:

```bash
curl -X POST http://localhost:8088/responses -H "Content-Type: application/json" -d '{"input": "How are you?", "previous_response_id": "REPLACE_WITH_PREVIOUS_RESPONSE_ID"}'
```
