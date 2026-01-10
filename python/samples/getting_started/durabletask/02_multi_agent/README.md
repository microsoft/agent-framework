# Multi-Agent

This sample demonstrates how to host multiple AI agents with different tools in a single worker-client setup using the Durable Task Scheduler.

## Key Concepts Demonstrated

- Hosting multiple agents (WeatherAgent and MathAgent) in a single worker process.
- Each agent with its own specialized tools and instructions.
- Interacting with different agents using separate conversation threads.
- Worker-client architecture for multi-agent systems.

## Environment Setup

See the [README.md](../README.md) file in the parent directory for more information on how to configure the environment, including how to install and run common sample dependencies.

## Running the Sample

With the environment setup, you can run the sample using the combined approach or separate worker and client processes:

**Option 1: Combined (Recommended for Testing)**

```bash
cd samples/getting_started/durabletask/02_multi_agent
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

The client will interact with both agents:

```
Starting Durable Task Multi-Agent Client...
Using taskhub: default
Using endpoint: http://localhost:8080

================================================================================
Testing WeatherAgent
================================================================================

Created weather conversation thread: <guid>
User: What is the weather in Seattle?

🔧 [TOOL CALLED] get_weather(location=Seattle)
✓ [TOOL RESULT] {'location': 'Seattle', 'temperature': 72, 'conditions': 'Sunny', 'humidity': 45}

WeatherAgent: The current weather in Seattle is sunny with a temperature of 72°F and 45% humidity.

================================================================================
Testing MathAgent
================================================================================

Created math conversation thread: <guid>
User: Calculate a 20% tip on a $50 bill

🔧 [TOOL CALLED] calculate_tip(bill_amount=50.0, tip_percentage=20.0)
✓ [TOOL RESULT] {'bill_amount': 50.0, 'tip_percentage': 20.0, 'tip_amount': 10.0, 'total': 60.0}

MathAgent: For a $50 bill with a 20% tip, the tip amount is $10.00 and the total is $60.00.
```

## Viewing Agent State

You can view the state of both agents in the Durable Task Scheduler dashboard:

1. Open your browser and navigate to `http://localhost:8082`
2. In the dashboard, you can view:
   - The state of both WeatherAgent and MathAgent entities (dafx-WeatherAgent, dafx-MathAgent)
   - Each agent's conversation state across multiple interactions
