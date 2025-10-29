# Microsoft.Agents.AI.AzureAIAgents.UnitTests

This project contains comprehensive unit tests for the `Microsoft.Agents.AI.AzureAIAgents` package, specifically testing all extension methods in `AgentsClientExtensions.cs`.

## Test Coverage

The test suite covers:

### GetAIAgent Overloads
- `GetAIAgent(AgentsClient, string model, AgentRecord)` - with various parameter validation scenarios
- `GetAIAgent(AgentsClient, string model, AgentVersion)` - with various parameter validation scenarios  
- `GetAIAgent(AgentsClient, string model, string name)` - by name lookup with error handling
- `GetAIAgent` with `ChatClientAgentOptions` parameter - testing options behavior and fallback to agent definition
- `GetAIAgent` with `clientFactory` parameter - verifying custom client factory application

### GetAIAgentAsync Overloads
- `GetAIAgentAsync(AgentsClient, string model, string name)` - async agent lookup by name
- `GetAIAgentAsync(AgentsClient, string model, string name, ChatClientAgentOptions)` - async with options

### CreateAIAgent Overloads
- `CreateAIAgent(AgentsClient, string model, string name, ...)` - with various optional parameters
- `CreateAIAgent(AgentsClient, string name, AgentDefinition, ...)` - with agent definition
- `CreateAIAgent(AgentsClient, string model, ChatClientAgentOptions)` - with options object

### CreateAIAgentAsync Overloads
- `CreateAIAgentAsync(AgentsClient, AgentDefinition, ...)` - async agent creation with definition
- `CreateAIAgentAsync(AgentsClient, string model, string name, ...)` - async with parameters

### Parameter Validation Tests
- Null parameter checks for all required parameters
- Empty/whitespace string validation
- AgentNotFound error scenarios
- Model requirement validation

### ClientFactory Tests
- Verification that custom `IChatClient` factories are correctly applied
- Service retrieval from the created agents

### Options Tests
- Verification that provided options override agent definition values
- Fallback behavior when options are null or have null properties

## Prerequisites

### Package Dependencies

This test project depends on the `Microsoft.Agents.AI.AzureAIAgents` package, which in turn requires the `Azure.AI.Agents` package (version `2.0.0-alpha.20251024.3`).

**Important**: The `Azure.AI.Agents` package is currently only available from a private Azure DevOps NuGet feed:

```
https://pkgs.dev.azure.com/azure-sdk/internal/_packaging/azure-sdk-for-net-pr/nuget/v3/index.json
```

### Running Tests Locally

To run these tests locally, you need:

1. **Azure DevOps Authentication**: Configure access to the private NuGet feed by setting up Azure Artifacts credentials. See [Azure Artifacts documentation](https://learn.microsoft.com/azure/devops/artifacts/nuget/nuget-exe) for details.

2. **NuGet Configuration**: Ensure your `nuget.config` includes the Azure DevOps source with proper authentication.

### Running Tests in CI/CD

In CI/CD pipelines (GitHub Actions, Azure DevOps, etc.):

1. Configure a NuGet service connection or PAT token with access to the Azure DevOps feed
2. Add authentication to the restore step before building/testing

Example for GitHub Actions:
```yaml
- name: Setup NuGet
  run: |
    dotnet nuget add source https://pkgs.dev.azure.com/azure-sdk/internal/_packaging/azure-sdk-for-net-pr/nuget/v3/index.json \
      --name azure-sdk-for-net-pr \
      --username az \
      --password ${{ secrets.AZURE_DEVOPS_PAT }} \
      --store-password-in-clear-text
```

## Running the Tests

Once dependencies are restored:

```bash
# Build the test project
dotnet build tests/Microsoft.Agents.AI.AzureAIAgents.UnitTests/Microsoft.Agents.AI.AzureAIAgents.UnitTests.csproj

# Run all tests
dotnet test tests/Microsoft.Agents.AI.AzureAIAgents.UnitTests/Microsoft.Agents.AI.AzureAIAgents.UnitTests.csproj

# Run specific test
dotnet test tests/Microsoft.Agents.AI.AzureAIAgents.UnitTests/Microsoft.Agents.AI.AzureAIAgents.UnitTests.csproj --filter "FullyQualifiedName~GetAIAgent_WithAgentRecord_CreatesValidAgent"
```

## Test Patterns

The tests follow established patterns from other test projects in the repository:

- Use of xUnit as the testing framework
- Moq for mocking dependencies
- Clear Arrange-Act-Assert structure with comments
- Descriptive test names indicating what is being tested
- Sealed test classes
- Use of `this.` prefix for instance members
- XML documentation comments for each test method
