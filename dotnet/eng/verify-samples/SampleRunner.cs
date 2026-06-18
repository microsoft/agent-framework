// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics;

namespace VerifySamples;

/// <summary>
/// Result of running a sample process.
/// </summary>
internal sealed record SampleRunResult(
    string Stdout,
    string Stderr,
    int ExitCode,
    TimeSpan Elapsed);

/// <summary>
/// Runs a sample project via <c>dotnet run</c> and captures its output.
/// </summary>
internal static class SampleRunner
{
    /// <summary>
    /// Runs <c>dotnet run --framework net10.0</c> in the given project directory.
    /// When <paramref name="build"/> is false (the default), <c>--no-build</c> is passed
    /// to skip building, assuming the project was pre-built.
    /// </summary>
    public static Task<SampleRunResult> RunAsync(
        string projectPath,
        TimeSpan timeout,
        bool build = false,
        CancellationToken cancellationToken = default)
        => RunAsync(projectPath, DotnetRunArgs(build), timeout, inputs: null, inputDelayMs: 0, cancellationToken: cancellationToken);

    /// <summary>
    /// Runs <c>dotnet run --framework net10.0</c> with stdin inputs.
    /// When <paramref name="build"/> is false (the default), <c>--no-build</c> is passed
    /// to skip building, assuming the project was pre-built.
    /// </summary>
    public static Task<SampleRunResult> RunAsync(
        string projectPath,
        TimeSpan timeout,
        string?[]? inputs,
        int inputDelayMs = 2000,
        bool build = false,
        CancellationToken cancellationToken = default)
        => RunAsync(projectPath, DotnetRunArgs(build), timeout, inputs, inputDelayMs, cancellationToken);

    private static string DotnetRunArgs(bool build) =>
        $"run {(build ? "" : "--no-build")} --framework net10.0";

    /// <summary>
    /// Runs an arbitrary <c>dotnet</c> command in the given working directory.
    /// </summary>
    public static async Task<SampleRunResult> RunAsync(
        string workingDirectory,
        string dotnetArgs,
        TimeSpan timeout,
        string?[]? inputs = null,
        int inputDelayMs = 0,
        CancellationToken cancellationToken = default)
    {
        var psi = new ProcessStartInfo
        {
            FileName = "dotnet",
            Arguments = dotnetArgs,
            WorkingDirectory = workingDirectory,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            RedirectStandardInput = inputs is { Length: > 0 },
            UseShellExecute = false,
            CreateNoWindow = true,
        };

        var sw = Stopwatch.StartNew();

        using var process = new Process { StartInfo = psi };
        process.Start();

        var stdoutTask = process.StandardOutput.ReadToEndAsync(cancellationToken);
        var stderrTask = process.StandardError.ReadToEndAsync(cancellationToken);

        // Feed stdin inputs with delays if configured
        if (inputs is { Length: > 0 })
        {
            _ = Task.Run(async () =>
            {
                try
                {
                    foreach (var input in inputs)
                    {
                        await Task.Delay(inputDelayMs, cancellationToken);
                        if (input is not null)
                        {
                            await process.StandardInput.WriteLineAsync(input.AsMemory(), cancellationToken);
                            await process.StandardInput.FlushAsync(cancellationToken);
                        }
                    }

                    process.StandardInput.Close();
                }
                catch (Exception ex) when (ex is IOException or ObjectDisposedException or OperationCanceledException)
                {
                    // Process may have exited before all inputs were sent
                }
            }, cancellationToken);
        }

        using var cts = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
        cts.CancelAfter(timeout);

        try
        {
            await process.WaitForExitAsync(cts.Token);
        }
        catch (OperationCanceledException) when (!cancellationToken.IsCancellationRequested)
        {
            // Timeout — kill the process
            try
            {
                process.Kill(entireProcessTree: true);
            }
            catch
            {
                // Best effort
            }

            sw.Stop();
            return new SampleRunResult(
                Stdout: await stdoutTask,
                Stderr: $"TIMEOUT: Sample did not complete within {timeout.TotalSeconds}s.\n{await stderrTask}",
                ExitCode: -1,
                Elapsed: sw.Elapsed);
        }

        sw.Stop();
        return new SampleRunResult(
            Stdout: await stdoutTask,
            Stderr: await stderrTask,
            ExitCode: process.ExitCode,
            Elapsed: sw.Elapsed);
    }
}
