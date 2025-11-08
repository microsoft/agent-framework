// Copyright (c) Microsoft. All rights reserved.

using System.ComponentModel;
using System.Diagnostics;
using System.Reflection;
using Microsoft.Agents.AI.DurableTask.IntegrationTests.Logging;
using Microsoft.DurableTask;
using Microsoft.DurableTask.Client;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.Configuration;
using OpenAI;
using Xunit.Abstractions;

namespace Microsoft.Agents.AI.DurableTask.IntegrationTests;

/// <summary>
/// Tests for scenarios where an external client interacts with Durable Task Agents.
/// </summary>
[Collection("Sequential")]
[Trait("Category", "Integration")]
public sealed class ExternalClientTests(ITestOutputHelper outputHelper) : IDisposable
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
    public async Task SimplePromptAsync()
    {
        // Setup
        AIAgent simpleAgent = TestHelper.GetAzureOpenAIChatClient(s_configuration).CreateAIAgent(
            instructions: "You are a helpful assistant that always responds with a friendly greeting.",
            name: "TestAgent");

        using TestHelper testHelper = TestHelper.Start([simpleAgent], this._outputHelper);

        // A proxy agent is needed to call the hosted test agent
        AIAgent simpleAgentProxy = simpleAgent.AsDurableAgentProxy(testHelper.Services);

        // Act: send a prompt to the agent and wait for a response
        AgentThread thread = simpleAgentProxy.GetNewThread();
        await simpleAgentProxy.RunAsync(
            message: "Hello!",
            thread,
            cancellationToken: this.TestTimeoutToken);

        AgentRunResponse response = await simpleAgentProxy.RunAsync(
            message: "Repeat what you just said but say it like a pirate",
            thread,
            cancellationToken: this.TestTimeoutToken);

        // Assert: verify the agent responded appropriately
        // We can't predict the exact response, but we can check that there is one response
        Assert.NotNull(response);
        Assert.NotEmpty(response.Text);

        // Assert: verify the expected log entries were created in the expected category
        IReadOnlyCollection<LogEntry> logs = testHelper.GetLogs();
        Assert.NotEmpty(logs);
        List<LogEntry> agentLogs = [.. logs.Where(log => log.Category.Contains(simpleAgent.Name!)).ToList()];
        Assert.NotEmpty(agentLogs);
        Assert.Contains(agentLogs, log => log.EventId.Name == "LogAgentRequest" && log.Message.Contains("Hello!"));
        Assert.Contains(agentLogs, log => log.EventId.Name == "LogAgentResponse");
    }

    [Fact]
    public async Task CallFunctionToolsAsync()
    {
        int weatherToolInvocationCount = 0;
        int packingListToolInvocationCount = 0;

        string GetWeather(string location)
        {
            weatherToolInvocationCount++;
            return $"The weather in {location} is sunny with a high of 75°F and a low of 55°F.";
        }

        string SuggestPackingList(string weather, bool isSunny)
        {
            packingListToolInvocationCount++;
            return isSunny ? "Pack sunglasses and sunscreen." : "Pack a raincoat and umbrella.";
        }

        AIAgent tripPlanningAgent = TestHelper.GetAzureOpenAIChatClient(s_configuration).CreateAIAgent(
            instructions: "You are a trip planning assistant. Use the weather tool and packing list tool as needed.",
            name: "TripPlanningAgent",
            description: "An agent to help plan your day trips",
            tools: [AIFunctionFactory.Create(GetWeather), AIFunctionFactory.Create(SuggestPackingList)]
        );

        using TestHelper testHelper = TestHelper.Start([tripPlanningAgent], this._outputHelper);
        AIAgent tripPlanningAgentProxy = tripPlanningAgent.AsDurableAgentProxy(testHelper.Services);

        // Act: send a prompt to the agent
        AgentRunResponse response = await tripPlanningAgentProxy.RunAsync(
            message: "Help me figure out what to pack for my Seattle trip next Sunday",
            cancellationToken: this.TestTimeoutToken);

        // Assert: verify the agent responded appropriately
        // We can't predict the exact response, but we can check that there is one response
        Assert.NotNull(response);
        Assert.NotEmpty(response.Text);

        // Assert: verify the expected log entries were created in the expected category
        IReadOnlyCollection<LogEntry> logs = testHelper.GetLogs();
        Assert.NotEmpty(logs);

        List<LogEntry> agentLogs = [.. logs.Where(log => log.Category.Contains(tripPlanningAgent.Name!)).ToList()];
        Assert.NotEmpty(agentLogs);
        Assert.Contains(agentLogs, log => log.EventId.Name == "LogAgentRequest" && log.Message.Contains("Seattle trip"));
        Assert.Contains(agentLogs, log => log.EventId.Name == "LogAgentResponse");

        // Assert: verify the tools were called
        Assert.Equal(1, weatherToolInvocationCount);
        Assert.Equal(1, packingListToolInvocationCount);
    }

    [Fact]
    public async Task CallLongRunningFunctionToolsAsync()
    {
        [Description("Starts a greeting workflow and returns the workflow instance ID")]
        string StartWorkflowTool(string name)
        {
            return DurableAgentContext.Current.ScheduleNewOrchestration(nameof(RunWorkflowAsync), input: name);
        }

        [Description("Gets the current status of a previously started workflow. A null response means the workflow has not started yet.")]
        static async Task<OrchestrationMetadata?> GetWorkflowStatusToolAsync(string instanceId)
        {
            OrchestrationMetadata? status = await DurableAgentContext.Current.GetOrchestrationStatusAsync(
                instanceId,
                includeDetails: true);
            if (status == null)
            {
                // If the status is not found, wait a bit before returning null to give the workflow time to start
                await Task.Delay(TimeSpan.FromSeconds(1));
            }

            return status;
        }

        async Task<string> RunWorkflowAsync(TaskOrchestrationContext context, string name)
        {
            // 1. Get agent and create a session
            DurableAIAgent agent = context.GetAgent("SimpleAgent");
            AgentThread thread = agent.GetNewThread();

            // 2. Call an agent and tell it my name
            await agent.RunAsync($"My name is {name}.", thread);

            // 3. Call the agent again with the same thread (ask it to tell me my name)
            AgentRunResponse response = await agent.RunAsync("What is my name?", thread);

            return response.Text;
        }

        using TestHelper testHelper = TestHelper.Start(
            this._outputHelper,
            configureAgents: agents =>
            {
                // This is the agent that will be used to start the workflow
                agents.AddAIAgentFactory(
                    "WorkflowAgent",
                    sp => TestHelper.GetAzureOpenAIChatClient(s_configuration).CreateAIAgent(
                        name: "WorkflowAgent",
                        instructions: "You can start greeting workflows and check their status.",
                        services: sp,
                        tools: [
                            AIFunctionFactory.Create(StartWorkflowTool),
                            AIFunctionFactory.Create(GetWorkflowStatusToolAsync)
                        ]));

                // This is the agent that will be called by the workflow
                agents.AddAIAgent(TestHelper.GetAzureOpenAIChatClient(s_configuration).CreateAIAgent(
                    name: "SimpleAgent",
                    instructions: "You are a simple assistant."
                ));
            },
            durableTaskRegistry: registry => registry.AddOrchestratorFunc<string, string>(nameof(RunWorkflowAsync), RunWorkflowAsync));

        AIAgent workflowManagerAgentProxy = testHelper.Services.GetDurableAgentProxy("WorkflowAgent");

        // Act: send a prompt to the agent
        AgentThread thread = workflowManagerAgentProxy.GetNewThread();
        await workflowManagerAgentProxy.RunAsync(
            message: "Start a greeting workflow for \"John Doe\".",
            thread,
            cancellationToken: this.TestTimeoutToken);

        // Act: prompt it again to wait for the workflow to complete
        AgentRunResponse response = await workflowManagerAgentProxy.RunAsync(
            message: "Wait for the workflow to complete and tell me the result.",
            thread,
            cancellationToken: this.TestTimeoutToken);

        // Assert: verify the agent responded appropriately
        // We can't predict the exact response, but we can check that there is one response
        Assert.NotNull(response);
        Assert.NotEmpty(response.Text);
        Assert.Contains("John Doe", response.Text);
    }
}
