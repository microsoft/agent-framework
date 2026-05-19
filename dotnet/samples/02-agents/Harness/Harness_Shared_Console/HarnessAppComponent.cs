// Copyright (c) Microsoft. All rights reserved.

using Harness.ConsoleReactiveComponents;
using Harness.ConsoleReactiveFramework;
using Harness.Shared.Console.Components;
using Microsoft.Extensions.AI;

namespace Harness.Shared.Console;

/// <summary>
/// The main application component for the Harness console. Manages the scroll region
/// and bottom panel (text input, list selection, or streaming indicator). Owns the
/// <see cref="HarnessConsoleUXStateDriver"/> and routes user input events to the
/// registered <see cref="HarnessAgentRunner"/>.
/// </summary>
public class HarnessAppComponent : ConsoleReactiveComponent<ConsoleReactiveProps, HarnessAppComponentState>, IDisposable
{
    private readonly TopBottomRule _rule = new();
    private readonly ListSelection _listSelection = new();
    private readonly TextInput _textInput = new();
    private readonly TextScrollPanel _textScrollPanel = new();
    private readonly TextPanel _textPanel = new();
    private readonly TextPanel _queuedPanel = new();
    private readonly AgentStatus _agentStatus = new();
    private readonly AgentModeAndHelp _modeAndHelp = new();
    private readonly HarnessConsoleUXStateDriver _uxDriver;
    private readonly TaskCompletionSource<bool> _shutdownTcs = new(TaskCreationOptions.RunContinuationsAsynchronously);
    private readonly SemaphoreSlim _followUpGate = new(1, 1);
    private int _scrollRegionBottom;
    private bool _resizedSinceLastRender = true;
    private bool _deactivated;

    /// <summary>
    /// Initializes a new instance of the <see cref="HarnessAppComponent"/> class.
    /// </summary>
    /// <param name="placeholder">Placeholder text shown when the input is empty.</param>
    /// <param name="initialMode">The current agent mode, used to colour the rule and prompt.</param>
    /// <param name="inputEnabled">Whether the bottom-panel input accepts keystrokes during streaming.</param>
    /// <param name="runnerFactory">Factory invoked with the component's <see cref="IUXStateDriver"/>
    /// to construct the <see cref="HarnessAgentRunner"/> that owns the agent loop.</param>
    /// <param name="modeColors">Optional mapping of mode names to console colors.</param>
    public HarnessAppComponent(
        string placeholder,
        string? initialMode,
        bool inputEnabled,
        Func<IUXStateDriver, HarnessAgentRunner> runnerFactory,
        IReadOnlyDictionary<string, ConsoleColor>? modeColors = null)
    {
        this.Props = new ConsoleReactiveProps();
        this.State = new HarnessAppComponentState
        {
            Mode = BottomPanelMode.TextInput,
            Prompt = "> ",
            Placeholder = placeholder,
            ModeColor = ModeColors.Get(initialMode, modeColors),
            ModeText = initialMode,
            InputEnabled = inputEnabled,
            ConsoleWidth = System.Console.WindowWidth,
            ConsoleHeight = System.Console.WindowHeight,
        };

        this._uxDriver = new HarnessConsoleUXStateDriver(
            getState: () => this.State!,
            setState: s => this.SetState(s),
            requestShutdown: () => this._shutdownTcs.TrySetResult(true),
            replaceSession: s => this.Runner!.ReplaceSessionAsync(s),
            modeColors: modeColors);

        this.Runner = runnerFactory(this._uxDriver);

        // Seed help text now that the runner (which knows the registered command handlers)
        // is available. Direct assignment — no Render is triggered until the caller invokes Render().
        this.State = this.State with { HelpText = this.Runner.HelpText };

        KeyEventListener.Instance.KeyPressed += this.OnKeyPressed;
        ConsoleResizeListener.Instance.ConsoleResized += this.OnConsoleResized;
    }

    /// <summary>
    /// Gets the agent runner that owns the agent loop. Constructed by the factory
    /// passed to the component's constructor.
    /// </summary>
    public HarnessAgentRunner Runner { get; }

    /// <summary>
    /// Completes when a command handler requests application shutdown (e.g. the user types <c>/exit</c>).
    /// Awaited by <see cref="HarnessConsole.RunAgentAsync"/>.
    /// </summary>
    public Task ShutdownTask => this._shutdownTcs.Task;

