# Multi-Agent Concurrent Orchestration Sample

This sample demonstrates how to use the Durable Agent Framework (DAFx) to create an Azure Functions app that orchestrates concurrent execution of multiple AI agents, each with specialized expertise, to provide comprehensive answers to complex questions.

## Key Concepts Demonstrated

- Multi-agent orchestration with specialized AI agents (physics and chemistry)
- Concurrent execution using the fan-out/fan-in pattern for improved performance and distributed processing
- Response aggregation from multiple agents into a unified result
- Durable orchestration with automatic checkpointing and resumption from failures

## Environment Setup

See the [README.md](../README.md) file in the parent directory for more information on how to configure the environment, including how to install and run common sample dependencies.

## Running the Sample

With the environment setup and function app running, you can test the sample by sending an HTTP request with a custom prompt to the orchestration.

You can use the `demo.http` file to send a message to the agents, or a command line tool like `curl` as shown below:

Bash (Linux/macOS/WSL):

```bash
curl -X POST http://localhost:7071/api/multiagent/run \
    -H "Content-Type: text/plain" \
    -d "What is temperature?"
```

PowerShell:

```powershell
Invoke-RestMethod -Method Post `
    -Uri http://localhost:7071/api/multiagent/run `
    -ContentType text/plain `
    -Body "What is temperature?"
```

The response will be a JSON object that looks something like the following, which indicates that the orchestration has started.

```json
{
  "message": "Multi-agent concurrent orchestration started.",
  "prompt": "What is temperature?",
  "instanceId": "e7e29999b6b8424682b3539292afc9ed",
  "statusQueryGetUri": "http://localhost:7071/api/multiagent/status/e7e29999b6b8424682b3539292afc9ed"
}
```

The orchestration will run both the PhysicistAgent and ChemistAgent concurrently, asking them the same question. Their responses will be combined to provide a comprehensive answer covering both physical and chemical aspects.

Once the orchestration has completed, you can get the status of the orchestration by sending a GET request to the `statusQueryGetUri` URL. The response will be a JSON object that looks something like the following:

```json
{
  "failureDetails": null,
  "input": "What is temperature?",
  "instanceId": "e7e29999b6b8424682b3539292afc9ed",
  "output": {
    "physicist": "Temperature is a measure of the average kinetic energy of particles in a system. From a physics perspective, it represents the thermal energy and determines the direction of heat flow between objects.",
    "chemist": "From a chemistry perspective, temperature is crucial for chemical reactions as it affects reaction rates through the Arrhenius equation. It influences the equilibrium position of reversible reactions and determines the physical state of substances."
  },
  "runtimeStatus": "Completed"
}
```
