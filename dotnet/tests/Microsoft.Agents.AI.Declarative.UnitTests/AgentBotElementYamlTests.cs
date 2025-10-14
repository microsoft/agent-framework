// Copyright (c) Microsoft. All rights reserved.
using System;
using System.ComponentModel;
using System.Linq;
using System.Text.Json.Serialization;
using Microsoft.Bot.ObjectModel;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.UnitTests;

/// <summary>
/// Unit tests for <see cref="AgentBotElementYaml"/>
/// </summary>
public class AgentBotElementYamlTests
{
    private const string AgentWithEverything =
        """
        kind: Prompt
        name: AgentName
        description: Agent description
        instructions: You are a helpful assistant.
        model:
          kind: OpenAIResponsesModel
          id: gpt-4o
          options:
            modelId: gpt-4o
            temperature: 0.7
            maxOutputTokens: 1024
            topP: 0.9
            topK: 50
            frequencyPenalty: 0.0
            presencePenalty: 0.0
            seed: 42
            responseFormat: text
            stopSequences:
              - "###"
              - "END"
              - "STOP"
            allowMultipleToolCalls: true
            chatToolMode: auto
        tools:
          - kind: codeInterpreter
          - kind: function
            name: GetWeather
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
          - kind: mcp
            name: PersonInfoTool
            description: Get information about a person.
            url: https://my-mcp-endpoint.com/api
          - kind: webSearch
            name: WebSearchTool
            description: Search the web for information.
          - kind: fileSearch
            name: FileSearchTool
            description: Search files for information.
            vectorScoreIds:
              - 1
              - 2
              - 3
        """;

    private const string AgentWithOutputSchema =
        """
        kind: Prompt
        name: Translation Assistant
        description: A helpful assistant that translates text to a specified language.
        model:
            kind: OpenAIResponsesModel
            id: gpt-4o
            options:
                temperature: 0.9
                topP: 0.95
        instructions: You are a helpful assistant. You answer questions in {language}. You return your answers in a JSON format.
        additionalInstructions: You must always respond in the specified language.
        tools:
          - kind: codeInterpreter
        template:
            format: PowerFx # Mustache is the other option
            parser: None # Prompty and XML are the other options
        inputSchema:
            properties:
                language: string
        outputSchema:
            properties:
                language:
                    type: string
                    required: true
                    description: The language of the answer.
                answer:
                    type: string
                    required: true
                    description: The answer text.
        """;

    private const string AgentWithConnection =
        """
        kind: Prompt
        name: AgentName
        description: Agent description
        instructions: You are a helpful assistant.
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
        kind: Prompt
        name: AgentName
        description: Agent description
        instructions: You are a helpful assistant.
        model:
          id: =Env.AzureOpenAIModelId
          connection:
            type: azure_openai
            provider: azure_openai
            endpoint: =Env.AzureOpenAIEndpoint
            options:
              deployment_name: =Env.AzureOpenAIDeploymentName
        """;

    private static readonly string[] s_stopSequences = ["###", "END", "STOP"];

    [Theory]
    [InlineData(AgentWithEverything)]
    [InlineData(AgentWithConnection)]
    [InlineData(AgentWithEnvironmentVariables)]
    public void FromYaml_DoesNotThrow(string text)
    {
        // Arrange & Act
        var agent = AgentBotElementYaml.FromYaml(text);

        // Assert
        Assert.NotNull(agent);
    }

    [Fact]
    public void FromYaml_Properties()
    {
        // Arrange & Act
        var agent = AgentBotElementYaml.FromYaml(AgentWithEverything);

        // Assert
        Assert.NotNull(agent);
        Assert.Equal("AgentName", agent.Name);
        Assert.Equal("Agent description", agent.Description);
        Assert.Equal("You are a helpful assistant.", agent.Instructions?.ToTemplateString());
        Assert.NotNull(agent.Model);
        Assert.True(agent.Tools.Length > 0);
    }

    [Fact]
    public void FromYaml_Model()
    {
        // Arrange & Act
        var agent = AgentBotElementYaml.FromYaml(AgentWithEverything);

        // Assert
        Assert.NotNull(agent);
        Assert.NotNull(agent.Model);
        Assert.Equal("gpt-4o", agent.Model.Id);
        OpenAIResponsesModel? model = agent.Model as OpenAIResponsesModel;
        Assert.NotNull(model);
        Assert.NotNull(model.Options);
        Assert.Equal(0.7f, (float?)model.Options?.Temperature.LiteralValue);
        Assert.Equal(0.9f, (float?)model.Options?.TopP.LiteralValue);

        // Assert contents using extension methods
        Assert.Equal(1024, model.Options?.GetMaxOutputTokens());
        Assert.Equal(50, model.Options?.GetTopK());
        Assert.Equal(0.0f, model.Options?.GetFrequencyPenalty());
        Assert.Equal(0.0f, model.Options?.GetPresencePenalty());
        Assert.Equal(42, model.Options?.GetSeed());
        Assert.Equal(s_stopSequences, model.Options?.GetStopSequences());
        Assert.True(model.Options?.GetAllowMultipleToolCalls());
        Assert.Equal(ChatToolMode.Auto, model.Options?.GetChatToolMode());
    }

