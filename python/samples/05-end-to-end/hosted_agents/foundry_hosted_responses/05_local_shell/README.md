# Agent Framework Agent with Local Shell

> Note: This agent can execute local shell commands. We recommend running it in an isolated environment for security reasons.

## Running the server in a Docker container

Build the Docker image:

```bash
docker build -t agent-framework-agent-with-local-shell .
```

Run the Docker container:

```bash
docker run -p 8088:8088 --env-file .env agent-framework-agent-with-local-shell
```

## Interacting with the agent

Send a POST request to the server with a JSON body containing a "message" field to interact with the agent. For example:

```bash
curl -X POST http://localhost:8088/responses -H "Content-Type: application/json" -d '{"input": "Hi"}'
```

The server will respond with a JSON object containing the response text and a response ID. You can use this response ID to continue the conversation in subsequent requests.

## Multi-turn conversation

To have a multi-turn conversation with the agent, include the previous response id in the request body. For example:

```bash
curl -X POST http://localhost:8088/responses -H "Content-Type: application/json" -d '{"input": "How are you?", "previous_response_id": "REPLACE_WITH_PREVIOUS_RESPONSE_ID"}'
```

## Deploying to Foundry

TODO

## Using the deployed agent in Agent Framework

TODO
