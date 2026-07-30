// Copyright (c) Microsoft. All rights reserved.

namespace Harness.ConsoleReactiveFramework;

/// <summary>
/// Event args for key press events, wrapping a <see cref="ConsoleKeyInfo"/>.
/// </summary>
public class KeyPressEventArgs : EventArgs
{
    /// <summary>Gets the key information for the pressed key.</summary>
    public ConsoleKeyInfo KeyInfo { get; }

    /// <summary>
    /// Initializes a new instance of the <see cref="KeyPressEventArgs"/> class.
    /// </summary>
    /// <param name="keyInfo">The key information.</param>
    public KeyPressEventArgs(ConsoleKeyInfo keyInfo)
    {
        this.KeyInfo = keyInfo;
    }
}

/// <summary>
/// Singleton that polls for console key presses every 16ms and raises the
/// <see cref="KeyPressed"/> event when a key is detected.
/// </summary>
public sealed class KeyEventListener
{
#pragma warning disable IDE0052 // Remove unread private members
    private readonly Task _task;
#pragma warning restore IDE0052 // Remove unread private members

    private KeyEventListener()
    {
        this._task = this.ListenForKeyPressesAsync();
    }

    /// <summary>Gets the singleton instance of <see cref="KeyEventListener"/>.</summary>
    public static KeyEventListener Instance { get; } = new KeyEventListener();

    /// <summary>Raised when a key is pressed in the console.</summary>
    public event EventHandler<KeyPressEventArgs>? KeyPressed;

    private async Task ListenForKeyPressesAsync()
    {
        while (true)
        {
            while (Console.KeyAvailable)
            {
                var keyInfo = Console.ReadKey(intercept: true);
                this.KeyPressed?.Invoke(this, new KeyPressEventArgs(keyInfo));
            }

            await Task.Delay(16);
        }
    }
}
