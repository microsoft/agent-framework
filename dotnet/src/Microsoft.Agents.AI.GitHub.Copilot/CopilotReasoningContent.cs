// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.GitHub.Copilot;

/// <summary>
/// Represents extended thinking (reasoning) content produced by a GitHub Copilot agent during a session.
/// </summary>
/// <remarks>
/// This content type is emitted in <see cref="AgentResponseUpdate"/> items for <c>assistant.reasoning</c> events
/// and contains the complete extended thinking text from the model. Use it when iterating over
/// streaming response updates to surface agent reasoning to users or to log it for diagnostics.
/// <code>
/// await foreach (var update in agent.RunStreamingAsync(prompt, cancellationToken: ct))
/// {
///     if (update.Contents.OfType&lt;CopilotReasoningContent&gt;().FirstOrDefault() is { } reasoning)
///         Console.WriteLine($"🧠 {reasoning.Content}");
/// }
/// </code>
/// </remarks>
public sealed class CopilotReasoningContent : AIContent
{
    /// <summary>
    /// Initializes a new instance of the <see cref="CopilotReasoningContent"/> class.
    /// </summary>
    /// <param name="content">The complete extended thinking text from the model.</param>
    /// <param name="reasoningId">The unique identifier for this reasoning block.</param>
    public CopilotReasoningContent(string content, string reasoningId)
    {
        Content = content;
        ReasoningId = reasoningId;
    }

    /// <summary>Gets the complete extended thinking text from the model.</summary>
    public string Content { get; }

    /// <summary>Gets the unique identifier for this reasoning block.</summary>
    public string ReasoningId { get; }
}
