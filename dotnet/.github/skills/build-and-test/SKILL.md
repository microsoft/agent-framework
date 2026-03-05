---
name: build-and-test
description: How to build and test .NET projects in the Agent Framework repository. Use this when verifying or testing changes.
---

- Only **UnitTest** projects need to be run locally; IntegrationTests require external dependencies.
- See `../project-structure/SKILL.md` for project structure details.

## Build, Test, and Lint Commands

```bash
# From dotnet/ directory
dotnet restore --tl:off   # Restore dependencies for all projects
dotnet build --tl:off     # Build all projects
dotnet test               # Run all tests
dotnet format             # Auto-fix formatting for all projects

# Build/test/format a specific project (preferred for isolated/internal changes)
dotnet build src/Microsoft.Agents.AI.<Package> --tl:off
dotnet test tests/Microsoft.Agents.AI.<Package>.UnitTests
dotnet format src/Microsoft.Agents.AI.<Package>

# Run a single test
dotnet test --filter "FullyQualifiedName~Namespace.TestClassName.TestMethodName"

# Run unit tests only
dotnet test --filter FullyQualifiedName\~UnitTests
```

Use `--tl:off` when building to avoid flickering when running commands in the agent.

## Speeding Up Builds and Testing

The full solution is large. Use these shortcuts:

| Change type | What to do |
|-------------|------------|
| Isolated/Internal logic | Build only the affected project and its `*.UnitTests` project. Fix issues, then build the full solution and run all unit tests. |
| Public API surface | Build the full solution and run all unit tests immediately. |

Example: Building a single code project for all target frameworks

```bash
# From dotnet/ directory
dotnet build ./src/Microsoft.Agents.AI.Abstractions
```

Example: Building a single code project for just .NET 10.

```bash
# From dotnet/ directory
dotnet build ./src/Microsoft.Agents.AI.Abstractions -f net10.0
```

Example: Running tests for a single project using .NET 10.

```bash
# From dotnet/ directory
dotnet test ./tests/Microsoft.Agents.AI.Abstractions.UnitTests -f net10.0
```

Example: Running a single test in a specific project using .NET 10.
Provide the full namespace, class name, and method name for the test you want to run:

```bash
# From dotnet/ directory
dotnet test ./tests/Microsoft.Agents.AI.Abstractions.UnitTests -f net10.0 --filter "FullyQualifiedName~Microsoft.Agents.AI.Abstractions.UnitTests.AgentRunOptionsTests.CloningConstructorCopiesProperties"
```

### Multi-target framework tip

Most projects target multiple .NET frameworks. If the affected code does **not** use `#if` directives for framework-specific logic, pass `-f net10.0` to speed up building and testing.

### Package Restore tip

`dotnet build` will try and restore packages for all projects on each build, which can be slow.
Unless packages have been changed, or it's the first time building the solution, add `--no-restore` to the build command to skip this step and speed up builds.

Just remember to run `dotnet restore` after pulling changes, making changes to project references, or when building for the first time.

### Testing on Linux tip

Unit tests target both .NET Framework as well as .NET Core. When running on Linux, only the .NET Core tests can be run, as .NET Framework is not supported on Linux.

To run only the .NET Core tests, use the `-f net10.0` option with `dotnet test`.