    /// <summary>
    /// Deactivates the component, resetting the scroll region and unsubscribing from events.
    /// This method is idempotent and safe to call multiple times.
    /// </summary>
    public void Deactivate()
    {
        if (this._deactivated)
        {
            return;
        }

        this._deactivated = true;
        this._agentStatus.Dispose();
        KeyEventListener.Instance.KeyPressed -= this.OnKeyPressed;
        ConsoleResizeListener.Instance.ConsoleResized -= this.OnConsoleResized;
    }

    /// <inheritdoc/>
    public void Dispose()
    {
        this.Dispose(true);
        GC.SuppressFinalize(this);
    }

    /// <summary>
    /// Releases managed resources.
    /// </summary>
    /// <param name="disposing"><c>true</c> to release managed resources.</param>
    protected virtual void Dispose(bool disposing)
    {
        if (disposing)
        {
            this.Deactivate();
            this._followUpGate.Dispose();
            this.Runner.Dispose();
        }
    }

    private void OnKeyPressed(object? sender, KeyPressEventArgs e)
    {
        BottomPanelMode mode = this.State!.Mode;
        if (mode == BottomPanelMode.TextInput)
        {
            this.HandleTextInputKey(e);
        }
        else if (mode == BottomPanelMode.ListSelection)
        {
            this.HandleListSelectionKey(e);
        }
        else if (mode == BottomPanelMode.Streaming && this.State.InputEnabled)
        {
            this.HandleStreamingInputKey(e);
        }
    }

    private void HandleTextInputKey(KeyPressEventArgs e)
    {
        if (e.KeyInfo.Key == ConsoleKey.Enter)
        {
            string text = this.State!.InputText;
            if (string.IsNullOrWhiteSpace(text))
            {
                return;
            }

            this.SetState(this.State with { InputText = "" });
            this.DispatchTextInputSubmission(text);
        }
        else if (e.KeyInfo.Key == ConsoleKey.Backspace)
        {
            if (this.State!.InputText.Length > 0)
            {
                this.SetState(this.State with { InputText = this.State.InputText[..^1] });
            }
        }
        else if (e.KeyInfo.KeyChar != '\0' && !char.IsControl(e.KeyInfo.KeyChar))
        {
            this.SetState(this.State! with { InputText = this.State.InputText + e.KeyInfo.KeyChar });
        }
    }

    private void HandleListSelectionKey(KeyPressEventArgs e)
    {
        int maxIndex = this.State!.ListSelectionOptions.Count - 1;
        if (this.State.ListSelectionCustomTextPlaceholder != null)
        {
            maxIndex = this.State.ListSelectionOptions.Count;
        }

        bool isOnCustomTextOption = this.State.ListSelectionCustomTextPlaceholder != null
            && this.State.ListSelectionIndex == this.State.ListSelectionOptions.Count;

        if (e.KeyInfo.Key == ConsoleKey.UpArrow)
        {
            this.SetState(this.State with { ListSelectionIndex = Math.Max(0, this.State.ListSelectionIndex - 1) });
        }
        else if (e.KeyInfo.Key == ConsoleKey.DownArrow)
        {
            this.SetState(this.State with { ListSelectionIndex = Math.Min(maxIndex, this.State.ListSelectionIndex + 1) });
        }
        else if (e.KeyInfo.Key == ConsoleKey.Enter)
        {
            string result = isOnCustomTextOption
                ? this.State.ListSelectionCustomInputText
                : this.State.ListSelectionOptions[this.State.ListSelectionIndex];

            this.SetState(this.State with { ListSelectionCustomInputText = "", ListSelectionIndex = 0 });
            this.DispatchListSelectionSubmission(result);
        }
        else if (isOnCustomTextOption)
        {
            if (e.KeyInfo.Key == ConsoleKey.Backspace)
            {
                if (this.State.ListSelectionCustomInputText.Length > 0)
                {
                    this.SetState(this.State with { ListSelectionCustomInputText = this.State.ListSelectionCustomInputText[..^1] });
                }
            }
            else if (e.KeyInfo.KeyChar != '\0' && !char.IsControl(e.KeyInfo.KeyChar))
            {
                this.SetState(this.State with { ListSelectionCustomInputText = this.State.ListSelectionCustomInputText + e.KeyInfo.KeyChar });
            }
        }
    }

