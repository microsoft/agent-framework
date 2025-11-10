// Copyright (c) Microsoft. All rights reserved.

using System;
using System.IO;
using System.Threading.Tasks;
using AgentConformance.IntegrationTests.Support;
using Azure.AI.Agents.Persistent;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;
using Shared.IntegrationTests;

namespace AzureAIAgentsPersistent.IntegrationTests;

public class AzureAIAgentsPersistentCreateTests
{
    private static readonly AzureAIConfiguration s_config = TestConfiguration.LoadSection<AzureAIConfiguration>();
    private readonly PersistentAgentsClient _persistentAgentsClient = new(s_config.Endpoint, new AzureCliCredential());

    [Theory]
    [InlineData("CreateWithChatClientAgentOptionsAsync")]
    [InlineData("CreateWithChatClientAgentOptionsSync")]
    [InlineData("CreateWithFoundryOptionsAsync")]
    [InlineData("CreateWithFoundryOptionsSync")]
    public async Task CreateAgent_CreatesAgentWithCorrectMetadataAsync(string createMechanism)
    {
        // Arrange.
        const string AgentName = "IntegrationTestAgent";
        const string AgentDescription = "An agent created during integration tests";
        const string AgentInstructions = "You are an integration test agent";

        // Act.
        var agent = createMechanism switch
        {
            "CreateWithChatClientAgentOptionsAsync" => await this._persistentAgentsClient.CreateAIAgentAsync(
                s_config.DeploymentName,
                options: new ChatClientAgentOptions(
                    instructions: AgentInstructions,
                    name: AgentName,
                    description: AgentDescription)),
            "CreateWithChatClientAgentOptionsSync" => this._persistentAgentsClient.CreateAIAgent(
                s_config.DeploymentName,
                options: new ChatClientAgentOptions(
                    instructions: AgentInstructions,
                    name: AgentName,
                    description: AgentDescription)),
            "CreateWithFoundryOptionsAsync" => await this._persistentAgentsClient.CreateAIAgentAsync(
                s_config.DeploymentName,
                instructions: AgentInstructions,
                name: AgentName,
                description: AgentDescription),
            "CreateWithFoundryOptionsSync" => this._persistentAgentsClient.CreateAIAgent(
                s_config.DeploymentName,
                instructions: AgentInstructions,
                name: AgentName,
                description: AgentDescription),
            _ => throw new InvalidOperationException($"Unknown create mechanism: {createMechanism}")
        };

        try
        {
            // Assert.
            Assert.NotNull(agent);
            Assert.Equal(AgentName, agent.Name);
            Assert.Equal(AgentDescription, agent.Description);
            Assert.Equal(AgentInstructions, agent.Instructions);

            var retrievedAgentMetadata = await this._persistentAgentsClient.Administration.GetAgentAsync(agent.Id);
            Assert.NotNull(retrievedAgentMetadata);
            Assert.Equal(AgentName, retrievedAgentMetadata.Value.Name);
            Assert.Equal(AgentDescription, retrievedAgentMetadata.Value.Description);
            Assert.Equal(AgentInstructions, retrievedAgentMetadata.Value.Instructions);
        }
        finally
        {
            // Cleanup.
            await this._persistentAgentsClient.Administration.DeleteAgentAsync(agent.Id);
        }
    }

