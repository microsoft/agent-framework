// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics;

internal sealed class ServerProcess
{
    private readonly Process _process;
    private readonly Task _outputPump;
    private readonly Task _errorPump;
    private bool _disposed;

    private ServerProcess(Process process, TextWriter logWriter)
    {
        this._process = process;
        this._outputPump = PumpAsync(process.StandardOutput, logWriter, "stdout");
        this._errorPump = PumpAsync(process.StandardError, logWriter, "stderr");
    }

    public int Id => this._process.Id;

    public static ServerProcess Start(ProcessStartInfo startInfo, TextWriter logWriter)
    {
        Process process = Process.Start(startInfo)
            ?? throw new InvalidOperationException("Could not start the server process.");
        return new ServerProcess(process, TextWriter.Synchronized(logWriter));
    }

    public async Task KillAsync()
    {
        if (!this._process.HasExited)
        {
            this._process.Kill(entireProcessTree: true);
        }

        await this.CompleteAsync();
    }

    public async Task WaitForExitAsync(CancellationToken cancellationToken)
    {
        await this._process.WaitForExitAsync(cancellationToken);
        await this.CompleteAsync();
    }

    private async Task CompleteAsync()
    {
        if (this._disposed)
        {
            return;
        }

        await this._process.WaitForExitAsync();
        await Task.WhenAll(this._outputPump, this._errorPump)
            .WaitAsync(TimeSpan.FromSeconds(5));
        this._process.Dispose();
        this._disposed = true;
    }

    private static async Task PumpAsync(StreamReader reader, TextWriter writer, string source)
    {
        while (await reader.ReadLineAsync() is { } line)
        {
            await writer.WriteLineAsync($"[{source}] {line}");
        }
    }
}