    private void HandleStreamingInputKey(KeyPressEventArgs e)
    {
        if (e.KeyInfo.Key == ConsoleKey.Enter)
        {
            string text = this.State!.InputText;
            if (string.IsNullOrWhiteSpace(text))
            {
                return;
            }

            this.SetState(this.State with { InputText = "" });
            _ = this.Runner.OnStreamingInputAsync(text);
        }
        else if (e.KeyInfo.Key == ConsoleKey.Backspace)
        {
            if (this.State!.InputText.Length > 0)
            {
                this.SetState(this.State with { InputText = this.State.InputText[..^1] });
            }
        }
        else if (e.KeyInfo.KeyChar != '\0' && !char.IsControl(e.KeyInfo.KeyChar))
        {
            this.SetState(this.State! with { InputText = this.State.InputText + e.KeyInfo.KeyChar });
        }
    }

    private void DispatchTextInputSubmission(string text)
    {
        if (this.State!.PendingQuestions.Count > 0)
        {
            _ = this.HandleFollowUpAnswerAsync(text);
        }
        else
        {
            _ = this.Runner.OnUserInputAsync(text);
        }
    }

    private void DispatchListSelectionSubmission(string text)
    {
        // List selection is only used to answer FollowUpQuestions.
        _ = this.HandleFollowUpAnswerAsync(text);
    }

    /// <summary>
    /// Handles a user answer to the head of the pending follow-up question queue:
    /// awaits the question's continuation (which is responsible for echoing both the
    /// question and answer to the scroll area as it sees fit), appends any returned
    /// chat message to the response accumulator, advances the queue, and — when the
    /// queue empties — drains the accumulator and resumes the runner.
    /// </summary>
    private async Task HandleFollowUpAnswerAsync(string text)
    {
        IReadOnlyList<ChatMessage>? messagesToSend = null;

        await this._followUpGate.WaitAsync().ConfigureAwait(false);
        try
        {
            HarnessConsoleUXStateDriver ux = this._uxDriver;
            IReadOnlyList<FollowUpQuestion> queue = this.State!.PendingQuestions;
            if (queue.Count == 0)
            {
                return;
            }

            FollowUpQuestion head = queue[0];

            ChatMessage? response;
            try
            {
                response = await head.Continuation(text, ux).ConfigureAwait(false);
            }
            catch (Exception ex)
            {
                await ux.WriteInfoLineAsync($"❌ Follow-up handler error: {ex.GetType().Name}: {ex.Message}", ConsoleColor.Red).ConfigureAwait(false);
                response = null;
            }

            if (response is not null)
            {
                ux.AddFollowUpResponse(response);
            }

            ux.AdvanceFollowUpQuestion();

            if (this.State!.PendingQuestions.Count == 0)
            {
                messagesToSend = ux.TakeFollowUpResponses();
            }
        }
        finally
        {
            this._followUpGate.Release();
        }

        // Resume the agent outside the gate — StartAgentTurnAsync runs the full agent
        // loop which may queue new follow-up questions (re-entering this method).
        if (messagesToSend is not null)
        {
            try
            {
                await this.Runner.StartAgentTurnAsync([.. messagesToSend]).ConfigureAwait(false);
            }
            catch (Exception ex)
            {
                await this._uxDriver.WriteInfoLineAsync($"❌ Agent error: {ex.GetType().Name}: {ex.Message}", ConsoleColor.Red).ConfigureAwait(false);
            }
        }
    }

    private void OnConsoleResized(object? sender, ConsoleResizeEventArgs e)
    {
        this._resizedSinceLastRender = true;
        this.SetState(this.State! with
        {
            ConsoleWidth = e.NewWidth,
            ConsoleHeight = e.NewHeight,
        });
    }

