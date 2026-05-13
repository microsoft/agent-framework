// Copyright (c) Microsoft. All rights reserved.

namespace Harness.Shared.Console;

/// <summary>
/// Represents the type of an output entry in the console conversation.
/// </summary>
public enum OutputEntryType
{
    /// <summary>User input echo (e.g. "You: hello").</summary>
    UserInput,

    /// <summary>In-progress streaming text from the agent (accumulated chunk by chunk).</summary>
    StreamingText,

    /// <summary>Informational line (tool calls, errors, usage, approval requests, etc.).</summary>
    InfoLine,

    /// <summary>Stream footer (e.g. "(no text response from agent)").</summary>
    StreamFooter,

    /// <summary>Pending injected message notification.</summary>
    PendingMessage,
}

/// <summary>
/// Represents a single output entry in the console conversation history.
/// These entries are rendered by the <see cref="HarnessAppComponent"/> via its render delegate.
/// </summary>
/// <param name="Type">The type of output entry.</param>
/// <param name="Text">The text content of the entry.</param>
/// <param name="Color">Optional foreground color for rendering.</param>
public record OutputEntry(OutputEntryType Type, string Text, ConsoleColor? Color = null);
