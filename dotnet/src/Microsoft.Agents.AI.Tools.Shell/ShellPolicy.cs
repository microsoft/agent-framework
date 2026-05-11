// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Text.RegularExpressions;

namespace Microsoft.Agents.AI.Tools.Shell;

/// <summary>
/// A shell command awaiting a policy decision.
/// </summary>
/// <remarks>
/// Plain <see langword="readonly struct"/> rather than a record struct: the
/// type carries no equality semantics that callers care about, and the
/// minimal POCO is cheaper than the synthesized record machinery.
/// </remarks>
public readonly struct ShellRequest : IEquatable<ShellRequest>
{
    /// <summary>Initializes a new instance of the <see cref="ShellRequest"/> struct.</summary>
    /// <param name="command">The full command line that the agent wants to run.</param>
    /// <param name="workingDirectory">Optional working directory the command will execute in, if known.</param>
    public ShellRequest(string command, string? workingDirectory = null)
    {
        this.Command = command;
        this.WorkingDirectory = workingDirectory;
    }

    /// <summary>Gets the full command line that the agent wants to run.</summary>
    public string Command { get; }

    /// <summary>Gets the optional working directory the command will execute in, if known.</summary>
    public string? WorkingDirectory { get; }

    /// <inheritdoc />
    public bool Equals(ShellRequest other) =>
        string.Equals(this.Command, other.Command, StringComparison.Ordinal)
        && string.Equals(this.WorkingDirectory, other.WorkingDirectory, StringComparison.Ordinal);

    /// <inheritdoc />
    public override bool Equals(object? obj) => obj is ShellRequest r && this.Equals(r);

    /// <inheritdoc />
    public override int GetHashCode() => HashCode.Combine(this.Command, this.WorkingDirectory);

    /// <summary>Equality operator.</summary>
    public static bool operator ==(ShellRequest left, ShellRequest right) => left.Equals(right);

    /// <summary>Inequality operator.</summary>
    public static bool operator !=(ShellRequest left, ShellRequest right) => !left.Equals(right);
}

/// <summary>
/// The outcome of a <see cref="ShellPolicy"/> evaluation.
/// </summary>
public readonly struct ShellPolicyOutcome : IEquatable<ShellPolicyOutcome>
{
    /// <summary>Initializes a new instance of the <see cref="ShellPolicyOutcome"/> struct.</summary>
    /// <param name="allowed"><see langword="true"/> when the command may run.</param>
    /// <param name="reason">Human-readable rationale; populated for both allow and deny when applicable.</param>
    public ShellPolicyOutcome(bool allowed, string? reason = null)
    {
        this.Allowed = allowed;
        this.Reason = reason;
    }

    /// <summary>Gets a value indicating whether the command may run.</summary>
    public bool Allowed { get; }

    /// <summary>Gets the human-readable rationale; populated for both allow and deny when applicable.</summary>
    public string? Reason { get; }

    /// <summary>Gets a default-allow outcome.</summary>
    public static ShellPolicyOutcome Allow { get; } = new(true);

    /// <summary>Build a deny outcome with a human-readable reason.</summary>
    /// <param name="reason">The rationale to surface to the caller.</param>
    /// <returns>A new <see cref="ShellPolicyOutcome"/>.</returns>
    public static ShellPolicyOutcome Deny(string reason) => new(false, reason);

    /// <inheritdoc />
    public bool Equals(ShellPolicyOutcome other) =>
        this.Allowed == other.Allowed
        && string.Equals(this.Reason, other.Reason, StringComparison.Ordinal);

    /// <inheritdoc />
    public override bool Equals(object? obj) => obj is ShellPolicyOutcome o && this.Equals(o);

    /// <inheritdoc />
    public override int GetHashCode() => HashCode.Combine(this.Allowed, this.Reason);

    /// <summary>Equality operator.</summary>
    public static bool operator ==(ShellPolicyOutcome left, ShellPolicyOutcome right) => left.Equals(right);

    /// <summary>Inequality operator.</summary>
    public static bool operator !=(ShellPolicyOutcome left, ShellPolicyOutcome right) => !left.Equals(right);
}

