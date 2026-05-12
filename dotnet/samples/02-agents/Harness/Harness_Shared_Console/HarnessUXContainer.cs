// Copyright (c) Microsoft. All rights reserved.

using Harness.ConsoleReactiveComponents;
using Microsoft.Extensions.AI;

namespace Harness.Shared.Console;

/// <summary>
/// Event arguments raised when the user submits text while the bottom panel is in
/// streaming mode (i.e. an agent turn is in progress).
/// </summary>
public sealed class StreamingInputReceivedEventArgs : EventArgs
{
    /// <summary>
    /// Initializes a new instance of the <see cref="StreamingInputReceivedEventArgs"/> class.
    /// </summary>
    /// <param name="text">The submitted text.</param>
    public StreamingInputReceivedEventArgs(string text)
    {
        this.Text = text;
    }

    /// <summary>
    /// Gets the submitted text.
    /// </summary>
    public string Text { get; }
}

/// <summary>
/// Façade over the harness UI: owns the <see cref="HarnessAppComponent"/>, manages
/// its props, dispatches input submissions, and provides the high-level read/write
/// operations used by observers, command handlers, and the harness loop.
/// </summary>
/// <remarks>
/// All callers interact with the UI exclusively through this class. The underlying
/// <see cref="HarnessAppComponent"/> and its props are an implementation detail and
/// must not be exposed.
/// </remarks>
public sealed class HarnessUXContainer : IDisposable
{
    /// <summary>
    /// The prompt displayed in the bottom-panel input area.
    /// </summary>
    private const string UserPrompt = "> ";

    private readonly IReadOnlyDictionary<string, ConsoleColor>? _modeColors;
    private readonly List<object> _outputItems = [];
    private readonly HarnessAppComponent _appComponent;
    private readonly object _outputLock = new();

    private TaskCompletionSource<string>? _pendingInputTcs;
    private OutputEntryType? _lastEntryType;
    private bool _hasReceivedAnyText;
    private OutputEntry? _currentStreamingEntry;
    private string? _currentMode;

    /// <summary>
    /// Initializes a new instance of the <see cref="HarnessUXContainer"/> class.
    /// </summary>
    /// <param name="placeholder">Placeholder text shown when the input is empty.</param>
    /// <param name="initialMode">The current agent mode, used to colour the rule and prompt.</param>
    /// <param name="inputEnabled">Whether the bottom-panel input accepts keystrokes during streaming.</param>
    /// <param name="modeColors">Optional mapping of mode names to console colors.</param>
    public HarnessUXContainer(
        string placeholder,
        string? initialMode,
        bool inputEnabled,
        IReadOnlyDictionary<string, ConsoleColor>? modeColors = null)
    {
        this._modeColors = modeColors;
        this._currentMode = initialMode;

        this._appComponent = new HarnessAppComponent(RenderOutputEntry)
        {
            Props = new HarnessAppComponentProps
            {
                ScrollItems = this._outputItems,
                Mode = BottomPanelMode.TextInput,
                Prompt = UserPrompt,
                Placeholder = placeholder,
                ModeColor = ModeColors.Get(initialMode, modeColors),
                ModeText = initialMode,
                InputEnabled = inputEnabled,
            },
        };

        this._appComponent.InputSubmitted += this.OnInputSubmitted;
    }

    /// <summary>
    /// Raised when the user submits text while the bottom panel is in streaming mode.
    /// Subscribers typically enqueue the text into a message-injecting chat client.
    /// </summary>
    public event EventHandler<StreamingInputReceivedEventArgs>? StreamingInputReceived;

    /// <summary>
    /// Gets or sets the current agent mode (e.g. "plan", "execute"). Updating this
    /// also refreshes the rule colour and bottom-panel prompt to match the new mode.
    /// </summary>
    public string? CurrentMode
    {
        get => this._currentMode;
        set
        {
            this._currentMode = value;
            this._appComponent.Props = this._appComponent.Props! with
            {
                ModeColor = ModeColors.Get(value, this._modeColors),
                ModeText = value,
            };
            this._appComponent.Render();
        }
    }

