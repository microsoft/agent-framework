# Agent-to-Agent (A2A) Samples

These samples demonstrate how to work with Agent-to-Agent (A2A) specific features in the Agent Framework.

For other samples that demonstrate how to use AIAgent instances,
see the [Getting Started With Agents](../Agents/README.md) samples.

## Prerequisites

See the README.md for each sample for the prerequisites for that sample.

## Samples

|Sample|Description|
|---|---|
|[A2A Agent As Function Tools](./A2AAgent_AsFunctionTools/)|This sample demonstrates how to represent an A2A agent as a set of function tools, where each function tool corresponds to a skill of the A2A agent, and register these function tools with another AI agent so it can leverage the A2A agent's skills.|

## Running the samples from the console

To run the samples, navigate to the desired sample directory, e.g.

```powershell
cd A2AAgent_AsFunctionTools
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