    [Fact]
    public void FromYaml_OutputSchema()
    {
        // Arrange & Act
        var agent = AgentBotElementYaml.FromYaml(AgentWithOutputSchema);

        // Assert
        Assert.NotNull(agent);
        Assert.NotNull(agent.OutputSchema);
        var responseFormat = agent.OutputSchema.AsResponseFormat() as ChatResponseFormatJson;
        Assert.NotNull(responseFormat);
        Assert.NotNull(responseFormat.Schema);
        var str = responseFormat.Schema.ToString();
        Assert.Equal(str, responseFormat.Schema.ToString());
    }

    [Fact]
    public void FromYaml_CodeInterpreter()
    {
        // Arrange & Act
        var agent = AgentBotElementYaml.FromYaml(AgentWithEverything);

        // Assert
        Assert.NotNull(agent);
        var tools = agent.Tools;
        var codeInterpreterTools = tools.Where(t => t is CodeInterpreterTool).ToArray();
        Assert.Single(codeInterpreterTools);
        var codeInterpreterTool = codeInterpreterTools[0] as CodeInterpreterTool;
        Assert.NotNull(codeInterpreterTool);
    }

    [Fact]
    public void FromYaml_FunctionTool()
    {
        // Arrange & Act
        var agent = AgentBotElementYaml.FromYaml(AgentWithEverything);

        // Assert
        Assert.NotNull(agent);
        var tools = agent.Tools;
        var functionTools = tools.Where(t => t is FunctionTool).ToArray();
        Assert.Single(functionTools);
        var functionTool = functionTools[0] as FunctionTool;
        Assert.NotNull(functionTool);
        Assert.Equal("GetWeather", functionTool.Name);
        Assert.Equal("Get the weather for a given location.", functionTool.Description);
        // TODO check schema
    }

    [Fact]
    public void FromYaml_MCP()
    {
        // Arrange & Act
        var agent = AgentBotElementYaml.FromYaml(AgentWithEverything);

        // Assert
        Assert.NotNull(agent);
        var tools = agent.Tools;
        var mcpTools = tools.Where(t => t is McpTool).ToArray();
        Assert.Single(mcpTools);
        var mcpTool = mcpTools[0] as McpTool;
        Assert.NotNull(mcpTool);
        Assert.Equal("PersonInfoTool", mcpTool.Name?.LiteralValue);
        Assert.Equal("https://my-mcp-endpoint.com/api", mcpTool.Url?.LiteralValue);
    }

    [Fact]
    public void FromYaml_WebSearchTool()
    {
        // Arrange & Act
        var agent = AgentBotElementYaml.FromYaml(AgentWithEverything);

        // Assert
        Assert.NotNull(agent);
        var tools = agent.Tools;
        var webSearchTools = tools.Where(t => t is WebSearchTool).ToArray();
        Assert.Single(webSearchTools);
        Assert.NotNull(webSearchTools[0] as WebSearchTool);
    }

    [Fact]
    public void FromYaml_FileSearchTool()
    {
        // Arrange & Act
        var agent = AgentBotElementYaml.FromYaml(AgentWithEverything);

        // Assert
        Assert.NotNull(agent);
        var tools = agent.Tools;
        var fileSearchTools = tools.Where(t => t is FileSearchTool).ToArray();
        Assert.Single(fileSearchTools);
        var fileSearchTool = fileSearchTools[0] as FileSearchTool;
        Assert.NotNull(fileSearchTool);

        // Verify VectorScoreIds property exists and has correct values
        Assert.Equal(3, fileSearchTool.VectorScoreIds.Length);
        Assert.Equal("1", fileSearchTool.VectorScoreIds[0]);
        Assert.Equal("2", fileSearchTool.VectorScoreIds[1]);
        Assert.Equal("3", fileSearchTool.VectorScoreIds[2]);
    }

    [Fact]
    public void FromYaml_Connection()
    {
        // Arrange & Act
        var agent = AgentBotElementYaml.FromYaml(AgentWithConnection);

        // Assert
        Assert.NotNull(agent);
        // TODO: Re-enable when connections are supported.
        // Assert.Equal("gpt-4o", agent.Model.Id);
        // Assert.Equal("https://my-azure-openai-endpoint.openai.azure.com/", agent.Model.Connection?.GetEndpoint());
    }

    [Fact]
    public void FromYaml_Connection_With_Configuration()
    {
        // Arrange
        Environment.SetEnvironmentVariable("AzureOpenAIEndpoint", "endpoint");
        Environment.SetEnvironmentVariable("AzureOpenAIModelId", "modelId");

        // Act
        var agent = AgentBotElementYaml.FromYaml(AgentWithConnection);

        // Assert
        Assert.NotNull(agent);
        // TODO: Re-enable when environment variables are supported.
        // Assert.Equal("=Env.AzureOpenAIModelId", agent.Model.Id);
        // Assert.Equal("=Env.AzureOpenAIEndpoint", agent.Model?.Connection?.GetEndpoint());
    }

    /// <summary>
    /// Represents information about a person, including their name, age, and occupation, matched to the JSON schema used in the agent.
    /// </summary>
    [Description("Information about a person including their name, age, and occupation")]
    public class PersonInfo
    {
        [JsonPropertyName("name")]
        public string? Name { get; set; }

        [JsonPropertyName("age")]
        public int? Age { get; set; }

        [JsonPropertyName("occupation")]
        public string? Occupation { get; set; }
    }
}