    [Theory(Skip = "For manual testing only")]
    [InlineData("CreateWithChatClientAgentOptionsAsync")]
    [InlineData("CreateWithChatClientAgentOptionsSync")]
    [InlineData("CreateWithFoundryOptionsAsync")]
    [InlineData("CreateWithFoundryOptionsSync")]
    public async Task CreateAgent_CreatesAgentWithVectorStoresAsync(string createMechanism)
    {
        // Arrange.
        const string AgentInstructions = """
            You are a helpful agent that can help fetch data from files you know about.
            Use the File Search Tool to look up codes for words.
            Do not answer a question unless you can find the answer using the File Search Tool.
            """;

        // Create a vector store.
        var searchFilePath = Path.GetTempFileName() + "wordcodelookup.txt";
        File.WriteAllText(
            path: searchFilePath,
            contents: "The word 'apple' uses the code 442345, while the word 'banana' uses the code 673457."
        );
        PersistentAgentFileInfo uploadedAgentFile = this._persistentAgentsClient.Files.UploadFile(
            filePath: searchFilePath,
            purpose: PersistentAgentFilePurpose.Agents
        );
        var vectorStoreMetadata = await this._persistentAgentsClient.VectorStores.CreateVectorStoreAsync([uploadedAgentFile.Id], name: "WordCodeLookup_VectorStore");

        // Act.
        var agent = createMechanism switch
        {
            "CreateWithChatClientAgentOptionsAsync" => await this._persistentAgentsClient.CreateAIAgentAsync(
                s_config.DeploymentName,
                options: new ChatClientAgentOptions(
                    instructions: AgentInstructions,
                    tools: [new HostedFileSearchTool() { Inputs = [new HostedVectorStoreContent(vectorStoreMetadata.Value.Id)] }])),
            "CreateWithChatClientAgentOptionsSync" => this._persistentAgentsClient.CreateAIAgent(
                s_config.DeploymentName,
                options: new ChatClientAgentOptions(
                    instructions: AgentInstructions,
                    tools: [new HostedFileSearchTool() { Inputs = [new HostedVectorStoreContent(vectorStoreMetadata.Value.Id)] }])),
            "CreateWithFoundryOptionsAsync" => await this._persistentAgentsClient.CreateAIAgentAsync(
                s_config.DeploymentName,
                instructions: AgentInstructions,
                tools: [new FileSearchToolDefinition()],
                toolResources: new ToolResources() { FileSearch = new([vectorStoreMetadata.Value.Id], null) }),
            "CreateWithFoundryOptionsSync" => this._persistentAgentsClient.CreateAIAgent(
                s_config.DeploymentName,
                instructions: AgentInstructions,
                tools: [new FileSearchToolDefinition()],
                toolResources: new ToolResources() { FileSearch = new([vectorStoreMetadata.Value.Id], null) }),
            _ => throw new InvalidOperationException($"Unknown create mechanism: {createMechanism}")
        };

        try
        {
            // Assert.
            // Verify that the agent can use the vector store to answer a question.
            var result = await agent.RunAsync("Can you give me the documented code for 'banana'?");
            Assert.Contains("673457", result.ToString());
        }
        finally
        {
            // Cleanup.
            await this._persistentAgentsClient.Administration.DeleteAgentAsync(agent.Id);
            await this._persistentAgentsClient.VectorStores.DeleteVectorStoreAsync(vectorStoreMetadata.Value.Id);
            await this._persistentAgentsClient.Files.DeleteFileAsync(uploadedAgentFile.Id);
            File.Delete(searchFilePath);
        }
    }

