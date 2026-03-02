// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI.Compaction;

/// <summary>
/// Identifies the kind of an atomic message group in a conversation.
/// </summary>
public enum ChatMessageGroupKind
{
    /// <summary>A system message.</summary>
    System,

    /// <summary>A user message (start of a user turn).</summary>
    UserTurn,

    /// <summary>An assistant message with tool calls and their corresponding tool result messages.</summary>
    AssistantToolGroup,

    /// <summary>An assistant message without tool calls.</summary>
    AssistantPlain,

    /// <summary>A tool result message that is not part of a recognized group.</summary>
    ToolResult,

    /// <summary>A message with an unrecognized role.</summary>
    Other
}