    /// <inheritdoc />
    public override void RenderCore(ConsoleReactiveProps props, HarnessAppComponentState state)
    {
        if (this._deactivated)
        {
            return;
        }

        // Determine the text panel height for the last scroll item
        IReadOnlyList<string> lastItems = state.ScrollAreaContentItems.Count > 0
            ? [state.ScrollAreaContentItems[^1]]
            : [];
        int textPanelHeight = TextPanel.CalculateHeight(lastItems);
        if (textPanelHeight > 0)
        {
            textPanelHeight++; // Extra line for spacing between text panel and rule
        }

        // Calculate queued items panel height
        int queuedPanelHeight = TextPanel.CalculateHeight(state.QueuedItems);

        // Build the bottom panel child based on mode
        ConsoleReactiveComponent bottomChild;
        int bottomChildHeight;

        if (state.Mode == BottomPanelMode.ListSelection)
        {
            var listProps = new ListSelectionProps
            {
                Title = state.ListSelectionTitle,
                Items = state.ListSelectionOptions,
                SelectedIndex = state.ListSelectionIndex,
                HighlightColor = state.ListHighlightColor,
                CustomTextPlaceholder = state.ListSelectionCustomTextPlaceholder,
                CustomText = state.ListSelectionCustomInputText,
            };

            bottomChildHeight = ListSelection.CalculateHeight(listProps);
            this._listSelection.Height = bottomChildHeight;
            this._listSelection.Props = listProps;
            bottomChild = this._listSelection;
        }
        else if (state.Mode == BottomPanelMode.Streaming)
        {
            TextInputProps textInputProps;
            if (state.InputEnabled)
            {
                textInputProps = new TextInputProps
                {
                    Prompt = state.Prompt,
                    Text = state.InputText,
                    Placeholder = state.Placeholder,
                };
            }
            else
            {
                textInputProps = new TextInputProps
                {
                    Prompt = state.Prompt,
                    Text = "",
                    Placeholder = state.StreamingPrompt,
                };
            }

            bottomChildHeight = TextInput.CalculateHeight(textInputProps, state.ConsoleWidth);
            this._textInput.Width = state.ConsoleWidth;
            this._textInput.Height = bottomChildHeight;
            this._textInput.Props = textInputProps;
            bottomChild = this._textInput;
        }
        else
        {
            var textInputProps = new TextInputProps
            {
                Prompt = state.Prompt,
                Text = state.InputText,
                Placeholder = state.Placeholder,
            };

            bottomChildHeight = TextInput.CalculateHeight(textInputProps, state.ConsoleWidth);
            this._textInput.Width = state.ConsoleWidth;
            this._textInput.Height = bottomChildHeight;
            this._textInput.Props = textInputProps;
            bottomChild = this._textInput;
        }

        var ruleProps = new TopBottomRuleProps
        {
            Width = state.ConsoleWidth,
            Color = state.ModeColor,
            Children = [bottomChild],
        };

        var agentStatusProps = new AgentStatusProps
        {
            ShowSpinner = state.ShowSpinner,
            UsageText = state.UsageText,
        };

        var modeAndHelpProps = new AgentModeAndHelpProps
        {
            Mode = state.ModeText,
            ModeColor = state.ModeColor,
            HelpText = state.HelpText,
        };

        // Hide agent status and mode/help during follow-up questions (ListSelection mode)
        // as they clutter the UI and aren't relevant.
        bool showStatusAndHelp = state.Mode != BottomPanelMode.ListSelection;
        int agentStatusHeight = showStatusAndHelp ? AgentStatus.CalculateHeight(agentStatusProps) : 0;
        int modeAndHelpHeight = showStatusAndHelp ? AgentModeAndHelp.CalculateHeight(modeAndHelpProps) : 0;

        int ruleHeight = TopBottomRule.CalculateHeight(ruleProps);
        int nonScrollHeight = ruleHeight + textPanelHeight + agentStatusHeight + queuedPanelHeight + modeAndHelpHeight + 1; // +1 for bottom padding
        int scrollBottom = Math.Max(1, state.ConsoleHeight - nonScrollHeight);

        // If scroll region changed or a clear is needed, reset everything
        if (this._resizedSinceLastRender || (this._scrollRegionBottom != 0 && scrollBottom != this._scrollRegionBottom))
        {
            // Reset scroll region to full screen before erasing so the erase covers all rows —
            // some terminals only erase within the active DECSTBM region.
            System.Console.Write(AnsiEscapes.ResetScrollRegion);
            System.Console.Write(AnsiEscapes.EraseEntireScreen);
            System.Console.Write(AnsiEscapes.EraseScrollbackBuffer);
            this._textScrollPanel.Reset();
            this._resizedSinceLastRender = false;
        }

        this._scrollRegionBottom = scrollBottom;

        System.Console.Write(AnsiEscapes.SetScrollRegion(scrollBottom));

        // Render text scroll panel in the scroll area (all items except the last)
        IReadOnlyList<string> scrollItems = state.ScrollAreaContentItems.Count > 1
            ? state.ScrollAreaContentItems.Take(state.ScrollAreaContentItems.Count - 1).ToList()
            : [];

        this._textScrollPanel.X = 1;
        this._textScrollPanel.Y = 1;
        this._textScrollPanel.Width = state.ConsoleWidth;
        this._textScrollPanel.Height = scrollBottom;
        this._textScrollPanel.Props = new TextScrollPanelProps
        {
            Items = scrollItems,
        };
        this._textScrollPanel.Render();

        // Render the text panel for the last (dynamic) item just below the scroll region
        this._textPanel.X = 1;
        this._textPanel.Y = scrollBottom + 1;
        this._textPanel.Width = state.ConsoleWidth;
        this._textPanel.Height = textPanelHeight;
        this._textPanel.Props = new TextPanelProps
        {
            Items = lastItems,
        };
        this._textPanel.Render();

        // Render queued input items between text panel and agent status
        int queuedPanelY = scrollBottom + textPanelHeight + 1;
        this._queuedPanel.X = 1;
        this._queuedPanel.Y = queuedPanelY;
        this._queuedPanel.Width = state.ConsoleWidth;
        this._queuedPanel.Height = queuedPanelHeight;
        this._queuedPanel.Props = new TextPanelProps
        {
            Items = state.QueuedItems,
        };
        this._queuedPanel.Render();

        // Render the agent status line between queued items and rule
        int agentStatusY = queuedPanelY + queuedPanelHeight;
        if (showStatusAndHelp)
        {
            this._agentStatus.X = 1;
            this._agentStatus.Y = agentStatusY;
            this._agentStatus.Width = state.ConsoleWidth;
            this._agentStatus.Height = agentStatusHeight;
            this._agentStatus.Props = agentStatusProps;
            this._agentStatus.Render();
        }

        // Render the bottom rule + child below the agent status
        this._rule.X = 1;
        this._rule.Y = agentStatusY + agentStatusHeight;
        this._rule.Props = ruleProps;
        this._rule.Render();

        // Render the mode-and-help line below the bottom rule
        if (showStatusAndHelp)
        {
            int modeAndHelpY = this._rule.Y + ruleHeight;
            this._modeAndHelp.X = 1;
            this._modeAndHelp.Y = modeAndHelpY;
            this._modeAndHelp.Width = state.ConsoleWidth;
            this._modeAndHelp.Height = modeAndHelpHeight;
            this._modeAndHelp.Props = modeAndHelpProps;
            this._modeAndHelp.Render();
        }

        // Position cursor for natural typing appearance
        this.PositionCursor(state);
    }

