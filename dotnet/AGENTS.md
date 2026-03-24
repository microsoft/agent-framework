# AGENTS.md

Instructions for AI coding agents working in the .NET codebase.

## Build, Test, and Lint Commands

See `./.github/skills/build-and-test/SKILL.md` for detailed instructions on building, testing, and linting projects.

## Project Structure

See `./.github/skills/project-structure/SKILL.md` for an overview of the project structure.

### Core types

- `AIAgent`: The abstract base class that all agents derive from, providing common methods for interacting with an agent.
- `AgentSession`: The abstract base class that all agent sessions derive from, representing a conversation with an agent.
- `ChatClientAgent`: An `AIAgent` implementation that uses an `IChatClient` to send messages to an AI provider and receive responses.
- `IChatClient`: Interface for sending messages to an AI provider and receiving responses. Used by `ChatClientAgent` and implemented by provider-specific packages.
- `FunctionInvokingChatClient`: Decorator for `IChatClient` that adds function invocation capabilities.
- `AITool`: Represents a tool that an agent/AI provider can use, with metadata and an execution delegate.
- `AIFunction`: A specific type of `AITool` that represents a local function the agent/AI provider can call, with parameters and return types defined.
- `ChatMessage`: Represents a message in a conversation.
- `AIContent`: Represents content in a message, which can be text, a function call, tool output and more.

### External Dependencies

The framework integrates with `Microsoft.Extensions.AI` and `Microsoft.Extensions.AI.Abstractions` (external NuGet packages)
using types like `IChatClient`, `FunctionInvokingChatClient`, `AITool`, `AIFunction`, `ChatMessage`, and `AIContent`.

## Key Conventions

- **Encoding**: All new files must be saved with UTF-8 encoding with BOM (Byte Order Mark). This is required for `dotnet format` to work correctly.
- **Copyright header**: `// Copyright (c) Microsoft. All rights reserved.` at top of all `.cs` files
- **XML docs**: Required for all public methods and classes
- **Async**: Use `Async` suffix for methods returning `Task`/`ValueTask`
- **Private classes**: Should be `sealed` unless subclassed
- **Config**: Read from environment variables with `UPPER_SNAKE_CASE` naming
- **Tests**: Add Arrange/Act/Assert comments; use Moq for mocking

## Key Design Principles

When developing or reviewing code, verify adherence to these key design principles:

- **DRY**: Avoid code duplication by moving common logic into helper methods or helper classes.
- **Single Responsibility**: Each class should have one clear responsibility.
- **Encapsulation**: Keep implementation details private and expose only necessary public APIs.
- **Strong Typing**: Use strong typing to ensure that code is self-documenting and to catch errors at compile time.

## Sample Structure

Samples (in `./samples/` folder) should follow this structure:

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
