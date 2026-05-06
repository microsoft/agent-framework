// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Text.RegularExpressions;

namespace Microsoft.Agents.AI.Tools.Shell;

/// <summary>
/// A shell command awaiting a policy decision.
/// </summary>
/// <param name="Command">The full command line that the agent wants to run.</param>
/// <param name="WorkingDirectory">Optional working directory the command will execute in, if known.</param>
public readonly record struct ShellRequest(string Command, string? WorkingDirectory = null);

/// <summary>
/// The outcome of a <see cref="ShellPolicy"/> evaluation.
/// </summary>
/// <param name="Allowed"><see langword="true"/> when the command may run.</param>
/// <param name="Reason">Human-readable rationale; populated for both allow and deny when applicable.</param>
public readonly record struct ShellDecision(bool Allowed, string? Reason = null)
{
    /// <summary>Gets a default-allow decision.</summary>
    public static ShellDecision Allow { get; } = new(true);

    /// <summary>Build a deny decision with a human-readable reason.</summary>
    /// <param name="reason">The rationale to surface to the caller.</param>
    /// <returns>A new <see cref="ShellDecision"/>.</returns>
    public static ShellDecision Deny(string reason) => new(false, reason);
}

/// <summary>
/// Layered allow/deny policy for shell commands.
/// </summary>
/// <remarks>
/// <para>
/// <b>This is a guardrail, not a security boundary.</b> Pattern-based filters
/// are routinely bypassed via variable expansion (<c>${RM:=rm} -rf /</c>),
/// interpreter escapes (<c>python -c "…"</c>), base64 smuggling, alternative
/// tools (<c>find / -delete</c>), or PowerShell-native verbs
/// (<c>Remove-Item -Recurse -Force</c>). The actual security boundary is
/// approval-in-the-loop (see <see cref="LocalShellTool"/>) or container
/// isolation (Docker/Firecracker, planned in a follow-up).
/// </para>
/// <para>
/// Evaluation order: explicit allow patterns short-circuit; otherwise the
/// command is checked against the deny list; otherwise the request is allowed.
/// </para>
/// </remarks>
public sealed class ShellPolicy
{
    /// <summary>
    /// Gets a conservative default deny list. Documented as a guardrail only.
    /// </summary>
    public static IReadOnlyList<string> DefaultDenyList { get; } =
    [
        @"\brm\s+(?:-[a-zA-Z]*r[a-zA-Z]*\s+)?-?\s*-?-?\s*[\/]",
        @"\brm\s+-rf?\s+~",
        @":\(\)\s*\{",
        @"\bdd\s+if=.*\bof=/dev/",
        @"\bmkfs(\.\w+)?\b",
        @"\bshutdown\b",
        @"\breboot\b",
        @"\bhalt\b",
        @"\bpoweroff\b",
        @">\s*/dev/sda",
        @"\bchmod\s+-R\s+777\s+/",
        @"\bchown\s+-R\s+",
        @"\bcurl\s+[^|]*\|\s*sh\b",
        @"\bwget\s+[^|]*\|\s*sh\b",
        @"\bRemove-Item\s+(?:-Path\s+)?[/\\]\s+-Recurse",
        @"\bFormat-Volume\b",
    ];

    private readonly IReadOnlyList<Regex> _denies;
    private readonly IReadOnlyList<Regex> _allows;

    /// <summary>
    /// Initializes a new instance of the <see cref="ShellPolicy"/> class.
    /// </summary>
    /// <param name="denyList">
    /// Patterns that trigger a deny decision. <see langword="null"/> selects
    /// <see cref="DefaultDenyList"/>; pass an empty collection to disable
    /// the deny list entirely.
    /// </param>
    /// <param name="allowList">
    /// Optional explicit-allow patterns. A match here short-circuits the
    /// deny list and is useful when the caller knows the command is safe.
    /// </param>
    public ShellPolicy(IEnumerable<string>? denyList = null, IEnumerable<string>? allowList = null)
    {
        var deny = new List<Regex>();
        foreach (var pattern in denyList ?? DefaultDenyList)
        {
            deny.Add(new Regex(pattern, RegexOptions.Compiled | RegexOptions.IgnoreCase));
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
    /// Evaluate <paramref name="request"/> and return a decision.
    /// </summary>
    /// <param name="request">The request to evaluate.</param>
    /// <returns>An allow or deny decision.</returns>
    public ShellDecision Evaluate(ShellRequest request)
    {
        var command = request.Command?.Trim() ?? string.Empty;
        if (command.Length == 0)
        {
            return ShellDecision.Deny("empty command");
        }

        foreach (var allow in this._allows)
        {
            if (allow.IsMatch(command))
            {
                return new ShellDecision(true, "matched allow pattern");
            }
        }

        foreach (var deny in this._denies)
        {
            if (deny.IsMatch(command))
            {
                return ShellDecision.Deny($"matched deny pattern: {deny}");
            }
        }

        return ShellDecision.Allow;
    }
}
