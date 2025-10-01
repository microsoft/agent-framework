# .NET/C# Development Instructions for Microsoft Agent Framework

## Overview

This document provides guidance for working with the .NET/C# implementation of the Microsoft Agent Framework. The .NET implementation is located in the `dotnet/` directory and follows modern C# conventions and best practices.

## Project Structure

```
dotnet/
├── src/                              # Source code
│   ├── Microsoft.Agents.AI/          # Core agent functionality
│   ├── Microsoft.Agents.AI.Abstractions/  # Shared abstractions and interfaces
│   ├── Microsoft.Agents.AI.OpenAI/   # OpenAI integration
│   ├── Microsoft.Agents.AI.AzureAI/  # Azure AI integration
│   ├── Microsoft.Agents.AI.CopilotStudio/ # Copilot Studio integration
│   ├── Microsoft.Agents.AI.A2A/      # Agent-to-Agent communication
│   ├── Microsoft.Agents.AI.Hosting/  # Hosting infrastructure
│   ├── Microsoft.Agents.AI.Workflows/     # Workflow orchestration
│   └── Shared/                       # Shared utilities
├── samples/                          # Sample applications
│   ├── GettingStarted/               # Getting started samples
│   │   ├── Agents/                   # Basic agent samples
│   │   ├── AgentProviders/           # Provider-specific samples
│   │   └── Workflows/                # Workflow samples
│   ├── AgentWebChat/                 # Web chat sample
│   └── SemanticKernelMigration/      # SK migration examples
├── tests/                            # Unit and integration tests
├── nuget/                            # NuGet packaging configuration
├── eng/                              # Engineering/build scripts
├── agent-framework-dotnet.slnx       # Solution file
├── Directory.Build.props             # MSBuild properties
├── Directory.Packages.props          # Central package management
├── global.json                       # .NET SDK version
└── README.md                         # .NET-specific documentation
```

## Platform and Framework Targets

### Target Frameworks

- **Primary**: .NET 9.0, .NET 8.0
- **Legacy Support**: .NET Standard 2.0, .NET Framework 4.7.2
- **Multi-targeting**: Projects use `<ProjectsTargetFrameworks>` for broad compatibility
- **Debug Targets**: Simplified targeting with `<ProjectsDebugTargetFrameworks>`

### SDK Version

See `global.json` for the required .NET SDK version.

## Architectural Patterns

### Dependency Injection

- Heavy use of Microsoft.Extensions.DependencyInjection
- Services registered via extension methods (e.g., `AddAzureOpenAIAgent()`)
- Constructor injection is the preferred pattern
- Avoid service locator pattern

### Async/Await

- All I/O operations must be asynchronous
- Use `async`/`await` consistently
- Method names should end with `Async` (e.g., `RunAsync()`, `GetResponseAsync()`)
- Avoid blocking on async code (never use `.Result` or `.Wait()`)

### Options Pattern

- Configuration uses `IOptions<T>` pattern
- Options classes should be POCOs with properties
- Validation via `IValidateOptions<T>` when needed
- Use `Configure<T>()` in DI registration

### Factory Pattern

- Client factories for creating agents and chat clients
- Use `IAIAgentFactory` and similar interfaces
- Allows for easier testing and lifetime management

## Coding Standards

### Naming Conventions

- **PascalCase**: Classes, methods, properties, public fields
- **camelCase**: Private fields, local variables, parameters
- **Interface names**: Start with `I` (e.g., `IAIAgent`, `IChatClient`)
- **Async methods**: End with `Async` suffix
- **Private fields**: Can optionally use `_camelCase` prefix

### Language Features

- **C# Version**: Currently C# 13 (`<LangVersion>13</LangVersion>`)
- **Nullable Reference Types**: Enabled (`<Nullable>enable</Nullable>`)
- **Implicit Usings**: Disabled (`<ImplicitUsings>disable</ImplicitUsings>`)
- Use modern C# features (pattern matching, records, init-only properties, etc.)
- Prefer expression-bodied members when appropriate
- Use primary constructors for simple classes

### Code Analysis

