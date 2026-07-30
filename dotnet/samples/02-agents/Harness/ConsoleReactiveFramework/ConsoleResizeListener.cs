// Copyright (c) Microsoft. All rights reserved.

namespace Harness.ConsoleReactiveFramework;

/// <summary>
/// Event args for console resize events, containing the old and new dimensions.
/// </summary>
public class ConsoleResizeEventArgs : EventArgs
{
    /// <summary>Gets the previous console width.</summary>
    public int OldWidth { get; }

    /// <summary>Gets the previous console height.</summary>
    public int OldHeight { get; }

    /// <summary>Gets the new console width.</summary>
    public int NewWidth { get; }

    /// <summary>Gets the new console height.</summary>
    public int NewHeight { get; }

    /// <summary>
    /// Initializes a new instance of the <see cref="ConsoleResizeEventArgs"/> class.
    /// </summary>
    /// <param name="oldWidth">The previous width.</param>
    /// <param name="oldHeight">The previous height.</param>
    /// <param name="newWidth">The new width.</param>
    /// <param name="newHeight">The new height.</param>
    public ConsoleResizeEventArgs(int oldWidth, int oldHeight, int newWidth, int newHeight)
    {
        this.OldWidth = oldWidth;
        this.OldHeight = oldHeight;
        this.NewWidth = newWidth;
        this.NewHeight = newHeight;
    }
}

/// <summary>
/// Singleton that polls console dimensions every 16ms and raises the
/// <see cref="ConsoleResized"/> event when the window size changes.
/// </summary>
public sealed class ConsoleResizeListener
{
#pragma warning disable IDE0052 // Remove unread private members
    private readonly Task _task;
#pragma warning restore IDE0052 // Remove unread private members

    private int _lastWidth;
    private int _lastHeight;

    private ConsoleResizeListener()
    {
        this._lastWidth = Console.WindowWidth;
        this._lastHeight = Console.WindowHeight;
        this._task = this.ListenForResizeAsync();
    }

    /// <summary>Gets the singleton instance of <see cref="ConsoleResizeListener"/>.</summary>
    public static ConsoleResizeListener Instance { get; } = new ConsoleResizeListener();

    /// <summary>Raised when the console window is resized.</summary>
    public event EventHandler<ConsoleResizeEventArgs>? ConsoleResized;

    private async Task ListenForResizeAsync()
    {
        while (true)
        {
            int currentWidth = Console.WindowWidth;
            int currentHeight = Console.WindowHeight;

            if (currentWidth != this._lastWidth || currentHeight != this._lastHeight)
            {
                int oldWidth = this._lastWidth;
                int oldHeight = this._lastHeight;
                this._lastWidth = currentWidth;
                this._lastHeight = currentHeight;
                this.ConsoleResized?.Invoke(this, new ConsoleResizeEventArgs(oldWidth, oldHeight, currentWidth, currentHeight));
            }

            await Task.Delay(16);
        }
    }
}
