// Copyright (c) Microsoft. All rights reserved.

using Harness.ConsoleReactiveComponents;
using Microsoft.Extensions.AI;

namespace Harness.Shared.Console;

/// <summary>
/// Default <see cref="IUXStateDriver"/> implementation. Owned by
/// <see cref="HarnessAppComponent"/>; mutates the component's state via a
/// <c>SetState</c>-style callback. Each public operation updates state and lets
/// the component's render-skip optimization handle the actual draw.
/// </summary>
internal sealed class HarnessConsoleUXStateDriver : IUXStateDriver
{
    private readonly Func<HarnessAppComponentState> _getState;
    private readonly Action<HarnessAppComponentState> _setState;
    private readonly Action _requestShutdown;
    private readonly IReadOnlyDictionary<string, ConsoleColor>? _modeColors;
    private readonly List<string> _outputItems = [];
    private readonly object _stateLock = new();

    private OutputEntryType? _lastEntryType;
    private bool _hasReceivedAnyText;
    private OutputEntry? _currentStreamingEntry;
    private int _currentStreamingEntryIndex = -1;
    private string? _currentMode;

    /// <summary>
    /// Initializes a new instance of the <see cref="HarnessConsoleUXStateDriver"/> class.
    /// </summary>
    /// <param name="getState">Returns the component's current state.</param>
    /// <param name="setState">Replaces the component's state and triggers a re-render.</param>
    /// <param name="requestShutdown">Callback invoked when a command handler requests application shutdown.</param>
    /// <param name="modeColors">Optional mapping of mode names to console colors.</param>
    public HarnessConsoleUXStateDriver(
        Func<HarnessAppComponentState> getState,
        Action<HarnessAppComponentState> setState,
        Action requestShutdown,
        IReadOnlyDictionary<string, ConsoleColor>? modeColors = null)
    {
        this._getState = getState;
        this._setState = setState;
        this._requestShutdown = requestShutdown;
        this._modeColors = modeColors;
        this._currentMode = getState().ModeText;
    }

    /// <inheritdoc/>
    public string? CurrentMode
    {
        get => this._currentMode;
        set
        {
            this.UpdateState(s =>
            {
                this._currentMode = value;
                return s with
                {
                    ModeColor = ModeColors.Get(value, this._modeColors),
                    ModeText = value,
                };
            });
        }
    }

    /// <inheritdoc/>
    public void BeginStreaming() =>
        this.UpdateState(s => s with
        {
            Mode = BottomPanelMode.Streaming,
            ShowSpinner = true,
        });

    /// <inheritdoc/>
    public void StopSpinner() =>
        this.UpdateState(s => s with { ShowSpinner = false });

    /// <inheritdoc/>
    public void EndStreaming() =>
        this.UpdateState(s => s with
        {
            Mode = BottomPanelMode.TextInput,
            ShowSpinner = false,
        });

    /// <inheritdoc/>
    public void BeginStreamingOutput()
    {
        lock (this._stateLock)
        {
            this._hasReceivedAnyText = false;
            this._currentStreamingEntry = null;
            this._currentStreamingEntryIndex = -1;
        }
    }

    /// <inheritdoc/>
    public void SetUsageText(string usageText) =>
        this.UpdateState(s => s with { UsageText = usageText });

    /// <inheritdoc/>
    public void SetQueuedMessages(IReadOnlyList<ChatMessage> pending)
    {
        var newQueued = new List<string>(pending.Count);
        foreach (var msg in pending)
        {
            string text = msg.Text ?? string.Empty;
            newQueued.Add(RenderEntry($"  💬 {text}\n", ConsoleColor.DarkGray));
        }

        this.UpdateState(s => s with { QueuedItems = newQueued });
    }

    /// <inheritdoc/>
    public void QueueFollowUpQuestions(IReadOnlyList<FollowUpQuestion> questions)
    {
        if (questions.Count == 0)
        {
            return;
        }

        this.UpdateState(s =>
        {
            bool wasEmpty = s.PendingQuestions.Count == 0;

            var combined = new List<FollowUpQuestion>(s.PendingQuestions.Count + questions.Count);
            combined.AddRange(s.PendingQuestions);
            combined.AddRange(questions);

            HarnessAppComponentState next = s with { PendingQuestions = combined };

            if (wasEmpty)
            {
                next = this.ConfigureForHeadQuestion(next, combined[0]);
            }

            return next;
        });
    }

