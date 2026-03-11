// Copyright (c) Microsoft. All rights reserved.

using System;
using System.IO;
using System.Threading.Tasks;
using AgentConformance.IntegrationTests.Support;
using Azure.AI.Projects;
using Azure.AI.Projects.OpenAI;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.AzureAI;
using Microsoft.Extensions.AI;
using OpenAI.Files;
using OpenAI.Responses;
using Shared.IntegrationTests;

namespace AzureAI.IntegrationTests;

/// <summary>
/// Integration tests for agent creation via <see cref="FoundryVersionedAgent"/> factory methods.
/// </summary>
public class FoundryVersionedAgentCreateTests
{
    private static Uri Endpoint => new(TestConfiguration.GetRequiredValue(TestSettings.AzureAIProjectEndpoint));

    private static DefaultAzureCredential Credential => new();

    private static string Model => TestConfiguration.GetRequiredValue(TestSettings.AzureAIModelDeploymentName);

    [Theory]
    [InlineData("CreateWithSimpleParamsAsync")]
    [InlineData("CreateWithChatClientAgentOptionsAsync")]
    [InlineData("CreateWithFoundryOptionsAsync")]
    public async Task CreateAgent_CreatesAgentWithCorrectMetadataAsync(string createMechanism)
    {
        // Arrange
        string agentName = FoundryVersionedAgentFixture.GenerateUniqueAgentName("IntegrationTestAgent");
        const string AgentDescription = "An agent created during integration tests";
        const string AgentInstructions = "You are an integration test agent";

        // Act
        FoundryVersionedAgent agent = createMechanism switch
        {
            "CreateWithSimpleParamsAsync" => await FoundryVersionedAgent.CreateAIAgentAsync(
                Endpoint, Credential,
                name: agentName,
                model: Model,
                instructions: AgentInstructions,
                description: AgentDescription),
            "CreateWithChatClientAgentOptionsAsync" => await FoundryVersionedAgent.CreateAIAgentAsync(
                Endpoint, Credential,
                model: Model,
                options: new ChatClientAgentOptions()
                {
                    Name = agentName,
                    Description = AgentDescription,
                    ChatOptions = new() { Instructions = AgentInstructions }
                }),
            "CreateWithFoundryOptionsAsync" => await FoundryVersionedAgent.CreateAIAgentAsync(
                Endpoint, Credential,
                name: agentName,
                creationOptions: new AgentVersionCreationOptions(new PromptAgentDefinition(Model) { Instructions = AgentInstructions }) { Description = AgentDescription }),
            _ => throw new InvalidOperationException($"Unknown create mechanism: {createMechanism}")
        };

        try
        {
            // Assert
            Assert.NotNull(agent);
            Assert.Equal(agentName, agent.Name);
            Assert.Equal(AgentDescription, agent.Description);

            AIProjectClient client = agent.GetService<AIProjectClient>()!;
            AgentRecord agentRecord = (await client.Agents.GetAgentAsync(agent.Name)).Value;
            Assert.NotNull(agentRecord);
            Assert.Equal(agentName, agentRecord.Name);
            PromptAgentDefinition definition = Assert.IsType<PromptAgentDefinition>(agentRecord.Versions.Latest.Definition);
            Assert.Equal(AgentDescription, agentRecord.Versions.Latest.Description);
            Assert.Equal(AgentInstructions, definition.Instructions);
        }
        finally
        {
            // Cleanup
            await FoundryVersionedAgent.DeleteAIAgentAsync(agent);
        }
    }

    [Theory]
    [InlineData("CreateWithSimpleParamsAsync")]
    [InlineData("CreateWithChatClientAgentOptionsAsync")]
    public async Task CreateAgent_CreatesAgentWithCodeInterpreterAsync(string createMechanism)
    {
        // Arrange
        string agentName = FoundryVersionedAgentFixture.GenerateUniqueAgentName("CodeInterpreterAgent");
        const string AgentInstructions = """
            You are a helpful coding agent. A Python file is provided. Use the Code Interpreter Tool to run the file
            and report the SECRET_NUMBER value it prints. Respond only with the number.
            """;

        AIProjectClient projectClient = new(Endpoint, Credential);
        var projectOpenAIClient = projectClient.GetProjectOpenAIClient();

        string codeFilePath = Path.GetTempFileName() + "secret_number.py";
        File.WriteAllText(
            path: codeFilePath,
            contents: "print(\"SECRET_NUMBER=24601\")");
        OpenAIFile uploadedCodeFile = projectOpenAIClient.GetProjectFilesClient().UploadFile(
            filePath: codeFilePath,
            purpose: FileUploadPurpose.Assistants);

        // Act
        FoundryVersionedAgent agent = createMechanism switch
        {
            "CreateWithSimpleParamsAsync" => await FoundryVersionedAgent.CreateAIAgentAsync(
                Endpoint, Credential,
                name: agentName,
                model: Model,
                instructions: AgentInstructions,
                tools: [FoundryAITool.CreateCodeInterpreterTool(new CodeInterpreterToolContainer(CodeInterpreterToolContainerConfiguration.CreateAutomaticContainerConfiguration([uploadedCodeFile.Id])))]),
            "CreateWithChatClientAgentOptionsAsync" => await FoundryVersionedAgent.CreateAIAgentAsync(
                Endpoint, Credential,
                name: agentName,
                model: Model,
                instructions: AgentInstructions,
                tools: [new HostedCodeInterpreterTool() { Inputs = [new HostedFileContent(uploadedCodeFile.Id)] }]),
            _ => throw new InvalidOperationException($"Unknown create mechanism: {createMechanism}")
        };

        try
        {
            // Assert
            AgentResponse result = await agent.RunAsync("What is the SECRET_NUMBER?");
            Assert.Contains("24601", result.ToString());
        }
        finally
        {
            // Cleanup
            await FoundryVersionedAgent.DeleteAIAgentAsync(agent);
            await projectOpenAIClient.GetProjectFilesClient().DeleteFileAsync(uploadedCodeFile.Id);
            File.Delete(codeFilePath);
        }
    }

    [Fact]
    public async Task CreateAgent_CreatesAgentWithAIFunctionToolsAsync()
    {
        // Arrange
        string agentName = FoundryVersionedAgentFixture.GenerateUniqueAgentName("WeatherAgent");
        const string AgentInstructions = "You are a helpful weather assistant. Always call the GetWeather function to answer questions about weather.";

        static string GetWeather(string location) => $"The weather in {location} is sunny with a high of 23C.";
        AIFunction weatherFunction = AIFunctionFactory.Create(GetWeather);

        FoundryVersionedAgent agent = await FoundryVersionedAgent.CreateAIAgentAsync(
            Endpoint, Credential,
            model: Model,
            options: new ChatClientAgentOptions()
            {
                Name = agentName,
                ChatOptions = new() { Instructions = AgentInstructions, Tools = [weatherFunction] }
            });

        try
        {
            // Act
            AgentResponse response = await agent.RunAsync("What is the weather like in Amsterdam?");

            // Assert
            string text = response.Text;
            Assert.Contains("Amsterdam", text, StringComparison.OrdinalIgnoreCase);
            Assert.Contains("sunny", text, StringComparison.OrdinalIgnoreCase);
            Assert.Contains("23", text, StringComparison.OrdinalIgnoreCase);
        }
        finally
        {
            await FoundryVersionedAgent.DeleteAIAgentAsync(agent);
        }
    }
}
