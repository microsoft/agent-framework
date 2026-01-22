// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI;

/// <summary>
/// A tool that executes shell commands with security controls.
/// </summary>
/// <remarks>
/// <para>
/// ShellTool provides a secure way to execute shell commands with configurable
/// allowlist/denylist patterns, privilege escalation prevention, and output limits.
/// </para>
/// <para>
/// Use the <see cref="ShellToolExtensions.AsAIFunction"/> extension method to convert
/// this tool to an <see cref="AIFunction"/> for use with AI agents.
/// </para>
/// </remarks>
public class ShellTool : AITool
{
    private readonly ShellToolOptions _options;
    private readonly ShellExecutor _executor;

    private static readonly string[] PrivilegeEscalationCommands =
    [
        "sudo",
        "su",
        "runas",
        "doas",
        "pkexec"
    ];

    /// <summary>
    /// Initializes a new instance of the <see cref="ShellTool"/> class.
    /// </summary>
    /// <param name="executor">The executor to use for command execution.</param>
    /// <param name="options">Optional configuration options.</param>
    /// <exception cref="ArgumentNullException"><paramref name="executor"/> is null.</exception>
    public ShellTool(ShellExecutor executor, ShellToolOptions? options = null)
    {
        _executor = Throw.IfNull(executor);
        _options = options ?? new ShellToolOptions();
    }

    /// <summary>
    /// Gets the name of the tool.
    /// </summary>
    public override string Name => "shell";

    /// <summary>
    /// Gets the description of the tool.
    /// </summary>
    public override string Description =>
        "Execute shell commands. Returns stdout, stderr, and exit code for each command.";

    /// <summary>
    /// Gets the configured options for this shell tool.
    /// </summary>
    public ShellToolOptions Options => _options;

    /// <summary>
    /// Executes shell commands and returns result content.
    /// </summary>
    /// <param name="callContent">The shell call content containing commands to execute.</param>
    /// <param name="cancellationToken">The cancellation token.</param>
    /// <returns>The result content containing output for each command.</returns>
    /// <exception cref="ArgumentNullException"><paramref name="callContent"/> is null.</exception>
    /// <exception cref="InvalidOperationException">A command is blocked by security rules.</exception>
    public async Task<ShellResultContent> ExecuteAsync(
        ShellCallContent callContent,
        CancellationToken cancellationToken = default)
    {
        _ = Throw.IfNull(callContent);

        // Apply call-specific overrides
        var effectiveOptions = ApplyOverrides(_options, callContent);

        // Validate all commands first
        foreach (var command in callContent.Commands)
        {
            ValidateCommand(command);
        }

        // Execute via the executor
        var rawOutputs = await _executor.ExecuteAsync(
            callContent.Commands,
            effectiveOptions,
            cancellationToken).ConfigureAwait(false);

        // Convert to content
        var outputs = rawOutputs.Select(r => new ShellCommandOutput
        {
            Command = r.Command,
            StandardOutput = r.StandardOutput,
            StandardError = r.StandardError,
            ExitCode = r.ExitCode,
            IsTimedOut = r.IsTimedOut,
            IsTruncated = r.IsTruncated,
            Error = r.Error
        }).ToList();

        return new ShellResultContent(callContent.CallId, outputs)
        {
            MaxOutputLength = effectiveOptions.MaxOutputLength
        };
    }

    private static ShellToolOptions ApplyOverrides(ShellToolOptions baseOptions, ShellCallContent callContent)
    {
        // If no overrides specified, use base options
        if (callContent.TimeoutInMilliseconds is null && callContent.MaxOutputLength is null)
        {
            return baseOptions;
        }

        // Create effective options with overrides
        return new ShellToolOptions
        {
            WorkingDirectory = baseOptions.WorkingDirectory,
            TimeoutInMilliseconds = callContent.TimeoutInMilliseconds ?? baseOptions.TimeoutInMilliseconds,
            MaxOutputLength = callContent.MaxOutputLength ?? baseOptions.MaxOutputLength,
            AllowedCommands = baseOptions.AllowedCommands,
            DeniedCommands = baseOptions.DeniedCommands,
            BlockPrivilegeEscalation = baseOptions.BlockPrivilegeEscalation,
            Shell = baseOptions.Shell
        };
    }

    private void ValidateCommand(string command)
    {
        // 1. Check denylist first (priority over allowlist)
        if (_options.CompiledDeniedPatterns is { Count: > 0 })
        {
            foreach (var pattern in _options.CompiledDeniedPatterns)
            {
                if (pattern.IsMatch(command))
                {
                    throw new InvalidOperationException(
                        "Command blocked by denylist pattern.");
                }
            }
        }

        // 2. Check allowlist (if configured)
        if (_options.CompiledAllowedPatterns is { Count: > 0 })
        {
            bool allowed = _options.CompiledAllowedPatterns
                .Any(p => p.IsMatch(command));
            if (!allowed)
            {
                throw new InvalidOperationException(
                    "Command not in allowlist.");
            }
        }

        // 3. Check privilege escalation
        if (_options.BlockPrivilegeEscalation &&
            ContainsPrivilegeEscalation(command))
        {
            throw new InvalidOperationException(
                "Privilege escalation commands are blocked.");
        }
    }

    private static bool ContainsPrivilegeEscalation(string command)
    {
        var trimmed = command.TrimStart();

        foreach (var dangerous in PrivilegeEscalationCommands)
        {
            if (trimmed.StartsWith(dangerous + " ", StringComparison.OrdinalIgnoreCase) ||
                trimmed.Equals(dangerous, StringComparison.OrdinalIgnoreCase))
            {
                return true;
            }
        }

        return false;
    }
}
