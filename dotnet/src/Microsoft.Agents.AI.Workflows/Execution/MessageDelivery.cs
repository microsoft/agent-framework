// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json.Serialization;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Workflows.Execution;

internal sealed class MessageDelivery
{
    [JsonConstructor]
    internal MessageDelivery(MessageEnvelope envelope, string targetId)
    {
        this.Envelope = Throw.IfNull(envelope);
        this.TargetId = Throw.IfNull(targetId);
    }

    internal MessageDelivery(MessageEnvelope envelope, Executor target)
        : this(envelope, target.Id)
    {
        this.TargetCache = Throw.IfNull(target);
    }

    public string TargetId { get; }
    public MessageEnvelope Envelope { get; }

    [JsonIgnore]
    internal Executor? TargetCache { get; set; }
}
