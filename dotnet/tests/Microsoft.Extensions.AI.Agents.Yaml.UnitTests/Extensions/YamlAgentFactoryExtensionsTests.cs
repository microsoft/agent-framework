// Copyright (c) Microsoft. All rights reserved.

using System.Threading.Tasks;
using Microsoft.Extensions.AI.Agents.AzureAI;

namespace Microsoft.Extensions.AI.Agents.Yaml.UnitTests;

/// <summary>
/// Unit tests for <see cref="YamlAgentFactoryExtensions"/>.
/// </summary>
public class YamlAgentFactoryExtensionsTests
{
    private const string SimpleAzureFoundryAgent =
    """
    type: azure_openai_agent
    name: Joker
    description: Joker Agent
    instructions: You are good at telling jokes.
    model:
      id: ${AzureFoundry:ModelId}
      connection:
        type: azure_foundry
        provider: azure_foundry
        endpoint: ${AzureFoundry:Endpoint}
    """;

    [Theory]
    [InlineData(SimpleAzureFoundryAgent)]
    public async Task CreateAgentFromYaml_DoesNotThrowAsync(string text)
    {
        // Arrange
        var agentFactory = new AzureOpenAIAgentFactory();
        var creationOptions = new AgentCreationOptions();

        // Act
        var agent = await agentFactory.CreateAgentFromYamlAsync(text, creationOptions);

        // Assert
        Assert.NotNull(agent);
    }
}
