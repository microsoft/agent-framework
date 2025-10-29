// Copyright (c) Microsoft. All rights reserved.

using System;
using System.ComponentModel;
using System.IO;
using System.Threading.Tasks;
using Azure.AI.OpenAI;
using Azure.Identity;
using Microsoft.Extensions.AI;
using Xunit.Abstractions;

namespace Microsoft.Agents.AI.Declarative.IntegrationTests;

/// <summary>
/// Tests for declarative agents created using <see cref="ChatClientAgentFactory"/>.
/// </summary>
public sealed class ChatClientDeclarativeAgentTests(ITestOutputHelper output) : BaseIntegrationTest(output)
{
    [Fact]
    public async Task CanCreateAndRunAssistantAgentAsync()
    {
        // Arrange
        var chatClient = this.CreateIChatClient();
        var agentFactory = new ChatClientAgentFactory(chatClient);
        var agentYaml = File.ReadAllText("../../../../../../agent-samples/chatclient/Assistant.yaml");

        // Act
        var agent = await agentFactory.CreateFromYamlAsync(agentYaml);
        var response = await agent!.RunAsync("Tell me a joke about a pirate in Italian.");
        this.Output.WriteLine($"Agent Response: {response.Text}");

        // Assert
        Assert.NotNull(agent);
        Assert.NotNull(response);
        Assert.NotEmpty(response.Text);
    }

    [Fact]
    public async Task CanCreateAndRunGetWeatherAgentAsync()
    {
        // Example function tool that can be used by the agent.
        [Description("Get the weather for a given location.")]
        static string GetWeather(
            [Description("The city and state, e.g. San Francisco, CA")] string location,
            [Description("The unit of temperature. Possible values are 'celsius' and 'fahrenheit'.")] string unit)
            => $"The weather in {location} is cloudy with a high of {(unit.Equals("celsius", StringComparison.Ordinal) ? "15°C" : "59°F")}.";

        // Arrange
        var chatClient = this.CreateIChatClient();
        var agentFactory = new ChatClientAgentFactory(chatClient, [AIFunctionFactory.Create(GetWeather, "GetWeather")]);
        var agentYaml = File.ReadAllText("../../../../../../agent-samples/chatclient/GetWeather.yaml");

        // Act
        var agent = await agentFactory.CreateFromYamlAsync(agentYaml);
        var response = await agent!.RunAsync("What is the weather in Cambridge, MA in °C?");
        this.Output.WriteLine($"Agent Response: {response.Text}");

        // Assert
        Assert.NotNull(agent);
        Assert.NotNull(response);
        Assert.NotEmpty(response.Text);
    }

    private IChatClient CreateIChatClient()
    {
        var endpoint = this.FoundryConfiguration.Endpoint;
        var deploymentName = this.FoundryConfiguration.DeploymentName;

        // Create the chat client
        return new AzureOpenAIClient(
            new Uri(endpoint),
            new AzureCliCredential())
             .GetChatClient(deploymentName)
             .AsIChatClient();
    }
}
