# Single Agent

This sample demonstrates how to create a worker-client setup that hosts a single AI agent and provides interactive conversation via the Durable Task Scheduler.

## Key Concepts Demonstrated

- Using the Microsoft Agent Framework to define a simple AI agent with a name and instructions.
- Registering durable agents with the worker and interacting with them via a client.
- Conversation management (via threads) for isolated interactions.
- Worker-client architecture for distributed agent execution.

## Environment Setup

See the [README.md](../README.md) file in the parent directory for more information on how to configure the environment, including how to install and run common sample dependencies.

## Running the Sample

With the environment setup, you can run the sample using the combined approach or separate worker and client processes:

**Option 1: Combined (Recommended for Testing)**

```bash
cd samples/getting_started/durabletask/01_single_agent
python sample.py
```

**Option 2: Separate Processes**

Start the worker in one terminal:

```bash
python worker.py
```

In a new terminal, run the client:

```bash
python client.py
```

The client will interact with the Joker agent:

```
Starting Durable Task Agent Client...
Using taskhub: default
Using endpoint: http://localhost:8080

Getting reference to Joker agent...
Created conversation thread: a1b2c3d4-e5f6-7890-abcd-ef1234567890

User: Tell me a short joke about cloud computing.

Joker: Why did the cloud break up with the server?
Because it found someone more "uplifting"!

User: Now tell me one about Python programming.

Joker: Why do Python programmers prefer dark mode?
Because light attracts bugs!
```

## Viewing Agent State

You can view the state of the agent in the Durable Task Scheduler dashboard:

1. Open your browser and navigate to `http://localhost:8082`
2. In the dashboard, you can view:
   - The state of the Joker agent entity (dafx-Joker)
   - Conversation history and current state
   - How the durable agents extension manages conversation context



