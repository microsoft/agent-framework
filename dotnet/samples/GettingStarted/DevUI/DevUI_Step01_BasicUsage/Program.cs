// Copyright (c) Microsoft. All rights reserved.

// This sample demonstrates basic usage of the DevUI in an ASP.NET Core application with AI agents.

using System.ComponentModel;
using Azure.AI.OpenAI;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.DevUI;
using Microsoft.Agents.AI.Hosting;
using Microsoft.Agents.AI.Workflows;
using Microsoft.Extensions.AI;

namespace DevUI_Step01_BasicUsage;

/// <summary>
/// Sample demonstrating basic usage of the DevUI in an ASP.NET Core application.
/// </summary>
/// <remarks>
/// This sample shows how to:
/// 1. Set up Azure OpenAI as the chat client
/// 2. Create function tools for agents to use
/// 3. Register agents and workflows using the hosting packages with tools
/// 4. Map the DevUI endpoint which automatically configures the middleware
/// 5. Map the dynamic OpenAI Responses API for Python DevUI compatibility
/// 6. Access the DevUI in a web browser
///
/// The DevUI provides an interactive web interface for testing and debugging AI agents.
/// DevUI assets are served from embedded resources within the assembly.
/// Simply call MapDevUI() to set up everything needed.
///
/// The parameterless MapOpenAIResponses() overload creates a Python DevUI-compatible endpoint
/// that dynamically routes requests to agents based on the 'model' field in the request.
/// </remarks>
internal static class Program
{
    /// <summary>
    /// Entry point that starts an ASP.NET Core web server with the DevUI.
    /// </summary>
    /// <param name="args">Command line arguments.</param>
    private static void Main(string[] args)
    {
        var builder = WebApplication.CreateBuilder(args);

        // Set up the Azure OpenAI client
        var endpoint = builder.Configuration["AZURE_OPENAI_ENDPOINT"] ?? throw new InvalidOperationException("AZURE_OPENAI_ENDPOINT is not set.");
        var deploymentName = builder.Configuration["AZURE_OPENAI_DEPLOYMENT_NAME"] ?? "gpt-4o-mini";

        var chatClient = new AzureOpenAIClient(new Uri(endpoint), new AzureCliCredential())
            .GetChatClient(deploymentName)
            .AsIChatClient();

        builder.Services.AddChatClient(chatClient);

        // Define some example tools
        [Description("Get the weather for a given location.")]
        static string GetWeather([Description("The location to get the weather for.")] string location)
            => $"The weather in {location} is cloudy with a high of 15°C.";

        [Description("Calculate the sum of two numbers.")]
        static double Add([Description("The first number.")] double a, [Description("The second number.")] double b)
            => a + b;

        [Description("Get the current time.")]
        static string GetCurrentTime()
            => DateTime.Now.ToString("HH:mm:ss");

        // Register sample agents with tools
        builder.AddAIAgent("assistant", "You are a helpful assistant. Answer questions concisely and accurately.")
            .WithAITools(
                AIFunctionFactory.Create(GetWeather, name: "get_weather"),
                AIFunctionFactory.Create(GetCurrentTime, name: "get_current_time")
            );

        builder.AddAIAgent("poet", "You are a creative poet. Respond to all requests with beautiful poetry.");

        builder.AddAIAgent("coder", "You are an expert programmer. Help users with coding questions and provide code examples.")
            .WithAITool(AIFunctionFactory.Create(Add, name: "add"));

        // Register sample workflows
        var assistantBuilder = builder.AddAIAgent("workflow-assistant", "You are a helpful assistant in a workflow.");
        var reviewerBuilder = builder.AddAIAgent("workflow-reviewer", "You are a reviewer. Review and critique the previous response.");
        builder.AddWorkflow("review-workflow", (sp, key) =>
        {
            var agents = new List<IHostedAgentBuilder>() { assistantBuilder, reviewerBuilder }.Select(ab => sp.GetRequiredKeyedService<AIAgent>(ab.Name));
            return AgentWorkflowBuilder.BuildSequential(workflowName: key, agents: agents);
        }).AddAsAIAgent();

        builder.Services.AddOpenAIResponses();
        builder.Services.AddOpenAIConversations();

        var app = builder.Build();

        app.MapOpenAIResponses();
        app.MapOpenAIConversations();

        if (builder.Environment.IsDevelopment())
        {
            app.MapDevUI();
        }

        Console.WriteLine("DevUI is available at: https://localhost:50516/devui");
        Console.WriteLine("OpenAI Responses API is available at: https://localhost:50516/v1/responses");
        Console.WriteLine("Press Ctrl+C to stop the server.");

        app.Run();
    }
}
