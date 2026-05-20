// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Shared.DiagnosticIds;

namespace Microsoft.Agents.AI;

/// <summary>
/// An <see cref="AIContextProvider"/> that tracks the agent's operating mode (e.g., "plan" or "execute")
/// in the session state and provides tools for querying and switching modes.
/// </summary>
/// <remarks>
/// <para>
/// The <see cref="AgentModeProvider"/> enables agents to operate in distinct modes during long-running
/// complex tasks. The current mode is persisted in the session's <see cref="AgentSessionStateBag"/>
/// and is included in the instructions provided to the agent on each invocation.
/// </para>
/// <para>
/// The set of available modes is configurable via <see cref="AgentModeProviderOptions.Modes"/>.
/// By default, two modes are provided: <c>"plan"</c> (interactive planning) and <c>"execute"</c>
/// (autonomous execution).
/// </para>
/// <para>
/// This provider exposes the following tools to the agent:
/// <list type="bullet">
/// <item><description><c>AgentMode_Set</c> — Switch the agent's operating mode.</description></item>
/// <item><description><c>AgentMode_Get</c> — Retrieve the agent's current operating mode.</description></item>
/// </list>
/// </para>
/// <para>
/// Public helper methods <see cref="GetMode"/> and <see cref="SetMode"/> allow external code
/// to programmatically read and change the mode.
/// </para>
/// </remarks>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public sealed class AgentModeProvider : AIContextProvider
{
    private const string DefaultInstructions =
        """
        ## Agent Mode

        - You can operate in different modes. Depending on the mode you are in, you will be required to follow different processes.
        - You must check the current mode after any user input, since the user may have changed the mode themselves,
          e.g. the user may have switched to 'plan' mode after a previous research task finished in 'execute' mode, meaning they want to review a plan first before execution.

        Use the AgentMode_Get tool to check your current operating mode.
        Use the AgentMode_Set tool to switch between modes as your work progresses. Only use AgentMode_Set if the user explicitly instructs/allows you to change modes.

        You are currently operating in the {current_mode} mode.

        ### Mandatory Mode based Workflow

        For every new substantive user request, including short factual questions, your behavior is determined by the mode you are in.

        {available_modes}
        """;

    private static readonly IReadOnlyList<AgentModeProviderOptions.AgentMode> s_defaultModes =
    [
        new(
            "plan",
            """
            Use this mode when analyzing requirements, breaking down tasks, and creating plans. This is the interactive mode — ask clarifying questions, discuss options, and get user approval before proceeding.

            Process to follow when in plan mode:
            1. Analyze the request with the purpose of building a research plan.
            2. Create a list of todo items.
            3. If needed, use the provided tools to do some exploratory checks to help build a plan and determine what clarifying questions you may need from the user.
            4. Ask for clarifications from the user where needed.
              1. Ask each clarification one by one.
              2. When asking for clarification and you have specific options in mind, present them to the user, so they can choose the option instead of having to retype the entire response.
              3. Do not proceed until you have received all the needed clarifications.
              4. Do short exploratory research if it helps with being able to ask sensible clarifications from the user.
            5. Write the plan to a memory file, so that it is retained even if compaction happens. Make sure to update the plan file if the user requests changes.
            6. Present the plan to the user and ask for approval to switch to execute mode and process the plan.
            7. When approval is granted, always switch to execute mode (using the `AgentMode_Set` tool), and follow the steps for *Execute mode*.
            """),
        new(
            "execute",
            """
            Use this mode when carrying out approved plans. Work autonomously using your best judgment — do not ask the user questions or wait for feedback.
            
            Process to follow when in execute mode:
            1. If you don't have a plan or tasks yet, analyze the user request and create tasks and a plan. (**Skip this step if you came from plan mode**)
            2. Work autonomously — use your best judgment to make decisions and keep progressing without asking the user questions. The goal is to have a complete, useful result ready when the user returns.
            3. If you encounter ambiguity or an unexpected situation during execution, choose the most reasonable option, note your choice, and keep going.
            4. Mark tasks as completed as you finish them.
            5. Continue working, thinking and calling tools until you have the research result for the user.
            """),
    ];

    private readonly ProviderSessionState<AgentModeState> _sessionState;
    private readonly IReadOnlyList<AgentModeProviderOptions.AgentMode> _modes;
    private readonly string _defaultMode;
    private readonly string? _instructions;
    private readonly HashSet<string> _validModeNames;
    private readonly string _modeNamesDisplay;
    private IReadOnlyList<string>? _stateKeys;

    /// <summary>
    /// Initializes a new instance of the <see cref="AgentModeProvider"/> class.
    /// </summary>
    /// <param name="options">Optional settings that control provider behavior. When <see langword="null"/>, defaults are used.</param>
    public AgentModeProvider(AgentModeProviderOptions? options = null)
    {
        this._modes = options?.Modes ?? s_defaultModes;

        if (this._modes.Count == 0)
        {
            throw new ArgumentException("At least one mode must be configured.", nameof(options));
        }

        this._instructions = options?.Instructions ?? DefaultInstructions;

        this._validModeNames = new HashSet<string>(StringComparer.Ordinal);
        var modeNamesList = new List<string>(this._modes.Count);
        for (int i = 0; i < this._modes.Count; i++)
        {
            var mode = this._modes[i];
            if (mode is null)
            {
                throw new ArgumentException($"Configured mode at index {i} must not be null.", nameof(options));
            }

            if (string.IsNullOrEmpty(mode.Name))
            {
                throw new ArgumentException($"Configured mode at index {i} must have a non-empty name.", nameof(options));
            }

            if (!this._validModeNames.Add(mode.Name))
            {
                throw new ArgumentException($"Configured modes contain a duplicate mode name \"{mode.Name}\".", nameof(options));
            }

            modeNamesList.Add(mode.Name);
        }

        this._modeNamesDisplay = string.Join("\", \"", modeNamesList);
        this._defaultMode = options?.DefaultMode ?? modeNamesList[0];

        if (!this._validModeNames.Contains(this._defaultMode))
        {
            throw new ArgumentException($"Default mode \"{this._defaultMode}\" is not in the configured modes list.", nameof(options));
        }

        this._sessionState = new ProviderSessionState<AgentModeState>(
            _ => new AgentModeState { CurrentMode = this._defaultMode },
            this.GetType().Name,
            AgentJsonUtilities.DefaultOptions);
    }

    /// <inheritdoc />
    public override IReadOnlyList<string> StateKeys => this._stateKeys ??= [this._sessionState.StateKey];

    /// <summary>
    /// Gets the current operating mode from the session state.
    /// </summary>
    /// <param name="session">The agent session to read the mode from.</param>
    /// <returns>The current mode string.</returns>
    public string GetMode(AgentSession? session)
    {
        return this._sessionState.GetOrInitializeState(session).CurrentMode;
    }

    /// <summary>
    /// Sets the operating mode in the session state.
    /// </summary>
    /// <param name="session">The agent session to update the mode in.</param>
    /// <param name="mode">The new mode to set.</param>
    /// <exception cref="ArgumentException"><paramref name="mode"/> is not a configured mode.</exception>
    public void SetMode(AgentSession? session, string mode)
    {
        this.ValidateMode(mode);

        AgentModeState state = this._sessionState.GetOrInitializeState(session);
        string previousMode = state.CurrentMode;
        state.CurrentMode = mode;

        if (!string.Equals(previousMode, mode, StringComparison.Ordinal))
        {
            state.PreviousModeForNotification = previousMode;
        }

        this._sessionState.SaveState(session, state);
    }

    /// <inheritdoc />
    protected override ValueTask<AIContext> ProvideAIContextAsync(InvokingContext context, CancellationToken cancellationToken = default)
    {
        AgentModeState state = this._sessionState.GetOrInitializeState(context.Session);

        string instructions = this.BuildInstructions(state.CurrentMode);

        var aiContext = new AIContext
        {
            Instructions = instructions,
            Tools = this.CreateTools(state, context.Session),
        };

        // If the mode was changed externally (e.g., via /mode command), inject a notification message
        // so the agent clearly sees the change rather than relying solely on the system instructions.
        if (state.PreviousModeForNotification != null)
        {
            string previousMode = state.PreviousModeForNotification;
            state.PreviousModeForNotification = null;

            aiContext.Messages =
            [
                new ChatMessage(ChatRole.User, $"[Mode changed: The operating mode has been switched from \"{previousMode}\" to \"{state.CurrentMode}\". You must now adjust your behavior to match the \"{state.CurrentMode}\" mode.]"),
            ];
        }

        return new ValueTask<AIContext>(aiContext);
    }

    private string BuildInstructions(string currentMode)
    {
        var modesListBuilder = new StringBuilder();
        foreach (var mode in this._modes)
        {
            modesListBuilder.AppendLine($"#### {mode.Name}");
            modesListBuilder.AppendLine();
            modesListBuilder.AppendLine(mode.Description.TrimEnd());
            modesListBuilder.AppendLine();
        }

        var modesListText = modesListBuilder.ToString();

        return new StringBuilder(this._instructions)
            .Replace("{available_modes}", modesListText)
            .Replace("{current_mode}", currentMode)
            .ToString();
    }

    private void ValidateMode(string mode)
    {
        if (!this._validModeNames.Contains(mode))
        {
            throw new ArgumentException($"Invalid mode: \"{mode}\". Supported modes are: \"{this._modeNamesDisplay}\".", nameof(mode));
        }
    }

    private AITool[] CreateTools(AgentModeState state, AgentSession? session)
    {
        var serializerOptions = AgentJsonUtilities.DefaultOptions;

        return
        [
            AIFunctionFactory.Create(
                (string mode) =>
                {
                    this.ValidateMode(mode);

                    state.CurrentMode = mode;
                    this._sessionState.SaveState(session, state);
                    return $"Mode changed to \"{mode}\".";
                },
                new AIFunctionFactoryOptions
                {
                    Name = "AgentMode_Set",
                    Description = $"Switch the agent's operating mode. Supported modes: \"{this._modeNamesDisplay}\".",
                    SerializerOptions = serializerOptions,
                }),

            AIFunctionFactory.Create(
                () => state.CurrentMode,
                new AIFunctionFactoryOptions
                {
                    Name = "AgentMode_Get",
                    Description = "Get the agent's current operating mode.",
                    SerializerOptions = serializerOptions,
                }),
        ];
    }
}
