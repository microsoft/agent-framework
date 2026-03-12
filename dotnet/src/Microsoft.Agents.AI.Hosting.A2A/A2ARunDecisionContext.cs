// Copyright (c) Microsoft. All rights reserved.

using A2A;

namespace Microsoft.Agents.AI.Hosting.A2A;

/// <summary>
/// Provides context for a custom A2A run mode decision.
/// </summary>
public sealed class A2ARunDecisionContext
{
    internal A2ARunDecisionContext(MessageSendParams messageSendParams)
    {
        this.MessageSendParams = messageSendParams;
    }

    /// <summary>
    /// Gets the parameters of the incoming A2A message that triggered this run.
    /// </summary>
    public MessageSendParams MessageSendParams { get; }
}
