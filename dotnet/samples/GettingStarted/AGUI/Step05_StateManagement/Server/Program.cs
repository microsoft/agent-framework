// Copyright (c) Microsoft. All rights reserved.

using Azure.AI.OpenAI;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Hosting.AGUI.AspNetCore;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.Options;
using OpenAI.Chat;
using RecipeAssistant;

WebApplicationBuilder builder = WebApplication.CreateBuilder(args);
builder.Services.AddHttpClient().AddLogging();
builder.Services.ConfigureHttpJsonOptions(options =>
    options.SerializerOptions.TypeInfoResolverChain.Add(RecipeSerializerContext.Default));
builder.Services.AddAGUI();

// Configure to listen on port 8888
builder.WebHost.UseUrls("http://localhost:8888");

WebApplication app = builder.Build();

string endpoint = builder.Configuration["AZURE_OPENAI_ENDPOINT"]
    ?? throw new InvalidOperationException("AZURE_OPENAI_ENDPOINT is not set.");
string deploymentName = builder.Configuration["AZURE_OPENAI_DEPLOYMENT_NAME"]
    ?? throw new InvalidOperationException("AZURE_OPENAI_DEPLOYMENT_NAME is not set.");

// Get JsonSerializerOptions
var jsonOptions = app.Services.GetRequiredService<IOptions<Microsoft.AspNetCore.Http.Json.JsonOptions>>().Value;

// Create base agent
ChatClient chatClient = new AzureOpenAIClient(
        new Uri(endpoint),
        new DefaultAzureCredential())
    .GetChatClient(deploymentName);

AIAgent baseAgent = chatClient.AsIChatClient().CreateAIAgent(
    name: "RecipeAgent",
    instructions: """
        You are a helpful recipe assistant. When users ask you to create or suggest a recipe,
        respond with a complete AgentState JSON object that includes:
        - recipe.title: The recipe name
        - recipe.cuisine: Type of cuisine (e.g., Italian, Mexican, Japanese)
        - recipe.ingredients: Array of ingredient strings with quantities
        - recipe.steps: Array of cooking instruction strings
        - recipe.prep_time_minutes: Preparation time in minutes
        - recipe.cook_time_minutes: Cooking time in minutes
        - recipe.skill_level: One of "beginner", "intermediate", or "advanced"

        Always include all fields in the response. Be creative and helpful.
        """);

// Wrap with state management middleware
AIAgent agent = new SharedStateAgent(baseAgent, jsonOptions.SerializerOptions);

// Map the AG-UI agent endpoint
app.MapAGUI("/", agent);

await app.RunAsync();
