// Copyright (c) Microsoft. All rights reserved.
using System;
using Microsoft.Bot.ObjectModel;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.UnitTests;

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

    private const string SimpleChatClientAgentWithEverything =
        """
        kind: GptComponentMetadata
        type: chat_client_agent
        name: JokerAgent
        description: Joker Agent
        instructions: You are good at telling jokes.
        model:
          id: gpt-4o
          options:
            model_id: gpt-4o
            temperature: 0.7
            max_output_tokens: 1024
            top_p: 0.9
            top_k: 50
            frequency_penalty: 0.0
            presence_penalty: 0.0
            seed: 42
            response_format: text
            stop_sequences:
              - "###"
              - "END"
              - "STOP"
            allow_multiple_tool_calls: true
            tool_mode: auto
        tools:
          - type: code_interpreter
         kind: GptComponentMetadata
        type: chat_client_agent
        name: JokerAgent
        description: Joker Agent
        instructions: You are good at telling jokes.
        model:
          id: gpt-4o
          options:
            model_id: gpt-4o
            temperature: 0.7
            max_output_tokens: 1024
            top_p: 0.9
            top_k: 50
            frequency_penalty: 0.0
            presence_penalty: 0.0
            seed: 42
            stop_sequences:
              - "###"
              - "END"
              - "STOP"
            allow_multiple_tool_calls: true
            tool_mode: auto
        tools:
          - type: code_interpreter
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
          id: gpt-4o
          connection:
            type: azure_openai
            provider: azure_openai
            endpoint: https://my-azure-openai-endpoint.openai.azure.com/
            options:
              deployment_name: gpt-4o-deployment
        """;

    private const string AgentWithEnvironmentVariables =
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

    private static readonly string[] s_stopSequences = new[] { "###", "END", "STOP" };

    [Theory]
    [InlineData(SimpleAgent)]
    [InlineData(SimpleChatClientAgent)]
    [InlineData(SimpleChatClientAgentWithEverything)]
    [InlineData(SimpleChatClientAgentWithFunctionTool)]
    [InlineData(AgentWithConnection)]
    [InlineData(AgentWithEnvironmentVariables)]
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
        Assert.Equal("JokerAgent", agentDefinition.Name);
        Assert.Equal("Joker Agent", agentDefinition.Description);
        Assert.Equal("You are good at telling jokes.", agentDefinition.Instructions?.ToTemplateString());
    }

    [Fact]
    public void FromYaml_Everything()
    {
        // Arrange & Act
        var agentDefinition = AgentBotElementYaml.FromYaml(SimpleChatClientAgentWithEverything);

        // Assert
        Assert.NotNull(agentDefinition);
        var tools = agentDefinition.Tools;
        Assert.Single(tools);
        Assert.NotNull(tools[0]);
        Assert.Equal("code_interpreter", tools[0].ExtensionData?.GetPropertyOrNull<StringDataValue>(InitializablePropertyPath.Create("type"))?.Value);
        Assert.NotNull(agentDefinition.Model);
        Assert.Equal("gpt-4o", agentDefinition.Model.Id);
        Assert.NotNull(agentDefinition.AISettings);
        Assert.Equal(0.7f, (float?)agentDefinition.AISettings.ExtensionData?.GetNumber("temperature"));
        Assert.Equal(1024, (int?)agentDefinition.AISettings.ExtensionData?.GetNumber("max_output_tokens"));
        Assert.Equal(0.9f, (float?)agentDefinition.AISettings.ExtensionData?.GetNumber("top_p"));
        Assert.Equal(50, (int?)agentDefinition.AISettings.ExtensionData?.GetNumber("top_k"));
        Assert.Equal(0.0f, (float?)agentDefinition.AISettings.ExtensionData?.GetNumber("frequency_penalty"));
        Assert.Equal(0.0f, (float?)agentDefinition.AISettings.ExtensionData?.GetNumber("presence_penalty"));
        Assert.Equal(42, (long?)agentDefinition.AISettings.ExtensionData?.GetNumber("seed"));
        Assert.Equal(s_stopSequences, agentDefinition.AISettings.GetStopSequences());
        Assert.True(agentDefinition.AISettings.ExtensionData?.GetBoolean("allow_multiple_tool_calls"));
        Assert.Equal(ChatToolMode.Auto, agentDefinition.AISettings.GetChatToolMode());
    }

    [Fact]
    public void FromYaml_FunctionTool()
    {
        // Arrange & Act
        var agentDefinition = AgentBotElementYaml.FromYaml(SimpleChatClientAgentWithFunctionTool);

        // Assert
        Assert.NotNull(agentDefinition);
        var tools = agentDefinition.Tools;
        Assert.Single(tools);
        Assert.NotNull(tools[0]);
        //Assert.Equal("function", tools[0].GetId());
        //Assert.Equal("GetWeather", tools[0].GetName());
        //Assert.Equal("Get the weather for a given location.", tools[0].GetDescription());
    }

    [Fact]
    public void FromYaml_Connection()
    {
        // Arrange & Act
        var agentDefinition = AgentBotElementYaml.FromYaml(AgentWithConnection);

        // Assert
        Assert.NotNull(agentDefinition);
        Assert.Equal("gpt-4o", agentDefinition.Model.Id);
        Assert.Equal("https://my-azure-openai-endpoint.openai.azure.com/", agentDefinition.Model.Connection?.GetEndpoint());
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
        Assert.Equal("=Env.AzureOpenAIModelId", agentDefinition.Model.Id);
        Assert.Equal("=Env.AzureOpenAIEndpoint", agentDefinition.Model?.Connection?.GetEndpoint());
    }
}
