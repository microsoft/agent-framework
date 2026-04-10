# Basic example of hosting an agent with the `responses` API and a workflow

Run the following command to start the server:

```bash
python main.py
```

Send a POST request to the server with a JSON body containing a "message" field to interact with the agent. For example:

```bash
curl -X POST http://localhost:8088/responses -H "Content-Type: application/json" -d '{"input": "Create a slogan for a new electric SUV that is affordable and fun to drive."}'
```