    [Theory]
    [InlineData("CreateWithChatClientAgentOptionsAsync")]
    [InlineData("CreateWithChatClientAgentOptionsSync")]
    [InlineData("CreateWithFoundryOptionsAsync")]
    [InlineData("CreateWithFoundryOptionsSync")]
    public async Task CreateAgent_CreatesAgentWithCodeInterpreterAsync(string createMechanism)
    {
        // Arrange.
        const string AgentInstructions = """
            You are a helpful coding agent. A Python file is provided. Use the Code Interpreter Tool to run the file
            and report the SECRET_NUMBER value it prints. Respond only with the number.
            """;

        // Create a python file that prints a known value.
        var codeFilePath = Path.GetTempFileName() + "secret_number.py";
        File.WriteAllText(
            path: codeFilePath,
            contents: "print(\"SECRET_NUMBER=24601\")" // Deterministic output we will look for.
        );
        PersistentAgentFileInfo uploadedCodeFile = this._persistentAgentsClient.Files.UploadFile(
            filePath: codeFilePath,
            purpose: PersistentAgentFilePurpose.Agents
        );
        CodeInterpreterToolResource toolResource = new();
        toolResource.FileIds.Add(uploadedCodeFile.Id);

        // Act.
        var agent = createMechanism switch
        {
            // Hosted tool path (tools supplied via ChatClientAgentOptions)
            "CreateWithChatClientAgentOptionsAsync" => await this._persistentAgentsClient.CreateAIAgentAsync(
                s_config.DeploymentName,
                options: new ChatClientAgentOptions(
                    instructions: AgentInstructions,
                    tools: [new HostedCodeInterpreterTool() { Inputs = [new HostedFileContent(uploadedCodeFile.Id)] }])),
            "CreateWithChatClientAgentOptionsSync" => this._persistentAgentsClient.CreateAIAgent(
                s_config.DeploymentName,
                options: new ChatClientAgentOptions(
                    instructions: AgentInstructions,
                    tools: [new HostedCodeInterpreterTool() { Inputs = [new HostedFileContent(uploadedCodeFile.Id)] }])),
            // Foundry (definitions + resources provided directly)
            "CreateWithFoundryOptionsAsync" => await this._persistentAgentsClient.CreateAIAgentAsync(
                s_config.DeploymentName,
                instructions: AgentInstructions,
                tools: [new CodeInterpreterToolDefinition()],
                toolResources: new ToolResources() { CodeInterpreter = toolResource }),
            "CreateWithFoundryOptionsSync" => this._persistentAgentsClient.CreateAIAgent(
                s_config.DeploymentName,
                instructions: AgentInstructions,
                tools: [new CodeInterpreterToolDefinition()],
                toolResources: new ToolResources() { CodeInterpreter = toolResource }),
            _ => throw new InvalidOperationException($"Unknown create mechanism: {createMechanism}")
        };

        try
        {
            // Assert.
            var result = await agent.RunAsync("What is the SECRET_NUMBER?");
            // We expect the model to run the code and surface the number.
            Assert.Contains("24601", result.ToString());
        }
        finally
        {
            // Cleanup.
            await this._persistentAgentsClient.Administration.DeleteAgentAsync(agent.Id);
            await this._persistentAgentsClient.Files.DeleteFileAsync(uploadedCodeFile.Id);
            File.Delete(codeFilePath);
        }
    }

    [Theory]
    [InlineData("CreateWithChatClientAgentOptionsAsync")]
    [InlineData("CreateWithChatClientAgentOptionsSync")]
    public async Task CreateAgent_CreatesAgentWithAIFunctionToolsAsync(string createMechanism)
    {
        // Arrange.
        const string AgentInstructions = "You are a helpful weather assistant. Always call the GetWeather function to answer questions about weather.";

        static string GetWeather(string location) => $"The weather in {location} is sunny with a high of 23C.";
        var weatherFunction = AIFunctionFactory.Create(GetWeather);

        ChatClientAgent agent = createMechanism switch
        {
            "CreateWithChatClientAgentOptionsAsync" => await this._persistentAgentsClient.CreateAIAgentAsync(
                s_config.DeploymentName,
                options: new ChatClientAgentOptions(
                    instructions: AgentInstructions,
                    tools: [weatherFunction])),
            "CreateWithChatClientAgentOptionsSync" => this._persistentAgentsClient.CreateAIAgent(
                s_config.DeploymentName,
                options: new ChatClientAgentOptions(
                    instructions: AgentInstructions,
                    tools: [weatherFunction])),
            _ => throw new InvalidOperationException($"Unknown create mechanism: {createMechanism}")
        };

        try
        {
            // Act.
            var response = await agent.RunAsync("What is the weather like in Amsterdam?");

            // Assert - ensure function was invoked and its output surfaced.
            var text = response.Text;
            Assert.Contains("Amsterdam", text, StringComparison.OrdinalIgnoreCase);
            Assert.Contains("sunny", text, StringComparison.OrdinalIgnoreCase);
            Assert.Contains("23", text, StringComparison.OrdinalIgnoreCase);
        }
        finally
        {
            await this._persistentAgentsClient.Administration.DeleteAgentAsync(agent.Id);
        }
    }
}
