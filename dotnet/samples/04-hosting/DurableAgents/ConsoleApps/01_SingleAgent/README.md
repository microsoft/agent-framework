# Single Agent Sample

This sample demonstrates how to use the durable agents extension to create a simple console app that hosts a single AI agent and provides interactive conversation via stdin/stdout.

## Key Concepts Demonstrated

- Using the Microsoft Agent Framework to define a simple AI agent with a name and instructions.
- Registering durable agents with the console app and running them interactively.
- Conversation management (via threads) for isolated interactions.

## Environment Setup

See the [README.md](../README.md) file in the parent directory for more information on how to configure the environment, including how to install and run common sample dependencies.

## Running the Sample

With the environment setup, you can run the sample:

```bash
cd dotnet/samples/04-hosting/DurableAgents/ConsoleApps/01_SingleAgent
dotnet run --framework net10.0
```

The app will prompt you for input. You can interact with the Joker agent:

```text
=== Single Agent Console Sample ===
Enter a message for the Joker agent (or 'exit' to quit):

You: Tell me a joke about a pirate.
Joker: Why don't pirates ever learn the alphabet? Because they always get stuck at "C"!

You: Now explain the joke.
Joker: The joke plays on the word "sea" (C), which pirates are famously associated with...

You: exit
```

## Scriptable Usage

You can also pipe input to the app for scriptable usage:

```bash
echo "Tell me a joke about a pirate." | dotnet run
```

The app will read from stdin, process the input, and write the response to stdout.

## Viewing Agent State

You can view the state of the agent in the Durable Task Scheduler dashboard:

1. Open your browser and navigate to `http://localhost:8082`
2. In the dashboard, you can view the state of the Joker agent, including its conversation history and current state

The agent maintains conversation state across multiple interactions, and you can inspect this state in the dashboard to understand how the durable agents extension manages conversation context.
