// Copyright (c) Microsoft. All rights reserved.

using System;
using System.IO;
using System.Threading.Tasks;
using AgentConformance.IntegrationTests.Support;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;
using OpenAI;
using OpenAI.Assistants;
using OpenAI.Files;
using OpenAI.VectorStores;
using Shared.IntegrationTests;

namespace OpenAIAssistant.IntegrationTests;

public class OpenAIAssistantClientExtensionsTests
{
    private static readonly OpenAIConfiguration s_config = TestConfiguration.LoadSection<OpenAIConfiguration>();
    private readonly AssistantClient _assistantClient = new OpenAIClient(s_config.ApiKey).GetAssistantClient();
    private readonly OpenAIFileClient _fileClient = new OpenAIClient(s_config.ApiKey).GetOpenAIFileClient();

    [Theory]
    [InlineData("CreateWithChatClientAgentOptionsAsync")]
    [InlineData("CreateWithChatClientAgentOptionsSync")]
    [InlineData("CreateWithParamsAsync")]
    public async Task CreateAIAgentAsync_WithAIFunctionTool_InvokesFunctionAsync(string createMechanism)
    {
        // Arrange
        const string AgentInstructions = "You are a helpful weather assistant. Always call the GetWeather function to answer questions about weather.";

        static string GetWeather(string location) => $"The weather in {location} is sunny with a high of 23C.";
        var weatherFunction = AIFunctionFactory.Create(GetWeather, nameof(GetWeather));

        // Act
        var agent = createMechanism switch
        {
            "CreateWithChatClientAgentOptionsAsync" => await this._assistantClient.CreateAIAgentAsync(
                model: s_config.ChatModelId!,
                options: new ChatClientAgentOptions(
                    instructions: AgentInstructions,
                    tools: [weatherFunction])),
            "CreateWithChatClientAgentOptionsSync" => this._assistantClient.CreateAIAgent(
                model: s_config.ChatModelId!,
                options: new ChatClientAgentOptions(
                    instructions: AgentInstructions,
                    tools: [weatherFunction])),
            "CreateWithParamsAsync" => await this._assistantClient.CreateAIAgentAsync(
                model: s_config.ChatModelId!,
                instructions: AgentInstructions,
                tools: [weatherFunction]),
            _ => throw new InvalidOperationException($"Unknown create mechanism: {createMechanism}")
        };

        try
        {
            // Trigger function call.
            var response = await agent.RunAsync("What is the weather like in Amsterdam?");
            var text = response.Text;

            // Assert
            Assert.Contains("Amsterdam", text, StringComparison.OrdinalIgnoreCase);
            Assert.Contains("sunny", text, StringComparison.OrdinalIgnoreCase);
            Assert.Contains("23", text, StringComparison.OrdinalIgnoreCase);
        }
        finally
        {
            await this._assistantClient.DeleteAssistantAsync(agent.Id);
        }
    }

    [Theory]
    [InlineData("CreateWithChatClientAgentOptionsAsync")]
    [InlineData("CreateWithChatClientAgentOptionsSync")]
    [InlineData("CreateWithParamsAsync")]
    public async Task CreateAIAgentAsync_WithHostedCodeInterpreter_RunsCodeAsync(string createMechanism)
    {
        // Arrange
        const string Instructions = "Use the Code Interpreter Tool to run the uploaded python file and respond only with the secret number.";

        // Create a python file that prints a known value.
        var codeFilePath = Path.GetTempFileName() + "openai_secret_number.py";
        File.WriteAllText(
            path: codeFilePath,
            contents: "print(\"OPENAI_SECRET=13579\")" // Deterministic output we will look for.
        );

        // Upload file to OpenAI Assistants file store for use with the Code Interpreter.
        var uploadResult = await this._fileClient.UploadFileAsync(codeFilePath, FileUploadPurpose.Assistants);
        string uploadedFileId = uploadResult.Value.Id;
        var codeInterpreterTool = new HostedCodeInterpreterTool() { Inputs = [new HostedFileContent(uploadedFileId)] };

        var agent = createMechanism switch
        {
            "CreateWithChatClientAgentOptionsAsync" => await this._assistantClient.CreateAIAgentAsync(
                model: s_config.ChatModelId!,
                options: new ChatClientAgentOptions(
                    instructions: Instructions,
                    tools: [codeInterpreterTool])),
            "CreateWithChatClientAgentOptionsSync" => this._assistantClient.CreateAIAgent(
                model: s_config.ChatModelId!,
                options: new ChatClientAgentOptions(
                    instructions: Instructions,
                    tools: [codeInterpreterTool])),
            "CreateWithParamsAsync" => await this._assistantClient.CreateAIAgentAsync(
                model: s_config.ChatModelId!,
                instructions: Instructions,
                tools: [codeInterpreterTool]),
            _ => throw new InvalidOperationException($"Unknown create mechanism: {createMechanism}")
        };

        try
        {
            var response = await agent.RunAsync("What is the OPENAI_SECRET number?");
            var text = response.ToString();
            Assert.Contains("13579", text);
        }
        finally
        {
            await this._assistantClient.DeleteAssistantAsync(agent.Id);
            await this._fileClient.DeleteFileAsync(uploadedFileId);
            File.Delete(codeFilePath);
        }
    }

