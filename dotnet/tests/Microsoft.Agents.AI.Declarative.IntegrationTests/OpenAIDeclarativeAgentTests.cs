// Copyright (c) Microsoft. All rights reserved.

using System;
using System.ComponentModel;
using System.IO;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Xunit.Abstractions;

namespace Microsoft.Agents.AI.Declarative.IntegrationTests;

/// <summary>
/// Tests for declarative agents created using <see cref="AggregatorAgentFactory"/>.
/// </summary>
public sealed class OpenAIDeclarativeAgentTests(ITestOutputHelper output) : BaseIntegrationTest(output)
{
    [Fact]
    public async Task CanCreateAndRunChatAgentAsync()
    {
        // Example function tool that can be used by the agent.
        [Description("Get the weather for a given location.")]
        static string GetWeather(
            [Description("The city and state, e.g. San Francisco, CA")] string location,
            [Description("The unit of temperature. Possible values are 'celsius' and 'fahrenheit'.")] string unit)
            => $"The weather in {location} is cloudy with a high of {(unit.Equals("celsius", StringComparison.Ordinal) ? "15°C" : "59°F")}.";

        // Arrange
        var agentFactory = new AggregatorAgentFactory(
        [
            new OpenAIChatAgentFactory(),
            new OpenAIResponseAgentFactory(),
            new OpenAIAssistantAgentFactory()
        ]);
        var agentYaml = File.ReadAllText("../../../../../../agent-samples/openai/OpenAI.yaml");
        agentYaml = agentYaml.Replace("=Env.OPENAI_APIKEY", this.OpenAIConfiguration.ApiKey);
        agentYaml = agentYaml.Replace("=Env.OPENAI_MODEL", this.OpenAIConfiguration.ChatModelId);

        // Create agent run options
        var options = new ChatClientAgentRunOptions(new()
        {
            Tools = [AIFunctionFactory.Create(GetWeather, name: nameof(GetWeather))]
        });

        // Act
        var agent = await agentFactory.CreateFromYamlAsync(agentYaml);
        var response = await agent!.RunAsync("What is the weather in Cambridge, MA in °C?", options: options);
        this.Output.WriteLine($"Agent Response: {response.Text}");

        // Assert
        Assert.NotNull(agent);
        Assert.NotNull(response);
        Assert.NotEmpty(response.Text);
    }

    [Fact]
    public async Task CanCreateAndRunResponsesAgentAsync()
    {
        // Example function tool that can be used by the agent.
        [Description("Get the weather for a given location.")]
        static string GetWeather(
            [Description("The city and state, e.g. San Francisco, CA")] string location,
            [Description("The unit of temperature. Possible values are 'celsius' and 'fahrenheit'.")] string unit)
            => $"The weather in {location} is cloudy with a high of {(unit.Equals("celsius", StringComparison.Ordinal) ? "15°C" : "59°F")}.";

        // Arrange
        var agentFactory = new AggregatorAgentFactory(
        [
            new OpenAIChatAgentFactory(),
            new OpenAIResponseAgentFactory(),
            new OpenAIAssistantAgentFactory()
        ]);
        var agentYaml = File.ReadAllText("../../../../../../agent-samples/openai/OpenAIResponses.yaml");
        agentYaml = agentYaml.Replace("=Env.OPENAI_APIKEY", this.OpenAIConfiguration.ApiKey);
        agentYaml = agentYaml.Replace("=Env.OPENAI_MODEL", this.OpenAIConfiguration.ChatModelId);

        // Create agent run options
        var options = new ChatClientAgentRunOptions(new()
        {
            Tools = [AIFunctionFactory.Create(GetWeather, name: nameof(GetWeather))]
        });

        // Act
        var agent = await agentFactory.CreateFromYamlAsync(agentYaml);
        var response = await agent!.RunAsync("What is the weather in Cambridge, MA in °C?", options: options);
        this.Output.WriteLine($"Agent Response: {response.Text}");

        // Assert
        Assert.NotNull(agent);
        Assert.NotNull(response);
        Assert.NotEmpty(response.Text);
    }

    [Fact]
    public async Task CanCreateAndRunAssistantsAgentAsync()
    {
        // Example function tool that can be used by the agent.
        [Description("Get the weather for a given location.")]
        static string GetWeather(
            [Description("The city and state, e.g. San Francisco, CA")] string location,
            [Description("The unit of temperature. Possible values are 'celsius' and 'fahrenheit'.")] string unit)
            => $"The weather in {location} is cloudy with a high of {(unit.Equals("celsius", StringComparison.Ordinal) ? "15°C" : "59°F")}.";

        // Arrange
        var agentFactory = new AggregatorAgentFactory(
        [
            new OpenAIChatAgentFactory(),
            new OpenAIResponseAgentFactory(),
            new OpenAIAssistantAgentFactory()
        ]);
        var agentYaml = File.ReadAllText("../../../../../../agent-samples/openai/OpenAIAssistants.yaml");
        agentYaml = agentYaml.Replace("=Env.OPENAI_APIKEY", this.OpenAIConfiguration.ApiKey);
        agentYaml = agentYaml.Replace("=Env.OPENAI_MODEL", this.OpenAIConfiguration.ChatModelId);

        // Create agent run options
        var options = new ChatClientAgentRunOptions(new()
        {
            Tools = [AIFunctionFactory.Create(GetWeather, name: nameof(GetWeather))]
        });

        // Act
        var agent = await agentFactory.CreateFromYamlAsync(agentYaml);
        var response = await agent!.RunAsync("What is the weather in Cambridge, MA in °C?", options: options);
        this.Output.WriteLine($"Agent Response: {response.Text}");

        // Assert
        Assert.NotNull(agent);
        Assert.NotNull(response);
        Assert.NotEmpty(response.Text);
    }
}
