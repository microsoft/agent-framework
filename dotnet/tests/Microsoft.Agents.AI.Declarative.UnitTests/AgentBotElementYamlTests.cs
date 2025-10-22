// Copyright (c) Microsoft. All rights reserved.
using System.Collections.Generic;
using System.ComponentModel;
using System.Linq;
using System.Text.Json.Serialization;
using Microsoft.Bot.ObjectModel;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.Configuration;

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

    private const string AgentWithKeyConnection =
        """
        kind: Prompt
        name: AgentName
        description: Agent description
        instructions: You are a helpful assistant.
        model:
          kind: OpenAIResponsesModel
          id: gpt-4o
          connection:
            kind: Key
            endpoint: https://my-azure-openai-endpoint.openai.azure.com/
            key: my-api-key
        """;

    private const string AgentWithEnvironmentVariables =
        """
        kind: Prompt
        name: AgentName
        description: Agent description
        instructions: You are a helpful assistant.
        model:
          kind: OpenAIResponsesModel
          id: =Env.OpenAIModelId
          connection:
            kind: Key
            endpoint: =Env.OpenAIEndpoint
            key: =Env.OpenAIApiKey
        """;

    private const string OpenAIChatAgent =
        """
        kind: Prompt
        name: Assistant
        description: Helpful assistant
        instructions: You are a helpful assistant. You answer questions is the language specified by the user. You return your answers in a JSON format.
        model:
            kind: OpenAIResponsesModel
            id: =Env.OPENAI_MODEL
            options:
                temperature: 0.9
                topP: 0.95
            connection:
                kind: Key
                key: =Env.OPENAI_APIKEY
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

    private const string AgentWithOpenAIResponsesModel =
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
        """;

    private const string AgentWithOpenAIChatModel =
        """
        kind: Prompt
        name: AgentName
        description: Agent description
        instructions: You are a helpful assistant.
        model:
          kind: OpenAIChatModel
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
        """;

    private const string AgentWithOpenAIAssistantsModel =
        """
        kind: Prompt
        name: AgentName
        description: Agent description
        instructions: You are a helpful assistant.
        model:
          kind: OpenAIAssistantsModel
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
        """;

    private static readonly string[] s_stopSequences = ["###", "END", "STOP"];

    [Theory]
    [InlineData(AgentWithEverything)]
    [InlineData(AgentWithKeyConnection)]
    [InlineData(AgentWithEnvironmentVariables)]
    [InlineData(AgentWithOutputSchema)]
    [InlineData(OpenAIChatAgent)]
    [InlineData(AgentWithOpenAIResponsesModel)]
    [InlineData(AgentWithOpenAIChatModel)]
    [InlineData(AgentWithOpenAIAssistantsModel)]
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
    public void FromYaml_OpenAIResponsesModel()
    {
        // Arrange & Act
        var agent = AgentBotElementYaml.FromYaml(AgentWithOpenAIResponsesModel);

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

    /*
    [Fact]
    public void FromYaml_OpenAIChatModel()
    {
        // Arrange & Act
        var agent = AgentBotElementYaml.FromYaml(AgentWithOpenAIResponsesModel);

        // Assert
        Assert.NotNull(agent);
        Assert.NotNull(agent.Model);
        Assert.Equal("gpt-4o", agent.Model.Id);
        OpenAIChatModel? model = agent.Model as OpenAIChatModel;
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
    public void FromYaml_OpenAIAssistantsModel()
    {
        // Arrange & Act
        var agent = AgentBotElementYaml.FromYaml(AgentWithOpenAIAssistantsModel);

        // Assert
        Assert.NotNull(agent);
        Assert.NotNull(agent.Model);
        Assert.Equal("gpt-4o", agent.Model.Id);
        OpenAIAssistantsModel? model = agent.Model as OpenAIAssistantsModel;
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
    */

    [Fact]
    public void FromYaml_OutputSchema()
    {
        // Arrange & Act
        var agent = AgentBotElementYaml.FromYaml(AgentWithOutputSchema);

        // Assert
        Assert.NotNull(agent);
        Assert.NotNull(agent.OutputSchema);
        var responseFormat = agent.OutputSchema.AsChatResponseFormat() as ChatResponseFormatJson;
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
        Assert.Equal(3, fileSearchTool.VectorStoreIds.Length);
        Assert.Equal("1", fileSearchTool.VectorStoreIds[0]);
        Assert.Equal("2", fileSearchTool.VectorStoreIds[1]);
        Assert.Equal("3", fileSearchTool.VectorStoreIds[2]);
    }

    [Fact]
    public void FromYaml_KeyConnection()
    {
        // Arrange & Act
        var agent = AgentBotElementYaml.FromYaml(AgentWithKeyConnection);

        // Assert
        Assert.NotNull(agent);
        OpenAIResponsesModel? model = agent.Model as OpenAIResponsesModel;
        Assert.NotNull(model);
        Assert.NotNull(model.Connection);
        KeyConnection? connection = model.Connection as KeyConnection;
        Assert.NotNull(connection);
        Assert.Equal("https://my-azure-openai-endpoint.openai.azure.com/", connection.Endpoint?.LiteralValue);
        Assert.Equal("my-api-key", connection.Key?.LiteralValue);
    }

    [Fact]
    public void FromYaml_WithEnvironmentVariables()
    {
        // Arrange
        IConfiguration configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["OpenAIEndpoint"] = "endpoint",
                ["OpenAIModelId"] = "modelId",
                ["OpenAIApiKey"] = "apiKey"
            })
            .Build();

        // Act
        PromptAgent agent = AgentBotElementYaml.FromYaml(AgentWithEnvironmentVariables, configuration);

        // Assert
        Assert.NotNull(agent);
        OpenAIResponsesModel? model = agent.Model as OpenAIResponsesModel;
        Assert.NotNull(model);
        Assert.NotNull(model.Connection);
        KeyConnection? connection = model.Connection as KeyConnection;
        Assert.NotNull(connection);
        Assert.Equal("endpoint", connection.Endpoint?.LiteralValue);
        Assert.Equal("apiKey", connection.Key?.LiteralValue);
        Assert.Equal("modelId", model.Id);
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