    [Theory(Skip = "For manual testing only")]
    [InlineData("CreateWithChatClientAgentOptionsAsync")]
    [InlineData("CreateWithChatClientAgentOptionsSync")]
    [InlineData("CreateWithParamsAsync")]
    public async Task CreateAIAgentAsync_WithHostedFileSearchTool_SearchesFilesAsync(string createMechanism)
    {
        // Arrange.
        const string Instructions = """
            You are a helpful agent that can help fetch data from files you know about.
            Use the File Search Tool to look up codes for words.
            Do not answer a question unless you can find the answer using the File Search Tool.
            """;

        // Create a local file with deterministic content and upload it.
        var searchFilePath = Path.GetTempFileName() + "wordcodelookup.txt";
        File.WriteAllText(
            path: searchFilePath,
            contents: "The word 'apple' uses the code 442345, while the word 'banana' uses the code 673457.");
        var uploadResult = await this._fileClient.UploadFileAsync(searchFilePath, FileUploadPurpose.Assistants);
        string uploadedFileId = uploadResult.Value.Id;

        // Create a vector store backing the file search (HostedFileSearchTool requires a vector store id).
        var vectorStoreClient = new OpenAIClient(s_config.ApiKey).GetVectorStoreClient();
        var vectorStoreCreate = await vectorStoreClient.CreateVectorStoreAsync(options: new VectorStoreCreationOptions()
        {
            Name = "WordCodeLookup_VectorStore",
            FileIds = { uploadedFileId }
        });
        string vectorStoreId = vectorStoreCreate.Value.Id;

        var fileSearchTool = new HostedFileSearchTool() { Inputs = [new HostedVectorStoreContent(vectorStoreId)] };

        var agent = createMechanism switch
        {
            "CreateWithChatClientAgentOptionsAsync" => await this._assistantClient.CreateAIAgentAsync(
                model: s_config.ChatModelId!,
                options: new ChatClientAgentOptions(
                    instructions: Instructions,
                    tools: [fileSearchTool])),
            "CreateWithChatClientAgentOptionsSync" => this._assistantClient.CreateAIAgent(
                model: s_config.ChatModelId!,
                options: new ChatClientAgentOptions(
                    instructions: Instructions,
                    tools: [fileSearchTool])),
            "CreateWithParamsAsync" => await this._assistantClient.CreateAIAgentAsync(
                model: s_config.ChatModelId!,
                instructions: Instructions,
                tools: [fileSearchTool]),
            _ => throw new InvalidOperationException($"Unknown create mechanism: {createMechanism}")
        };

        try
        {
            // Act - ask about banana code which must be retrieved via file search.
            var response = await agent.RunAsync("Can you give me the documented code for 'banana'?");
            var text = response.ToString();
            Assert.Contains("673457", text);
        }
        finally
        {
            await this._assistantClient.DeleteAssistantAsync(agent.Id);
            await vectorStoreClient.DeleteVectorStoreAsync(vectorStoreId);
            await this._fileClient.DeleteFileAsync(uploadedFileId);
            File.Delete(searchFilePath);
        }
    }
}