    /// <inheritdoc/>
    public void AddFollowUpResponse(ChatMessage response)
    {
        this.UpdateState(s =>
        {
            var combined = new List<ChatMessage>(s.AccumulatedFollowUpResponses.Count + 1);
            combined.AddRange(s.AccumulatedFollowUpResponses);
            combined.Add(response);
            return s with { AccumulatedFollowUpResponses = combined };
        });
    }

    /// <inheritdoc/>
    public void AdvanceFollowUpQuestion()
    {
        this.UpdateState(s =>
        {
            if (s.PendingQuestions.Count == 0)
            {
                return s;
            }

            var remaining = s.PendingQuestions.Skip(1).ToList();
            HarnessAppComponentState next = s with { PendingQuestions = remaining };

            if (remaining.Count > 0)
            {
                return this.ConfigureForHeadQuestion(next, remaining[0]);
            }

            return next with
            {
                Mode = BottomPanelMode.TextInput,
                ListSelectionOptions = [],
                ListSelectionTitle = null,
                ListSelectionCustomTextPlaceholder = null,
                ListSelectionIndex = 0,
                ListSelectionCustomInputText = "",
            };
        });
    }

    /// <inheritdoc/>
    public IReadOnlyList<ChatMessage> TakeFollowUpResponses()
    {
        return this.UpdateState(s =>
        {
            IReadOnlyList<ChatMessage> responses = s.AccumulatedFollowUpResponses;
            if (responses.Count == 0)
            {
                return (s, responses);
            }

            return (s with { AccumulatedFollowUpResponses = [] }, responses);
        });
    }

    /// <summary>
    /// Configures the bottom-panel display fields on the supplied state for the
    /// given head question. For text questions, also writes the prompt as an
    /// info line above the input row as a side effect.
    /// </summary>
    private HarnessAppComponentState ConfigureForHeadQuestion(HarnessAppComponentState state, FollowUpQuestion question)
    {
        if (question is ChoiceFollowUpQuestion choice)
        {
            return state with
            {
                Mode = BottomPanelMode.ListSelection,
                ListSelectionOptions = choice.Choices.ToList(),
                ListSelectionTitle = choice.Prompt,
                ListSelectionCustomTextPlaceholder = choice.AllowCustomText ? "✏️  Type a custom response..." : null,
                ListSelectionIndex = 0,
                ListSelectionCustomInputText = "",
            };
        }

        // Text question — prompt is rendered as an info line above the input row.
        // We append entries and capture the scroll snapshot inline so the caller's
        // single _setState picks up both the new output and the UI mode change.
        ConsoleColor ruleColor = ModeColors.Get(this._currentMode, this._modeColors);
        List<string> scrollSnapshot = this.AppendOutputEntriesAndSnapshot(
            new OutputEntry(OutputEntryType.InfoLine, "\n", ruleColor),
            new OutputEntry(OutputEntryType.InfoLine, $"  {question.Prompt}", ruleColor));

        return state with
        {
            Mode = BottomPanelMode.TextInput,
            ListSelectionOptions = [],
            ListSelectionTitle = null,
            ListSelectionCustomTextPlaceholder = null,
            ListSelectionIndex = 0,
            ListSelectionCustomInputText = "",
            ScrollAreaContentItems = scrollSnapshot,
        };
    }

    /// <inheritdoc/>
    public void WriteUserInputEcho(string text)
    {
        this.UpdateState(s =>
        {
            List<string> snapshot = this.AppendOutputEntriesAndSnapshot(new OutputEntry(
                OutputEntryType.UserInput,
                $"\nYou: {text}\n\n",
                ConsoleColor.Green));
            return s with { ScrollAreaContentItems = snapshot };
        });
    }

    /// <inheritdoc/>
    public Task WriteInfoAsync(string text, ConsoleColor? color = null) =>
        this.WriteInfoCoreAsync(text, color, newLine: false);

    /// <inheritdoc/>
    public Task WriteInfoLineAsync(string text, ConsoleColor? color = null) =>
        this.WriteInfoCoreAsync(text, color, newLine: true);

    private Task WriteInfoCoreAsync(string text, ConsoleColor? color, bool newLine)
    {
        this.UpdateState(s =>
        {
            // Add a blank line separator when transitioning from streaming text or user input.
            string prefix = this._lastEntryType is OutputEntryType.StreamingText or OutputEntryType.StreamFooter
                ? "\n  "
                : "  ";

            string fullText = newLine ? prefix + text + "\n\n" : prefix + text;
            List<string> snapshot = this.AppendOutputEntriesAndSnapshot(new OutputEntry(
                OutputEntryType.InfoLine,
                fullText,
                color ?? ModeColors.Get(this._currentMode, this._modeColors)));
            return s with { ScrollAreaContentItems = snapshot };
        });
        return Task.CompletedTask;
    }

