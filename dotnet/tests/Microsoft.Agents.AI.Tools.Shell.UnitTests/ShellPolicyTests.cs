// Copyright (c) Microsoft. All rights reserved.

using System;
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
    /// <summary>
    /// A pattern that backtracks exponentially, and a command it cannot match.
    /// </summary>
    /// <remarks>
    /// Deliberately not <c>(a|a)*$</c>, which is the equivalent used by the Python tests.
    /// .NET matches that one instantly: <c>(a|a)*</c> can match zero times, so the engine
    /// finds an empty match at the end anchor and never backtracks. <c>(a+)+$</c> requires
    /// at least one character per iteration, which forces the exponential search.
    /// </remarks>
    private const string RedosPattern = "(a+)+$";
    private static readonly string s_redosCommand = new string('a', 30) + "!";

    [Fact]
    public void Evaluate_DenyPatternTimesOut_FailsClosed()
    {
        // Arrange
        var policy = new ShellPolicy(denyList: [RedosPattern]);

        // Act
        var sw = Stopwatch.StartNew();
        var outcome = policy.Evaluate(new ShellRequest(s_redosCommand));
        sw.Stop();

        // Assert
        Assert.False(outcome.Allowed);
        Assert.Contains("could not be evaluated in time", outcome.Reason ?? string.Empty, StringComparison.Ordinal);
        Assert.True(sw.Elapsed < TimeSpan.FromSeconds(10), $"policy evaluation overran: {sw.Elapsed}");
    }

    [Fact]
    public void Evaluate_AllowPatternTimesOut_DoesNotGrantAccess()
    {
        // Arrange
        var policy = new ShellPolicy(allowList: [RedosPattern]);

        // Act
        var sw = Stopwatch.StartNew();
        var outcome = policy.Evaluate(new ShellRequest(s_redosCommand));
        sw.Stop();

        // Assert
        Assert.False(outcome.Allowed);
        Assert.Contains("does not match allow list", outcome.Reason ?? string.Empty, StringComparison.Ordinal);
        Assert.True(sw.Elapsed < TimeSpan.FromSeconds(10), $"policy evaluation overran: {sw.Elapsed}");
    }

    [Fact]
    public void Evaluate_NormalPatterns_StillDecideAsBefore()
    {
        // Arrange
        var policy = new ShellPolicy(denyList: ["^ssh\\b"], allowList: ["^ls\\b", "^ssh\\b"]);

        // Act & Assert
        Assert.False(policy.Evaluate(new ShellRequest("ssh host")).Allowed);
        Assert.True(policy.Evaluate(new ShellRequest("ls -la")).Allowed);
        Assert.False(policy.Evaluate(new ShellRequest("cat /etc/passwd")).Allowed);
    }
}
