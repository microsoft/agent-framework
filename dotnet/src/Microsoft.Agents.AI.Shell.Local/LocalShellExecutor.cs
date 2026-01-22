// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Text;
using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Agents.AI;

/// <summary>
/// Executes shell commands on the local machine using the native shell.
/// </summary>
/// <remarks>
/// <para>
/// On Windows, commands are executed using <c>cmd.exe /c</c>.
/// On Unix-like systems, commands are executed using <c>/bin/sh -c</c>.
/// </para>
/// <para>
/// The shell can be overridden using <see cref="ShellToolOptions.Shell"/>.
/// </para>
/// </remarks>
public sealed class LocalShellExecutor : ShellExecutor
{
    /// <inheritdoc/>
    public override async Task<IReadOnlyList<ShellExecutorOutput>> ExecuteAsync(
        IReadOnlyList<string> commands,
        ShellToolOptions options,
        CancellationToken cancellationToken = default)
    {
        var results = new List<ShellExecutorOutput>(commands.Count);

        foreach (var command in commands)
        {
            var result = await ExecuteSingleCommandAsync(
                command, options, cancellationToken).ConfigureAwait(false);
            results.Add(result);
        }

        return results;
    }

    private static async Task<ShellExecutorOutput> ExecuteSingleCommandAsync(
        string command,
        ShellToolOptions options,
        CancellationToken cancellationToken)
    {
        var (shell, args) = GetShellAndArgs(command, options.Shell);

        using var process = new Process
        {
            StartInfo = new ProcessStartInfo
            {
                FileName = shell,
                Arguments = args,
                WorkingDirectory = options.WorkingDirectory ?? Environment.CurrentDirectory,
                RedirectStandardOutput = true,
                RedirectStandardError = true,
                UseShellExecute = false,
                CreateNoWindow = true
            }
        };

        var stdout = new StringBuilder();
        var stderr = new StringBuilder();
        bool stdoutTruncated = false;
        bool stderrTruncated = false;
        var outputLock = new object();

        process.OutputDataReceived += (_, e) =>
        {
            if (e.Data != null)
            {
                lock (outputLock)
                {
                    if (stdout.Length < options.MaxOutputLength)
                    {
                        if (stdout.Length + e.Data.Length + 1 > options.MaxOutputLength)
                        {
                            int remainingLength = options.MaxOutputLength - stdout.Length;
                            stdout.Append(e.Data, 0, remainingLength);
                            stdoutTruncated = true;
                        }
                        else
                        {
                            stdout.AppendLine(e.Data);
                        }
                    }
                    else
                    {
                        stdoutTruncated = true;
                    }
                }
            }
        };

        process.ErrorDataReceived += (_, e) =>
        {
            if (e.Data != null)
            {
                lock (outputLock)
                {
                    if (stderr.Length < options.MaxOutputLength)
                    {
                        if (stderr.Length + e.Data.Length + 1 > options.MaxOutputLength)
                        {
                            int remainingLength = options.MaxOutputLength - stderr.Length;
                            stderr.Append(e.Data, 0, remainingLength);
                            stderrTruncated = true;
                        }
                        else
                        {
                            stderr.AppendLine(e.Data);
                        }
                    }
                    else
                    {
                        stderrTruncated = true;
                    }
                }
            }
        };

        using var timeoutCts = new CancellationTokenSource(options.TimeoutInMilliseconds);
        using var linkedCts = CancellationTokenSource.CreateLinkedTokenSource(
            cancellationToken, timeoutCts.Token);

        try
        {
            process.Start();
            process.BeginOutputReadLine();
            process.BeginErrorReadLine();

            await WaitForExitAsync(process, linkedCts.Token).ConfigureAwait(false);

            return new ShellExecutorOutput
            {
                Command = command,
                StandardOutput = stdout.ToString(),
                StandardError = stderr.ToString(),
                ExitCode = process.ExitCode,
                IsTimedOut = false,
                IsTruncated = stdoutTruncated || stderrTruncated
            };
        }
        catch (OperationCanceledException) when (timeoutCts.IsCancellationRequested && !cancellationToken.IsCancellationRequested)
        {
            TryKillProcess(process);
            return new ShellExecutorOutput
            {
                Command = command,
                StandardOutput = stdout.ToString(),
                StandardError = stderr.ToString(),
                IsTimedOut = true,
                IsTruncated = stdoutTruncated || stderrTruncated
            };
        }
        catch (OperationCanceledException)
        {
            // Cancellation was requested by the user
            TryKillProcess(process);
            throw;
        }
        catch (Exception ex)
        {
            return new ShellExecutorOutput
            {
                Command = command,
                Error = ex.Message
            };
        }
    }

    private static (string Shell, string Args) GetShellAndArgs(
        string command, string? shellOverride)
    {
        if (!string.IsNullOrEmpty(shellOverride))
        {
            // When shell is overridden, pass command as single argument
            return (shellOverride!, command);
        }

#if NET
        if (OperatingSystem.IsWindows())
        {
            return ("cmd.exe", $"/c {command}");
        }

        return ("/bin/sh", $"-c \"{command.Replace("\"", "\\\"")}\"");
#else
        // For .NET Framework and .NET Standard, use runtime check
        if (Environment.OSVersion.Platform == PlatformID.Win32NT)
        {
            return ("cmd.exe", $"/c {command}");
        }

        return ("/bin/sh", $"-c \"{command.Replace("\"", "\\\"")}\"");
#endif
    }

    private static void TryKillProcess(Process process)
    {
        try
        {
            if (!process.HasExited)
            {
#if NET
                process.Kill(entireProcessTree: true);
#else
                process.Kill();
#endif
            }
        }
        catch
        {
            // Best effort - process may have already exited
        }
    }

    private static async Task WaitForExitAsync(Process process, CancellationToken cancellationToken)
    {
#if NET
        await process.WaitForExitAsync(cancellationToken).ConfigureAwait(false);
#else
        // Polyfill for .NET Framework and .NET Standard
        var tcs = new TaskCompletionSource<bool>();

        process.EnableRaisingEvents = true;
        process.Exited += (sender, args) => tcs.TrySetResult(true);

        if (process.HasExited)
        {
            tcs.TrySetResult(true);
        }

        using (cancellationToken.Register(() => tcs.TrySetCanceled(cancellationToken)))
        {
            await tcs.Task.ConfigureAwait(false);
        }
#endif
    }
}
