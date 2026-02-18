# AGENTS.md

Instructions for AI coding agents working in the .NET codebase.

## Build, Test, and Lint Commands

```bash
# From dotnet/ directory
dotnet build --tl:off              # Build all projects
dotnet test --tl:off               # Run all tests
dotnet format             # Auto-fix formatting

# Build/test a specific project (preferred for isolated changes)
dotnet build src/Microsoft.Agents.AI.<Package> --tl:off
dotnet test tests/Microsoft.Agents.AI.<Package>.UnitTests --tl:off

# Run a single test
dotnet test --filter "FullyQualifiedName~TestClassName.TestMethodName" --tl:off
```

**Note**: Always use `--tl:off` when running `dotnet build`, `dotnet test`, or `dotnet restore` to disable the terminal logger, which can cause issues with non-interactive environments. This flag is not needed for `dotnet format`.

**Note**: Changes to core packages (`Microsoft.Agents.AI`, `Microsoft.Agents.AI.Abstractions`) affect dependent projects - run checks across the entire solution. For isolated changes, build/test only the affected project to save time.

## Project Structure

```
dotnet/
├── src/
│   ├── Microsoft.Agents.AI/              # Core AI agent abstractions
│   ├── Microsoft.Agents.AI.Abstractions/ # Shared abstractions and interfaces
│   ├── Microsoft.Agents.AI.OpenAI/       # OpenAI provider
│   ├── Microsoft.Agents.AI.AzureAI/      # Azure AI provider
│   ├── Microsoft.Agents.AI.Anthropic/    # Anthropic provider
│   ├── Microsoft.Agents.AI.Workflows/    # Workflow orchestration
│   └── ...                               # Other packages
├── samples/                              # Sample applications
└── tests/                                # Unit and integration tests
```

### External Dependencies

The framework integrates with `Microsoft.Extensions.AI` and `Microsoft.Extensions.AI.Abstractions` (external NuGet packages) using types like `IChatClient`, `FunctionInvokingChatClient`, `AITool`, and `AIContent`.

## Key Conventions

- **Encoding**: All new files must be saved with UTF-8 encoding with BOM (Byte Order Mark). This is required for `dotnet format` to work correctly.
- **Copyright header**: `// Copyright (c) Microsoft. All rights reserved.` at top of all `.cs` files
- **XML docs**: Required for all public methods and classes
- **Async**: Use `Async` suffix for methods returning `Task`/`ValueTask`
- **Private classes**: Should be `sealed` unless subclassed
- **Config**: Read from environment variables with `UPPER_SNAKE_CASE` naming
- **Tests**: Add Arrange/Act/Assert comments; use Moq for mocking

## Sample Structure

1. Copyright header: `// Copyright (c) Microsoft. All rights reserved.`
2. Description comment explaining what the sample demonstrates
3. Using statements
4. Main code logic
5. Helper methods at bottom

Configuration via environment variables (never hardcode secrets). Keep samples simple and focused.

When adding a new sample:
- Create a standalone project in `samples/` with matching directory and project names
- Include a README.md explaining what the sample does and how to run it
- Add the project to the solution file
- Reference the sample in the parent directory's README.md
