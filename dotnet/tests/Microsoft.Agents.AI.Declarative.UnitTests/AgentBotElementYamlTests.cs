// Copyright (c) Microsoft. All rights reserved.
using System;
using Microsoft.Agents.AI;
using Microsoft.Bot.ObjectModel;

namespace Microsoft.Agents.Declarative.UnitTests;

/// <summary>
/// Unit tests for <see cref="AgentBotElementYaml"/>
/// </summary>
public class AgentBotElementYamlTests
{
    private const string SimpleAgent =
        """
        kind: GptComponentMetadata
        name: JokerAgent
        instructions: You are good at telling jokes.
        """;

    private const string SimpleChatClientAgent =
        """
        kind: GptComponentMetadata
        type: chat_client_agent
        name: JokerAgent
        description: Joker Agent
        instructions: You are good at telling jokes.
        """;

    private const string SimpleChatClientAgentWithFunctionTool =
        """
        kind: GptComponentMetadata
        type: chat_client_agent
        name: WeatherAgent
        description: Weather Agent
        instructions: You provide weather information for a given location.
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

    private const string AgentWithConnection =
        """
        kind: GptComponentMetadata
        type: azure_openai_agent
        name: Joker
        description: Joker Agent
        instructions: You are good at telling jokes.
        model:
          id: =Env.AzureOpenAIModelId
          connection:
            type: azure_openai
            provider: azure_openai
            endpoint: =Env.AzureOpenAIEndpoint
            options:
              deployment_name: =Env.AzureOpenAIDeploymentName
        """;

    [Theory]
    [InlineData(SimpleAgent)]
    [InlineData(SimpleChatClientAgent)]
    [InlineData(SimpleChatClientAgentWithFunctionTool)]
    public void FromYaml_DoesNotThrow(string text)
    {
        // Arrange & Act
        var agentDefinition = AgentBotElementYaml.FromYaml(text);

        // Assert
        Assert.NotNull(agentDefinition);
    }

    [Fact]
    public void FromYaml_Properties()
    {
        // Arrange & Act
        var agentDefinition = AgentBotElementYaml.FromYaml(SimpleChatClientAgent);

        // Assert
        Assert.NotNull(agentDefinition);
        Assert.Equal("chat_client_agent", agentDefinition.GetTypeValue());
        Assert.Equal("JokerAgent", agentDefinition.GetName());
        Assert.Equal("Joker Agent", agentDefinition.GetDescription());
        Assert.Equal("You are good at telling jokes.", agentDefinition.Instructions?.ToTemplateString());
    }

    [Fact]
    public void FromYaml_FunctionTool()
    {
        // Arrange & Act
        var agentDefinition = AgentBotElementYaml.FromYaml(SimpleChatClientAgentWithFunctionTool);

        // Assert
        Assert.NotNull(agentDefinition);
        var tools = agentDefinition.GetTools();
        Assert.Single(tools);
        Assert.NotNull(tools[0]);
        Assert.Equal("function", tools[0].GetTypeValue());
        Assert.Equal("GetWeather", tools[0].GetName());
        Assert.Equal("Get the weather for a given location.", tools[0].GetDescription());
    }

    [Fact]
    public void FromYaml_Connection()
    {
        // Arrange & Act
        var agentDefinition = AgentBotElementYaml.FromYaml(AgentWithConnection);

        // Assert
        Assert.NotNull(agentDefinition);
        Assert.Equal("=Env.AzureOpenAIModelId", agentDefinition.GetModelId());
        Assert.Equal("=Env.AzureOpenAIEndpoint", agentDefinition.GetModelConnectionEndpoint());
    }

    [Fact]
    public void FromYaml_Connection_With_Configuration()
    {
        // Arrange
        Environment.SetEnvironmentVariable("AzureOpenAIEndpoint", "endpoint");
        Environment.SetEnvironmentVariable("AzureOpenAIModelId", "modelId");

        // Act
        var agentDefinition = AgentBotElementYaml.FromYaml(AgentWithConnection);

        // Assert
        Assert.NotNull(agentDefinition);
        Assert.Equal("=Env.AzureOpenAIModelId", agentDefinition.GetModelId());
        Assert.Equal("=Env.AzureOpenAIEndpoint", agentDefinition.GetModelConnectionEndpoint());
    }
}
