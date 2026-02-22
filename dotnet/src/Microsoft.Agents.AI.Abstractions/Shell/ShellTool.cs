// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text;
using System.Text.RegularExpressions;
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
    private readonly ShellExecutor _executor;
    private readonly IReadOnlyList<Regex>? _compiledAllowedPatterns;
    private readonly IReadOnlyList<Regex>? _compiledDeniedPatterns;

    private static readonly string[] s_privilegeEscalationCommands =
    [
        "sudo",
        "su",
        "runas",
        "doas",
        "pkexec"
    ];

    private static readonly string[] s_shellWrapperCommands =
    [
        "sh",
        "bash",
        "zsh",
        "dash",
        "ksh",
        "csh",
        "tcsh"
    ];

    private static readonly Regex[] s_defaultDangerousPatterns =
    [
        // Fork bomb: :(){ :|:& };:
        new Regex(@":\(\)\s*\{\s*:\|:\s*&\s*\}\s*;", RegexOptions.Compiled, TimeSpan.FromSeconds(1)),
        // rm -rf / variants
        new Regex(@"rm\s+(-[rRfF]+\s+)*(/|/\*|\*/)", RegexOptions.Compiled, TimeSpan.FromSeconds(1)),
        // Format filesystem
        new Regex(@"mkfs\.", RegexOptions.Compiled, TimeSpan.FromSeconds(1)),
        // Direct disk write
        new Regex(@"dd\s+.*of=/dev/", RegexOptions.Compiled, TimeSpan.FromSeconds(1)),
        // Overwrite disk
        new Regex(@">\s*/dev/sd", RegexOptions.Compiled, TimeSpan.FromSeconds(1)),
        // chmod 777 /
        new Regex(@"chmod\s+(-[rR]\s+)?777\s+/", RegexOptions.Compiled, TimeSpan.FromSeconds(1)),
    ];

    /// <summary>
    /// Initializes a new instance of the <see cref="ShellTool"/> class.
    /// </summary>
    /// <param name="executor">The executor to use for command execution.</param>
    /// <param name="options">Optional configuration options.</param>
    /// <exception cref="ArgumentNullException"><paramref name="executor"/> is null.</exception>
    public ShellTool(ShellExecutor executor, ShellToolOptions? options = null)
    {
        this._executor = Throw.IfNull(executor);
        this.Options = options ?? new ShellToolOptions();

        // Compile patterns once at construction time
        this._compiledAllowedPatterns = CompilePatterns(this.Options.AllowedCommands);
        this._compiledDeniedPatterns = CompilePatterns(this.Options.DeniedCommands);
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
    public ShellToolOptions Options { get; }

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

        // Validate all commands first
        foreach (var command in callContent.Commands)
        {
            this.ValidateCommand(command);
        }

        // Execute via the executor
        var rawOutputs = await this._executor.ExecuteAsync(
            callContent.Commands,
            this.Options,
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
            MaxOutputLength = this.Options.MaxOutputLength
        };
    }

    private void ValidateCommand(string command)
    {
        // 1. Check denylist first (priority over allowlist)
        if (this._compiledDeniedPatterns is { Count: > 0 })
        {
            foreach (var pattern in this._compiledDeniedPatterns)
            {
                if (pattern.IsMatch(command))
                {
                    throw new InvalidOperationException(
                        "Command blocked by denylist pattern.");
                }
            }
        }

        // 2. Check default dangerous patterns (if enabled)
        if (this.Options.BlockDangerousPatterns)
        {
            foreach (var pattern in s_defaultDangerousPatterns)
            {
                if (pattern.IsMatch(command))
                {
                    throw new InvalidOperationException(
                        "Command blocked by dangerous pattern.");
                }
            }
        }

        // 3. Check command chaining (if enabled)
        if (this.Options.BlockCommandChaining && ContainsCommandChaining(command))
        {
            throw new InvalidOperationException(
                "Command chaining operators are blocked.");
        }

        // 4. Check privilege escalation
        if (this.Options.BlockPrivilegeEscalation && ContainsPrivilegeEscalation(command))
        {
            throw new InvalidOperationException(
                "Privilege escalation commands are blocked.");
        }

        // 5. Check path access control
        this.ValidatePathAccess(command);

        // 6. Check allowlist (if configured)
        if (this._compiledAllowedPatterns is { Count: > 0 })
        {
            bool allowed = this._compiledAllowedPatterns
                .Any(p => p.IsMatch(command));
            if (!allowed)
            {
                throw new InvalidOperationException(
                    "Command not in allowlist.");
            }
        }
    }

    private static bool ContainsCommandChaining(string command)
    {
        var inSingleQuote = false;
        var inDoubleQuote = false;
        var i = 0;

        while (i < command.Length)
        {
            var c = command[i];

            // Handle escape sequences
            if (c == '\\' && i + 1 < command.Length)
            {
                i += 2;
                continue;
            }

            // Handle quote state transitions
            if (c == '\'' && !inDoubleQuote)
            {
                inSingleQuote = !inSingleQuote;
                i++;
                continue;
            }

            if (c == '"' && !inSingleQuote)
            {
                inDoubleQuote = !inDoubleQuote;
                i++;
                continue;
            }

            // Only check for operators outside quotes
            if (!inSingleQuote && !inDoubleQuote)
            {
                // Check for semicolon
                if (c == ';')
                {
                    return true;
                }

                // Check for pipe (but not ||)
                if (c == '|')
                {
                    // Check if it's || (OR operator) or just |
                    return true; // Both are blocked
                }

                // Check for &&
                if (c == '&' && i + 1 < command.Length && command[i + 1] == '&')
                {
                    return true;
                }

                // Check for $() command substitution
                if (c == '$' && i + 1 < command.Length && command[i + 1] == '(')
                {
                    return true;
                }

                // Check for backtick command substitution
                if (c == '`')
                {
                    return true;
                }
            }

            i++;
        }

        return false;
    }

    private static bool ContainsPrivilegeEscalation(string command)
    {
        var tokens = TokenizeCommand(command);

        if (tokens.Count == 0)
        {
            return false;
        }

        var firstToken = tokens[0];

        // Normalize path separators for cross-platform compatibility
        var normalizedToken = firstToken.Replace('\\', '/');

        // Normalize: extract filename from path (e.g., "/usr/bin/sudo" -> "sudo")
        var executable = Path.GetFileName(normalizedToken);

        // Also handle Windows .exe extension (e.g., "runas.exe" -> "runas")
        var executableWithoutExt = Path.GetFileNameWithoutExtension(normalizedToken);

        // Check if the first token is a privilege escalation command
        if (s_privilegeEscalationCommands.Any(d =>
            string.Equals(executable, d, StringComparison.OrdinalIgnoreCase) ||
            string.Equals(executableWithoutExt, d, StringComparison.OrdinalIgnoreCase)))
        {
            return true;
        }

        // Check for shell wrapper patterns (e.g., "sh -c 'sudo ...'") and recursively validate
        if (IsShellWrapper(executable, executableWithoutExt) && tokens.Count >= 3)
        {
            // Look for -c flag followed by command string
            for (var i = 1; i < tokens.Count - 1; i++)
            {
                if (string.Equals(tokens[i], "-c", StringComparison.Ordinal))
                {
                    // The next token is the command string to execute
                    var nestedCommand = tokens[i + 1];
                    if (ContainsPrivilegeEscalation(nestedCommand))
                    {
                        return true;
                    }

                    break;
                }
            }
        }

        return false;
    }

    private static bool IsShellWrapper(string executable, string executableWithoutExt)
    {
        return s_shellWrapperCommands.Any(s =>
            string.Equals(executable, s, StringComparison.OrdinalIgnoreCase) ||
            string.Equals(executableWithoutExt, s, StringComparison.OrdinalIgnoreCase));
    }

    private static List<string> TokenizeCommand(string command)
    {
        var tokens = new List<string>();
        var currentToken = new StringBuilder();
        var inSingleQuote = false;
        var inDoubleQuote = false;
        var i = 0;

        while (i < command.Length)
        {
            var c = command[i];

            // Handle escape sequences (only when inside double quotes or for special characters)
            // Don't treat backslash as escape if followed by alphanumeric (likely Windows path)
            if (c == '\\' && i + 1 < command.Length && !inSingleQuote)
            {
                var nextChar = command[i + 1];
                var isEscapeSequence = inDoubleQuote || !char.IsLetterOrDigit(nextChar);

                if (isEscapeSequence)
                {
                    currentToken.Append(nextChar);
                    i += 2;
                    continue;
                }
            }

            // Handle quote state transitions
            if (c == '\'' && !inDoubleQuote)
            {
                inSingleQuote = !inSingleQuote;
                i++;
                continue;
            }

            if (c == '"' && !inSingleQuote)
            {
                inDoubleQuote = !inDoubleQuote;
                i++;
                continue;
            }

            // Handle whitespace
            if (char.IsWhiteSpace(c) && !inSingleQuote && !inDoubleQuote)
            {
                if (currentToken.Length > 0)
                {
                    tokens.Add(currentToken.ToString());
                    currentToken.Clear();
                }

                i++;
                continue;
            }

            currentToken.Append(c);
            i++;
        }

        // Add the last token if any
        if (currentToken.Length > 0)
        {
            tokens.Add(currentToken.ToString());
        }

        return tokens;
    }

    private void ValidatePathAccess(string command)
    {
        var blockedPaths = this.Options.BlockedPaths;
        var allowedPaths = this.Options.AllowedPaths;

        // If no path restrictions are configured, skip
        if ((blockedPaths is null || blockedPaths.Count == 0) &&
            (allowedPaths is null || allowedPaths.Count == 0))
        {
            return;
        }

        // Extract paths from the command
        foreach (var path in this.ExtractPaths(command))
        {
            var normalizedPath = NormalizePath(path);

            // Check blocklist first (takes priority)
            if (blockedPaths is { Count: > 0 })
            {
                foreach (var blockedPath in blockedPaths)
                {
                    var normalizedBlockedPath = NormalizePath(blockedPath);
                    if (IsPathWithin(normalizedPath, normalizedBlockedPath))
                    {
                        throw new InvalidOperationException(
                            $"Access to path '{path}' is blocked.");
                    }
                }
            }

            // Check allowlist (if configured, all paths must be within allowed paths)
            if (allowedPaths is { Count: > 0 })
            {
                var isAllowed = allowedPaths.Any(allowedPath =>
                    IsPathWithin(normalizedPath, NormalizePath(allowedPath)));

                if (!isAllowed)
                {
                    throw new InvalidOperationException(
                        $"Access to path '{path}' is not allowed.");
                }
            }
        }
    }

    private List<string> ExtractPaths(string command)
    {
        var paths = new List<string>();
        var tokens = TokenizeCommand(command);

        // Skip command name (first token), check remaining for paths
        for (var i = 1; i < tokens.Count; i++)
        {
            var token = tokens[i];

            // Skip flags/options
            if (token.StartsWith("-", StringComparison.Ordinal))
            {
                continue;
            }

            // Check if token looks like a path (contains separators or starts with .)
            if (token.Contains('/') || token.Contains('\\') ||
                token.StartsWith(".", StringComparison.Ordinal))
            {
                // Resolve relative paths against working directory
                var resolved = Path.IsPathRooted(token)
                    ? token
                    : Path.Combine(this.Options.WorkingDirectory ?? Environment.CurrentDirectory, token);
                paths.Add(resolved);
            }
        }

        return paths;
    }

    private static string NormalizePath(string path)
    {
        // Handle empty or whitespace
        if (string.IsNullOrWhiteSpace(path))
        {
            return string.Empty;
        }

        // Normalize path separators and resolve . and ..
        try
        {
            // Use GetFullPath to resolve relative paths like /etc/../etc
            var fullPath = Path.GetFullPath(path);

            // Normalize to forward slashes for consistent comparison on all platforms
            return fullPath.Replace('\\', '/').TrimEnd('/').ToUpperInvariant();
        }
        catch
        {
            // If path resolution fails, just normalize separators
            return path.Replace('\\', '/').TrimEnd('/').ToUpperInvariant();
        }
    }

    private static bool IsPathWithin(string path, string basePath)
    {
        if (string.IsNullOrEmpty(basePath))
        {
            return false;
        }

        // Ensure basePath ends with separator for proper prefix matching
        var basePathWithSep = basePath[basePath.Length - 1] == '/' ? basePath : basePath + "/";

        // Path is within basePath if it equals basePath or starts with basePath/
        return string.Equals(path, basePath, StringComparison.OrdinalIgnoreCase) ||
               path.StartsWith(basePathWithSep, StringComparison.OrdinalIgnoreCase);
    }

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
                // Invalid regex - treat as literal string match
                compiled.Add(new Regex(
                    Regex.Escape(pattern),
                    RegexOptions.Compiled | RegexOptions.IgnoreCase,
                    TimeSpan.FromSeconds(1)));
            }
        }

        return compiled;
    }
}