- **Analyzers**: Enabled during build (`<RunAnalyzersDuringBuild>true</RunAnalyzersDuringBuild>`)
- **Analysis Mode**: All rules enabled by default (`<AnalysisMode>AllEnabledByDefault</AnalysisMode>`)
- **Warnings as Errors**: Enabled (`<TreatWarningsAsErrors>true</TreatWarningsAsErrors>`)
- **Documentation**: XML documentation required (`<GenerateDocumentationFile>true</GenerateDocumentationFile>`)

### Documentation

- All public APIs must have XML documentation comments
- Use `<summary>`, `<param>`, `<returns>`, `<exception>` tags
- Include code examples in `<example>` tags for complex APIs
- Document thread safety considerations
- Document exceptions that can be thrown

Example:
```csharp
/// <summary>
/// Creates a new AI agent with the specified configuration.
/// </summary>
/// <param name="name">The name of the agent.</param>
/// <param name="instructions">The system instructions for the agent.</param>
/// <returns>A new <see cref="IAIAgent"/> instance.</returns>
/// <exception cref="ArgumentNullException">Thrown when <paramref name="name"/> is null.</exception>
public IAIAgent CreateAgent(string name, string instructions)
{
    // Implementation
}
```

## Build System

### MSBuild

- **Central Package Management**: All package versions in `Directory.Packages.props`
- **Shared Properties**: Common properties in `Directory.Build.props`
- **Shared Targets**: Build customizations in `Directory.Build.targets`
- **Engineering Scripts**: Build automation in `eng/MSBuild/`

### Build Commands

```bash
# Restore dependencies
dotnet restore

# Build solution
dotnet build

# Build specific project
dotnet build src/Microsoft.Agents.AI/Microsoft.Agents.AI.csproj

# Run tests
dotnet test

# Create NuGet packages
dotnet pack

# Run specific sample
dotnet run --project samples/GettingStarted/Agents/Agent_Step01_BasicAgent/Agent_Step01_BasicAgent.csproj
```

### Solution Structure

The solution uses `.slnx` format (XML-based solution file). Open with Visual Studio 2022 or use `dotnet sln` commands.

## Testing

### Test Organization

- **Unit Tests**: Located in `tests/*UnitTests` projects
- **Integration Tests**: Located in `tests/*IntegrationTests` projects
- **Test Framework**: xUnit
- **Mocking**: Moq or NSubstitute
- **Assertions**: FluentAssertions recommended

### Test Naming

- Use descriptive test names: `MethodName_Scenario_ExpectedBehavior`
- Example: `CreateAgent_WithNullName_ThrowsArgumentNullException`
- Use `[Fact]` for single tests, `[Theory]` with `[InlineData]` for parameterized tests

### Running Tests

```bash
# Run all tests
dotnet test

# Run tests for specific project
dotnet test tests/Microsoft.Agents.AI.UnitTests

# Run with coverage
dotnet test --collect:"XPlat Code Coverage"

# Run only unit tests (exclude integration tests)
dotnet test --filter "Category!=Integration"
```

## Dependencies and Package Management

### Central Package Management (CPM)

All NuGet package versions are managed centrally in `Directory.Packages.props`. To add a dependency:

1. Add package reference without version in project file:
   ```xml
   <PackageReference Include="Azure.AI.OpenAI" />
   ```

2. Add version in `Directory.Packages.props`:
   ```xml
   <PackageVersion Include="Azure.AI.OpenAI" Version="2.0.0" />
   ```

### Common Dependencies

- **Azure.AI.OpenAI**: Azure OpenAI client library
- **OpenAI**: OpenAI client library
- **Microsoft.Extensions.DependencyInjection**: DI container
- **Microsoft.Extensions.Logging**: Logging abstractions
- **Microsoft.Extensions.Options**: Options pattern
- **System.Text.Json**: JSON serialization

## Common Patterns in Agent Framework

### Creating an Agent

```csharp
using Azure.AI.OpenAI;
using Azure.Identity;
using Microsoft.Agents.AI;

var endpoint = Environment.GetEnvironmentVariable("AZURE_OPENAI_ENDPOINT")!;
var deploymentName = Environment.GetEnvironmentVariable("AZURE_OPENAI_DEPLOYMENT_NAME")!;

var agent = new AzureOpenAIClient(new Uri(endpoint), new AzureCliCredential())
    .GetOpenAIResponseClient(deploymentName)
    .CreateAIAgent(
        name: "MyAgent",
        instructions: "You are a helpful assistant."
    );

var response = await agent.RunAsync("Hello!");
```