    /// <summary>
    /// Performs the initial screen clear, sets the help text in the mode-and-help bar,
    /// and adds the title to the output area.
    /// </summary>
    /// <param name="title">The title displayed in the console header.</param>
    /// <param name="commandHelpTexts">The command help strings displayed in the mode-and-help bar.</param>
    /// <param name="messageInjectionActive">Whether streaming-time message injection is enabled.</param>
    public void Initialize(string title, IEnumerable<string> commandHelpTexts, bool messageInjectionActive)
    {
        // Set the help text on the mode-and-help bar (persists below the rule).
        this._appComponent.Props = this._appComponent.Props! with
        {
            HelpText = string.Join(", ", commandHelpTexts),
            ModeText = this._currentMode,
        };

        System.Console.Write(AnsiEscapes.EraseEntireScreen);
        System.Console.Write(AnsiEscapes.EraseScrollbackBuffer);
        this._appComponent.Render();

        this.AppendOutputEntries(
            new OutputEntry(OutputEntryType.InfoLine, $"=== {title} ===\n", ConsoleColor.White),
            new OutputEntry(OutputEntryType.InfoLine, "\n"));
    }

    /// <summary>
    /// Restores the cursor and exits the alternate screen, ending the interactive UI.
    /// </summary>
    public void Deactivate() => this._appComponent.Deactivate();

    /// <summary>
    /// Switches the bottom panel to streaming mode and starts the spinner.
    /// </summary>
    public void BeginStreaming()
    {
        this._appComponent.Props = this._appComponent.Props! with
        {
            Mode = BottomPanelMode.Streaming,
            ShowSpinner = true,
        };
        this._appComponent.Render();
    }

    /// <summary>
    /// Stops the spinner without leaving streaming mode. Use between the end of the
    /// stream and any observer-driven prompts (e.g. tool approvals).
    /// </summary>
    public void StopSpinner()
    {
        this._appComponent.Props = this._appComponent.Props! with { ShowSpinner = false };
        this._appComponent.Render();
    }

    /// <summary>
    /// Switches the bottom panel back to text-input mode and stops the spinner.
    /// </summary>
    public void EndStreaming()
    {
        this._appComponent.Props = this._appComponent.Props! with
        {
            Mode = BottomPanelMode.TextInput,
            ShowSpinner = false,
        };
        this._appComponent.Render();
    }

    /// <summary>
    /// Resets per-turn streaming bookkeeping in preparation for a new agent turn.
    /// </summary>
    public void BeginStreamingOutput()
    {
        this._hasReceivedAnyText = false;
        this._currentStreamingEntry = null;
    }

    /// <summary>
    /// Sets the formatted usage text shown on the agent status bar.
    /// </summary>
    public void SetUsageText(string usageText)
    {
        this._appComponent.Props = this._appComponent.Props! with { UsageText = usageText };
        this._appComponent.Render();
    }

    /// <summary>
    /// Clears the usage text from the agent status bar.
    /// </summary>
    public void ClearUsageText()
    {
        this._appComponent.Props = this._appComponent.Props! with { UsageText = null };
        this._appComponent.Render();
    }

    /// <summary>
    /// Replaces the queued-message display with one entry per pending message.
    /// </summary>
    public void ShowQueuedMessages(IReadOnlyList<ChatMessage> pending)
    {
        var newQueued = new List<object>(pending.Count);
        foreach (var msg in pending)
        {
            string text = msg.Text ?? string.Empty;
            newQueued.Add(new OutputEntry(OutputEntryType.UserInput, $"  💬 {text}\n", ConsoleColor.DarkGray));
        }

        this._appComponent.Props = this._appComponent.Props! with { QueuedItems = newQueued };
        this._appComponent.Render();
    }

    /// <summary>
    /// Echoes a submitted user input as a regular user-input entry in the output area,
    /// using the current mode-aware prompt prefix.
    /// </summary>
    /// <param name="text">The user-entered text.</param>
    public void WriteUserInputEcho(string text)
    {
        this.AppendOutputEntries(new OutputEntry(
            OutputEntryType.UserInput,
            $"\nYou: {text}\n",
            ConsoleColor.Green));
    }

