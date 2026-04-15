# Basic example of hosting an agent with the `invocations` API

Run the following command to start the server:

```bash
python main.py
```

Send a POST request to the server with a JSON body containing a "message" field to interact with the agent. For example:

```bash
curl -X POST http://localhost:8088/invocations -H "Content-Type: application/json" -d '{"message": "Hi!"}'
```
