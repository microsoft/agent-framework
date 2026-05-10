// Copyright (c) Microsoft. All rights reserved.

using Spectre.Console;

namespace Harness.Shared.Console;

/// <summary>
/// Centralizes all console output and spinner management for the harness console.
/// Observers write through this class so the spinner is automatically paused before output.
/// </summary>
public sealed class ConsoleWriter : IDisposable
{
    private readonly Spinner _spinner = new();
    private readonly IReadOnlyDictionary<string, ConsoleColor>? _modeColors;

    private bool _lastWasText;
    private bool _hasReceivedAnyText;

    /// <summary>
    /// Initializes a new instance of the <see cref="ConsoleWriter"/> class.
    /// </summary>
    /// <param name="modeColors">Optional mapping of mode names to console colors.</param>
    public ConsoleWriter(IReadOnlyDictionary<string, ConsoleColor>? modeColors = null)
    {
        this._modeColors = modeColors;
    }

    /// <summary>
    /// Gets or sets the current agent mode (e.g., "plan", "execute").
    /// Used to determine the console color for mode-prefixed output.
    /// </summary>
    public string? CurrentMode { get; set; }

    /// <summary>
    /// Writes the agent response header (e.g., "[plan] Agent: ") and starts the spinner.
    /// </summary>
    public void WriteResponseHeader()
    {
        if (this.CurrentMode is not null)
        {
            System.Console.ForegroundColor = GetModeColor(this.CurrentMode, this._modeColors);
            System.Console.Write($"\n[{this.CurrentMode}] Agent: ");
        }
        else
        {
            System.Console.Write("\nAgent: ");
        }

        this._lastWasText = true;
        this._hasReceivedAnyText = false;
        this._spinner.Start();
    }

    /// <summary>
    /// Writes informational output with automatic prefix spacing, without a trailing newline.
    /// Use when continuation content will be appended on the same line.
    /// </summary>
    /// <param name="text">The informational text to write (without leading newline/indent — added automatically).</param>
    /// <param name="color">Optional console color for the text.</param>
    public async Task WriteInfoAsync(string text, ConsoleColor? color = null)
    {
        await this.WriteInfoCoreAsync(text, color, newLine: false);
    }

    /// <summary>
    /// Writes informational output with automatic prefix spacing, followed by a newline.
    /// </summary>
    /// <param name="text">The informational text to write (without leading newline/indent — added automatically).</param>
    /// <param name="color">Optional console color for the text.</param>
    public async Task WriteInfoLineAsync(string text, ConsoleColor? color = null)
    {
        await this.WriteInfoCoreAsync(text, color, newLine: true);
    }

    private async Task WriteInfoCoreAsync(string text, ConsoleColor? color, bool newLine)
    {
        await this._spinner.StopAsync();

        string prefix = this._lastWasText ? "\n\n  " : "  ";
        this._lastWasText = false;

        System.Console.ForegroundColor = color ?? GetModeColor(this.CurrentMode, this._modeColors);

        if (newLine)
        {
            System.Console.WriteLine(prefix + text);
        }
        else
        {
            System.Console.Write(prefix + text);
        }

        System.Console.ForegroundColor = GetModeColor(this.CurrentMode, this._modeColors);

        this._spinner.Start();
    }

    /// <summary>
    /// Writes text output from the agent, managing line break state.
    /// Ensures a newline is written before the first text output.
    /// </summary>
    /// <param name="text">The text to write.</param>
    /// <param name="color">Optional console color override for this text.</param>
    public async Task WriteTextAsync(string text, ConsoleColor? color = null)
    {
        await this._spinner.StopAsync();

        if (!this._lastWasText)
        {
            System.Console.Write("\n");
            this._lastWasText = true;
        }

        this._hasReceivedAnyText = true;

        if (color.HasValue)
        {
            System.Console.ForegroundColor = color.Value;
        }

        System.Console.Write(text);

        if (color.HasValue)
        {
            System.Console.ForegroundColor = GetModeColor(this.CurrentMode, this._modeColors);
        }

        this._spinner.Start();
    }

