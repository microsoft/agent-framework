// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to use plugins with an AI agent. Plugin classes can
// depend on other services that need to be injected. In this sample, the
// AgentPlugin class uses the WeatherProvider and CurrentTimeProvider classes
// to get weather and current time information. Both services are registered
// in the service collection and injected into the plugin.
// Plugin classes may have many methods, but only some are intended to be used
// as AI functions. The AsAITools method of the plugin class shows how to specify
// which methods should be exposed to the AI agent.

using Azure.AI.Projects;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.DependencyInjection;

string endpoint = Environment.GetEnvironmentVariable("AZURE_FOUNDRY_PROJECT_ENDPOINT") ?? throw new InvalidOperationException("AZURE_FOUNDRY_PROJECT_ENDPOINT is not set.");
string deploymentName = Environment.GetEnvironmentVariable("AZURE_FOUNDRY_PROJECT_DEPLOYMENT_NAME") ?? "gpt-4o-mini";

const string AssistantInstructions = "You are a helpful assistant that helps people find information.";
const string AssistantName = "PluginAssistant";

// Create a service collection to hold the agent plugin and its dependencies.
ServiceCollection services = new();
services.AddSingleton<WeatherProvider>();
services.AddSingleton<CurrentTimeProvider>();
services.AddSingleton<AgentPlugin>(); // The plugin depends on WeatherProvider and CurrentTimeProvider registered above.

IServiceProvider serviceProvider = services.BuildServiceProvider();

// Get a client to create/retrieve/delete server side agents with Azure Foundry Agents.
AIProjectClient aiProjectClient = new(new Uri(endpoint), new AzureCliCredential());

// Define the agent with plugin tools
// Define the agent you want to create. (Prompt Agent in this case)
AIAgent agent = aiProjectClient.CreateAIAgent(
    name: AssistantName,
    model: deploymentName,
    instructions: AssistantInstructions,
    tools: serviceProvider.GetRequiredService<AgentPlugin>().AsAITools().ToList(),
    services: serviceProvider);

// Invoke the agent and output the text result.
AgentThread thread = agent.GetNewThread();
Console.WriteLine(await agent.RunAsync("Tell me current time and weather in Seattle.", thread));

// Cleanup by agent name removes the agent version created.
await aiProjectClient.Agents.DeleteAgentAsync(agent.Name);

/// <summary>
/// The agent plugin that provides weather and current time information.
/// </summary>
/// <param name="weatherProvider">The weather provider to get weather information.</param>
internal sealed class AgentPlugin(WeatherProvider weatherProvider)
{
    /// <summary>
    /// Gets the weather information for the specified location.
    /// </summary>
    /// <remarks>
    /// This method demonstrates how to use the dependency that was injected into the plugin class.
    /// </remarks>
    /// <param name="location">The location to get the weather for.</param>
    /// <returns>The weather information for the specified location.</returns>
    public string GetWeather(string location)
    {
        return weatherProvider.GetWeather(location);
    }

    /// <summary>
    /// Gets the current date and time for the specified location.
    /// </summary>
    /// <remarks>
    /// This method demonstrates how to resolve a dependency using the service provider passed to the method.
    /// </remarks>
    /// <param name="sp">The service provider to resolve the <see cref="CurrentTimeProvider"/>.</param>
    /// <param name="location">The location to get the current time for.</param>
    /// <returns>The current date and time as a <see cref="DateTimeOffset"/>.</returns>
    public DateTimeOffset GetCurrentTime(IServiceProvider sp, string location)
    {
        // Resolve the CurrentTimeProvider from the service provider
        CurrentTimeProvider currentTimeProvider = sp.GetRequiredService<CurrentTimeProvider>();

        return currentTimeProvider.GetCurrentTime(location);
    }

    /// <summary>
    /// Returns the functions provided by this plugin.
    /// </summary>
    /// <remarks>
    /// In real world scenarios, a class may have many methods and only a subset of them may be intended to be exposed as AI functions.
    /// This method demonstrates how to explicitly specify which methods should be exposed to the AI agent.
    /// </remarks>
    /// <returns>The functions provided by this plugin.</returns>
    public IEnumerable<AITool> AsAITools()
    {
        yield return AIFunctionFactory.Create(this.GetWeather);
        yield return AIFunctionFactory.Create(this.GetCurrentTime);
    }
}

/// <summary>
/// The weather provider that returns weather information.
/// </summary>
internal sealed class WeatherProvider
{
    /// <summary>
    /// Gets the weather information for the specified location.
    /// </summary>
    /// <remarks>
    /// The weather information is hardcoded for demonstration purposes.
    /// In a real application, this could call a weather API to get actual weather data.
    /// </remarks>
    /// <param name="location">The location to get the weather for.</param>
    /// <returns>The weather information for the specified location.</returns>
    public string GetWeather(string location)
    {
        return $"The weather in {location} is cloudy with a high of 15°C.";
    }
}

/// <summary>
/// Provides the current date and time.
/// </summary>
/// <remarks>
/// This class returns the current date and time using the system's clock.
/// </remarks>
internal sealed class CurrentTimeProvider
{
    /// <summary>
    /// Gets the current date and time.
    /// </summary>
    /// <param name="location">The location to get the current time for (not used in this implementation).</param>
    /// <returns>The current date and time as a <see cref="DateTimeOffset"/>.</returns>
    public DateTimeOffset GetCurrentTime(string location)
    {
        return DateTimeOffset.Now;
    }
}
