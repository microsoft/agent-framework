// Copyright (c) Microsoft. All rights reserved.

using System.Collections.ObjectModel;
using Harness.Shared.Console.Commands;
using Harness.Shared.Console.Observers;
using Harness.Shared.Console.ToolFormatters;
using Microsoft.Agents.AI;

namespace Harness.Shared.Console;

/// <summary>
/// Configuration options for <see cref="HarnessConsole"/>.
/// </summary>
public class HarnessConsoleOptions
{
    /// <summary>
    /// Gets or sets the list of console observers that participate in the agent response
    /// streaming lifecycle. Use the factory methods on this class to create common observer sets.
    /// When <see langword="null"/> (the default), a default set of observers is used.
    /// Set to an empty list to disable all observers.
    /// </summary>
    public IReadOnlyList<ConsoleObserver>? Observers { get; set; }

    /// <summary>
    /// Gets or sets the list of command handlers to check before sending user input to the agent.
    /// Use <see cref="BuildDefaultCommandHandlers"/> to create the default set.
    /// When <see langword="null"/> (the default), a default set of handlers is used.
    /// Set to an empty list to disable all command handlers.
    /// </summary>
    public IReadOnlyList<CommandHandler>? CommandHandlers { get; set; }

    /// <summary>
    /// The default mode-to-color mapping used when no custom <see cref="ModeColors"/> are provided.
    /// </summary>
    public static readonly IReadOnlyDictionary<string, ConsoleColor> DefaultModeColors = new ReadOnlyDictionary<string, ConsoleColor>(
        new Dictionary<string, ConsoleColor>(StringComparer.OrdinalIgnoreCase)
        {
            ["plan"] = ConsoleColor.Cyan,
            ["execute"] = ConsoleColor.Green,
        });

    /// <summary>
    /// Gets or sets a mapping of agent mode names to console colors.
    /// When a mode is not found in this dictionary, the default color (<see cref="ConsoleColor.Gray"/>) is used.
    /// </summary>
    public Dictionary<string, ConsoleColor> ModeColors { get; set; } = new(DefaultModeColors, StringComparer.OrdinalIgnoreCase);

    /// <summary>
    /// Creates the default set of observers without planning support.
    /// Includes tool call display, tool approval, error display, reasoning display,
    /// usage display, and text output.
    /// </summary>
    /// <param name="maxContextWindowTokens">Optional maximum context window size in tokens for usage display.</param>
    /// <param name="maxOutputTokens">Optional maximum output tokens for usage display.</param>
    /// <param name="toolFormatters">Optional tool call formatters. When <see langword="null"/>,
    /// each observer uses the default formatters from <see cref="ToolCallFormatter.BuildDefaultToolFormatters"/>.</param>
    /// <returns>A list of observers for a standard (non-planning) console session.</returns>
    public static List<ConsoleObserver> BuildDefaultObservers(
        int? maxContextWindowTokens = null,
        int? maxOutputTokens = null,
        IReadOnlyList<ToolCallFormatter>? toolFormatters = null)
    {
        return
        [
            new ToolCallDisplayObserver(toolFormatters),
            new ToolApprovalObserver(toolFormatters),
            new ErrorDisplayObserver(),
            new ReasoningDisplayObserver(),
            new UsageDisplayObserver(maxContextWindowTokens, maxOutputTokens),
            new TextOutputObserver(),
        ];
    }

    /// <summary>
    /// Creates the default set of observers with planning support.
    /// Includes a <see cref="PlanningOutputObserver"/> instead of <see cref="TextOutputObserver"/>.
    /// </summary>
    /// <param name="agent">The agent, used to resolve <see cref="AgentModeProvider"/>.</param>
    /// <param name="planModeName">The mode name that represents the planning mode.</param>
    /// <param name="executionModeName">The mode name to switch to when the user approves a plan.</param>
    /// <param name="modeColors">Optional mode-to-color mapping for display.
    /// Defaults to <see cref="DefaultModeColors"/> when <see langword="null"/>.</param>
    /// <param name="maxContextWindowTokens">Optional maximum context window size in tokens for usage display.</param>
    /// <param name="maxOutputTokens">Optional maximum output tokens for usage display.</param>
    /// <param name="toolFormatters">Optional tool call formatters. When <see langword="null"/>,
    /// each observer uses the default formatters from <see cref="ToolCallFormatter.BuildDefaultToolFormatters"/>.</param>
    /// <returns>A list of observers for a planning-enabled console session.</returns>
    public static List<ConsoleObserver> BuildObserversWithPlanning(
        AIAgent agent,
        string planModeName,
        string executionModeName,
        IReadOnlyDictionary<string, ConsoleColor>? modeColors = null,
        int? maxContextWindowTokens = null,
        int? maxOutputTokens = null,
        IReadOnlyList<ToolCallFormatter>? toolFormatters = null)
    {
        var modeProvider = agent.GetService<AgentModeProvider>()
            ?? throw new InvalidOperationException("Planning requires an AgentModeProvider service on the agent.");

        return
        [
            new ToolCallDisplayObserver(toolFormatters),
            new ToolApprovalObserver(toolFormatters),
            new ErrorDisplayObserver(),
            new ReasoningDisplayObserver(),
            new UsageDisplayObserver(maxContextWindowTokens, maxOutputTokens),
            new PlanningOutputObserver(modeProvider, planModeName, executionModeName, modeColors ?? DefaultModeColors),
        ];
    }

    /// <summary>
    /// Creates the default set of command handlers.
    /// Includes exit, todo, and mode command handlers.
    /// </summary>
    /// <param name="agent">The agent, used to resolve <see cref="TodoProvider"/> and <see cref="AgentModeProvider"/>.</param>
    /// <param name="modeColors">Optional mode-to-color mapping for the mode command display.
    /// Defaults to <see cref="DefaultModeColors"/> when <see langword="null"/>.</param>
    /// <returns>A list of command handlers for a standard console session.</returns>
    public static List<CommandHandler> BuildDefaultCommandHandlers(
        AIAgent agent,
        IReadOnlyDictionary<string, ConsoleColor>? modeColors = null)
    {
        var todoProvider = agent.GetService<TodoProvider>();
        var modeProvider = agent.GetService<AgentModeProvider>();

        return
        [
            new ExitCommandHandler(),
            new TodoCommandHandler(todoProvider),
            new ModeCommandHandler(modeProvider, modeColors ?? DefaultModeColors),
        ];
    }
}
