---
name: build-and-test
description: How to build and test .NET projects in the Agent Framework repository. Use this when verifying or testing changes.
---

# Build and Test

- Only **UnitTest** projects need to be run locally; IntegrationTests require external dependencies.
- See `../project-structure/SKILL.md` for project structure details.

## Speeding Up Builds

The full solution is large. Use these shortcuts:

| Change type | What to do |
|-------------|------------|
| Internal logic | Build only the affected project and its `*.UnitTests` project. Fix issues, then build the full solution and run all unit tests. |
| Public API surface | Build the full solution and run all unit tests immediately. |

Example: Building a single code project for all target frameworks

```bash
cd /workspaces/agent-framework/dotnet
dotnet build ./src/Microsoft.Agents.AI.Abstractions/Microsoft.Agents.AI.Abstractions.csproj
```

Example: Building a single code project for just .NET 10.

```bash
cd /workspaces/agent-framework/dotnet
dotnet build ./src/Microsoft.Agents.AI.Abstractions/Microsoft.Agents.AI.Abstractions.csproj -f net10.0
```

Example: Running tests for a single project using .net 10.

```bash
cd /workspaces/agent-framework/dotnet
dotnet test ./tests/Microsoft.Agents.AI.Abstractions.UnitTests/Microsoft.Agents.AI.Abstractions.UnitTests.csproj -f net10.0
```

### Multi-target framework tip

Most projects target multiple .NET frameworks. If the affected code does **not** use `#if` directives for framework-specific logic, pass `--framework net10.0` to speed up building and testing.
