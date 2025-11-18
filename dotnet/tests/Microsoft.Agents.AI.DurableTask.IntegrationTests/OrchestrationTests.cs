// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics;
using System.Reflection;
using Microsoft.DurableTask;
using Microsoft.DurableTask.Client;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.Configuration;
using OpenAI;
using Xunit.Abstractions;

namespace Microsoft.Agents.AI.DurableTask.IntegrationTests;

/// <summary>
/// Tests for orchestration execution scenarios with Durable Task Agents.
/// </summary>
[Collection("Sequential")]
[Trait("Category", "Integration")]
public sealed class OrchestrationTests(ITestOutputHelper outputHelper) : IDisposable
{
    private static readonly TimeSpan s_defaultTimeout = Debugger.IsAttached
        ? TimeSpan.FromMinutes(5)
        : TimeSpan.FromSeconds(30);

    private static readonly IConfiguration s_configuration =
        new ConfigurationBuilder()
            .AddUserSecrets(Assembly.GetExecutingAssembly())
            .AddEnvironmentVariables()
            .Build();

    private readonly ITestOutputHelper _outputHelper = outputHelper;
    private readonly CancellationTokenSource _cts = new(delay: s_defaultTimeout);

    private CancellationToken TestTimeoutToken => this._cts.Token;

    public void Dispose() => this._cts.Dispose();

    [Fact]
    public async Task GetAgent_ThrowsWhenAgentNotRegisteredAsync()
    {
        // Define an orchestration that tries to use an unregistered agent
        static async Task<string> TestOrchestrationAsync(TaskOrchestrationContext context)
        {
            // Get an agent that hasn't been registered
            DurableAIAgent agent = context.GetAgent("NonExistentAgent");

            // This should throw when RunAsync is called because the agent doesn't exist
            await agent.RunAsync("Hello");
            return "Should not reach here";
        }

        // Setup: Create test helper without registering "NonExistentAgent"
        using TestHelper testHelper = TestHelper.Start(
            this._outputHelper,
            configureAgents: agents =>
            {
                // Register a different agent, but not "NonExistentAgent"
                agents.AddAIAgentFactory(
                    "OtherAgent",
                    sp => TestHelper.GetAzureOpenAIChatClient(s_configuration).CreateAIAgent(
                        name: "OtherAgent",
                        instructions: "You are a test agent."));
            },
            durableTaskRegistry: registry =>
                registry.AddOrchestratorFunc(
                    name: nameof(TestOrchestrationAsync),
                    orchestrator: TestOrchestrationAsync));

        DurableTaskClient client = testHelper.GetClient();

        // Act: Start the orchestration
        string instanceId = await client.ScheduleNewOrchestrationInstanceAsync(
            orchestratorName: nameof(TestOrchestrationAsync),
            cancellation: this.TestTimeoutToken);

        // Wait for the orchestration to complete and check for failure
        OrchestrationMetadata status = await client.WaitForInstanceCompletionAsync(
            instanceId,
            getInputsAndOutputs: true,
            this.TestTimeoutToken);

        // Assert: Verify the orchestration failed with the expected exception
        Assert.NotNull(status);
        Assert.Equal(OrchestrationRuntimeStatus.Failed, status.RuntimeStatus);
        Assert.NotNull(status.FailureDetails);

        // Verify the exception type is AgentNotRegisteredException
        Assert.True(
            status.FailureDetails.ErrorType == typeof(AgentNotRegisteredException).FullName,
            $"Expected AgentNotRegisteredException but got ErrorType: {status.FailureDetails.ErrorType}, Message: {status.FailureDetails.ErrorMessage}");

        // Verify the exception message contains the agent name
        Assert.Contains("NonExistentAgent", status.FailureDetails.ErrorMessage, StringComparison.OrdinalIgnoreCase);
    }
}