    /// <summary>
    /// Writes informational output as an output entry, without a trailing newline.
    /// </summary>
    public Task WriteInfoAsync(string text, ConsoleColor? color = null) =>
        this.WriteInfoCoreAsync(text, color, newLine: false);

    /// <summary>
    /// Writes informational output as an output entry, followed by a newline.
    /// </summary>
    public Task WriteInfoLineAsync(string text, ConsoleColor? color = null) =>
        this.WriteInfoCoreAsync(text, color, newLine: true);

    private Task WriteInfoCoreAsync(string text, ConsoleColor? color, bool newLine)
    {
        // Add a blank line separator when transitioning from streaming text or user input.
        string prefix = this._lastEntryType is OutputEntryType.StreamingText or OutputEntryType.StreamFooter
            ? "\n\n  "
            : "  ";

        string fullText = newLine ? prefix + text + "\n" : prefix + text;
        this.AppendOutputEntries(new OutputEntry(
            OutputEntryType.InfoLine,
            fullText,
            color ?? ModeColors.Get(this.CurrentMode, this._modeColors)));
        return Task.CompletedTask;
    }

    /// <summary>
    /// Writes streaming text output from the agent. Successive calls accumulate into a
    /// single streaming entry that is re-rendered by the text panel.
    /// </summary>
    public Task WriteTextAsync(string text, ConsoleColor? color = null)
    {
        lock (this._outputLock)
        {
            this._lastEntryType = OutputEntryType.StreamingText;
            this._hasReceivedAnyText = true;

            ConsoleColor effectiveColor = color ?? ModeColors.Get(this.CurrentMode, this._modeColors);

            if (this._currentStreamingEntry is not null)
            {
                this._currentStreamingEntry = this._currentStreamingEntry with
                {
                    Text = this._currentStreamingEntry.Text + text,
                };
                this._outputItems[^1] = this._currentStreamingEntry;
            }
            else
            {
                const string Prefix = "\n";
                this._currentStreamingEntry = new OutputEntry(OutputEntryType.StreamingText, Prefix + text, effectiveColor);
                this._outputItems.Add(this._currentStreamingEntry);
            }

            this._appComponent.Props = this._appComponent.Props! with
            {
                ScrollItems = new List<object>(this._outputItems),
            };
        }

        this._appComponent.Render();
        return Task.CompletedTask;
    }

    /// <summary>
    /// Writes a blank-line separator to visually close the streaming output section.
    /// Call before observer completions so their output is visually separated.
    /// </summary>
    public Task EndStreamingOutputAsync()
    {
        lock (this._outputLock)
        {
            this._outputItems.Add(new OutputEntry(OutputEntryType.StreamFooter, "\n"));
            this._currentStreamingEntry = null;
            this._lastEntryType = OutputEntryType.StreamFooter;
            this._appComponent.Props = this._appComponent.Props! with
            {
                ScrollItems = new List<object>(this._outputItems),
            };
        }

        this._appComponent.Render();
        return Task.CompletedTask;
    }

    /// <summary>
    /// Shows a "(no text response from agent)" warning if no text was received
    /// and no observer produced follow-up messages. Call after observer completions.
    /// </summary>
    /// <param name="hasFollowUpMessages">Whether any observer produced follow-up messages.</param>
    public Task WriteNoTextWarningAsync(bool hasFollowUpMessages)
    {
        if (!this._hasReceivedAnyText && !hasFollowUpMessages)
        {
            this.AppendOutputEntries(new OutputEntry(
                OutputEntryType.StreamFooter,
                "  (no text response from agent)\n",
                ConsoleColor.DarkYellow));
        }

        return Task.CompletedTask;
    }

