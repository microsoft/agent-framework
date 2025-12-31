# Multi-Agent Orchestration with Concurrency Sample (Python) - Durable Task

This sample demonstrates how to use the **Durable Task package** with **OrchestrationAgentExecutor** to orchestrate multiple AI agents running concurrently and aggregate their responses.

## Description of the Sample

This sample shows how to run two domain-specific agents (a Physicist and a Chemist) concurrently using Durable Task orchestration. The agents respond to the same prompt from their respective domain perspectives, demonstrating:

- How to register multiple agents as durable entities
- How to create an orchestration function that executes agents in parallel
- How to use `OrchestrationAgentExecutor` for concurrent agent execution
- How to aggregate results from multiple agents
- The benefits of concurrent execution for improved performance

## Key Concepts Demonstrated

- **Multi-Agent Architecture**: Running multiple specialized agents in parallel
- **Orchestration Functions**: Using Durable Task orchestrations to coordinate agent execution
- **OrchestrationAgentExecutor**: Execution strategy for orchestrations that returns `DurableAgentTask` objects
- **Concurrent Execution**: Using `task.when_all()` to run agents in parallel
- **Result Aggregation**: Collecting and combining responses from multiple agents
- **Thread Management**: Creating separate conversation threads for each agent
- **BYOP (Bring Your Own Platform)**: Not tied to Azure Functions - run anywhere with Durable Task Scheduler

## Architecture Overview

This sample uses a **worker-orchestration-client architecture**:

1. **Worker Process** (`worker.py`): Registers two agents (Physicist and Chemist) as durable entities and an orchestration function
2. **Orchestration Function**: Coordinates concurrent execution of both agents and aggregates results
3. **Client Process** (`client.py`): Starts the orchestration and retrieves aggregated results
4. **Durable Task Scheduler**: Coordinates communication and orchestration execution (runs separately)

### Execution Flow

```
Client → Start Orchestration → Orchestration Context
                                      ↓
                        ┌─────────────┴─────────────┐
                        ↓                           ↓
                  Physicist Agent              Chemist Agent
                  (Concurrent)                 (Concurrent)
                        ↓                           ↓
                        └─────────────┬─────────────┘
                                      ↓
                          Aggregate Results → Client
```

## What Makes This Different?

This sample differs from the single agent sample in several key ways:

1. **Multiple Agents**: Two specialized agents with different domain expertise
2. **Concurrent Execution**: Both agents run simultaneously using `task.when_all()`
3. **Orchestration Function**: Uses a Durable Task orchestrator to coordinate execution
4. **OrchestrationAgentExecutor**: Different execution strategy that returns tasks instead of blocking
5. **Result Aggregation**: Combines responses from multiple agents into a single result

## Prerequisites

### 1. Python 3.9+

Ensure you have Python 3.9 or later installed.

### 2. Azure OpenAI Setup

Configure your Azure OpenAI credentials:
- Set `AZURE_OPENAI_ENDPOINT` environment variable
- Set `AZURE_OPENAI_CHAT_DEPLOYMENT_NAME` environment variable
- Either:
  - Set `AZURE_OPENAI_API_KEY` environment variable, OR
  - Run `az login` to authenticate with Azure CLI

### 3. Install Dependencies

Install the required packages:

```bash
pip install -r requirements.txt
```

Or if using uv:

```bash
uv pip install -r requirements.txt
```

### 4. Durable Task Scheduler

The sample requires a Durable Task Scheduler running. For local development, use the emulator:

#### Using the Emulator (Recommended for Local Development)

1. Pull the Docker Image for the Emulator:
   ```bash
   docker pull mcr.microsoft.com/dts/dts-emulator:latest
   ```

2. Run the Emulator:
   ```bash
   docker run --name dtsemulator -d -p 8080:8080 -p 8082:8082 mcr.microsoft.com/dts/dts-emulator:latest
   ```
   Wait a few seconds for the container to be ready.

## Running the Sample

### Option 1: Combined Worker + Client (Recommended for Quick Start)

The easiest way to run the sample is using `sample.py`, which runs both worker and client in a single process:

```bash
python sample.py
```

This will:
1. Start the worker and register both agents and the orchestration
2. Start the orchestration with a sample prompt
3. Wait for completion and display aggregated results
4. Shut down the worker

### Option 2: Separate Worker and Client

For a more realistic distributed setup, run the worker and client separately:

1. **Start the worker** in one terminal:
   ```bash
   python worker.py
   ```
   
   You should see output indicating both agents are registered:
   ```
   INFO:__main__:Starting Durable Task Multi-Agent Worker with Orchestration...
   INFO:__main__:Using taskhub: default
   INFO:__main__:Using endpoint: http://localhost:8080
   INFO:__main__:Creating and registering agents...
   INFO:__main__:✓ Registered agent: PhysicistAgent
   INFO:__main__:  Entity name: dafx-PhysicistAgent
   INFO:__main__:✓ Registered agent: ChemistAgent
   INFO:__main__:  Entity name: dafx-ChemistAgent
   INFO:__main__:✓ Registered orchestration: multi_agent_concurrent_orchestration
   INFO:__main__:Worker is ready and listening for requests...
   ```

2. **In a new terminal**, run the client:
   ```bash
   python client.py
   ```
   
   The client will start the orchestration and wait for results.