    /// <summary>
    /// Reads a line of input from the console, pausing the spinner while waiting for input.
    /// Optionally displays a prompt before reading. The prompt is rendered between
    /// two horizontal rules for visual clarity.
    /// </summary>
    /// <param name="prompt">Optional prompt text to display before reading input.</param>
    /// <param name="promptColor">Optional console color for the prompt text.</param>
    /// <returns>The line read from the console, or <c>null</c> if no input is available.</returns>
    public async Task<string?> ReadLineAsync(string? prompt = null, ConsoleColor? promptColor = null)
    {
        await this._spinner.StopAsync();

        if (prompt is not null)
        {
            System.Console.WriteLine();
            AnsiConsole.Write(this.CreateModeRule());

            if (promptColor.HasValue)
            {
                System.Console.ForegroundColor = promptColor.Value;
            }

            System.Console.Write($"  {prompt}");

            if (promptColor.HasValue)
            {
                System.Console.ForegroundColor = GetModeColor(this.CurrentMode, this._modeColors);
            }
        }

        string? input = System.Console.ReadLine();

        if (prompt is not null)
        {
            AnsiConsole.Write(this.CreateModeRule());
        }

        this._lastWasText = false;
        return input;
    }

    /// <summary>
    /// Presents a selection prompt with the given choices, plus an option to type a custom response.
    /// Uses Spectre.Console <see cref="SelectionPrompt{T}"/> for interactive arrow-key selection.
    /// </summary>
    /// <param name="title">The title/question displayed above the selection list.</param>
    /// <param name="choices">The list of choices to present.</param>
    /// <returns>The selected choice text, or the custom-typed response.</returns>
    public async Task<string> ReadSelectionAsync(string title, IList<string> choices)
    {
        await this._spinner.StopAsync();

        AnsiConsole.Write(this.CreateModeRule());

        const string FreeformOption = "✏️  Type a custom response...";
        var allChoices = choices.Concat([FreeformOption]).ToList();

        var prompt = new SelectionPrompt<string>()
            .Title($"  [bold]{Markup.Escape(title)}[/]")
            .PageSize(10)
            .AddChoices(allChoices);

        string selection = AnsiConsole.Prompt(prompt);

        if (selection == FreeformOption)
        {
            var textPrompt = new TextPrompt<string>("  [grey]Response:[/]");
            selection = AnsiConsole.Prompt(textPrompt);
        }

        AnsiConsole.MarkupLine($"  [dim]→ {Markup.Escape(selection)}[/]");
        AnsiConsole.Write(this.CreateModeRule());

        this._lastWasText = false;
        return selection;
    }

    /// <summary>
    /// Writes the stream-complete footer (handles "no text response" fallback, resets color).
    /// </summary>
    public async Task WriteStreamFooterAsync(bool hasFollowUpMessages)
    {
        await this._spinner.StopAsync();

        if (!this._hasReceivedAnyText && !hasFollowUpMessages)
        {
            System.Console.ForegroundColor = ConsoleColor.DarkYellow;
            System.Console.Write("\n  (no text response from agent)");
        }

        System.Console.ResetColor();
        System.Console.WriteLine();
    }

    /// <inheritdoc/>
    public void Dispose()
    {
        this._spinner.Dispose();
    }

    /// <summary>
    /// Gets the console color associated with a mode name, using the provided color map.
    /// </summary>
    internal static ConsoleColor GetModeColor(string? mode, IReadOnlyDictionary<string, ConsoleColor>? modeColors = null)
    {
        if (mode is null)
        {
            return ConsoleColor.Gray;
        }

        if (modeColors is not null && modeColors.TryGetValue(mode, out var color))
        {
            return color;
        }

        return ConsoleColor.Gray;
    }

    /// <summary>
    /// Creates a <see cref="Rule"/> styled with the current mode color.
    /// </summary>
    internal Rule CreateModeRule()
    {
        var spectreColor = ToSpectreColor(GetModeColor(this.CurrentMode, this._modeColors));
        return new Rule().RuleStyle(new Style(spectreColor));
    }

    internal static Color ToSpectreColor(ConsoleColor consoleColor) => consoleColor switch
    {
        ConsoleColor.Black => Color.Black,
        ConsoleColor.DarkBlue => Color.Blue,
        ConsoleColor.DarkGreen => Color.Green,
        ConsoleColor.DarkCyan => Color.Teal,
        ConsoleColor.DarkRed => Color.Red,
        ConsoleColor.DarkMagenta => Color.Purple,
        ConsoleColor.DarkYellow => Color.Olive,
        ConsoleColor.Gray => Color.Silver,
        ConsoleColor.DarkGray => Color.Grey,
        ConsoleColor.Blue => Color.Blue1,
        ConsoleColor.Green => Color.Green1,
        ConsoleColor.Cyan => Color.Aqua,
        ConsoleColor.Red => Color.Red1,
        ConsoleColor.Magenta => Color.Fuchsia,
        ConsoleColor.Yellow => Color.Yellow,
        ConsoleColor.White => Color.White,
        _ => Color.Silver,
    };
}
