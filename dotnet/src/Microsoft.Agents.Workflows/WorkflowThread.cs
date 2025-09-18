// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.AI.Agents;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.Workflows;

internal sealed class WorkflowThread : AgentThread
{
    public WorkflowThread(string workflowId, string? workflowName, string runId)
    {
        this.MessageStore = new();
        this.RunId = Throw.IfNullOrEmpty(runId, nameof(runId));
    }

    public WorkflowThread(JsonElement serializedThread, JsonSerializerOptions? jsonSerializerOptions = null)
    {
        throw new NotImplementedException("Pending Checkpointing work.");
    }

    public string RunId { get; }
    public int Halts { get; }

    public string ResponseId => $"{this.RunId}@{this.Halts}";

    public override Task<JsonElement> SerializeAsync(JsonSerializerOptions? jsonSerializerOptions = null, CancellationToken cancellationToken = default) => throw new NotImplementedException("Pending Checkpointing work.");

    public AgentRunResponseUpdate CreateUpdate(params AIContent[] parts)
    {
        Throw.IfNullOrEmpty(parts);

        AgentRunResponseUpdate update = new(ChatRole.Assistant, parts)
        {
            CreatedAt = DateTimeOffset.Now,
            MessageId = Guid.NewGuid().ToString("N"),
        };

        this.MessageStore.AddMessages(update.ToChatMessage());

        return update;
    }

    /// <inheritdoc/>
    public WorkflowMessageStore MessageStore { get; }
}
