# Agent-to-Agent (A2A) Samples

These samples demonstrate how to use Agent-to-Agent (A2A) agents in the Agent Framework.
Start with [A2A Agent Basic Usage](./A2AAgent_BasicUsage/) for a minimal example using default settings.

For other samples that demonstrate how to use AIAgent instances,
see the [Getting Started With Agents](../Agents/README.md) samples.

## Prerequisites

See the README.md for each sample for the prerequisites for that sample.

## Samples

|Sample|Description|
|---|---|
|[A2A Agent Basic Usage](./A2AAgent_BasicUsage/)|Send a single message to an existing A2A agent using default settings and display the response.|
|[A2A Agent as a Function Tool](./A2AAgent_AsFunctionTool/)|This sample demonstrates how to expose an A2A agent as a single function tool that another AI agent can call.|
|[A2A Agent Skills](./A2AAgent_Skills/)|This sample demonstrates how to expose each skill advertised by an A2A agent as a separate function tool.|
|[A2A Agent Polling For Task Completion](./A2AAgent_PollingForTaskCompletion/)|This sample demonstrates how to poll for long-running task completion using continuation tokens with an A2A agent.|
|[A2A Agent Stream Reconnection](./A2AAgent_StreamReconnection/)|This sample demonstrates how to reconnect to an A2A agent's streaming response using continuation tokens, allowing recovery from stream interruptions.|
|[A2A Agent Protocol Selection](./A2AAgent_ProtocolSelection/)|This sample demonstrates how to select HTTP+JSON, JSON-RPC, or gRPC when creating an AIAgent from an A2A agent card using A2AClientOptions.|

## Running the samples from the console

To run the samples, navigate to the desired sample directory, e.g.

```powershell
cd A2AAgent_BasicUsage
```

Set the required environment variables as documented in the sample readme.
If the variables are not set, you will be prompted for the values when running the samples.
Execute the following command to build the sample:

```powershell
dotnet build
```

Execute the following command to run the sample:

```powershell
dotnet run --no-build
```

Or just build and run in one step:

```powershell
dotnet run
```

## Running the samples from Visual Studio

Open the solution in Visual Studio and set the desired sample project as the startup project. Then, run the project using the built-in debugger or by pressing `F5`.

You will be prompted for any required environment variables if they are not already set.
