# Single Agent Sample (Python) - Durable Task

This sample demonstrates how to use the **Durable Task package** for Agent Framework to create a simple agent hosting setup with persistent conversation state and distributed execution capabilities.

## Description of the Sample

This sample shows how to host a single AI agent (the "Joker" agent) using the Durable Task Scheduler. The agent responds to user messages by telling jokes, demonstrating:

- How to register agents as durable entities that can persist state
- How to interact with registered agents from external clients
- How to maintain conversation context across multiple interactions
- The worker-client architecture pattern for distributed agent execution

## Key Concepts Demonstrated

- **Worker Registration**: Using `DurableAIAgentWorker` to register agents as durable entities that can process requests
- **Client Interaction**: Using `DurableAIAgentClient` to send messages to registered agents from external contexts
- **Thread Management**: Creating and maintaining conversation threads for stateful interactions
- **Distributed Architecture**: Separating worker (agent host) and client (caller) into independent processes
- **BYOP (Bring Your Own Platform)**: Not tied to Azure Functions - run anywhere with Durable Task Scheduler

## Architecture Overview

This sample uses a **client-worker architecture**:

1. **Worker Process** (`worker.py`): Registers agents as durable entities and continuously listens for requests
2. **Client Process** (`client.py`): Connects to the same scheduler and sends requests to agents by name
3. **Durable Task Scheduler**: Coordinates communication between clients and workers (runs separately)

This architecture enables:
- **Scalability**: Multiple workers can process requests in parallel
- **Reliability**: State is persisted, so conversations survive process restarts
- **Flexibility**: Clients and workers can be on different machines
- **BYOP (Bring Your Own Platform)**: Not tied to Azure Functions - run anywhere

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

The sample requires a Durable Task Scheduler running. There are two options:

#### Using the Emulator (Recommended for Local Development)

The emulator simulates a scheduler and taskhub in a Docker container, making it ideal for development and learning.

1. Pull the Docker Image for the Emulator:
   ```bash
   docker pull mcr.microsoft.com/dts/dts-emulator:latest
   ```

2. Run the Emulator:
   ```bash
   docker run --name dtsemulator -d -p 8080:8080 -p 8082:8082 mcr.microsoft.com/dts/dts-emulator:latest
   ```
   Wait a few seconds for the container to be ready.

> *How to Run the Sample

Once you have set up either the emulator or deployed scheduler, follow these steps to run the sample:

