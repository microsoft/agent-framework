// Copyright (c) Microsoft. All rights reserved.

namespace AGUIDojoClient.Services;

/// <summary>
/// Event arguments for background color changes.
/// </summary>
public class BackgroundColorChangedEventArgs : EventArgs
{
    /// <summary>
    /// Initializes a new instance of the <see cref="BackgroundColorChangedEventArgs"/> class.
    /// </summary>
    /// <param name="color">The new background color.</param>
    public BackgroundColorChangedEventArgs(string color)
    {
        Color = color;
    }

    /// <summary>
    /// Gets the new background color.
    /// </summary>
    public string Color { get; }
}

/// <summary>
/// Service for managing the background color of the chat interface.
/// Used by frontend tools to change the background color.
/// </summary>
public interface IBackgroundColorService
{
    /// <summary>
    /// Gets the current background color.
    /// </summary>
    string? CurrentColor { get; }

    /// <summary>
    /// Event raised when the background color changes.
    /// </summary>
    event EventHandler<BackgroundColorChangedEventArgs>? ColorChanged;

    /// <summary>
    /// Sets the background color and notifies subscribers.
    /// </summary>
    /// <param name="color">The color value (e.g., "blue", "#FF5733", "rgb(255,87,51)").</param>
    void SetColor(string color);
}

/// <summary>
/// Default implementation of <see cref="IBackgroundColorService"/>.
/// </summary>
public class BackgroundColorService : IBackgroundColorService
{
    /// <inheritdoc/>
    public string? CurrentColor { get; private set; }

    /// <inheritdoc/>
    public event EventHandler<BackgroundColorChangedEventArgs>? ColorChanged;

    /// <inheritdoc/>
    public void SetColor(string color)
    {
        CurrentColor = color;
        ColorChanged?.Invoke(this, new BackgroundColorChangedEventArgs(color));
    }
}
