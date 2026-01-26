// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.Workflows;

namespace SingleAgent;

/// <summary>
/// Event emitted when an email is sent.
/// </summary>
public sealed class EmailSentEvent(string email, string subject) : WorkflowEvent($"Email sent to {email}")
{
    public string Email { get; } = email;
    public string Subject { get; } = subject;
}
