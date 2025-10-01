// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Text.Json;
using Microsoft.Extensions.AI;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Workflows;

internal sealed class WorkflowThread : AgentThread
{
    public WorkflowThread(string workflowId, string? workflowName, string runId)
    {
        this.MessageStore = new();
        this.RunId = Throw.IfNullOrEmpty(runId);
    }

    public WorkflowThread(JsonElement serializedThread, JsonSerializerOptions? jsonSerializerOptions = null)
    {
        throw new NotImplementedException("Pending Checkpointing work.");
    }

    public string RunId { get; }
    public int Halts { get; }

    public string ResponseId => $"{this.RunId}@{this.Halts}";

    public override JsonElement Serialize(JsonSerializerOptions? jsonSerializerOptions = null)
        => throw new NotImplementedException("Pending Checkpointing work.");

    public AgentRunResponseUpdate CreateUpdate(params AIContent[] parts)
    {
        Throw.IfNullOrEmpty(parts);

        AgentRunResponseUpdate update = new(ChatRole.Assistant, parts)
        {
            CreatedAt = DateTimeOffset.UtcNow,
            MessageId = Guid.NewGuid().ToString("N"),
        };

        this.MessageStore.AddMessages(update.ToChatMessage());

        return update;
    }

    /// <inheritdoc/>
    public WorkflowMessageStore MessageStore { get; }
}
