// Copyright (c) Microsoft. All rights reserved.

namespace Harness.Shared.Console;

/// <summary>
/// A restartable spinner that can be started and stopped multiple times.
/// </summary>
internal sealed class Spinner : IDisposable
{
    private static readonly string[] s_frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"];

    private CancellationTokenSource? _cts;
    private Task? _task;

    public void Start()
    {
        if (this._task is not null)
        {
            return;
        }

        this._cts = new CancellationTokenSource();
        this._task = RunAsync(this._cts.Token);
    }

    public async Task StopAsync()
    {
        if (this._cts is null || this._task is null)
        {
            return;
        }

        this._cts.Cancel();
        await this._task;
        this._cts.Dispose();
        this._cts = null;
        this._task = null;
    }

    public void Dispose()
    {
        if (this._cts is not null && this._task is not null)
        {
            this._cts.Cancel();

            // Block briefly to let the spinner task clean up.
            // This prevents the background task from writing to the console after disposal.
#pragma warning disable VSTHRD002 // Synchronous wait in Dispose is acceptable here — the spinner task completes quickly on cancellation.
            this._task.Wait();
#pragma warning restore VSTHRD002
        }

        this._cts?.Dispose();
        this._cts = null;
        this._task = null;
    }

    private static async Task RunAsync(CancellationToken cancellationToken)
    {
        int i = 0;
        try
        {
            while (!cancellationToken.IsCancellationRequested)
            {
                System.Console.Write(s_frames[i % s_frames.Length]);
                await Task.Delay(80, cancellationToken);
                System.Console.Write("\b \b");
                i++;
            }
        }
        catch (OperationCanceledException)
        {
            // Clear the last spinner frame left on screen.
            System.Console.Write("\b \b");
        }
    }
}
