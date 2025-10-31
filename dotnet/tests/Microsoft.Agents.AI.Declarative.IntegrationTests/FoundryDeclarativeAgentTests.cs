// Copyright (c) Microsoft. All rights reserved.

using System;
using System.ComponentModel;
using System.IO;
using System.Threading.Tasks;
using Azure.Identity;
using Microsoft.Extensions.AI;
using Xunit.Abstractions;

namespace Microsoft.Agents.AI.Declarative.IntegrationTests;

/// <summary>
/// Tests for declarative agents created using <see cref="FoundryPersistentAgentFactory"/>.
/// </summary>
public sealed class FoundryDeclarativeAgentTests(ITestOutputHelper output) : BaseIntegrationTest(output)
{
    [Fact]
    public async Task CanCreateAndRunPersistentAgentAsync()
    {
        // Example function tool that can be used by the agent.
        [Description("Get the weather for a given location.")]
        static string GetWeather(
            [Description("The city and state, e.g. San Francisco, CA")] string location,
            [Description("The unit of temperature. Possible values are 'celsius' and 'fahrenheit'.")] string unit)
            => $"The weather in {location} is cloudy with a high of {(unit.Equals("celsius", StringComparison.Ordinal) ? "15°C" : "59°F")}.";

        // Arrange
        var endpointUri = new Uri(this.FoundryConfiguration.Endpoint);
        var tokenCredential = new AzureCliCredential();
        var agentFactory = new FoundryPersistentAgentFactory(new AzureCliCredential());
        var agentYaml = File.ReadAllText("../../../../../../agent-samples/foundry/PersistentAgent.yaml");
        agentYaml = agentYaml.Replace("=Env.AZURE_FOUNDRY_PROJECT_ENDPOINT", this.FoundryProjectConfiguration.Endpoint);
        agentYaml = agentYaml.Replace("=Env.AZURE_FOUNDRY_PROJECT_MODEL_ID", this.FoundryProjectConfiguration.ModelId);

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
