// Copyright (c) Microsoft. All rights reserved.
using System.Collections.Generic;
using System.ComponentModel;
using System.Linq;
using System.Text.Json.Serialization;
using Microsoft.Bot.ObjectModel;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.Configuration;

namespace Microsoft.Agents.AI.Declarative.UnitTests;

/// <summary>
/// Unit tests for <see cref="AgentBotElementYaml"/>
/// </summary>
public sealed class AgentBotElementYamlTests
{
    [Theory]
    [InlineData(PromptAgents.AgentWithEverything)]
    [InlineData(PromptAgents.AgentWithApiKeyConnection)]
    [InlineData(PromptAgents.AgentWithEnvironmentVariables)]
    [InlineData(PromptAgents.AgentWithOutputSchema)]
    [InlineData(PromptAgents.OpenAIChatAgent)]
    [InlineData(PromptAgents.AgentWithCurrentModels)]
    [InlineData(PromptAgents.AgentWithRemoteConnection)]
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
        var agent = AgentBotElementYaml.FromYaml(PromptAgents.AgentWithEverything);

        // Assert
        Assert.NotNull(agent);
        Assert.Equal("AgentName", agent.Name);
        Assert.Equal("Agent description", agent.Description);
        Assert.Equal("You are a helpful assistant.", agent.Instructions?.ToTemplateString());
        Assert.NotNull(agent.Model);
        Assert.True(agent.Tools.Length > 0);
    }

    [Fact]
    public void FromYaml_CurrentModels()
    {
        // Arrange & Act
        var agent = AgentBotElementYaml.FromYaml(PromptAgents.AgentWithCurrentModels);

        // Assert
        Assert.NotNull(agent);
        Assert.NotNull(agent.Model);
        Assert.Equal("gpt-4o", agent.Model.ModelNameHint);
        Assert.NotNull(agent.Model.Options);
        Assert.Equal(0.7f, (float?)agent.Model.Options?.Temperature?.LiteralValue);
        Assert.Equal(0.9f, (float?)agent.Model.Options?.TopP?.LiteralValue);

        // Assert contents using extension methods
        Assert.Equal(1024, agent.Model.Options?.MaxOutputTokens?.LiteralValue);
        Assert.Equal(50, agent.Model.Options?.TopK?.LiteralValue);
        Assert.Equal(0.7f, (float?)agent.Model.Options?.FrequencyPenalty?.LiteralValue);
        Assert.Equal(0.7f, (float?)agent.Model.Options?.PresencePenalty?.LiteralValue);
        Assert.Equal(42, agent.Model.Options?.Seed?.LiteralValue);
        Assert.Equal(PromptAgents.s_stopSequences, agent.Model.Options?.StopSequences);
        Assert.True(agent.Model.Options?.AllowMultipleToolCalls?.LiteralValue);
        Assert.Equal(ChatToolMode.Auto, agent.Model.Options?.AsChatToolMode());
    }

    [Fact]
    public void FromYaml_OutputSchema()
    {
        // Arrange & Act
        var agent = AgentBotElementYaml.FromYaml(PromptAgents.AgentWithOutputSchema);

        // Assert
        Assert.NotNull(agent);
        Assert.NotNull(agent.OutputType);
        var responseFormat = agent.OutputType.AsChatResponseFormat() as ChatResponseFormatJson;
        Assert.NotNull(responseFormat);
        Assert.NotNull(responseFormat.Schema);
    }

    [Fact]
    public void FromYaml_CodeInterpreter()
    {
        // Arrange & Act
        var agent = AgentBotElementYaml.FromYaml(PromptAgents.AgentWithEverything);

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
        var agent = AgentBotElementYaml.FromYaml(PromptAgents.AgentWithEverything);

        // Assert
        Assert.NotNull(agent);
        var tools = agent.Tools;
        var functionTools = tools.Where(t => t is InvokeClientTaskAction).ToArray();
        Assert.Single(functionTools);
        var functionTool = functionTools[0] as InvokeClientTaskAction;
        Assert.NotNull(functionTool);
        Assert.Equal("GetWeather", functionTool.Name);
        Assert.Equal("Get the weather for a given location.", functionTool.Description);
        // TODO check schema
    }

    [Fact]
    public void FromYaml_MCP()
    {
        // Arrange & Act
        var agent = AgentBotElementYaml.FromYaml(PromptAgents.AgentWithEverything);

        // Assert
        Assert.NotNull(agent);
        var tools = agent.Tools;
        var mcpTools = tools.Where(t => t is McpServerTool).ToArray();
        Assert.Single(mcpTools);
        var mcpTool = mcpTools[0] as McpServerTool;
        Assert.NotNull(mcpTool);
        Assert.Equal("PersonInfoTool", mcpTool.ServerName?.LiteralValue);
        var connection = mcpTool.Connection as AnonymousConnection;
        Assert.NotNull(connection);
        Assert.Equal("https://my-mcp-endpoint.com/api", connection.Endpoint?.LiteralValue);
    }

    [Fact]
    public void FromYaml_WebSearchTool()
    {
        // Arrange & Act
        var agent = AgentBotElementYaml.FromYaml(PromptAgents.AgentWithEverything);

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
        var agent = AgentBotElementYaml.FromYaml(PromptAgents.AgentWithEverything);

        // Assert
        Assert.NotNull(agent);
        var tools = agent.Tools;
        var fileSearchTools = tools.Where(t => t is FileSearchTool).ToArray();
        Assert.Single(fileSearchTools);
        var fileSearchTool = fileSearchTools[0] as FileSearchTool;
        Assert.NotNull(fileSearchTool);

        // Verify vector store content property exists and has correct values
        Assert.NotNull(fileSearchTool.VectorStoreIds);
        Assert.Equal(3, fileSearchTool.VectorStoreIds.LiteralValue.Length);
        Assert.Equal("1", fileSearchTool.VectorStoreIds.LiteralValue[0]);
        Assert.Equal("2", fileSearchTool.VectorStoreIds.LiteralValue[1]);
        Assert.Equal("3", fileSearchTool.VectorStoreIds.LiteralValue[2]);
    }

    [Fact]
    public void FromYaml_ApiKeyConnection()
    {
        // Arrange & Act
        var agent = AgentBotElementYaml.FromYaml(PromptAgents.AgentWithApiKeyConnection);

        // Assert
        Assert.NotNull(agent);
        Assert.NotNull(agent.Model);
        var model = agent.Model as CurrentModels;
        Assert.NotNull(model);
        Assert.NotNull(model.Connection);
        Assert.IsType<ApiKeyConnection>(model.Connection);
        var connection = model.Connection as ApiKeyConnection;
        Assert.NotNull(connection);
        Assert.Equal("https://my-azure-openai-endpoint.openai.azure.com/", connection.Endpoint?.LiteralValue);
        Assert.Equal("my-api-key", connection.Key?.LiteralValue);
    }

    [Fact]
    public void FromYaml_RemoteConnection()
    {
        // Arrange & Act
        var agent = AgentBotElementYaml.FromYaml(PromptAgents.AgentWithRemoteConnection);

        // Assert
        Assert.NotNull(agent);
        Assert.NotNull(agent.Model);
        var model = agent.Model as CurrentModels;
        Assert.NotNull(model);
        Assert.NotNull(model.Connection);
        Assert.IsType<RemoteConnection>(model.Connection);
        var connection = model.Connection as RemoteConnection;
        Assert.NotNull(connection);
        Assert.Equal("https://my-azure-openai-endpoint.openai.azure.com/", connection.Endpoint?.LiteralValue);
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
        var agent = AgentBotElementYaml.FromYaml(PromptAgents.AgentWithEnvironmentVariables, configuration);

        // Assert
        Assert.NotNull(agent);
        Assert.NotNull(agent.Model);
        var model = agent.Model as CurrentModels;
        Assert.NotNull(model);
        Assert.NotNull(model.Connection);
        Assert.IsType<ApiKeyConnection>(model.Connection);
        //Assert.Equal("https://my-azure-openai-endpoint.openai.azure.com/", agent.Model.Connection.Endpoint?.LiteralValue);
        //Assert.Equal("apiKey", connection.Key?.LiteralValue);
        //Assert.Equal("modelId", model.Id);
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
