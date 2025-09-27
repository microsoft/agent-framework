// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using Microsoft.Agents.Workflows.Checkpointing;

namespace Microsoft.Agents.Workflows.Execution;

internal sealed class MessageEnvelope(
    object message,
    ExecutorIdentity source,
    TypeId? declaredType = null,
    string? targetId = null,
    Dictionary<string, string>? traceContext = null)
{
    public TypeId MessageType => declaredType ?? new(message.GetType());
    public object Message => message;
    public ExecutorIdentity Source => source;
    public string? TargetId => targetId;

    public Dictionary<string, string>? TraceContext => traceContext;

    [MemberNotNullWhen(false, nameof(SourceId))]
    public bool IsExternal => this.Source == ExecutorIdentity.None;

    public string? SourceId => this.Source.Id;

    internal MessageEnvelope(
        object message,
        ExecutorIdentity source,
        Type declaredType,
        string? targetId = null,
        Dictionary<string, string>? traceContext = null) : this(message, source, new TypeId(declaredType), targetId, traceContext)
    {
        if (!declaredType.IsAssignableFrom(message.GetType()))
        {
            throw new ArgumentException($"The declared type {declaredType} is not compatible with the message instance of type {message.GetType()}");
        }
    }
}
