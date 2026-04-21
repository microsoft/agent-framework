# Basic example of hosting an agent with the `invocations` API

## Running the server locally

### Environment setup

Follow the instructions in the [Environment setup](../../README.md#environment-setup) section of the README in the parent directory to set up your environment and install dependencies.

Run the following command to start the server:

```bash
python main.py
```

### Interacting with the agent

Send a POST request to the server with a JSON body containing a "message" field to interact with the agent. For example:

```bash
curl -X POST http://localhost:8088/invocations -i -H "Content-Type: application/json" -d '{"message": "Hi"}'
```

The server will respond with a JSON object containing the response text. The `-i` flag in the `curl` command includes the HTTP response headers in the output, which includes the session ID that can be used for multi-turn conversations. Here is an example of the response:

```bash
HTTP/1.1 200
content-length: 34
content-type: application/json
x-agent-invocation-id: ec04d020-a0e7-441e-ae83-db75635a9f83
x-agent-session-id: 9370b9d4-cd13-4436-a57f-03b843ac0e17
x-platform-server: azure-ai-agentserver-core/2.0.0a20260410006 (python/3.12)
date: Fri, 17 Apr 2026 23:46:44 GMT
server: hypercorn-h11

{"response":"Hi! How can I help?"}
```

### Multi-turn conversation

To have a multi-turn conversation with the agent, take the session ID from the response headers of the previous request and include it in URL parameters for the next request. For example:

```bash
curl -X POST http://localhost:8088/invocations?agent_session_id=9370b9d4-cd13-4436-a57f-03b843ac0e17 -i -H "Content-Type: application/json" -d '{"message": "How are you?"}'
```
