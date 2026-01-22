// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Text.RegularExpressions;

namespace Microsoft.Agents.AI;

/// <summary>
/// Options for configuring shell tool behavior and security.
/// </summary>
public class ShellToolOptions
{
    /// <summary>
    /// Gets or sets the working directory for command execution.
    /// When null, uses the current working directory.
    /// </summary>
    public string? WorkingDirectory { get; set; }

    /// <summary>
    /// Gets or sets the command execution timeout in milliseconds.
    /// Default: 60000 (60 seconds).
    /// </summary>
    public int TimeoutInMilliseconds { get; set; } = 60000;

    /// <summary>
    /// Gets or sets the maximum output size in bytes.
    /// Default: 51200 (50 KB).
    /// </summary>
    public int MaxOutputLength { get; set; } = 51200;

    /// <summary>
    /// Gets or sets the allowlist of permitted command patterns.
    /// Supports regex patterns. Denylist takes priority over allowlist.
    /// </summary>
    /// <remarks>
    /// <para>
    /// When configured, only commands matching at least one of the patterns will be allowed to execute.
    /// If a command matches a denylist pattern, it will be blocked regardless of allowlist matches.
    /// </para>
    /// <para>
    /// Patterns can be regular expressions (e.g., <c>^git\s</c>) or literal strings.
    /// Invalid regex patterns are automatically treated as literal strings.
    /// </para>
    /// </remarks>
    public IList<string>? AllowedCommands
    {
        get;
        set
        {
            field = value;
            this.CompiledAllowedPatterns = CompilePatterns(value);
        }
    }

    /// <summary>
    /// Gets or sets the denylist of blocked command patterns.
    /// Supports regex patterns. Denylist takes priority over allowlist.
    /// </summary>
    /// <remarks>
    /// <para>
    /// Commands matching any denylist pattern will be blocked, even if they also match an allowlist pattern.
    /// </para>
    /// <para>
    /// Patterns can be regular expressions (e.g., <c>rm\s+-rf</c>) or literal strings.
    /// Invalid regex patterns are automatically treated as literal strings.
    /// </para>
    /// </remarks>
    public IList<string>? DeniedCommands
    {
        get;
        set
        {
            field = value;
            this.CompiledDeniedPatterns = CompilePatterns(value);
        }
    }

    /// <summary>
    /// Gets or sets a value indicating whether privilege escalation commands are blocked.
    /// Default: true.
    /// </summary>
    /// <remarks>
    /// When enabled, commands starting with <c>sudo</c>, <c>su</c>, <c>runas</c>, <c>doas</c>, or <c>pkexec</c>
    /// will be blocked.
    /// </remarks>
    public bool BlockPrivilegeEscalation { get; set; } = true;

    /// <summary>
    /// Gets or sets a value indicating whether command chaining operators are blocked.
    /// Default: true.
    /// </summary>
    /// <remarks>
    /// <para>
    /// When enabled, commands containing shell metacharacters for chaining are blocked.
    /// This includes: <c>;</c> (command separator), <c>|</c> (pipe), <c>&amp;&amp;</c> (AND),
    /// <c>||</c> (OR), <c>$()</c> (command substitution), and backticks.
    /// </para>
    /// <para>
    /// Operators inside quoted strings are allowed.
    /// </para>
    /// </remarks>
    public bool BlockCommandChaining { get; set; } = true;

    /// <summary>
    /// Gets or sets a value indicating whether default dangerous patterns are blocked.
    /// Default: true.
    /// </summary>
    /// <remarks>
    /// When enabled, commands matching dangerous patterns are blocked, including fork bombs,
    /// <c>rm -rf /</c> variants, filesystem formatting commands, and direct disk writes.
    /// </remarks>
    public bool BlockDangerousPatterns { get; set; } = true;

    /// <summary>
    /// Gets or sets paths that commands are not allowed to access.
    /// Takes priority over <see cref="AllowedPaths"/>.
    /// </summary>
    /// <remarks>
    /// Paths are normalized for comparison. A command is blocked if it references
    /// any path that starts with a blocked path.
    /// </remarks>
    public IList<string>? BlockedPaths { get; set; }

    /// <summary>
    /// Gets or sets paths that commands are allowed to access.
    /// If set, commands can only access these paths.
    /// </summary>
    /// <remarks>
    /// <para>
    /// When configured, all paths in the command must be within one of the allowed paths.
    /// If a command references a path not in the allowed list, it will be blocked.
    /// </para>
    /// <para>
    /// <see cref="BlockedPaths"/> takes priority over this setting.
    /// </para>
    /// </remarks>
    public IList<string>? AllowedPaths { get; set; }

    /// <summary>
    /// Gets or sets the shell executable to use.
    /// When null, auto-detects based on OS (cmd.exe on Windows, /bin/sh on Unix).
    /// </summary>
    public string? Shell { get; set; }

    /// <summary>
    /// Gets the compiled allowlist patterns for internal use.
    /// </summary>
    internal IReadOnlyList<Regex>? CompiledAllowedPatterns { get; private set; }

    /// <summary>
    /// Gets the compiled denylist patterns for internal use.
    /// </summary>
    internal IReadOnlyList<Regex>? CompiledDeniedPatterns { get; private set; }

    private static List<Regex>? CompilePatterns(IList<string>? patterns)
    {
        if (patterns is null || patterns.Count == 0)
        {
            return null;
        }

        var compiled = new List<Regex>(patterns.Count);
        foreach (var pattern in patterns)
        {
            // Try-catch is used here because there is no way to validate a regex pattern
            // without attempting to compile it.
            try
            {
                compiled.Add(new Regex(
                    pattern,
                    RegexOptions.Compiled | RegexOptions.IgnoreCase,
                    TimeSpan.FromSeconds(1)));
            }
            catch (ArgumentException)
            {
                // Treat as literal string match
                compiled.Add(new Regex(
                    Regex.Escape(pattern),
                    RegexOptions.Compiled | RegexOptions.IgnoreCase,
                    TimeSpan.FromSeconds(1)));
            }
        }

        return compiled;
    }
}
