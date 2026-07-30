// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Runtime.CompilerServices;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using FluentAssertions;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Workflows.UnitTests;

/// <summary>
/// Verifies that a workflow hosted as an <see cref="AIAgent"/> resumes a serialized session after its inner
/// agents are reconstructed only when each inner agent keeps a stable executor identity. A stable
/// <see cref="ChatClientAgentOptions.Id"/> is sufficient; if an agent also sets a
/// <see cref="ChatClientAgentOptions.Name"/>, that name must stay stable because the executor id includes it.
/// </summary>
public class WorkflowAgentCheckpointIdentityTests
{
    private const string TriageName = "triage_agent";
    private const string SpecialistName = "specialist_agent";
    private const string SpecialistReply = "SPECIALIST_REPLY";

    // Held constant across reconstruction so resume differences come only from the inner agent identities.
    private const string OuterWorkflowAgentId = "workflow-agent";

    [Fact]
    public async Task WorkflowAgentSession_WithStableInnerAgentIds_ResumesAcrossReconstructionAsync()
    {
        // Arrange: build a first-generation workflow agent whose inner agents have stable, explicit ids.
        AIAgent firstGeneration = BuildWorkflowAgent(useStableInnerIds: true);
        AgentSession session = await firstGeneration.CreateSessionAsync();

        // Act: complete a first turn (triage hands off to the specialist), then serialize the session.
        AgentResponse firstResponse = await firstGeneration.RunAsync("Please help me.", session);
        firstResponse.Text.Should().Contain(SpecialistReply, "the first turn should route triage -> specialist");

        JsonElement serialized = await firstGeneration.SerializeSessionAsync(session);

        // Reconstruct a completely fresh object graph (new clients, agents, and workflow) using the same stable ids,
        // modeling a second dependency-injection scope.
        AIAgent secondGeneration = BuildWorkflowAgent(useStableInnerIds: true);
        AgentSession resumedSession = await secondGeneration.DeserializeSessionAsync(serialized);

        AgentResponse secondResponse = await secondGeneration.RunAsync("Anything else?", resumedSession);

        // Assert: the reconstructed workflow resumes from the checkpoint and completes without a compatibility error.
        secondResponse.Text.Should().Contain(
            SpecialistReply,
            "stable inner agent ids keep the executor identities compatible with the checkpoint across reconstruction");
    }

    [Fact]
    public async Task WorkflowAgentSession_WithoutStableInnerAgentIds_FailsAcrossReconstructionAsync()
    {
        // Arrange: build a first-generation workflow agent whose inner agents receive random ids (no explicit id).
        AIAgent firstGeneration = BuildWorkflowAgent(useStableInnerIds: false);
        AgentSession session = await firstGeneration.CreateSessionAsync();

        // Complete a first turn and serialize the session; a completed handoff turn captures a checkpoint.
        AgentResponse firstResponse = await firstGeneration.RunAsync("Please help me.", session);
        firstResponse.Text.Should().Contain(SpecialistReply, "the first turn should route triage -> specialist");

        JsonElement serialized = await firstGeneration.SerializeSessionAsync(session);

        // Reconstruct with new random inner ids but the SAME outer workflow-agent id, proving that a stable outer id
        // alone does not stabilize the inner executor identities.
        AIAgent secondGeneration = BuildWorkflowAgent(useStableInnerIds: false);

        // Act: deserialization itself succeeds; the incompatibility surfaces only when the resuming run validates the
        // checkpoint against the reconstructed workflow.
        AgentSession resumedSession = await secondGeneration.DeserializeSessionAsync(serialized);

        Func<Task> resumeAndRun = () => secondGeneration.RunAsync("Anything else?", resumedSession);

        // Assert: the second run throws because the reconstructed executor ids no longer match the checkpoint.
        await resumeAndRun.Should().ThrowAsync<InvalidDataException>()
            .WithMessage("The specified checkpoint is not compatible with the workflow associated with this runner.");
    }

    /// <summary>
    /// Builds a fresh Handoff workflow-as-agent object graph. Every call constructs new chat clients, agents, and a
    /// new workflow, modeling reconstruction across dependency-injection scopes.
    /// </summary>
    /// <param name="useStableInnerIds">
    /// When <see langword="true"/>, each inner agent is assigned a deterministic <see cref="ChatClientAgentOptions.Id"/>.
    /// When <see langword="false"/>, the id is left unset so each agent receives a random per-instance id.
    /// </param>
    private static AIAgent BuildWorkflowAgent(bool useStableInnerIds)
    {
        AIAgent triage = CreateTriageClient().AsAIAgent(new ChatClientAgentOptions
        {
            Id = useStableInnerIds ? "triage-agent" : null,
            Name = TriageName,
            Description = "Routes the request to a specialist.",
            ChatOptions = new() { Instructions = "Always hand off to the specialist." },
        });

        AIAgent specialist = CreateSpecialistClient().AsAIAgent(new ChatClientAgentOptions
        {
            Id = useStableInnerIds ? "specialist-agent" : null,
            Name = SpecialistName,
            Description = "Handles the request once triage hands off.",
            ChatOptions = new() { Instructions = "Answer the request." },
        });

        Workflow workflow = AgentWorkflowBuilder.CreateHandoffBuilderWith(triage)
            .WithHandoff(triage, specialist)
            .Build();

        return workflow.AsAIAgent(id: OuterWorkflowAgentId, name: OuterWorkflowAgentId);
    }

    // Triage hands off to the specialist by calling the handoff tool present on the request.
    private static StatelessMockChatClient CreateTriageClient() => new((messages, options) =>
    {
        string? handoffTool = options?.Tools?
            .FirstOrDefault(t => t.Name.StartsWith("handoff_to_", StringComparison.Ordinal))?.Name;

        return new ChatResponse(new ChatMessage(ChatRole.Assistant, [new FunctionCallContent("handoff-call", handoffTool!)]));
    });

    // The specialist returns a fixed reply.
    private static StatelessMockChatClient CreateSpecialistClient() => new((_, _) =>
        new ChatResponse(new ChatMessage(ChatRole.Assistant, SpecialistReply)));

    /// <summary>
    /// A minimal <see cref="IChatClient"/> whose response is a pure function of the request, so reconstructing it
    /// preserves behavior.
    /// </summary>
    private sealed class StatelessMockChatClient(Func<IEnumerable<ChatMessage>, ChatOptions?, ChatResponse> responseFactory) : IChatClient
    {
        public Task<ChatResponse> GetResponseAsync(IEnumerable<ChatMessage> messages, ChatOptions? options = null, CancellationToken cancellationToken = default) =>
            Task.FromResult(responseFactory(messages, options));

        public async IAsyncEnumerable<ChatResponseUpdate> GetStreamingResponseAsync(
            IEnumerable<ChatMessage> messages, ChatOptions? options = null, [EnumeratorCancellation] CancellationToken cancellationToken = default)
        {
            foreach (var update in (await this.GetResponseAsync(messages, options, cancellationToken).ConfigureAwait(false)).ToChatResponseUpdates())
            {
                yield return update;
            }
        }

        public object? GetService(Type serviceType, object? serviceKey = null) => null;

        public void Dispose() { }
    }
}