## Understanding the Output

### Worker Output

The worker shows:
- Connection information (taskhub and endpoint)
- Registration of both agents (Physicist and Chemist) as durable entities
- Registration of the orchestration function
- Status messages during orchestration execution

Example:
```
INFO:__main__:Starting Durable Task Multi-Agent Worker with Orchestration...
INFO:__main__:Using taskhub: default
INFO:__main__:Using endpoint: http://localhost:8080
INFO:__main__:Creating and registering agents...
INFO:__main__:✓ Registered agent: PhysicistAgent
INFO:__main__:  Entity name: dafx-PhysicistAgent
INFO:__main__:✓ Registered agent: ChemistAgent
INFO:__main__:  Entity name: dafx-ChemistAgent
INFO:__main__:✓ Registered orchestration: multi_agent_concurrent_orchestration
INFO:__main__:Worker is ready and listening for requests...
```

### Client Output

The client shows:
- The prompt sent to both agents
- Orchestration instance ID
- Status updates during execution
- Aggregated results from both agents

Example:
```
INFO:__main__:Starting Durable Task Multi-Agent Orchestration Client...
INFO:__main__:Using taskhub: default
INFO:__main__:Using endpoint: http://localhost:8080

INFO:__main__:Prompt: What is temperature?

INFO:__main__:Starting multi-agent concurrent orchestration...
INFO:__main__:Orchestration started with instance ID: abc123...
INFO:__main__:Waiting for orchestration to complete...

INFO:__main__:Orchestration status: COMPLETED
================================================================================
Orchestration completed successfully!
================================================================================

Prompt: What is temperature?

Results:

Physicist's response:
  Temperature measures the average kinetic energy of particles in a system...

Chemist's response:
  Temperature reflects how molecular motion influences reaction rates...

================================================================================
```

### Orchestration Output

During execution, the orchestration logs show:
- When concurrent execution starts
- Thread creation for each agent
- Task creation and execution
- Completion and result aggregation

Example:
```
INFO:__main__:[Orchestration] Starting concurrent execution for prompt: What is temperature?
INFO:__main__:[Orchestration] Created threads - Physicist: session-123, Chemist: session-456
INFO:__main__:[Orchestration] Created agent tasks, executing concurrently...
INFO:__main__:[Orchestration] Both agents completed
INFO:__main__:[Orchestration] Aggregated results ready
```

## How It Works

### 1. Agent Registration

Both agents are registered as durable entities in the worker:

```python
agent_worker.add_agent(physicist_agent)
agent_worker.add_agent(chemist_agent)
```

### 2. Orchestration Registration

The orchestration function is registered with the worker:

```python
worker.add_orchestrator(multi_agent_concurrent_orchestration)
```

### 3. Orchestration Execution

The orchestration uses `OrchestrationAgentExecutor` (implicitly through `context.get_agent()`):

```python
@task.orchestrator
def multi_agent_concurrent_orchestration(context: OrchestrationContext):
    # Get agents (uses OrchestrationAgentExecutor internally)
    physicist = context.get_agent(PHYSICIST_AGENT_NAME)
    chemist = context.get_agent(CHEMIST_AGENT_NAME)
    
    # Create tasks (returns DurableAgentTask instances)
    physicist_task = physicist.run(messages=prompt, thread=physicist_thread)
    chemist_task = chemist.run(messages=prompt, thread=chemist_thread)
    
    # Execute concurrently
    task_results = yield task.when_all([physicist_task, chemist_task])
    
    # Aggregate results
    return {
        "physicist": task_results[0].text,
        "chemist": task_results[1].text,
    }
```

### 4. Key Differences from Single Agent

- **OrchestrationAgentExecutor**: Returns `DurableAgentTask` instead of `AgentRunResponse`
- **Concurrent Execution**: Uses `task.when_all()` for parallel execution
- **Yield Syntax**: Orchestrations use `yield` to await async operations
- **Result Aggregation**: Combines multiple agent responses into one result

## Customization

You can modify the sample to:

1. **Change the prompt**: Edit the `prompt` variable in `sample.py` or `client.py`
2. **Add more agents**: Create additional agents and add them to the orchestration
3. **Change agent instructions**: Modify the `instructions` parameter when creating agents
4. **Adjust concurrency**: Use different task combination patterns (e.g., sequential, selective)
5. **Add error handling**: Implement retry logic or fallback agents

## Troubleshooting

### Orchestration times out
- Increase `max_wait_time` in the client code
- Check that both agents are properly registered in the worker
- Verify Azure OpenAI endpoint and credentials

### Agents return errors
- Verify Azure OpenAI deployment name is correct
- Check Azure OpenAI quota and rate limits
- Review worker logs for detailed error messages

### Connection errors
- Ensure the Durable Task Scheduler is running
- Verify `ENDPOINT` and `TASKHUB` environment variables
- Check network connectivity and firewall rules

## Related Samples

- **01_single_agent**: Basic single agent setup
- **Azure Functions 05_multi_agent_orchestration_concurrency**: Similar pattern using Azure Functions

## Learn More

- [Agent Framework Documentation](https://github.com/microsoft/agent-framework)
- [Durable Task Framework](https://github.com/microsoft/durabletask)
- [Azure OpenAI Service](https://azure.microsoft.com/en-us/products/cognitive-services/openai-service)