    /// <summary>
    /// Reads a line of input from the user. If <paramref name="prompt"/> is supplied
    /// it is rendered as an info line above the input row before reading.
    /// </summary>
    public async Task<string?> ReadLineAsync(string? prompt = null, ConsoleColor? promptColor = null)
    {
        if (prompt is not null)
        {
            ConsoleColor ruleColor = ModeColors.Get(this.CurrentMode, this._modeColors);
            this.AppendOutputEntries(
                new OutputEntry(OutputEntryType.InfoLine, "\n", ruleColor),
                new OutputEntry(OutputEntryType.InfoLine, $"  {prompt}", promptColor ?? ruleColor));
        }

        this._appComponent.Props = this._appComponent.Props! with { Mode = BottomPanelMode.TextInput };
        this._appComponent.Render();

        string input = await this.WaitForInputAsync();

        this.AppendOutputEntries(new OutputEntry(
            OutputEntryType.UserInput,
            $"\nYou: {input}\n",
            ConsoleColor.Green));

        return input;
    }

    /// <summary>
    /// Presents a selection prompt with the given choices and waits for the user's
    /// selection. The title is displayed above the list in the bottom panel. After
    /// selection the bottom panel is restored to text-input mode and both the question
    /// and selection are echoed in the output area.
    /// </summary>
    public async Task<string> ReadSelectionAsync(string title, IList<string> choices)
    {
        this._appComponent.Props = this._appComponent.Props! with
        {
            Mode = BottomPanelMode.ListSelection,
            Items = choices.ToList(),
            ListTitle = title,
            ListCustomTextPlaceholder = "✏️  Type a custom response...",
        };
        this._appComponent.Render();

        string selection = await this.WaitForInputAsync();

        this._appComponent.Props = this._appComponent.Props with { Mode = BottomPanelMode.TextInput };

        this.AppendOutputEntries(
            new OutputEntry(
                OutputEntryType.InfoLine,
                $"\n  {title}\n",
                ModeColors.Get(this.CurrentMode, this._modeColors)),
            new OutputEntry(
                OutputEntryType.UserInput,
                $"\nYou: {selection}\n",
                ConsoleColor.Green));

        return selection;
    }

    /// <summary>
    /// Awaits the next non-streaming user input submission.
    /// </summary>
    public Task<string> WaitForInputAsync()
    {
        this._pendingInputTcs = new TaskCompletionSource<string>(TaskCreationOptions.RunContinuationsAsynchronously);
        return this._pendingInputTcs.Task;
    }

    private void OnInputSubmitted(object? sender, InputSubmittedEventArgs e)
    {
        if (e.Mode == BottomPanelMode.Streaming)
        {
            this.StreamingInputReceived?.Invoke(this, new StreamingInputReceivedEventArgs(e.Text));
        }
        else
        {
            var waiter = this._pendingInputTcs;
            this._pendingInputTcs = null;
            waiter?.TrySetResult(e.Text);
        }
    }

    /// <inheritdoc/>
    public void Dispose()
    {
        this._appComponent.InputSubmitted -= this.OnInputSubmitted;
        this._appComponent.Deactivate();
        this._appComponent.Dispose();
    }

    /// <summary>
    /// Renders an <see cref="OutputEntry"/> to a string with ANSI color codes.
    /// Used as the render delegate for the <see cref="HarnessAppComponent"/>.
    /// </summary>
    private static string RenderOutputEntry(object item)
    {
        if (item is not OutputEntry entry)
        {
            return item?.ToString() ?? string.Empty;
        }

        if (entry.Color.HasValue)
        {
            return $"{AnsiEscapes.SetForegroundColor(entry.Color.Value)}{entry.Text}{AnsiEscapes.ResetAttributes}";
        }

        return entry.Text;
    }

    /// <summary>
    /// Appends one or more output entries to the output list under lock,
    /// updates <see cref="_lastEntryType"/> to the last entry's type, and renders.
    /// </summary>
    private void AppendOutputEntries(params OutputEntry[] entries)
    {
        lock (this._outputLock)
        {
            foreach (OutputEntry entry in entries)
            {
                this._outputItems.Add(entry);
            }

            if (entries.Length > 0)
            {
                this._lastEntryType = entries[^1].Type;
            }

            this._appComponent.Props = this._appComponent.Props! with
            {
                ScrollItems = new List<object>(this._outputItems),
            };
        }

        this._appComponent.Render();
    }
}
