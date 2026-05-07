// Copyright (c) Microsoft. All rights reserved.

namespace Harness.Shared.Console;

/// <summary>
/// Configuration options for <see cref="HarnessConsole"/>.
/// </summary>
public class HarnessConsoleOptions
{
    /// <summary>
    /// Gets or sets the optional maximum context window size in tokens.
    /// When set, token usage is displayed as a percentage of the budget.
    /// </summary>
    public int? MaxContextWindowTokens { get; set; }

    /// <summary>
    /// Gets or sets the optional maximum output tokens.
    /// Used with <see cref="MaxContextWindowTokens"/> to show input/output budget breakdown.
    /// </summary>
    public int? MaxOutputTokens { get; set; }

    /// <summary>
    /// Gets or sets a value indicating whether the planning UX is enabled.
    /// When <see langword="true"/> and the agent is in the mode specified by <see cref="PlanningModeName"/>,
    /// the console uses structured output to present clarification questions and approval requests
    /// instead of streaming free-form text.
    /// </summary>
    /// <value>Defaults to <see langword="false"/>.</value>
    public bool EnablePlanningUx { get; set; }

    /// <summary>
    /// Gets or sets the name of the agent mode that activates the planning UX.
    /// Must be set when <see cref="EnablePlanningUx"/> is <see langword="true"/>.
    /// </summary>
    public string? PlanningModeName { get; set; }

    /// <summary>
    /// Gets or sets the name of the agent mode to switch to when the user approves a plan.
    /// Must be set when <see cref="EnablePlanningUx"/> is <see langword="true"/>.
    /// </summary>
    public string? ExecutionModeName { get; set; }

    /// <summary>
    /// Gets or sets a mapping of agent mode names to console colors.
    /// When a mode is not found in this dictionary, the default color (<see cref="ConsoleColor.Gray"/>) is used.
    /// </summary>
    public Dictionary<string, ConsoleColor> ModeColors { get; set; } = new(StringComparer.OrdinalIgnoreCase)
    {
        ["plan"] = ConsoleColor.Cyan,
        ["execute"] = ConsoleColor.Green,
    };
}
