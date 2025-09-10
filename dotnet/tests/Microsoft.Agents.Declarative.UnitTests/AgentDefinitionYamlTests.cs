// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.Declarative.UnitTests;

/// <summary>
/// Unit tests for <see cref="AgentDefinitionYaml"/>
/// </summary>
public class AgentDefinitionYamlTests
{
    private const string SimpleChatClientAgent =
        """
        type: chat_client_agent
        name: Joker
        description: Joker Agent
        instructions: You are good at telling jokes.
        """;

    private const string SimpleChatClientAgentWithFunctionTool =
        """
        type: chat_client_agent
        name: Joker
        description: Joker Agent
        instructions: You are good at telling jokes.
        tools:
          - name: GetWeather
            type: function
            description: Get the weather for a given location.
            parameters:
              - name: location
                type: string
                description: The city and state, e.g. San Francisco, CA
                required: true
              - name: unit
                type: string
                description: The unit of temperature. Possible values are 'celsius' and 'fahrenheit'.
                required: false
                enum:
                  - celsius
                  - fahrenheit
        """;

    [Theory]
    [InlineData(SimpleChatClientAgent)]
    [InlineData(SimpleChatClientAgentWithFunctionTool)]
    public void FromYaml_DoesNotThrow(string text)
    {
        // Arrange
        var agentFactory = new ChatClientAgentFactory();
        var creationOptions = new AgentCreationOptions();

        // Act
        var agentDefinition = AgentDefinitionYaml.FromYaml(text);

        // Assert
        Assert.NotNull(agentDefinition);
    }

    [Fact]
    public void FromYaml_FunctionTool()
    {
        // Arrange
        var agentFactory = new ChatClientAgentFactory();
        var creationOptions = new AgentCreationOptions();

        // Act
        var agentDefinition = AgentDefinitionYaml.FromYaml(SimpleChatClientAgentWithFunctionTool);

        // Assert
        Assert.NotNull(agentDefinition);
        Assert.NotNull(agentDefinition.Tools);
        Assert.Single(agentDefinition.Tools);
    }
}