    private void PositionCursor(HarnessAppComponentState state)
    {
        if (state.Mode == BottomPanelMode.TextInput
            || (state.Mode == BottomPanelMode.Streaming && state.InputEnabled))
        {
            int promptLength = state.Prompt.Length;
            int textWidth = state.ConsoleWidth - promptLength;
            int textLength = state.InputText.Length;

            int textInputY = this._rule.Y + 1;

            if (textWidth <= 0 || textLength == 0)
            {
                System.Console.Write(AnsiEscapes.MoveCursor(textInputY, promptLength + 1));
            }
            else
            {
                int cursorRow = textLength < textWidth ? 0 : 1 + ((textLength - textWidth) / textWidth);
                int cursorCol = textLength < textWidth ? textLength : (textLength - textWidth) % textWidth;
                System.Console.Write(AnsiEscapes.MoveCursor(textInputY + cursorRow, promptLength + cursorCol + 1));
            }
        }
        else if (state.Mode == BottomPanelMode.ListSelection
            && state.ListSelectionCustomTextPlaceholder != null
            && state.ListSelectionIndex == state.ListSelectionOptions.Count)
        {
            int titleLines = state.ListSelectionTitle?.Split('\n').Length ?? 0;
            int customOptionY = this._rule.Y + 1 + titleLines + state.ListSelectionOptions.Count;
            int cursorCol = 2 + state.ListSelectionCustomInputText.Length + 1;
            System.Console.Write(AnsiEscapes.MoveCursor(customOptionY, cursorCol));
        }
    }
}
