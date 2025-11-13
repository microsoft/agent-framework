// Copyright (c) Microsoft. All rights reserved.

using System.ComponentModel;
using AGUIDojoClient.Components;
using AGUIDojoClient.Components.Shared;
using AGUIDojoClient.Services;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.AGUI;
using Microsoft.Extensions.AI;

WebApplicationBuilder builder = WebApplication.CreateBuilder(args);

// Add services to the container.
builder.Services.AddRazorComponents()
    .AddInteractiveServerComponents();

string serverUrl = builder.Configuration["SERVER_URL"] ?? "http://localhost:5018";

builder.Services.AddHttpClient("aguiserver", httpClient => httpClient.BaseAddress = new Uri(serverUrl));

// Register the DemoService for managing demo scenarios
builder.Services.AddSingleton<DemoService>();

// Register the BackgroundColorService for frontend tool support
builder.Services.AddSingleton<IBackgroundColorService, BackgroundColorService>();

// Register IChatClient for components like ChatSuggestions
builder.Services.AddChatClient(sp =>
{
    HttpClient httpClient = sp.GetRequiredService<IHttpClientFactory>().CreateClient("aguiserver");
    return new AGUIChatClient(httpClient, "agentic_chat");
});

// Register a keyed AIAgent using AGUIChatClient with frontend tools
builder.Services.AddKeyedSingleton<AIAgent>("agentic-chat", (sp, key) =>
{
    HttpClient httpClient = sp.GetRequiredService<IHttpClientFactory>().CreateClient("aguiserver");
    AGUIChatClient aguiChatClient = new AGUIChatClient(httpClient, "agentic_chat");

    // Get the background color service for the frontend tool
    IBackgroundColorService backgroundService = sp.GetRequiredService<IBackgroundColorService>();

    // Define the frontend tool that changes the background color
    [Description("Change the background color of the chat interface.")]
    string ChangeBackground([Description("The color to change the background to. Can be a color name (e.g., 'blue'), hex value (e.g., '#FF5733'), or RGB value (e.g., 'rgb(255,87,51)').")] string color)
    {
        backgroundService.SetColor(color);
        return $"Background color changed to {color}";
    }

    // Create frontend tools array
    AITool[] frontendTools = [AIFunctionFactory.Create(ChangeBackground)];

    return aguiChatClient.CreateAIAgent(
        name: "AgenticChatAssistant",
        description: "A helpful assistant for the agentic chat demo",
        tools: frontendTools);
});

// Register a keyed AIAgent for backend tool rendering (weather demo)
builder.Services.AddKeyedSingleton<AIAgent>("backend-tool-rendering", (sp, key) =>
{
    HttpClient httpClient = sp.GetRequiredService<IHttpClientFactory>().CreateClient("aguiserver");
    AGUIChatClient aguiChatClient = new AGUIChatClient(httpClient, "backend_tool_rendering");

    return aguiChatClient.CreateAIAgent(
        name: "BackendToolRenderingAssistant",
        description: "A helpful assistant that can look up weather information");
});

// Register a keyed AIAgent for human-in-the-loop demo
builder.Services.AddKeyedSingleton<AIAgent>("human-in-the-loop", (sp, key) =>
{
    HttpClient httpClient = sp.GetRequiredService<IHttpClientFactory>().CreateClient("aguiserver");
    AGUIChatClient aguiChatClient = new AGUIChatClient(httpClient, "human_in_the_loop");

    // Create the base agent and wrap it with a delegating agent that adds instructions
    AIAgent baseAgent = aguiChatClient.CreateAIAgent(
        name: "HumanInTheLoopAssistant",
        description: "A helpful assistant that creates plans and asks for user confirmation");

    return new AGUIDojoClient.Components.Demos.HumanInTheLoop.HumanInTheLoopAgent(baseAgent);
});

// Register a keyed AIAgent for tool-based generative UI demo (haiku generator)
builder.Services.AddKeyedSingleton<AIAgent>("tool-based-generative-ui", (sp, key) =>
{
    HttpClient httpClient = sp.GetRequiredService<IHttpClientFactory>().CreateClient("aguiserver");
    AGUIChatClient aguiChatClient = new AGUIChatClient(httpClient, "tool_based_generative_ui");

    return aguiChatClient.CreateAIAgent(
        name: "ToolBasedGenerativeUIAssistant",
        description: "A helpful assistant that generates haikus with Japanese text and images");
});

// Register a keyed AIAgent for agentic generative UI demo (long-running task execution)
builder.Services.AddKeyedSingleton<AIAgent>("agentic-generative-ui", (sp, key) =>
{
    HttpClient httpClient = sp.GetRequiredService<IHttpClientFactory>().CreateClient("aguiserver");
    AGUIChatClient aguiChatClient = new AGUIChatClient(httpClient, "agentic_generative_ui");

    return aguiChatClient.CreateAIAgent(
        name: "AgenticGenerativeUIAssistant",
        description: "A helpful assistant that executes long-running tasks and shows progress");
});

// Register a keyed AIAgent for shared state demo (recipe copilot)
builder.Services.AddKeyedSingleton<AIAgent>("shared-state", (sp, key) =>
{
    HttpClient httpClient = sp.GetRequiredService<IHttpClientFactory>().CreateClient("aguiserver");
    AGUIChatClient aguiChatClient = new AGUIChatClient(httpClient, "shared_state");

    return aguiChatClient.CreateAIAgent(
        name: "SharedStateAssistant",
        description: "A recipe copilot that reads and updates collaboratively");
});

// Register a keyed AIAgent for predictive state updates demo (document editor)
builder.Services.AddKeyedSingleton<AIAgent>("predictive-state-updates", (sp, key) =>
{
    HttpClient httpClient = sp.GetRequiredService<IHttpClientFactory>().CreateClient("aguiserver");
    AGUIChatClient aguiChatClient = new AGUIChatClient(httpClient, "predictive_state_updates");

    return aguiChatClient.CreateAIAgent(
        name: "PredictiveStateUpdatesAssistant",
        description: "An AI document editor that streams content updates");
});

WebApplication app = builder.Build();

// Configure the HTTP request pipeline.
if (!app.Environment.IsDevelopment())
{
    app.UseExceptionHandler("/Error", createScopeForErrors: true);
    app.UseHsts();
}

app.UseHttpsRedirection();
app.UseAntiforgery();
app.MapStaticAssets();
app.MapRazorComponents<App>()
    .AddInteractiveServerRenderMode();

app.Run();
