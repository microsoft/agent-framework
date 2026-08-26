// Copyright (c) Microsoft. All rights reserved.

using System.ComponentModel;
using AGUI.Server;
using Azure.AI.OpenAI;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Hosting.AGUI.AspNetCore;
using Microsoft.Extensions.AI;
using OpenAI.Chat;
using RecipeAssistant;

WebApplicationBuilder builder = WebApplication.CreateBuilder(args);
builder.Services.ConfigureHttpJsonOptions(options =>
    options.SerializerOptions.TypeInfoResolverChain.Add(RecipeSerializerContext.Default));
builder.Services.AddAGUIServer();

// Configure to listen on port 8888
builder.WebHost.UseUrls("http://localhost:8888");

// WARNING: When adding session persistence (e.g., WithInMemorySessionStore), or running in production,
// make sure to also register an AgentIsolationKeyProvider to scope sessions by principal in multi-user
// deployments, e.g.:
// builder.Services.UseClaimsBasedAgentIsolation(new() { ClaimType = ClaimTypes.NameIdentifier });

WebApplication app = builder.Build();

string endpoint = builder.Configuration["AZURE_OPENAI_ENDPOINT"]
    ?? throw new InvalidOperationException("AZURE_OPENAI_ENDPOINT is not set.");
string deploymentName = builder.Configuration["AZURE_OPENAI_DEPLOYMENT_NAME"]
    ?? throw new InvalidOperationException("AZURE_OPENAI_DEPLOYMENT_NAME is not set.");

// The tool returns the complete recipe. The hosting layer turns each result into a STATE_SNAPSHOT
// event via AGUIStreamOptions.MapResultAsStateSnapshot("generate_recipe") - no protocol content by hand.
[Description("Generate or update the shared recipe and display it to the user.")]
static RecipeResponse GenerateRecipe(
    [Description("The complete recipe to display.")] Recipe recipe) => new() { Recipe = recipe };

AITool generateRecipe = AIFunctionFactory.Create(
    GenerateRecipe,
    name: "generate_recipe",
    description: "Generate or update the shared recipe and display it to the user.",
    RecipeSerializerContext.Default.Options);

const string SharedStateSystemPrompt =
    """
    You are a helpful recipe assistant that maintains a shared recipe state with the user.

    IMPORTANT:
    - When the user asks you to create, change, or improve a recipe, call the `generate_recipe`
      tool with a COMPLETE recipe: a title, skill_level, cooking_time, special_preferences, the
      full list of ingredients (each with an icon, name and amount) and the step-by-step
      instructions.
    - Always include every ingredient the recipe needs, keeping any the user already added.
    - When the user only asks a question about the recipe, answer in plain text and do NOT call the tool.
    """;

// Create the AI agent with the recipe tool.
// WARNING: DefaultAzureCredential is convenient for development but requires careful consideration in production.
// In production, consider using a specific credential (e.g., ManagedIdentityCredential) to avoid
// latency issues, unintended credential probing, and potential security risks from fallback mechanisms.
ChatClient chatClient = new AzureOpenAIClient(
        new Uri(endpoint),
        new DefaultAzureCredential())
    .GetChatClient(deploymentName);

AIAgent baseAgent = chatClient.AsAIAgent(new ChatClientAgentOptions
{
    Name = "RecipeAgent",
    Description = "An agent that maintains a shared recipe state with the user.",
    ChatOptions = new ChatOptions
    {
        Instructions = SharedStateSystemPrompt,
        Tools = [generateRecipe],
    },
});

// Wrap with a thin agent that injects the client's current recipe (input side of shared state).
AIAgent agent = new RecipeStateAgent(baseAgent);

// Map the AG-UI endpoint. A generate_recipe result becomes a STATE_SNAPSHOT event (output side).
app.MapAGUIServer("/", agent)
    .WithMetadata(new AGUIStreamOptions().MapResultAsStateSnapshot("generate_recipe"));

await app.RunAsync();
