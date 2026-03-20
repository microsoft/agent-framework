// Copyright (c) Microsoft. All rights reserved.

using Azure;
using Azure.AI.OpenAI;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.DurableTask;
using Microsoft.DurableTask.Client.AzureManaged;
using Microsoft.DurableTask.Worker.AzureManaged;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;
using OpenAI.Chat;

// Get the Azure OpenAI endpoint and deployment name from environment variables.
string endpoint = Environment.GetEnvironmentVariable("AZURE_OPENAI_ENDPOINT")
    ?? throw new InvalidOperationException("AZURE_OPENAI_ENDPOINT is not set.");
string deploymentName = Environment.GetEnvironmentVariable("AZURE_OPENAI_DEPLOYMENT_NAME")
    ?? throw new InvalidOperationException("AZURE_OPENAI_DEPLOYMENT_NAME is not set.");

// Get DTS connection string from environment variable
string dtsConnectionString = Environment.GetEnvironmentVariable("DURABLE_TASK_SCHEDULER_CONNECTION_STRING")
    ?? "Endpoint=http://localhost:8080;TaskHub=default;Authentication=None";

// Use Azure Key Credential if provided, otherwise use Azure CLI Credential.
string? azureOpenAiKey = Environment.GetEnvironmentVariable("AZURE_OPENAI_API_KEY");
// WARNING: DefaultAzureCredential is convenient for development but requires careful consideration in production.
// In production, consider using a specific credential (e.g., ManagedIdentityCredential) to avoid
// latency issues, unintended credential probing, and potential security risks from fallback mechanisms.
AzureOpenAIClient client = !string.IsNullOrEmpty(azureOpenAiKey)
    ? new AzureOpenAIClient(new Uri(endpoint), new AzureKeyCredential(azureOpenAiKey))
    : new AzureOpenAIClient(new Uri(endpoint), new DefaultAzureCredential());

// Set up an AI agent following the standard Microsoft Agent Framework pattern.
const string JokerName = "Joker";
const string JokerInstructions = "You are good at telling jokes.";

AIAgent agent = client.GetChatClient(deploymentName).AsAIAgent(JokerInstructions, JokerName);

// Configure the console app to host the AI agent.
IHost host = Host.CreateDefaultBuilder(args)
    .ConfigureLogging(logging => logging.SetMinimumLevel(LogLevel.Warning))
    .ConfigureServices(services =>
    {
        services.ConfigureDurableAgents(
            options => options.AddAIAgent(agent, timeToLive: TimeSpan.FromHours(1)),
            workerBuilder: builder => builder.UseDurableTaskScheduler(dtsConnectionString),
            clientBuilder: builder => builder.UseDurableTaskScheduler(dtsConnectionString));
    })
    .Build();

await host.StartAsync();

// Get the agent proxy from services
IServiceProvider services = host.Services;
AIAgent agentProxy = services.GetRequiredKeyedService<AIAgent>(JokerName);

// Console colors for better UX
Console.ForegroundColor = ConsoleColor.Cyan;
Console.WriteLine("=== Single Agent Console Sample ===");
Console.ResetColor();
Console.WriteLine("Enter a message for the Joker agent (or 'exit' to quit):");
Console.WriteLine();

// Create a session for the conversation
AgentSession session = await agentProxy.CreateSessionAsync();

while (true)
{
    // Read input from stdin
    Console.ForegroundColor = ConsoleColor.Yellow;
    Console.Write("You: ");
    Console.ResetColor();

    string? input = Console.ReadLine();
    if (string.IsNullOrWhiteSpace(input) || input.Equals("exit", StringComparison.OrdinalIgnoreCase))
    {
        break;
    }

    // Run the agent
    Console.ForegroundColor = ConsoleColor.Green;
    Console.Write("Joker: ");
    Console.ResetColor();

    try
    {
        AgentResponse agentResponse = await agentProxy.RunAsync(
            message: input,
            session: session,
            cancellationToken: CancellationToken.None);

        Console.WriteLine(agentResponse.Text);
        Console.WriteLine();
    }
    catch (Exception ex)
    {
        Console.ForegroundColor = ConsoleColor.Red;
        Console.Error.WriteLine($"Error: {ex.Message}");
        Console.ResetColor();
        Console.WriteLine();
    }
}

await host.StopAsync();
