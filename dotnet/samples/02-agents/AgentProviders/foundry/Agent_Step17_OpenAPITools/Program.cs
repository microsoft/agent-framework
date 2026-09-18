// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to use OpenAPI Tools with AI Agents.

using Azure.AI.Projects;
using Azure.AI.Projects.Agents;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Foundry;
using Microsoft.Extensions.AI;

string endpoint = Environment.GetEnvironmentVariable("FOUNDRY_PROJECT_ENDPOINT") ?? throw new InvalidOperationException("FOUNDRY_PROJECT_ENDPOINT is not set.");
string deploymentName = Environment.GetEnvironmentVariable("FOUNDRY_MODEL") ?? "gpt-5.4-mini";

const string AgentInstructions = "You are a helpful assistant that can retrieve the latest currency exchange rates using the Frankfurter API. Always call the API to get live data rather than guessing.";
// WARNING: DefaultAzureCredential is convenient for development but requires careful consideration in production.
// In production, consider using a specific credential (e.g., ManagedIdentityCredential) to avoid
// latency issues, unintended credential probing, and potential security risks from fallback mechanisms.
AIProjectClient aiProjectClient = new(new Uri(endpoint), new DefaultAzureCredential());

AITool openApiTool = FoundryAITool.CreateOpenApiTool(CreateOpenAPIFunctionDefinition());

AIAgent agent = aiProjectClient.AsAIAgent(deploymentName,
    instructions: AgentInstructions,
    name: "OpenAPIToolsAgent",
    tools: [openApiTool]);

// Run the agent with a question about EUR exchange rates
Console.WriteLine(await agent.RunAsync("What is the latest EUR exchange rate against the US Dollar (USD) and British Pound (GBP)?"));

OpenApiFunctionDefinition CreateOpenAPIFunctionDefinition()
{
    // OpenAPI spec for Frankfurter — a free, no-auth exchange rate API backed by ECB data.
    // See https://www.frankfurter.dev/ for documentation.
    const string FrankfurterOpenApiSpec = """
{
  "openapi": "3.1.0",
  "info": {
    "title": "Frankfurter Exchange Rate API",
    "description": "Free currency exchange rates from the European Central Bank",
    "version": "v1"
  },
  "servers": [
    {
      "url": "https://api.frankfurter.dev/v1"
    }
  ],
  "paths": {
    "/latest": {
      "get": {
        "description": "Get the latest exchange rates for a given base currency",
        "operationId": "GetLatestExchangeRates",
        "parameters": [
          {
            "name": "from",
            "in": "query",
            "description": "Base currency code (e.g. EUR, USD, GBP). Defaults to EUR.",
            "required": false,
            "schema": {
              "type": "string"
            }
          },
          {
            "name": "to",
            "in": "query",
            "description": "Comma-separated list of target currency codes (e.g. USD,GBP,JPY).",
            "required": false,
            "schema": {
              "type": "string"
            }
          }
        ],
        "responses": {
          "200": {
            "description": "Latest exchange rates",
            "content": {
              "application/json": {
                "schema": {
                  "type": "object"
                }
              }
            }
          }
        }
      }
    }
  }
}
""";

    return new(
        "get_exchange_rates",
        BinaryData.FromString(FrankfurterOpenApiSpec),
        new OpenAPIAnonymousAuthenticationDetails())
    {
        Description = "Get live currency exchange rates from the European Central Bank via Frankfurter"
    };
}
