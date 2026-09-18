// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics;

namespace Microsoft.Agents.AI.Tools.Shell.UnitTests;

/// <summary>
/// Guards the fail-closed behavior of <see cref="ShellPolicy.Evaluate"/> when a policy
/// pattern backtracks catastrophically. Patterns are operator-authored, but the commands
/// they filter are model-generated, so an unbounded match would let injected input stall
/// the authorization path itself.
/// </summary>
public sealed class ShellPolicyTests
{
    /// <summary>A pattern that backtracks exponentially, and a command it cannot match.</summary>
    private const string RedosPattern = "(a|a)*$";
    private static readonly string s_redosCommand = new string('a', 30) + "!";

    [Fact]
    public void Evaluate_DenyPatternTimesOut_FailsClosed()
    {
        var policy = new ShellPolicy(denyList: [RedosPattern]);

        var sw = Stopwatch.StartNew();
        var outcome = policy.Evaluate(new ShellRequest(s_redosCommand));
        sw.Stop();

        Assert.False(outcome.Allowed);
        Assert.Contains("could not be evaluated in time", outcome.Reason ?? string.Empty, StringComparison.Ordinal);
        Assert.True(sw.Elapsed < TimeSpan.FromSeconds(10), $"policy evaluation overran: {sw.Elapsed}");
    }

    [Fact]
    public void Evaluate_AllowPatternTimesOut_DoesNotGrantAccess()
    {
        var policy = new ShellPolicy(allowList: [RedosPattern]);

        var sw = Stopwatch.StartNew();
        var outcome = policy.Evaluate(new ShellRequest(s_redosCommand));
        sw.Stop();

        Assert.False(outcome.Allowed);
        Assert.Contains("does not match allow list", outcome.Reason ?? string.Empty, StringComparison.Ordinal);
        Assert.True(sw.Elapsed < TimeSpan.FromSeconds(10), $"policy evaluation overran: {sw.Elapsed}");
    }

    [Fact]
    public void Evaluate_NormalPatterns_StillDecideAsBefore()
    {
        var policy = new ShellPolicy(denyList: ["^ssh\\b"], allowList: ["^ls\\b", "^ssh\\b"]);

        Assert.False(policy.Evaluate(new ShellRequest("ssh host")).Allowed);
        Assert.True(policy.Evaluate(new ShellRequest("ls -la")).Allowed);
        Assert.False(policy.Evaluate(new ShellRequest("cat /etc/passwd")).Allowed);
    }
}
