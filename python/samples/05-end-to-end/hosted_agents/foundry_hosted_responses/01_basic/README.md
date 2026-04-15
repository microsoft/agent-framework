# Basic example of hosting an agent with the `responses` API

This agent only contains an instruction (personal). It's the most basic agent with an LLM and no tools.

## Interacting with the agent

Send a POST request to the server with a JSON body containing a "message" field to interact with the agent. For example:

```bash
curl -X POST http://localhost:8088/responses -H "Content-Type: application/json" -d '{"input": "Hi"}'
```

### Invoke with `azd`

```bash
azd ai agent invoke --local "Hi"
```

## Multi-turn conversation

To have a multi-turn conversation with the agent, include the previous response id in the request body. For example:

```bash
curl -X POST http://localhost:8088/responses -H "Content-Type: application/json" -d '{"input": "How are you?", "previous_response_id": "REPLACE_WITH_PREVIOUS_RESPONSE_ID"}'
```

Invoke with `azd`:

```bash
azd ai agent invoke --local "How are you?" --conversation-id "REPLACE_WITH_CONVERSATION_ID"
```
