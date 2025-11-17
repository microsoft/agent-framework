// Copyright (c) Microsoft. All rights reserved.

using System;
using System.IO;
using System.Threading.Tasks;
using AgentConformance.IntegrationTests.Support;
using Azure.AI.Projects;
using Azure.AI.Projects.OpenAI;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;
using OpenAI.Files;
using OpenAI.Responses;
using Shared.IntegrationTests;

namespace AzureAI.IntegrationTests;

public class AIProjectClientCreateTests
{
    private static readonly AzureAIConfiguration s_config = TestConfiguration.LoadSection<AzureAIConfiguration>();
    private readonly AIProjectClient _client = new(new Uri(s_config.Endpoint), new AzureCliCredential());

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
            "CreateWithChatClientAgentOptionsAsync" => await this._client.CreateAIAgentAsync(
                model: s_config.DeploymentName,
                options: new ChatClientAgentOptions(
                    instructions: AgentInstructions,
                    name: AgentName,
                    description: AgentDescription)),
            "CreateWithChatClientAgentOptionsSync" => this._client.CreateAIAgent(
                model: s_config.DeploymentName,
                options: new ChatClientAgentOptions(
                    instructions: AgentInstructions,
                    name: AgentName,
                    description: AgentDescription)),
            "CreateWithFoundryOptionsAsync" => await this._client.CreateAIAgentAsync(
                name: AgentName,
                creationOptions: new AgentVersionCreationOptions(new PromptAgentDefinition(s_config.DeploymentName) { Instructions = AgentInstructions }) { Description = AgentDescription }),
            "CreateWithFoundryOptionsSync" => this._client.CreateAIAgent(
                name: AgentName,
                creationOptions: new AgentVersionCreationOptions(new PromptAgentDefinition(s_config.DeploymentName) { Instructions = AgentInstructions }) { Description = AgentDescription }),
            _ => throw new InvalidOperationException($"Unknown create mechanism: {createMechanism}")
        };

        try
        {
            // Assert.
            Assert.NotNull(agent);
            Assert.Equal(AgentName, agent.Name);
            Assert.Equal(AgentDescription, agent.Description);
            Assert.Equal(AgentInstructions, agent.Instructions);

            var agentRecord = await this._client.Agents.GetAgentAsync(agent.Name);
            Assert.NotNull(agentRecord);
            Assert.Equal(AgentName, agentRecord.Value.Name);
            var definition = Assert.IsType<PromptAgentDefinition>(agentRecord.Value.Versions.Latest.Definition);
            Assert.Equal(AgentDescription, agentRecord.Value.Versions.Latest.Description);
            Assert.Equal(AgentInstructions, definition.Instructions);
        }
        finally
        {
            // Cleanup.
            await this._client.Agents.DeleteAgentAsync(agent.Name);
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
        const string AgentName = "VectorStoreAgent";
        const string AgentInstructions = """
            You are a helpful agent that can help fetch data from files you know about.
            Use the File Search Tool to look up codes for words.
            Do not answer a question unless you can find the answer using the File Search Tool.
            """;

        // Get the project OpenAI client.
        var projectOpenAIClient = this._client.GetProjectOpenAIClient();

        // Create a vector store.
        var searchFilePath = Path.GetTempFileName() + "wordcodelookup.txt";
        File.WriteAllText(
            path: searchFilePath,
            contents: "The word 'apple' uses the code 442345, while the word 'banana' uses the code 673457."
        );
        OpenAIFile uploadedAgentFile = projectOpenAIClient.GetProjectFilesClient().UploadFile(
            filePath: searchFilePath,
            purpose: FileUploadPurpose.Assistants
        );
        var vectorStoreMetadata = await projectOpenAIClient.GetProjectVectorStoresClient().CreateVectorStoreAsync(options: new() { FileIds = { uploadedAgentFile.Id }, Name = "WordCodeLookup_VectorStore" });

        // Act.
        var agent = createMechanism switch
        {
            "CreateWithChatClientAgentOptionsAsync" => await this._client.CreateAIAgentAsync(
                model: s_config.DeploymentName,
                name: AgentName,
                instructions: AgentInstructions,
                tools: [new HostedFileSearchTool() { Inputs = [new HostedVectorStoreContent(vectorStoreMetadata.Value.Id)] }]),
            "CreateWithChatClientAgentOptionsSync" => this._client.CreateAIAgent(
                model: s_config.DeploymentName,
                name: AgentName,
                instructions: AgentInstructions,
                tools: [new HostedFileSearchTool() { Inputs = [new HostedVectorStoreContent(vectorStoreMetadata.Value.Id)] }]),
            "CreateWithFoundryOptionsAsync" => await this._client.CreateAIAgentAsync(
                model: s_config.DeploymentName,
                name: AgentName,
                instructions: AgentInstructions,
                tools: [ResponseTool.CreateFileSearchTool(vectorStoreIds: [vectorStoreMetadata.Value.Id]).AsAITool()]),
            "CreateWithFoundryOptionsSync" => this._client.CreateAIAgent(
                model: s_config.DeploymentName,
                name: AgentName,
                instructions: AgentInstructions,
                tools: [ResponseTool.CreateFileSearchTool(vectorStoreIds: [vectorStoreMetadata.Value.Id]).AsAITool()]),
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
            await this._client.Agents.DeleteAgentAsync(agent.Name);
            await projectOpenAIClient.GetProjectVectorStoresClient().DeleteVectorStoreAsync(vectorStoreMetadata.Value.Id);
            await projectOpenAIClient.GetProjectFilesClient().DeleteFileAsync(uploadedAgentFile.Id);
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
        const string AgentName = "CodeInterpreterAgent";
        const string AgentInstructions = """
            You are a helpful coding agent. A Python file is provided. Use the Code Interpreter Tool to run the file
            and report the SECRET_NUMBER value it prints. Respond only with the number.
            """;

        // Get the project OpenAI client.
        var projectOpenAIClient = this._client.GetProjectOpenAIClient();

        // Create a python file that prints a known value.
        var codeFilePath = Path.GetTempFileName() + "secret_number.py";
        File.WriteAllText(
            path: codeFilePath,
            contents: "print(\"SECRET_NUMBER=24601\")" // Deterministic output we will look for.
        );
        OpenAIFile uploadedCodeFile = projectOpenAIClient.GetProjectFilesClient().UploadFile(
            filePath: codeFilePath,
            purpose: FileUploadPurpose.Assistants
        );

        // Act.
        var agent = createMechanism switch
        {
            // Hosted tool path (tools supplied via ChatClientAgentOptions)
            "CreateWithChatClientAgentOptionsAsync" => await this._client.CreateAIAgentAsync(
                model: s_config.DeploymentName,
                name: AgentName,
                instructions: AgentInstructions,
                tools: [new HostedCodeInterpreterTool() { Inputs = [new HostedFileContent(uploadedCodeFile.Id)] }]),
            "CreateWithChatClientAgentOptionsSync" => this._client.CreateAIAgent(
                model: s_config.DeploymentName,
                name: AgentName,
                instructions: AgentInstructions,
                tools: [new HostedCodeInterpreterTool() { Inputs = [new HostedFileContent(uploadedCodeFile.Id)] }]),
            // Foundry (definitions + resources provided directly)
            "CreateWithFoundryOptionsAsync" => await this._client.CreateAIAgentAsync(
                model: s_config.DeploymentName,
                name: AgentName,
                instructions: AgentInstructions,
                tools: [ResponseTool.CreateCodeInterpreterTool(new CodeInterpreterToolContainer(CodeInterpreterToolContainerConfiguration.CreateAutomaticContainerConfiguration([uploadedCodeFile.Id]))).AsAITool()]),
            "CreateWithFoundryOptionsSync" => this._client.CreateAIAgent(
                model: s_config.DeploymentName,
                name: AgentName,
                instructions: AgentInstructions,
                tools: [ResponseTool.CreateCodeInterpreterTool(new CodeInterpreterToolContainer(CodeInterpreterToolContainerConfiguration.CreateAutomaticContainerConfiguration([uploadedCodeFile.Id]))).AsAITool()]),
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
            await this._client.Agents.DeleteAgentAsync(agent.Name);
            await projectOpenAIClient.GetProjectFilesClient().DeleteFileAsync(uploadedCodeFile.Id);
            File.Delete(codeFilePath);
        }
    }

    [Theory]
    [InlineData("CreateWithChatClientAgentOptionsAsync")]
    [InlineData("CreateWithChatClientAgentOptionsSync")]
    public async Task CreateAgent_CreatesAgentWithAIFunctionToolsAsync(string createMechanism)
    {
        // Arrange.
        const string AgentName = "WeatherAgent";
        const string AgentInstructions = "You are a helpful weather assistant. Always call the GetWeather function to answer questions about weather.";

        static string GetWeather(string location) => $"The weather in {location} is sunny with a high of 23C.";
        var weatherFunction = AIFunctionFactory.Create(GetWeather);

        ChatClientAgent agent = createMechanism switch
        {
            "CreateWithChatClientAgentOptionsAsync" => await this._client.CreateAIAgentAsync(
                model: s_config.DeploymentName,
                options: new ChatClientAgentOptions(
                    name: AgentName,
                    instructions: AgentInstructions,
                    tools: [weatherFunction])),
            "CreateWithChatClientAgentOptionsSync" => this._client.CreateAIAgent(
                s_config.DeploymentName,
                options: new ChatClientAgentOptions(
                    name: AgentName,
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
            await this._client.Agents.DeleteAgentAsync(agent.Name);
        }
    }
}