    /// <inheritdoc/>
    public Task WriteTextAsync(string text, ConsoleColor? color = null)
    {
        this.UpdateState(s =>
        {
            this._lastEntryType = OutputEntryType.StreamingText;
            this._hasReceivedAnyText = true;

            ConsoleColor effectiveColor = color ?? ModeColors.Get(this._currentMode, this._modeColors);

            if (this._currentStreamingEntry is not null
                && this._currentStreamingEntryIndex == this._outputItems.Count - 1)
            {
                // The streaming entry is still the last item — safe to replace in place.
                this._currentStreamingEntry = this._currentStreamingEntry with
                {
                    Text = this._currentStreamingEntry.Text + text,
                };
                this._outputItems[^1] = RenderEntry(this._currentStreamingEntry.Text, this._currentStreamingEntry.Color);
            }
            else
            {
                // Either the first text delta or other entries (tool calls, info lines)
                // were appended after the previous streaming entry — start a fresh one.
                const string Prefix = "\n";
                this._currentStreamingEntry = new OutputEntry(OutputEntryType.StreamingText, Prefix + text, effectiveColor);
                this._outputItems.Add(RenderEntry(this._currentStreamingEntry.Text, this._currentStreamingEntry.Color));
                this._currentStreamingEntryIndex = this._outputItems.Count - 1;
            }

            return s with { ScrollAreaContentItems = new List<string>(this._outputItems) };
        });

        return Task.CompletedTask;
    }

    /// <inheritdoc/>
    public Task EndStreamingOutputAsync()
    {
        this.UpdateState(s =>
        {
            if (this._hasReceivedAnyText)
            {
                this._outputItems.Add(RenderEntry("\n", null));
                this._currentStreamingEntry = null;
                this._lastEntryType = OutputEntryType.StreamFooter;
                return s with { ScrollAreaContentItems = new List<string>(this._outputItems) };
            }

            return s;
        });

        return Task.CompletedTask;
    }

    /// <inheritdoc/>
    public Task WriteNoTextWarningAsync(bool hasFollowUpActions)
    {
        if (!this._hasReceivedAnyText && !hasFollowUpActions)
        {
            this.UpdateState(s =>
            {
                List<string> snapshot = this.AppendOutputEntriesAndSnapshot(new OutputEntry(
                    OutputEntryType.StreamFooter,
                    "  (no text response from agent)\n",
                    ConsoleColor.DarkYellow));
                return s with { ScrollAreaContentItems = snapshot };
            });
        }

        return Task.CompletedTask;
    }

    /// <summary>
    /// Wraps the supplied text with ANSI foreground color escape sequences (or returns
    /// the text unchanged when no color is specified). Output is appended to
    /// <see cref="_outputItems"/> and consumed verbatim by <see cref="TextScrollPanel"/>
    /// and <see cref="TextPanel"/>.
    /// </summary>
    private static string RenderEntry(string text, ConsoleColor? color) =>
        color.HasValue
            ? $"{AnsiEscapes.SetForegroundColor(color.Value)}{text}{AnsiEscapes.ResetAttributes}"
            : text;

    private void UpdateState(Func<HarnessAppComponentState, HarnessAppComponentState> update)
    {
        lock (this._stateLock)
        {
            this._setState(update(this._getState()));
        }
    }

    private T UpdateState<T>(Func<HarnessAppComponentState, (HarnessAppComponentState State, T Result)> update)
    {
        lock (this._stateLock)
        {
            var (newState, result) = update(this._getState());
            this._setState(newState);
            return result;
        }
    }

    /// <summary>
    /// Appends one or more output entries to the output list, updates
    /// <see cref="_lastEntryType"/> to the last entry's type, and returns a
    /// snapshot of <see cref="_outputItems"/>. Must be called inside a locked
    /// context (e.g. within an <see cref="UpdateState"/> callback).
    /// </summary>
    private List<string> AppendOutputEntriesAndSnapshot(params OutputEntry[] entries)
    {
        this.AppendOutputEntriesCore(entries);
        return new List<string>(this._outputItems);
    }

    private void AppendOutputEntriesCore(OutputEntry[] entries)
    {
        foreach (OutputEntry entry in entries)
        {
            this._outputItems.Add(RenderEntry(entry.Text, entry.Color));
        }

        if (entries.Length > 0)
        {
            this._lastEntryType = entries[^1].Type;
        }
    }

    /// <inheritdoc/>
    public void RequestShutdown() => this._requestShutdown();
}
