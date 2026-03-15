// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to use plugins with a ChatClientAgent.
// Plugin classes can depend on other services that need to be injected.

using Azure.AI.Projects;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.DependencyInjection;
using SampleApp;

const string AssistantInstructions = "You are a helpful assistant that helps people find information.";
const string AssistantName = "PluginAssistant";

// Create a service collection to hold the agent plugin and its dependencies.
ServiceCollection services = new();
services.AddSingleton<WeatherProvider>();
services.AddSingleton<CurrentTimeProvider>();
services.AddSingleton<AgentPlugin>(); // The plugin depends on WeatherProvider and CurrentTimeProvider registered above.

IServiceProvider serviceProvider = services.BuildServiceProvider();

string endpoint = Environment.GetEnvironmentVariable("AZURE_AI_PROJECT_ENDPOINT") ?? throw new InvalidOperationException("AZURE_AI_PROJECT_ENDPOINT is not set.");
string deploymentName = Environment.GetEnvironmentVariable("AZURE_AI_MODEL_DEPLOYMENT_NAME") ?? "gpt-4o-mini";

AIProjectClient aiProjectClient = new(new Uri(endpoint), new DefaultAzureCredential());

// Create a ChatClientAgent with the options-based constructor to pass services.
ChatClientAgent agent = aiProjectClient.AsAIAgent(
    new ChatClientAgentOptions
    {
        Name = AssistantName,
        ChatOptions = new()
        {
            ModelId = deploymentName,
            Instructions = AssistantInstructions,
            Tools = serviceProvider.GetRequiredService<AgentPlugin>().AsAITools().ToList(),
        },
    },
    services: serviceProvider);

// Invoke the agent and output the text result.
AgentSession session = await agent.CreateSessionAsync();
Console.WriteLine(await agent.RunAsync("Tell me current time and weather in Seattle.", session));

namespace SampleApp
{
    /// <summary>
    /// The agent plugin that provides weather and current time information.
    /// </summary>
    internal sealed class AgentPlugin
    {
        private readonly WeatherProvider _weatherProvider;

        /// <summary>
        /// Initializes a new instance of the <see cref="AgentPlugin"/> class.
        /// </summary>
        /// <param name="weatherProvider">The weather provider to get weather information.</param>
        public AgentPlugin(WeatherProvider weatherProvider)
        {
            this._weatherProvider = weatherProvider;
        }

        /// <summary>
        /// Gets the weather information for the specified location.
        /// </summary>
        /// <param name="location">The location to get the weather for.</param>
        /// <returns>The weather information for the specified location.</returns>
        public string GetWeather(string location)
        {
            return this._weatherProvider.GetWeather(location);
        }

        /// <summary>
        /// Gets the current date and time for the specified location.
        /// </summary>
        /// <param name="sp">The service provider to resolve the <see cref="CurrentTimeProvider"/>.</param>
        /// <param name="location">The location to get the current time for.</param>
        /// <returns>The current date and time as a <see cref="DateTimeOffset"/>.</returns>
        public DateTimeOffset GetCurrentTime(IServiceProvider sp, string location)
        {
            CurrentTimeProvider currentTimeProvider = sp.GetRequiredService<CurrentTimeProvider>();
            return currentTimeProvider.GetCurrentTime(location);
        }

        /// <summary>
        /// Returns the functions provided by this plugin.
        /// </summary>
        /// <returns>The functions provided by this plugin.</returns>
        public IEnumerable<AITool> AsAITools()
        {
            yield return AIFunctionFactory.Create(this.GetWeather);
            yield return AIFunctionFactory.Create(this.GetCurrentTime);
        }
    }

    internal sealed class WeatherProvider
    {
        private readonly string _weatherSummary = "cloudy with a high of 15°C";

        /// <summary>
        /// The weather provider that returns weather information.
        /// </summary>
        /// <summary>
        /// Gets the weather information for the specified location.
        /// </summary>
        /// <param name="location">The location to get the weather for.</param>
        /// <returns>The weather information for the specified location.</returns>
        public string GetWeather(string location)
        {
            return $"The weather in {location} is {this._weatherSummary}.";
        }
    }

    internal sealed class CurrentTimeProvider
    {
        private readonly TimeProvider _timeProvider = TimeProvider.System;

        /// <summary>
        /// Provides the current date and time.
        /// </summary>
        /// <summary>
        /// Gets the current date and time.
        /// </summary>
        /// <param name="location">The location to get the current time for (not used in this implementation).</param>
        /// <returns>The current date and time as a <see cref="DateTimeOffset"/>.</returns>
        public DateTimeOffset GetCurrentTime(string location)
        {
            return this._timeProvider.GetLocalNow();
        }
    }
}
