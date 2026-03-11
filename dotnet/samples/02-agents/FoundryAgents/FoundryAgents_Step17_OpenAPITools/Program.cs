// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to use OpenAPI Tools with a FoundryAgentClient.

using Azure.AI.Projects.OpenAI;
using Azure.Identity;
using Microsoft.Agents.AI.AzureAI;

const string AgentInstructions = "You are a helpful assistant that can use the countries API to retrieve information about countries by their currency code.";

string endpoint = Environment.GetEnvironmentVariable("AZURE_AI_PROJECT_ENDPOINT") ?? throw new InvalidOperationException("AZURE_AI_PROJECT_ENDPOINT is not set.");
string deploymentName = Environment.GetEnvironmentVariable("AZURE_AI_MODEL_DEPLOYMENT_NAME") ?? "gpt-4o-mini";

// Create a FoundryAgent with OpenAPI tool.
FoundryAgent agent = new(
    new Uri(endpoint),
    new DefaultAzureCredential(),
    deploymentName,
    instructions: AgentInstructions,
    name: "OpenAPIToolsAgent-RAPI",
    tools: [FoundryAITool.CreateOpenApiTool(CreateOpenAPIFunctionDefinition())]);

// Run the agent with a question about countries
Console.WriteLine(await agent.RunAsync("What countries use the Euro (EUR) as their currency? Please list them."));

OpenAPIFunctionDefinition CreateOpenAPIFunctionDefinition()
{
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

    return new OpenAPIFunctionDefinition(
        "get_countries",
        BinaryData.FromString(CountriesOpenApiSpec),
        new OpenAPIAnonymousAuthenticationDetails())
    {
        Description = "Retrieve information about countries by currency code"
    };
}
