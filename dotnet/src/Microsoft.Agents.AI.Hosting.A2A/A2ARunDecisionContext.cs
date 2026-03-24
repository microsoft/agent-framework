// Copyright (c) Microsoft. All rights reserved.

using A2A;

namespace Microsoft.Agents.AI.Hosting.A2A;

/// <summary>
/// Provides context for a custom A2A run mode decision.
/// </summary>
public sealed class A2ARunDecisionContext
{
    internal A2ARunDecisionContext(SendMessageRequest sendMessageRequest)
    {
        this.SendMessageRequest = sendMessageRequest;
    }

    /// <summary>
    /// Gets the <see cref="SendMessageRequest"/> that triggered this run.
    /// </summary>
    public SendMessageRequest SendMessageRequest { get; }
}