/// <summary>
/// Layered allow/deny pattern filter for shell commands.
/// </summary>
/// <remarks>
/// <para>
/// <b>This is not a security control.</b> It is a regex-based pre-filter
/// that operators can use to fast-fail literal commands they would rather
/// see rejected with a clear error than run (e.g. site-specific patterns
/// like a production hostname, or obviously-destructive shapes like
/// <c>rm -rf /</c>). Pattern-based filters are trivially bypassed by
/// variable expansion (<c>${RM:=rm} -rf /</c>), interpreter escapes
/// (<c>python -c "…"</c>), command substitution
/// (<c>$(base64 -d &lt;&lt;&lt; …)</c>, <c>$(echo -e "\xNN…")</c>),
/// envvar splicing (<c>$(A=r B=m; echo $A$B)</c>), alternative tools
/// (<c>find / -delete</c>), or PowerShell-native verbs
/// (<c>Remove-Item -Recurse -Force</c>). The real security boundary is
/// approval-in-the-loop (see <see cref="LocalShellExecutor"/>,
/// <see cref="DockerShellExecutor"/>) and container isolation (Docker).
/// No major agent framework relies on pattern matching as a primary
/// shell-command defense for these reasons.
/// </para>
/// <para>
/// <b>No default patterns.</b> A <see cref="ShellPolicy"/> constructed
/// with no arguments has an empty deny list and an empty allow list —
/// it will allow any non-empty command. Operators who want pre-execution
/// rejection of specific shapes must supply their own
/// <paramref>denyList</paramref>.
/// </para>
/// <para>
/// <b>Evaluation order — allow short-circuits deny.</b> Allow patterns are
/// checked first; a match returns immediately without consulting the deny
/// list. Use allow patterns sparingly (and prefer narrowly anchored regexes
/// like <c>^git\s+status$</c> rather than substring matches), because an
/// over-broad allow pattern can re-enable a command that the deny list was
/// supposed to block.
/// </para>
/// </remarks>
public sealed class ShellPolicy
{
    private readonly IReadOnlyList<Regex> _denies;
    private readonly IReadOnlyList<Regex> _allows;

    /// <summary>
    /// Initializes a new instance of the <see cref="ShellPolicy"/> class.
    /// </summary>
    /// <param name="denyList">
    /// Patterns that trigger a deny outcome. <see langword="null"/> or an
    /// empty collection disables the deny list entirely.
    /// </param>
    /// <param name="allowList">
    /// Optional explicit-allow patterns. A match here short-circuits the
    /// deny list and is useful when the caller knows the command is safe.
    /// </param>
    public ShellPolicy(IEnumerable<string>? denyList = null, IEnumerable<string>? allowList = null)
    {
        var deny = new List<Regex>();
        if (denyList is not null)
        {
            foreach (var pattern in denyList)
            {
                deny.Add(new Regex(pattern, RegexOptions.Compiled | RegexOptions.IgnoreCase));
            }
        }
        this._denies = deny;

        var allow = new List<Regex>();
        if (allowList is not null)
        {
            foreach (var pattern in allowList)
            {
                allow.Add(new Regex(pattern, RegexOptions.Compiled | RegexOptions.IgnoreCase));
            }
        }
        this._allows = allow;
    }

    /// <summary>
    /// Evaluate <paramref name="request"/> and return an outcome.
    /// </summary>
    /// <remarks>
    /// Order of operations: empty-command guard → explicit allow patterns
    /// (a match short-circuits with <see cref="ShellPolicyOutcome.Allow"/>)
    /// → deny patterns (first match wins) → default allow.
    /// </remarks>
    /// <param name="request">The request to evaluate.</param>
    /// <returns>An allow or deny outcome.</returns>
    public ShellPolicyOutcome Evaluate(ShellRequest request)
    {
        var command = request.Command?.Trim() ?? string.Empty;
        if (command.Length == 0)
        {
            return ShellPolicyOutcome.Deny("empty command");
        }

        foreach (var allow in this._allows)
        {
            if (allow.IsMatch(command))
            {
                return new ShellPolicyOutcome(true, "matched allow pattern");
            }
        }

        foreach (var deny in this._denies)
        {
            if (deny.IsMatch(command))
            {
                return ShellPolicyOutcome.Deny($"matched deny pattern: {deny}");
            }
        }

        return ShellPolicyOutcome.Allow;
    }
}
