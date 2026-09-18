// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics;
using System.Text.Json;
using Microsoft.Agents.AI;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Logging.Abstractions;

namespace ClawAgent;

/// <summary>
/// Executes file-based skill scripts as local subprocesses.
/// </summary>
internal sealed class SubprocessScriptRunner
{
    private static readonly TimeSpan s_scriptTimeout = TimeSpan.FromSeconds(30);
    private readonly ILogger _logger;

    /// <summary>
    /// Initializes a new instance of the <see cref="SubprocessScriptRunner" /> class.
    /// </summary>
    public SubprocessScriptRunner(ILoggerFactory? loggerFactory = null)
    {
        this._logger = (loggerFactory ?? NullLoggerFactory.Instance).CreateLogger<SubprocessScriptRunner>();
    }

    /// <summary>
    /// Runs a skill script as a local subprocess.
    /// </summary>
    public async Task<object?> RunAsync(
        AgentFileSkill skill,
        AgentFileSkillScript script,
        JsonElement? arguments,
        IServiceProvider? serviceProvider,
        CancellationToken cancellationToken)
    {
        this._logger.LogDebug("Running script '{ScriptName}' from skill '{SkillName}'.", script.Name, skill.Frontmatter.Name);

        if (!File.Exists(script.FullPath))
        {
            this._logger.LogError("Script file not found for skill '{SkillName}': {ScriptPath}", skill.Frontmatter.Name, script.FullPath);
            return $"Error: Script file not found: {script.FullPath}";
        }

        string extension = Path.GetExtension(script.FullPath);
        string? interpreter = extension switch
        {
            ".py" => OperatingSystem.IsWindows() ? "python" : "python3",
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

        if (arguments is { ValueKind: JsonValueKind.Array } json)
        {
            foreach (var element in json.EnumerateArray())
            {
                if (element.ValueKind != JsonValueKind.String)
                {
                    throw new InvalidOperationException(
                        $"File-based skill scripts only accept string CLI arguments but received a JSON element of kind '{element.ValueKind}'. " +
                        "All array elements must be JSON strings.");
                }

                startInfo.ArgumentList.Add(element.GetString()!);
            }
        }
        else if (arguments?.ValueKind is not null and not JsonValueKind.Null and not JsonValueKind.Undefined)
        {
            throw new InvalidOperationException(
                $"Expected a JSON array of CLI arguments but received {arguments.Value.ValueKind}. " +
                "File-based skill scripts expect positional arguments as a JSON array of strings.");
        }

        using var timeoutCts = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
        timeoutCts.CancelAfter(s_scriptTimeout);
        CancellationToken runToken = timeoutCts.Token;

        Process? process = null;
        try
        {
            process = Process.Start(startInfo);
            if (process is null)
            {
                this._logger.LogError("Failed to start process for script '{ScriptName}' from skill '{SkillName}'.", script.Name, skill.Frontmatter.Name);
                return $"Error: Failed to start process for script '{script.Name}'.";
            }

            Task<string> outputTask = process.StandardOutput.ReadToEndAsync(runToken);
            Task<string> errorTask = process.StandardError.ReadToEndAsync(runToken);

            await process.WaitForExitAsync(runToken).ConfigureAwait(false);

            string output = await outputTask.ConfigureAwait(false);
            string error = await errorTask.ConfigureAwait(false);

            if (!string.IsNullOrEmpty(error))
            {
                if (process.ExitCode == 0)
                {
                    this._logger.LogWarning(
                        "Script '{ScriptName}' from skill '{SkillName}' succeeded but wrote to stderr:\n{Stderr}",
                        script.Name, skill.Frontmatter.Name, error.Trim());
                }

                output += $"\nStderr:\n{error}";
            }

            if (process.ExitCode != 0)
            {
                this._logger.LogError(
                    "Script '{ScriptName}' from skill '{SkillName}' exited with code {ExitCode}.{Stderr}",
                    script.Name,
                    skill.Frontmatter.Name,
                    process.ExitCode,
                    string.IsNullOrEmpty(error) ? string.Empty : $"\nStderr:\n{error.Trim()}");

                output += $"\nScript exited with code {process.ExitCode}";
            }

            string result = string.IsNullOrEmpty(output) ? "(no output)" : output.Trim();

            if (process.ExitCode == 0)
            {
                this._logger.LogInformation(
                    "Script '{ScriptName}' from skill '{SkillName}' completed successfully. Output:\n{Output}",
                    script.Name,
                    skill.Frontmatter.Name,
                    result);
            }

            return result;
        }
        catch (OperationCanceledException) when (!cancellationToken.IsCancellationRequested)
        {
            process?.Kill(entireProcessTree: true);
            this._logger.LogError(
                "Script '{ScriptName}' from skill '{SkillName}' timed out after {Timeout} seconds.",
                script.Name,
                skill.Frontmatter.Name,
                s_scriptTimeout.TotalSeconds);
            return $"Error: Script '{script.Name}' timed out after {s_scriptTimeout.TotalSeconds:0} seconds.";
        }
        catch (OperationCanceledException)
        {
            process?.Kill(entireProcessTree: true);
            throw;
        }
        catch (Exception ex)
        {
            this._logger.LogError(ex, "Failed to execute script '{ScriptName}' from skill '{SkillName}'.", script.Name, skill.Frontmatter.Name);
            return $"Error: Failed to execute script '{script.Name}': {ex.Message}";
        }
        finally
        {
            process?.Dispose();
        }
    }
}
