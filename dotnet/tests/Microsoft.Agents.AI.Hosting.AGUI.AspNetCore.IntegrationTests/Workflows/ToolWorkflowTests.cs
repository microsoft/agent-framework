// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Linq;
using System.Runtime.CompilerServices;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using AGUI.Abstractions;
using AGUI.Client;
using AGUI.WorkflowTools;
using FluentAssertions;
using Microsoft.Agents.AI.Workflows;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Hosting.AGUI.AspNetCore.IntegrationTests.Workflows;

public sealed class ToolWorkflowTests
{
    [Fact]
    public async Task ClientReceivesStepsToolContentAndTextOnceAsync()
    {
        // Arrange
        Workflow workflow = ToolWorkflow.Create(new DeterministicToolAgent());
        await using WorkflowTestHost host = await WorkflowTestHost.StartAsync(
            workflow.AsAIAgent(name: "ToolWorkflow"));
        AGUIChatClient chatClient = new(new(host.Client, ""));
        AIAgent clientAgent = chatClient.AsAIAgent(name: "client");
        AgentSession session = await clientAgent.CreateSessionAsync();

        // Act
        List<AgentResponseUpdate> updates = await clientAgent
            .RunStreamingAsync(new ChatMessage(ChatRole.User, "weather"), session)
            .ToListAsync();

        // Assert
        updates.Select(static update => update.AsChatResponseUpdate().RawRepresentation)
            .OfType<StepStartedEvent>()
            .Should().Contain(static evt => evt.StepName.StartsWith("WeatherAgent_"));
        updates.Select(static update => update.AsChatResponseUpdate().RawRepresentation)
            .OfType<StepFinishedEvent>()
            .Should().Contain(static evt => evt.StepName.StartsWith("WeatherAgent_"));
        updates.SelectMany(static update => update.Contents).OfType<FunctionCallContent>().Should().ContainSingle();
        updates.SelectMany(static update => update.Contents).OfType<FunctionResultContent>().Should().ContainSingle();
        updates.Count(static update => update.Text == "Sunny").Should().Be(1);
    }

    private sealed class DeterministicToolAgent : AIAgent
    {
        public override string? Name => "WeatherAgent";

        protected override Task<AgentResponse> RunCoreAsync(
            IEnumerable<ChatMessage> messages,
            AgentSession? session = null,
            AgentRunOptions? options = null,
            CancellationToken cancellationToken = default)
            => this.RunStreamingAsync(messages, session, options, cancellationToken).ToAgentResponseAsync(cancellationToken);

        protected override async IAsyncEnumerable<AgentResponseUpdate> RunCoreStreamingAsync(
            IEnumerable<ChatMessage> messages,
            AgentSession? session = null,
            AgentRunOptions? options = null,
            [EnumeratorCancellation] CancellationToken cancellationToken = default)
        {
            yield return CreateUpdate(new FunctionCallContent(
                "weather-call",
                "GetWeather",
                new Dictionary<string, object?> { ["city"] = "Seattle" }));
            yield return CreateUpdate(new FunctionResultContent("weather-call", "Sunny"));
            yield return CreateUpdate(new TextContent("Sunny"));
            await Task.Yield();
        }

        protected override ValueTask<AgentSession> CreateSessionCoreAsync(CancellationToken cancellationToken = default)
            => new(new ToolSession());

        protected override ValueTask<JsonElement> SerializeSessionCoreAsync(
            AgentSession session,
            JsonSerializerOptions? jsonSerializerOptions = null,
            CancellationToken cancellationToken = default)
            => new(JsonSerializer.SerializeToElement(new Dictionary<string, string>()));

        protected override ValueTask<AgentSession> DeserializeSessionCoreAsync(
            JsonElement serializedState,
            JsonSerializerOptions? jsonSerializerOptions = null,
            CancellationToken cancellationToken = default)
            => new(new ToolSession());

        private static AgentResponseUpdate CreateUpdate(AIContent content)
            => new(ChatRole.Assistant, [content])
            {
                MessageId = "weather-message",
                ResponseId = "weather-response",
            };

        private sealed class ToolSession : AgentSession;
    }
}