1. **Activate your Python virtual environment** (if you're using one):
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows, use: venv\Scripts\activate
   ```

2. **If you're using a deployed scheduler**, set environment variables:
   ```bash
   export ENDPOINT=$(az durabletask scheduler show \
       --resource-group my-resource-group \
       --name my-scheduler \
       --query "properties.endpoint" \
       --output tsv)

   export TASKHUB="my-taskhub"
   ```

3. **Install the required packages**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Start the worker** in a terminal:
   ```bash
   python worker.py
   ```
   You should see output indicating the worker has started and registered the agent:
   ```
   INFO:__main__:Starting Durable Task Agent Worker...
   INFO:__main__:Using taskhub: default
   INFO:__main__:Using endpoint: http://localhost:8080
   INFO:__main__:Creating and registering Joker agent...
   INFO:__main__:✓ Registered agent: Joker
   INFO:__main__:  Entity name: dafx-Joker
   INFO:__main__:
   INFO:__main__:Worker is ready and listening for requests...
   INFO:__main__:Press Ctrl+C to stop.
   ```

5. **In a new terminal** (with the virtual environment activated if applicable), **run the client**:
   > **Note:** Remember to set the environment variables again if you're using a deployed scheduler.

   ```bash
   python client.py
   ```
   az role assignment create \
       --assignee $loggedInUser \
       --role "Durable Task Data Contributor" \
       --scope "/subscriptions/$subscriptionId/resourceGroups/my-resource-group/providers/Microsoft.DurableTask/schedulers/my-scheduler/taskHubs/my-taskhub"
   ```

5. Set environment variables:
   ```bash
   export ENDPOINT=$(az durabletask scheduler show \
       --resource-group my-resource-group \
       --name my-scheduler \
       --query "properties.endpoint" \
       --output tsv)
   
   export TASKHUB="my-taskhub"
   ```

## Running the Sample

### Step 1: Start the Worker

In one terminal, start the worker to host the agent:

```bash
python sample.py worker
```

You should see output similar to:
```
Starting Durable Task worker...
Connecting to scheduler at: localhost:4001
✓ Registered agent: Joker
  Entity name: dafx-Joker

Worker is ready and listening for requests...
Press Ctrl+C to stop.
```

The worker will continue running and processing requests until you stop it (Ctrl+C).

### Step 2: Run the Client

In a **separate terminal**, run the client to interact with the agent:
Understanding the Output

When you run the sample, you'll see output from both the worker and client processes:

### Worker Output

The worker shows:
- Connection information (taskhub and endpoint)
- Registration of the Joker agent as a durable entity
- Entity name (`dafx-Joker`)
- Status message indicating it's ready to process requests

Example:
```
INFO:__main__:Starting Durable Task Agent Worker...
INFO:__main__:Using taskhub: default
INFO:__main__:Using endpoint: http://localhost:8080
INFO:__main__:Creating and registering Joker agent...
INFO:__main__:✓ Registered agent: Joker
INFO:__main__:  Entity name: dafx-Joker
INFO:__main__:
INFO:__main__:Worker is ready and listening for requests...
INFO:__main__:Press Ctrl+C to stop.
```

### Client Output

The client shows:
- Connection information
- Thread creation
- User messages sent to the agent
- Agent responses (jokes)
- Token usage statistics
- Conversation completion status

Example:
```
INFO:__main__:Starting Durable Task Agent Client...
INFO:__main__:Using taskhub: default
INFO:__main__:Using endpoint: http://localhost:8080
INFO:__main__:
INFO:__main__:Getting reference to Joker agent...
INFO:__main__:Created conversation thread: a1b2c3d4-e5f6-7890-abcd-ef1234567890
INFO:__main__:
INFO:__main__:User: Tell me a short joke about cloud computing.
INFO:__main__:
INFO:__main__:Joker: Why did the cloud break up with the server?

Because it found someone more "uplifting"!
INFO:__main__:Usage: UsageStats(input_tokens=42, output_tokens=18, total_tokens=60)
INFO:__main__:
INFO:__main__:User: Now tell me one about Python programming.
INFO:__main__:
INFO:__main__:Joker: Why do Python programmers prefer dark mode?
Understanding the Code

### Worker (`worker.py`)

The worker process is responsible for hosting agents:

```python
from durabletask.azuremanaged.worker import DurableTaskSchedulerWorker
from agent_framework_durabletask import DurableAIAgentWorker

# Create a worker using Azure Managed Durable Task
worker = DurableTaskSchedulerWorker(
    host_address=endpoint,
    secure_channel=endpoint != "http://localhost:8080",
    taskhub=taskhub_name,
    token_credential=credential
)

# Wrap it with the agent worker
agent_worker = DurableAIAgentWorker(worker)

# Create and register agents
joker_agent = create_joker_agent()
agent_worker.add_agent(joker_agent)

# Start processing (blocks until stopped)
worker.start()
```

**What happens:**
- The agent is registered as a durable entity with name `dafx-{agent_name}`
- The worker continuously polls for requests directed to this entity
- Each request is routed to the agent's execution logic
- Conversation state is persisted automatically in the entity

### Client (`client.py`)

The client process interacts with registered agents:

```python
from durabletask.azuremanaged.client import DurableTaskSchedulerClient
from agent_framework_durabletask import DurableAIAgentClient

# Create a client using Azure Managed Durable Task
client = DurableTaskSchedulerClient(
    host_address=endpoint,
    secure_channel=endpoint != "http://localhost:8080",
    taskhub=taskhub_name,
    token_credential=credential
)

# Wrap it with the agent client
agent_client = DurableAIAgentClient(client)

# Get agent reference (no validation until execution)
joker = agent_client.get_agent("Joker")

# Create thread and run
thread = joker.get_new_thread()
response = await joker.run(message, thread=thread)
```

**What happens:**
- The client constructs a request with the message and thread information
- The request is sent to the entity `dafx-Joker` via the scheduler
- The client waits for the entity to process theEmulator is running:
```bash
docker ps | grep dts-emulator
```

If not running, start it:
```bash
docker run --name dtsemulator -d -p 8080:8080 -p 8082:8082 mcr.microsoft.com/dts/dts-emulator:latest
```

### Agent Not Found

**Error**: Agent execution fails with "entity not found" or similar

**Solution**: 
1. Ensure the worker is running and has registered the agent
2. Check that the agent name matches exactly (case-sensitive)
3. Verify both client and worker are connecting to the same endpoint and taskhub
4. Check worker logs for successful agent registration

### Azure OpenAI Authentication

**Error**: Authentication errors when creating the agent

**Solution**:
1. Ensure `AZURE_OPENAI_ENDPOINT` and `AZURE_OPENAI_CHAT_DEPLOYMENT_NAME` are set
2. Either:
   - Set `AZURE_OPENAI_API_KEY` environment variable, OR
   - Run `az login` to authenticate with Azure CLI

### Environment Variables Not Set

If using a deployed scheduler, ensure you set the environment variables in **both** terminals (worker and client):
```bash
export ENDPOINT="<your-endpoint>"
export TASKHUB="<your-taskhub>"
```

## Reviewing the Agent in the Durable Task Scheduler Dashboard

### Using the Emulator

1. Navigate to http://localhost:8082 in your web browser
2. Click on the "default" task hub
3. You'll see the agent entity (`dafx-Joker`) in the list
4. Click on the entity to view:
   - Entity state and conversation history
   - Request and response details
   - Execution timeline

### Using a Deployed Scheduler

1. Navigate to the Scheduler resource in the Azure portal
2. Go to the Task Hub subresource that you're using
3. Click on the dashboard URL in the top right corner
4. Search for your entity (`dafx-Joker`)
5. Review the entity state and execution history

## Comparison with Azure Functions Sample

| Aspect | Azure Functions | Durable Task (BYOP) |
|--------|----------------|---------------------|
| **Platform** | Azure Functions (PaaS) | Any platform with gRPC |
| **Hosting** | AgentFunctionApp | DurableTaskSchedulerWorker + DurableAIAgentWorker |
| **Client API** | HTTP endpoints | DurableAIAgentClient |
| **Infrastructure** | Managed by Azure | Self-hosted scheduler or Azure DTS |
| **Scalability** | Auto-scaling | Manual scaling or K8s |
| **Use Case** | Production cloud workloads | Local dev, on-prem, custom platforms |

## Identity-based Authentication

Learn how to set up [identity-based authentication](https://learn.microsoft.com/azure/azure-functions/durable/durable-task-scheduler/durable-task-scheduler-identity?tabs=df&pivots=az-cli) when you deploy to Azure.

## Next Steps

- **Multiple Agents**: Modify the sample to register multiple agents with different capabilities
- **Structured Responses**: Use `response_format` parameter to get JSON structured output
- **Agent Orchestration**: Create orchestrations that coordinate multiple agents (see advanced samples)
- **Production Deployment**: Deploy workers to Kubernetes, VMs, or container services
- **Monitoring**: Add telemetry and logging for production workloads

## Related Samples

- [Azure Functions Single Agent Sample](../../../azure_functions/01_single_agent/) - Azure Functions hosting
- [Durable Task Scheduler Samples](https://github.com/Azure-Samples/Durable-Task-Scheduler) - More patterns and examples

## Additional Resources

- [Durable Task Framework](https://github.com/microsoft/durabletask-python)
- [Agent Framework Documentation](https://github.com/microsoft/agent-framework)
- [Durable Task Scheduler](https://github.com/Azure-Samples/Durable-Task-Scheduler)
- [Azure Durable Task Scheduler Documentation](https://learn.microsoft.com/azure/azure-functions/durable/durable-task-scheduler/)

