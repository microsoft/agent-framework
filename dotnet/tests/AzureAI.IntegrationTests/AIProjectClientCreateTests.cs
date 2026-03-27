// Copyright (c) Microsoft. All rights reserved.

using System;
using System.IO;
using System.Threading.Tasks;
using AgentConformance.IntegrationTests.Support;
using Azure.AI.Projects;
using Azure.AI.Projects.Agents;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;
using OpenAI.Files;
using OpenAI.Responses;
using Shared.IntegrationTests;

namespace AzureAI.IntegrationTests;

public class AIProjectClientCreateTests
{
    private readonly AIProjectClient _client = new(new Uri(TestConfiguration.GetRequiredValue(TestSettings.AzureAIProjectEndpoint)), TestAzureCliCredentials.CreateAzureCliCredential());

    [Theory]
    [InlineData("CreateWithChatClientAgentOptionsAsync")]
    [InlineData("CreateWithFoundryOptionsAsync")]
    public async Task CreateAgent_CreatesAgentWithCorrectMetadataAsync(string createMechanism)
    {
        // Arrange.
        string AgentName = AIProjectClientFixture.GenerateUniqueAgentName("IntegrationTestAgent");
        const string AgentDescription = "An agent created during integration tests";
        const string AgentInstructions = "You are an integration test agent";

        // Act.
        var agent = createMechanism switch
        {
            "CreateWithChatClientAgentOptionsAsync" => await this._client.CreateAIAgentAsync(
                model: TestConfiguration.GetRequiredValue(TestSettings.AzureAIModelDeploymentName),
                options: new ChatClientAgentOptions()
                {
                    Name = AgentName,
                    Description = AgentDescription,
                    ChatOptions = new() { Instructions = AgentInstructions }
                }),
            "CreateWithFoundryOptionsAsync" => await this._client.CreateAIAgentAsync(
                name: AgentName,
                creationOptions: new AgentVersionCreationOptions(new PromptAgentDefinition(TestConfiguration.GetRequiredValue(TestSettings.AzureAIModelDeploymentName)) { Instructions = AgentInstructions }) { Description = AgentDescription }),
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
            var definition = Assert.IsType<PromptAgentDefinition>(agentRecord.Value.GetLatestVersion().Definition);
            Assert.Equal(AgentDescription, agentRecord.Value.GetLatestVersion().Description);
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
    [InlineData("CreateWithFoundryOptionsAsync")]
    public async Task CreateAgent_CreatesAgentWithVectorStoresAsync(string createMechanism)
    {
        // Arrange.
        string AgentName = AIProjectClientFixture.GenerateUniqueAgentName("VectorStoreAgent");
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
                model: TestConfiguration.GetRequiredValue(TestSettings.AzureAIModelDeploymentName),
                name: AgentName,
                instructions: AgentInstructions,
                tools: [new HostedFileSearchTool() { Inputs = [new HostedVectorStoreContent(vectorStoreMetadata.Value.Id)] }]),
            "CreateWithFoundryOptionsAsync" => await this._client.CreateAIAgentAsync(
                model: TestConfiguration.GetRequiredValue(TestSettings.AzureAIModelDeploymentName),
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
    [InlineData("CreateWithFoundryOptionsAsync")]
    public async Task CreateAgent_CreatesAgentWithCodeInterpreterAsync(string createMechanism)
    {
        // Arrange.
        string AgentName = AIProjectClientFixture.GenerateUniqueAgentName("CodeInterpreterAgent");
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
                model: TestConfiguration.GetRequiredValue(TestSettings.AzureAIModelDeploymentName),
                name: AgentName,
                instructions: AgentInstructions,
                tools: [new HostedCodeInterpreterTool() { Inputs = [new HostedFileContent(uploadedCodeFile.Id)] }]),
            // Foundry (definitions + resources provided directly)
            "CreateWithFoundryOptionsAsync" => await this._client.CreateAIAgentAsync(
                model: TestConfiguration.GetRequiredValue(TestSettings.AzureAIModelDeploymentName),
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

    /// <summary>
    /// Validates that an agent version created with an OpenAPI tool definition via the native
    /// Azure.AI.Projects SDK and then wrapped with <c>AsAIAgent(agentVersion)</c> correctly
    /// invokes the server-side OpenAPI function through <c>RunAsync</c>.
    /// Regression test for https://github.com/microsoft/agent-framework/issues/4883.
    /// </summary>
    [RetryFact(Constants.RetryCount, Constants.RetryDelay, Skip = "For manual testing only")]
    public async Task AsAIAgent_WithOpenAPITool_NativeSDKCreation_InvokesServerSideToolAsync()
    {
        // Arrange — create agent version with OpenAPI tool using native Azure.AI.Projects SDK types.
        string AgentName = AIProjectClientFixture.GenerateUniqueAgentName("OpenAPITestAgent");
        const string AgentInstructions = "You are a helpful assistant that can use the countries API to retrieve information about countries by their currency code.";

        const string CountriesOpenApiSpec = """
        {
          "openapi": "3.1.0",
          "info": {
            "title": "REST Countries API",
            "description": "Retrieve information about countries by currency code",
            "version": "v3.1"
          },
          "servers": [
            {
              "url": "https://restcountries.com/v3.1"
            }
          ],
          "paths": {
            "/currency/{currency}": {
              "get": {
                "description": "Get countries that use a specific currency code (e.g., USD, EUR, GBP)",
                "operationId": "GetCountriesByCurrency",
                "parameters": [
                  {
                    "name": "currency",
                    "in": "path",
                    "description": "Currency code (e.g., USD, EUR, GBP)",
                    "required": true,
                    "schema": {
                      "type": "string"
                    }
                  }
                ],
                "responses": {
                  "200": {
                    "description": "Successful response with list of countries",
                    "content": {
                      "application/json": {
                        "schema": {
                          "type": "array",
                          "items": {
                            "type": "object"
                          }
                        }
                      }
                    }
                  },
                  "404": {
                    "description": "No countries found for the currency"
                  }
                }
              }
            }
          }
        }
        """;

        // Step 1: Create the OpenAPI function definition and agent version using native SDK types.
        var openApiFunction = new OpenApiFunctionDefinition(
            "get_countries",
            BinaryData.FromString(CountriesOpenApiSpec),
            new OpenAPIAnonymousAuthenticationDetails())
        {
            Description = "Retrieve information about countries by currency code"
        };

        var definition = new PromptAgentDefinition(model: TestConfiguration.GetRequiredValue(TestSettings.AzureAIModelDeploymentName))
        {
            Instructions = AgentInstructions,
            Tools = { (ResponseTool)AgentTool.CreateOpenApiTool(openApiFunction) }
        };

        AgentVersionCreationOptions creationOptions = new(definition);
        AgentVersion agentVersion = await this._client.Agents.CreateAgentVersionAsync(AgentName, creationOptions);

        try
        {
            // Step 2: Wrap the agent version using AsAIAgent extension.
            ChatClientAgent agent = this._client.AsAIAgent(agentVersion);

            // Assert the agent was created correctly and retains version metadata.
            Assert.NotNull(agent);
            Assert.Equal(AgentName, agent.Name);
            var retrievedVersion = agent.GetService<AgentVersion>();
            Assert.NotNull(retrievedVersion);

            // Step 3: Call RunAsync to trigger the server-side OpenAPI function.
            var result = await agent.RunAsync("What countries use the Euro (EUR) as their currency? Please list them.");

            // Step 4: Validate the OpenAPI tool was invoked server-side.
            // Note: Server-side OpenAPI tools (executed within the Responses API via AgentReference)
            // do not surface as FunctionCallContent in the MEAI abstraction — the API handles the full
            // tool loop internally. We validate tool invocation by asserting the response contains
            // multiple specific country names that the model would need API data to enumerate accurately.
            var text = result.ToString();
            Assert.NotEmpty(text);

            // The response must mention multiple well-known Eurozone countries — requiring several
            // correct entries makes it highly unlikely the model answered purely from parametric knowledge.
            int matchCount = 0;
            foreach (var country in new[] { "Germany", "France", "Italy", "Spain", "Portugal", "Netherlands", "Belgium", "Austria", "Ireland", "Finland" })
            {
                if (text.Contains(country, StringComparison.OrdinalIgnoreCase))
                {
                    matchCount++;
                }
            }

            Assert.True(
                matchCount >= 3,
                $"Expected response to list at least 3 Eurozone countries from the OpenAPI tool, but found {matchCount}. Response: {text}");
        }
        finally
        {
            // Cleanup.
            await this._client.Agents.DeleteAgentAsync(AgentName);
        }
    }

    [Theory]
    [InlineData("CreateWithChatClientAgentOptionsAsync")]
    public async Task CreateAgent_CreatesAgentWithAIFunctionToolsAsync(string createMechanism)
    {
        // Arrange.
        string AgentName = AIProjectClientFixture.GenerateUniqueAgentName("WeatherAgent");
        const string AgentInstructions = "You are a helpful weather assistant. Always call the GetWeather function to answer questions about weather.";

        static string GetWeather(string location) => $"The weather in {location} is sunny with a high of 23C.";
        var weatherFunction = AIFunctionFactory.Create(GetWeather);

        ChatClientAgent agent = createMechanism switch
        {
            "CreateWithChatClientAgentOptionsAsync" => await this._client.CreateAIAgentAsync(
                model: TestConfiguration.GetRequiredValue(TestSettings.AzureAIModelDeploymentName),
                options: new ChatClientAgentOptions()
                {
                    Name = AgentName,
                    ChatOptions = new() { Instructions = AgentInstructions, Tools = [weatherFunction] }
                }),
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
