// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.GitHub.Copilot;

/// <summary>
/// Indicates the execution phase of a tool invocation in a GitHub Copilot agent session.
/// </summary>
public enum CopilotToolExecutionPhase
{
    /// <summary>The tool has started executing.</summary>
    Started,

    /// <summary>The tool reported an incremental progress update.</summary>
    Progress,

    /// <summary>The tool has finished executing.</summary>
    Completed,
}

/// <summary>
/// Represents tool execution content produced by a GitHub Copilot agent during a session.
/// </summary>
/// <remarks>
/// This content type is emitted in <see cref="AgentResponseUpdate"/> items for
/// <c>tool.execution_start</c>, <c>tool.execution_progress</c>, and <c>tool.execution_complete</c>
/// events. Use <see cref="Phase"/> to distinguish the lifecycle stage, then access the
/// phase-specific properties.
/// <code>
/// await foreach (var update in agent.RunStreamingAsync(prompt, cancellationToken: ct))
/// {
///     foreach (var tool in update.Contents.OfType&lt;CopilotToolExecutionContent&gt;())
///     {
///         switch (tool.Phase)
///         {
///             case CopilotToolExecutionPhase.Started:
///                 Console.WriteLine($"🔧 {tool.ToolName}");
///                 break;
///             case CopilotToolExecutionPhase.Progress:
///                 Console.WriteLine($"⏳ {tool.ProgressMessage}");
///                 break;
///             case CopilotToolExecutionPhase.Completed:
///                 Console.WriteLine(tool.IsSuccess ? "✅ done" : $"❌ {tool.ErrorMessage}");
///                 break;
///         }
///     }
/// }
/// </code>
/// </remarks>
public sealed class CopilotToolExecutionContent : AIContent
{
    /// <summary>
    /// Initializes a new instance of <see cref="CopilotToolExecutionContent"/> for the
    /// <see cref="CopilotToolExecutionPhase.Started"/> phase.
    /// </summary>
    /// <param name="toolCallId">Unique identifier for this tool call.</param>
    /// <param name="toolName">Name of the tool being executed.</param>
    /// <param name="arguments">Raw JSON arguments passed to the tool, or <see langword="null"/> if none.</param>
    public static CopilotToolExecutionContent ForStart(string toolCallId, string toolName, string? arguments)
        => new(CopilotToolExecutionPhase.Started, toolCallId, toolName: toolName, arguments: arguments);

    /// <summary>
    /// Initializes a new instance of <see cref="CopilotToolExecutionContent"/> for the
    /// <see cref="CopilotToolExecutionPhase.Progress"/> phase.
    /// </summary>
    /// <param name="toolCallId">Unique identifier for this tool call.</param>
    /// <param name="progressMessage">Human-readable progress status message.</param>
    public static CopilotToolExecutionContent ForProgress(string toolCallId, string progressMessage)
        => new(CopilotToolExecutionPhase.Progress, toolCallId, progressMessage: progressMessage);

    /// <summary>
    /// Initializes a new instance of <see cref="CopilotToolExecutionContent"/> for the
    /// <see cref="CopilotToolExecutionPhase.Completed"/> phase.
    /// </summary>
    /// <param name="toolCallId">Unique identifier for this tool call.</param>
    /// <param name="isSuccess"><see langword="true"/> if the tool executed successfully; <see langword="false"/> otherwise.</param>
    /// <param name="errorMessage">Error message when <paramref name="isSuccess"/> is <see langword="false"/>; otherwise <see langword="null"/>.</param>
    public static CopilotToolExecutionContent ForComplete(string toolCallId, bool isSuccess, string? errorMessage)
        => new(CopilotToolExecutionPhase.Completed, toolCallId, isSuccess: isSuccess, errorMessage: errorMessage);

    private CopilotToolExecutionContent(
        CopilotToolExecutionPhase phase,
        string toolCallId,
        string? toolName = null,
        string? arguments = null,
        string? progressMessage = null,
        bool isSuccess = true,
        string? errorMessage = null)
    {
        Phase = phase;
        ToolCallId = toolCallId;
        ToolName = toolName;
        Arguments = arguments;
        ProgressMessage = progressMessage;
        IsSuccess = isSuccess;
        ErrorMessage = errorMessage;
    }

    /// <summary>Gets the execution phase this content represents.</summary>
    public CopilotToolExecutionPhase Phase { get; }

    /// <summary>Gets the unique identifier for this tool call.</summary>
    public string ToolCallId { get; }

    /// <summary>
    /// Gets the name of the tool being executed.
    /// Non-<see langword="null"/> only when <see cref="Phase"/> is <see cref="CopilotToolExecutionPhase.Started"/>.
    /// </summary>
    public string? ToolName { get; }

    /// <summary>
    /// Gets the raw JSON arguments passed to the tool.
    /// Non-<see langword="null"/> only when <see cref="Phase"/> is <see cref="CopilotToolExecutionPhase.Started"/>
    /// and the tool was invoked with arguments.
    /// </summary>
    public string? Arguments { get; }

    /// <summary>
    /// Gets the human-readable progress status message.
    /// Non-<see langword="null"/> only when <see cref="Phase"/> is <see cref="CopilotToolExecutionPhase.Progress"/>.
    /// </summary>
    public string? ProgressMessage { get; }

    /// <summary>
    /// Gets a value indicating whether the tool executed successfully.
    /// Meaningful only when <see cref="Phase"/> is <see cref="CopilotToolExecutionPhase.Completed"/>.
    /// </summary>
    public bool IsSuccess { get; }

    /// <summary>
    /// Gets the error message when the tool execution failed.
    /// Non-<see langword="null"/> only when <see cref="Phase"/> is <see cref="CopilotToolExecutionPhase.Completed"/>
    /// and <see cref="IsSuccess"/> is <see langword="false"/>.
    /// </summary>
    public string? ErrorMessage { get; }
}
