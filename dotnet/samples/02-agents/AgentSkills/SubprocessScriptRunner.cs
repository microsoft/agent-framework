// Copyright (c) Microsoft. All rights reserved.

// Sample subprocess-based skill script runner.
// Executes file-based skill scripts as local subprocesses.
// This is provided for demonstration purposes only.

using System.Diagnostics;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;

/// <summary>
/// Executes file-based skill scripts as local subprocesses.
/// </summary>
/// <remarks>
/// This runner uses the script's absolute path, converts the arguments
/// to CLI flags, and returns captured output. It is intended for
/// demonstration purposes only.
/// </remarks>
internal static class SubprocessScriptRunner
{
    /// <summary>
    /// Runs a skill script as a local subprocess.
    /// </summary>
    public static async Task<object?> RunAsync(
        AgentFileSkill skill,
        AgentFileSkillScript script,
        AIFunctionArguments arguments,
        CancellationToken cancellationToken)
    {
        if (!File.Exists(script.FullPath))
        {
            return $"Error: Script file not found: {script.FullPath}";
        }

        string extension = Path.GetExtension(script.FullPath);
        string? interpreter = extension switch
        {
            ".py" => "python3",
            ".js" => "node",
            ".sh" => "bash",
            ".ps1" => "pwsh",
            _ => null,
        };

        var startInfo = new ProcessStartInfo
        {
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            UseShellExecute = false,
            CreateNoWindow = true,
            WorkingDirectory = Path.GetDirectoryName(script.FullPath) ?? ".",
        };

        if (interpreter is not null)
        {
            startInfo.FileName = interpreter;
            startInfo.ArgumentList.Add(script.FullPath);
        }
        else
        {
            startInfo.FileName = script.FullPath;
        }

        if (arguments is not null)
        {
            foreach (var (key, value) in arguments)
            {
                if (value is bool boolValue)
                {
                    if (boolValue)
                    {
                        startInfo.ArgumentList.Add(NormalizeKey(key));
                    }
                }
                else if (value is not null)
                {
                    startInfo.ArgumentList.Add(NormalizeKey(key));
                    startInfo.ArgumentList.Add(value.ToString()!);
                }
            }
        }

        Process? process = null;
        try
        {
            process = Process.Start(startInfo);
            if (process is null)
            {
                return $"Error: Failed to start process for script '{script.Name}'.";
            }

            Task<string> outputTask = process.StandardOutput.ReadToEndAsync(cancellationToken);
            Task<string> errorTask = process.StandardError.ReadToEndAsync(cancellationToken);

            await process.WaitForExitAsync(cancellationToken).ConfigureAwait(false);

            string output = await outputTask.ConfigureAwait(false);
            string error = await errorTask.ConfigureAwait(false);

            if (!string.IsNullOrEmpty(error))
            {
                output += $"\nStderr:\n{error}";
            }

            if (process.ExitCode != 0)
            {
                output += $"\nScript exited with code {process.ExitCode}";
            }

            return string.IsNullOrEmpty(output) ? "(no output)" : output.Trim();
        }
        catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
        {
            // Kill the process on cancellation to avoid leaving orphaned subprocesses.
            process?.Kill(entireProcessTree: true);
            throw;
        }
        catch (OperationCanceledException)
        {
            throw;
        }
        catch (Exception ex)
        {
            return $"Error: Failed to execute script '{script.Name}': {ex.Message}";
        }
        finally
        {
            process?.Dispose();
        }
    }

    /// <summary>
    /// Normalizes a parameter key to a consistent --flag format.
    /// Models may return keys with or without leading dashes (e.g., "value" vs "--value").
    /// </summary>
    private static string NormalizeKey(string key) => "--" + key.TrimStart('-');
}
