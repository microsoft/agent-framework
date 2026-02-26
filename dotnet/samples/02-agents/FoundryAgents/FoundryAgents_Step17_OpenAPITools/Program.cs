// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to use OpenAPI Tools with AI Agents.

using Azure.AI.Projects;
using Azure.AI.Projects.OpenAI;
using Azure.Identity;
using Microsoft.Agents.AI;
using OpenAI.Responses;

// Warning: DefaultAzureCredential is intended for simplicity in development. For production scenarios, consider using a more specific credential.
string endpoint = Environment.GetEnvironmentVariable("AZURE_AI_PROJECT_ENDPOINT") ?? throw new InvalidOperationException("AZURE_AI_PROJECT_ENDPOINT is not set.");
string deploymentName = Environment.GetEnvironmentVariable("AZURE_AI_MODEL_DEPLOYMENT_NAME") ?? "gpt-4o-mini";

const string AgentInstructions = "You are a helpful assistant that can use the countries API to retrieve information about countries by their currency code.";

// A simple OpenAPI specification for the REST Countries API
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

// Get a client to create/retrieve/delete server side agents with Azure Foundry Agents.
AIProjectClient aiProjectClient = new(new Uri(endpoint), new DefaultAzureCredential());

// Create the OpenAPI function definition
var openApiFunction = new OpenAPIFunctionDefinition(
    "get_countries",
    BinaryData.FromString(CountriesOpenApiSpec),
    new OpenAPIAnonymousAuthenticationDetails())
{
    Description = "Retrieve information about countries by currency code"
};

AIAgent agent = await CreateAgentWithMEAI();
// AIAgent agent = await CreateAgentWithNativeSDK();

// Run the agent with a question about countries
Console.WriteLine(await agent.RunAsync("What countries use the Euro (EUR) as their currency? Please list them."));

// Cleanup by deleting the agent
await aiProjectClient.Agents.DeleteAgentAsync(agent.Name);

// --- Agent Creation Options ---

// Option 1 - Using AsAITool wrapping for OpenApiTool (MEAI + AgentFramework)
async Task<AIAgent> CreateAgentWithMEAI()
{
    return await aiProjectClient.CreateAIAgentAsync(
        model: deploymentName,
        name: "OpenAPIToolsAgent-MEAI",
        instructions: AgentInstructions,
        tools: [((ResponseTool)AgentTool.CreateOpenApiTool(openApiFunction)).AsAITool()]);
}

// Option 2 - Using PromptAgentDefinition with AgentTool.CreateOpenApiTool (Native SDK)
async Task<AIAgent> CreateAgentWithNativeSDK()
{
    return await aiProjectClient.CreateAIAgentAsync(
        name: "OpenAPIToolsAgent-NATIVE",
        creationOptions: new AgentVersionCreationOptions(
            new PromptAgentDefinition(model: deploymentName)
            {
                Instructions = AgentInstructions,
                Tools = { (ResponseTool)AgentTool.CreateOpenApiTool(openApiFunction) }
            })
    );
}
