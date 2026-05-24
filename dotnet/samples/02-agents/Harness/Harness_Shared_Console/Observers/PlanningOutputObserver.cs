// Copyright (c) Microsoft. All rights reserved.

using System.Text;
using System.Text.Json;
using Harness.ConsoleReactiveComponents;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;

namespace Harness.Shared.Console.Observers;

/// <summary>
/// Planning observer that is mode-aware: in planning mode it configures structured
/// JSON output, collects streamed text, and deserializes it as a <see cref="PlanningResponse"/>;
/// in execution mode it passes text straight through to <see cref="IUXStateDriver.WriteTextAsync"/>
/// for live streaming display.
/// </summary>
public sealed class PlanningOutputObserver : ConsoleObserver
{
    private readonly StringBuilder _textCollector = new();
    private readonly AgentModeProvider _modeProvider;
    private readonly string _planModeName;
    private readonly string _executionModeName;
    private readonly IReadOnlyDictionary<string, ConsoleColor>? _modeColors;

    /// <summary>
    /// Initializes a new instance of the <see cref="PlanningOutputObserver"/> class.
    /// </summary>
    /// <param name="modeProvider">The mode provider for switching modes on approval.</param>
    /// <param name="planModeName">The mode name that represents the planning mode.</param>
    /// <param name="executionModeName">The mode name to switch to when the user approves a plan.</param>
    /// <param name="modeColors">Optional mode-to-color mapping for display.</param>
    public PlanningOutputObserver(AgentModeProvider modeProvider, string planModeName, string executionModeName, IReadOnlyDictionary<string, ConsoleColor>? modeColors = null)
    {
        this._modeProvider = modeProvider;
        this._planModeName = planModeName;
        this._executionModeName = executionModeName;
        this._modeColors = modeColors;
    }

    /// <inheritdoc/>
    public override void ConfigureRunOptions(AgentRunOptions options, AIAgent agent, AgentSession session)
    {
        if (this.IsPlanningMode(this._modeProvider.GetMode(session)))
        {
            options.ResponseFormat = ChatResponseFormat.ForJsonSchema<PlanningResponse>();
        }
    }

    /// <inheritdoc/>
    public override Task OnTextAsync(IUXStateDriver ux, string text, AIAgent agent, AgentSession session)
    {
        if (this.IsPlanningMode(ux.CurrentMode))
        {
            // Planning mode: collect text silently for JSON parsing after the stream.
            this._textCollector.Append(text);
            return Task.CompletedTask;
        }

        // Execution mode: stream text directly to the console.
        return ux.WriteTextAsync(text);
    }

    /// <inheritdoc/>
    public override async Task<IList<FollowUpAction>?> OnStreamCompleteAsync(
        IUXStateDriver ux,
        AIAgent agent,
        AgentSession session)
    {
        if (!this.IsPlanningMode(ux.CurrentMode))
        {
            // Execution mode: text was already streamed live; nothing to parse.
            this._textCollector.Clear();
            return null;
        }

        // Read collected text from our stream observation.
        string collectedText = this._textCollector.ToString();
        this._textCollector.Clear();

        if (string.IsNullOrWhiteSpace(collectedText))
        {
            return null;
        }

        // Deserialize the structured response.
        PlanningResponse? planningResponse;
        try
        {
            planningResponse = JsonSerializer.Deserialize<PlanningResponse>(collectedText);
        }
        catch (JsonException ex)
        {
            await ux.WriteInfoLineAsync($"❌ Failed to parse planning response: {ex.Message}", ConsoleColor.Red);
            await ux.WriteInfoLineAsync($"(raw response) {collectedText}", ConsoleColor.DarkYellow);
            return null;
        }

        if (planningResponse is null)
        {
            await ux.WriteInfoLineAsync("(no structured response from agent)", ConsoleColor.DarkYellow);
            return null;
        }

        if (planningResponse.Type == PlanningResponseType.Clarification)
        {
            return BuildClarificationActions(planningResponse);
        }

        if (planningResponse.Type == PlanningResponseType.Approval)
        {
            var question = planningResponse.Questions.FirstOrDefault();
            if (question is null)
            {
                await ux.WriteInfoLineAsync("(approval response had no content)", ConsoleColor.DarkYellow);
                return null;
            }

            return new List<FollowUpAction> { this.BuildApprovalAction(question, session) };
        }

        await ux.WriteInfoLineAsync($"(unexpected response type: {planningResponse.Type})", ConsoleColor.DarkYellow);
        return null;
    }

    private static List<FollowUpAction> BuildClarificationActions(PlanningResponse response)
    {
        var actions = new List<FollowUpAction>(response.Questions.Count);

        foreach (var question in response.Questions)
        {
            string prompt = question.Message;

            async Task<ChatMessage?> Continuation(string answer, IUXStateDriver ux)
            {
                if (string.IsNullOrWhiteSpace(answer))
                {
                    string noAnswer = $"🔹 {prompt}\n   └─ {AnsiEscapes.SetForegroundColor(ConsoleColor.DarkGray)}(no answer){AnsiEscapes.ResetAttributes}";
                    await ux.WriteInfoLineAsync(noAnswer, ConsoleColor.Gray).ConfigureAwait(false);
                    return null;
                }

                string formatted = $"🔹 {prompt}\n   └─ {AnsiEscapes.SetForegroundColor(ConsoleColor.Green)}{answer}{AnsiEscapes.ResetAttributes}";
                await ux.WriteInfoLineAsync(formatted, ConsoleColor.Gray).ConfigureAwait(false);

                return new ChatMessage(ChatRole.User, $"Q: {prompt}\nA: {answer}");
            }

            if (question.Choices is { Count: > 0 })
            {
                actions.Add(new ChoiceFollowUpQuestion(
                    Prompt: prompt,
                    Choices: question.Choices,
                    AllowCustomText: true,
                    Continuation: Continuation));
            }
            else
            {
                actions.Add(new TextFollowUpQuestion(
                    Prompt: prompt,
                    Continuation: Continuation));
            }
        }

        return actions;
    }

    private ChoiceFollowUpQuestion BuildApprovalAction(PlanningQuestion question, AgentSession session)
    {
        const string ApproveOption = "Approve and switch to execute mode";
        var choices = new List<string> { ApproveOption };

        return new ChoiceFollowUpQuestion(
            Prompt: question.Message,
            Choices: choices,
            AllowCustomText: true,
            Continuation: async (selection, ux) =>
            {
                string formatted = $"🔹 {question.Message}\n   └─ {AnsiEscapes.SetForegroundColor(ConsoleColor.Green)}{selection}{AnsiEscapes.ResetAttributes}";
                await ux.WriteInfoLineAsync(formatted, ConsoleColor.Gray).ConfigureAwait(false);

                if (selection == ApproveOption)
                {
                    this._modeProvider.SetMode(session, this._executionModeName);
                    await ux.WriteInfoLineAsync(
                        $"✅ Switched to {this._executionModeName} mode.",
                        ModeColors.Get(this._executionModeName, this._modeColors)).ConfigureAwait(false);
                    return new ChatMessage(ChatRole.User, "Approved");
                }

                // Custom freeform input — treat as suggested changes.
                return new ChatMessage(ChatRole.User, selection);
            });
    }

    /// <summary>
    /// Returns <see langword="true"/> when the current mode matches the configured plan mode name.
    /// A <see langword="null"/> mode (no mode provider) is also treated as planning mode.
    /// </summary>
    private bool IsPlanningMode(string? currentMode) =>
        currentMode is null || string.Equals(currentMode, this._planModeName, StringComparison.OrdinalIgnoreCase);
}
