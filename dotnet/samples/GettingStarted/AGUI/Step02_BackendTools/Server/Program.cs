// Copyright (c) Microsoft. All rights reserved.

using System.ComponentModel;
using System.Text.Json.Serialization;
using Azure.AI.OpenAI;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Hosting.AGUI.AspNetCore;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.Options;
using OpenAI.Chat;

WebApplicationBuilder builder = WebApplication.CreateBuilder(args);
builder.Services.AddHttpClient().AddLogging();
builder.Services.ConfigureHttpJsonOptions(options =>
    options.SerializerOptions.TypeInfoResolverChain.Add(SampleJsonSerializerContext.Default));
builder.Services.AddAGUI();

WebApplication app = builder.Build();

string endpoint = builder.Configuration["AZURE_OPENAI_ENDPOINT"]
    ?? throw new InvalidOperationException("AZURE_OPENAI_ENDPOINT is not set.");
string deploymentName = builder.Configuration["AZURE_OPENAI_DEPLOYMENT_NAME"]
    ?? throw new InvalidOperationException("AZURE_OPENAI_DEPLOYMENT_NAME is not set.");

// Define the function tool
[Description("Search for restaurants in a location.")]
static RestaurantSearchResponse SearchRestaurants(
    [Description("The restaurant search request")] RestaurantSearchRequest request)
{
    // Simulated restaurant data
    string cuisine = request.Cuisine == "any" ? "Italian" : request.Cuisine;

    return new RestaurantSearchResponse
    {
        Location = request.Location,
        Cuisine = request.Cuisine,
        Results =
        [
            new RestaurantInfo
            {
                Name = "The Golden Fork",
                Cuisine = cuisine,
                Rating = 4.5,
                Address = $"123 Main St, {request.Location}"
            },
            new RestaurantInfo
            {
                Name = "Spice Haven",
                Cuisine = cuisine == "Italian" ? "Indian" : cuisine,
                Rating = 4.7,
                Address = $"456 Oak Ave, {request.Location}"
            },
            new RestaurantInfo
            {
                Name = "Green Leaf",
                Cuisine = "Vegetarian",
                Rating = 4.3,
                Address = $"789 Elm Rd, {request.Location}"
            }
        ]
    };
}

// Get JsonSerializerOptions from the configured HTTP JSON options
Microsoft.AspNetCore.Http.Json.JsonOptions jsonOptions = app.Services.GetRequiredService<IOptions<Microsoft.AspNetCore.Http.Json.JsonOptions>>().Value;

// Create tool with serializer options
AITool[] tools =
[
    AIFunctionFactory.Create(
        SearchRestaurants,
        serializerOptions: jsonOptions.SerializerOptions)
];

// Create the AI agent with tools
ChatClient chatClient = new AzureOpenAIClient(
        new Uri(endpoint),
        new DefaultAzureCredential())
    .GetChatClient(deploymentName);

ChatClientAgent agent = chatClient.AsIChatClient().CreateAIAgent(
    name: "AGUIAssistant",
    instructions: "You are a helpful assistant with access to restaurant information.",
    tools: tools);

// Map the AG-UI agent endpoint
app.MapAGUI("/", agent);

await app.RunAsync();

// Define request/response types for the tool
internal sealed class RestaurantSearchRequest
{
    public string Location { get; set; } = string.Empty;
    public string Cuisine { get; set; } = "any";
}

internal sealed class RestaurantSearchResponse
{
    public string Location { get; set; } = string.Empty;
    public string Cuisine { get; set; } = string.Empty;
    public RestaurantInfo[] Results { get; set; } = [];
}

internal sealed class RestaurantInfo
{
    public string Name { get; set; } = string.Empty;
    public string Cuisine { get; set; } = string.Empty;
    public double Rating { get; set; }
    public string Address { get; set; } = string.Empty;
}

// JSON serialization context for source generation
[JsonSerializable(typeof(RestaurantSearchRequest))]
[JsonSerializable(typeof(RestaurantSearchResponse))]
internal sealed partial class SampleJsonSerializerContext : JsonSerializerContext;
