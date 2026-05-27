# LocalCodeAct Sample

This sample demonstrates using the `Microsoft.Agents.AI.LocalCodeAct` package for local Python code execution.

## ⚠️ Security Warning

This package executes LLM-generated Python code in a subprocess. It is **NOT** a security sandbox.

**Use only in environments with proper external isolation:**
- Azure Container Instances
- Virtual Machines with network isolation
- Foundry hosted agents
- Docker containers with restricted capabilities

**Do NOT use on:**
- Developer workstations
- Production hosts without sandboxing
- Any environment with access to sensitive data or credentials

## Prerequisites

- Python 3.10 or later installed
- .NET 8.0 or later
- External container/VM sandboxing for safe execution

## Running the Sample

```bash
dotnet run
```

This will demonstrate:
1. Creating a `LocalCodeActProvider`
2. Creating a `LocalExecuteCodeFunction` directly
3. Execution modes (Subprocess only in .NET)
4. File mount configuration

## Configuration

The sample uses `/usr/bin/python3` as the Python executable path. Adjust this in `Program.cs` if your Python is installed elsewhere:

```csharp
pythonExecutablePath: "/path/to/your/python3"
```

## Next Steps

For actual code execution with an AI agent, see:
- `Microsoft.Agents.AI` documentation for agent setup
- `Microsoft.Extensions.AI` for model client configuration
- Foundry hosting samples for containerized deployment

## License

MIT