### Adding Tools to an Agent

```csharp
using System.ComponentModel;

public class WeatherTools
{
    [Description("Get the current weather for a location")]
    public static string GetWeather(
        [Description("The city name")] string location)
    {
        return $"The weather in {location} is sunny.";
    }
}

var agent = client.CreateAIAgent(
    name: "WeatherAgent",
    instructions: "You help with weather information.",
    tools: [WeatherTools.GetWeather]
);
```

### Using Middleware

```csharp
agent.AddMiddleware(async (context, next) =>
{
    // Pre-processing
    Console.WriteLine($"Request: {context.Request}");
    
    await next();
    
    // Post-processing
    Console.WriteLine($"Response: {context.Response}");
});
```

### Workflows

```csharp
using Microsoft.Agents.AI.Workflows;

var workflow = new WorkflowBuilder()
    .AddAgent("researcher", researchAgent)
    .AddAgent("writer", writerAgent)
    .Connect("researcher", "writer")
    .Build();

await workflow.RunAsync("Research and write about AI agents");
```

## Debugging and Diagnostics

### Logging

- Use `ILogger<T>` for logging
- Follow standard log levels (Trace, Debug, Information, Warning, Error, Critical)
- Use structured logging with named parameters

```csharp
logger.LogInformation("Agent {AgentName} processing request {RequestId}", 
    agentName, requestId);
```

### OpenTelemetry

- OpenTelemetry integration available via `Microsoft.Agents.AI` package
- Automatic tracing for agent operations
- See samples in `samples/GettingStarted/AgentOpenTelemetry/`

## Code Formatting

### Tools

- Use built-in Visual Studio formatting (Ctrl+K, Ctrl+D)
- EditorConfig settings in `.editorconfig` at root
- Follow the style guidelines in `.editorconfig`

### Style Guidelines

- **Indentation**: 4 spaces
- **Braces**: Opening brace on new line (Allman style)
- **Line Length**: No hard limit, but be reasonable (~120 chars)
- **Ordering**: Usings at top, sorted, with `System` namespaces first

## Common Development Tasks

### Adding a New Provider

1. Create new project in `src/` (e.g., `Microsoft.Agents.AI.NewProvider`)
2. Add abstractions and interfaces in `Abstractions` project if needed
3. Implement client interfaces (`IChatClient`, etc.)
4. Add extension methods for DI registration
5. Create samples in `samples/GettingStarted/AgentProviders/`
6. Add tests in `tests/`
7. Update documentation

### Adding a New Feature

1. Design the API (consider both C# and Python implementations)
2. Add interfaces to `Abstractions` project
3. Implement in appropriate project
4. Add XML documentation
5. Create unit tests
6. Add integration tests if applicable
7. Create sample demonstrating the feature
8. Update README and documentation

## Security Best Practices

- Never hardcode API keys or secrets
- Use environment variables or Azure Key Vault for sensitive configuration
- Use `SecureString` for passwords when appropriate
- Follow the OWASP guidelines for input validation
- See `SECURITY.md` for security policy

## Performance Considerations

- Use `ValueTask<T>` for hot paths when appropriate
- Avoid allocations in tight loops
- Use `ArrayPool<T>` for temporary buffers
- Consider `Span<T>` and `Memory<T>` for buffer operations
- Profile before optimizing

## Additional Resources

- **.NET Documentation**: [Microsoft Learn - Agent Framework](https://learn.microsoft.com/agent-framework/)
- **Samples**: Browse `samples/GettingStarted/` for comprehensive examples
- **Design Docs**: See `../docs/design/` for technical specifications
- **ADRs**: Review `../docs/decisions/` for architectural decisions
- **Migration Guides**: See samples for migrating from Semantic Kernel

## Getting Help

- Check existing samples first
- Review test cases for usage examples
- File GitHub issues for bugs
- Use GitHub Discussions for questions
- Join the Microsoft Azure AI Foundry Discord
