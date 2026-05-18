// Copyright (c) Microsoft. All rights reserved.

using Harness.ConsoleReactiveComponents;
using Harness.ConsoleReactiveFramework;

namespace Harness.Shared.Console.Components;

/// <summary>
/// Props for <see cref="AgentStatus"/>.
/// </summary>
public record AgentStatusProps : ConsoleReactiveProps
{
    /// <summary>Gets or sets a value indicating whether the spinner is visible.</summary>
    public bool ShowSpinner { get; set; }

    /// <summary>Gets or sets the formatted token usage text to display.</summary>
    public string? UsageText { get; set; }
}

/// <summary>
/// State for <see cref="AgentStatus"/>.
/// </summary>
/// <param name="SpinnerIndex">The current spinner animation frame index.</param>
public record AgentStatusState(int SpinnerIndex = 0) : ConsoleReactiveState;

/// <summary>
/// A component that renders a single-line agent status bar with an animated spinner
/// and token usage statistics. Positioned above the rule in the non-scrolling area.
/// </summary>
public class AgentStatus : ConsoleReactiveComponent<AgentStatusProps, AgentStatusState>, IDisposable
{
    private static readonly string[] s_spinnerFrames =
    [
        "⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏",
    ];

    private readonly Timer _timer;

    /// <summary>
    /// Initializes a new instance of the <see cref="AgentStatus"/> class.
    /// </summary>
    public AgentStatus()
    {
        this.State = new AgentStatusState();
        this._timer = new Timer(this.OnTimerTick, null, TimeSpan.Zero, TimeSpan.FromMilliseconds(100));
    }

    /// <summary>
    /// Calculates the height of the agent status component.
    /// </summary>
    /// <param name="props">The component props.</param>
    /// <returns>1 if the spinner or usage text is visible; otherwise 0.</returns>
    public static int CalculateHeight(AgentStatusProps props)
    {
        return (props.ShowSpinner || !string.IsNullOrEmpty(props.UsageText)) ? 1 : 0;
    }

    /// <summary>
    /// Disposes the internal spinner timer.
    /// </summary>
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
            this._timer.Dispose();
        }
    }

    /// <inheritdoc />
    public override void RenderCore(AgentStatusProps props, AgentStatusState state)
    {
        if (!props.ShowSpinner && string.IsNullOrEmpty(props.UsageText))
        {
            return;
        }

        System.Console.Write(AnsiEscapes.SaveCursor);
        System.Console.Write(AnsiEscapes.MoveAndEraseLine(this.Y));

        if (props.ShowSpinner)
        {
            string frame = s_spinnerFrames[state.SpinnerIndex];
            System.Console.Write(AnsiEscapes.SetForegroundColor(ConsoleColor.Cyan));
            System.Console.Write($" {frame} ");
            System.Console.Write(AnsiEscapes.ResetAttributes);
        }
        else
        {
            System.Console.Write("   ");
        }

        if (!string.IsNullOrEmpty(props.UsageText))
        {
            System.Console.Write(AnsiEscapes.SetForegroundColor(ConsoleColor.DarkGray));
            System.Console.Write(props.UsageText);
            System.Console.Write(AnsiEscapes.ResetAttributes);
        }

        System.Console.Write(AnsiEscapes.RestoreCursor);
    }

    private void OnTimerTick(object? timerState)
    {
        if (this.Props is { ShowSpinner: true })
        {
            int nextIndex = ((this.State?.SpinnerIndex ?? 0) + 1) % s_spinnerFrames.Length;
            this.SetState(new AgentStatusState(nextIndex));
        }
    }
}
