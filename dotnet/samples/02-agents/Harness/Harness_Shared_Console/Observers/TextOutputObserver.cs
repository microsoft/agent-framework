// Copyright (c) Microsoft. All rights reserved.

namespace Harness.Shared.Console.Observers;

/// <summary>
/// Streams agent text output directly to the console.
/// Used in normal (non-planning) mode.
/// </summary>
internal sealed class TextOutputObserver : ConsoleObserver
{
    /// <inheritdoc/>
    public override async Task OnTextAsync(HarnessUXContainer ux, string text)
    {
        await ux.WriteTextAsync(text);
    }
}
