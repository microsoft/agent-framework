// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.Hyperlight.Internal;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Hyperlight.UnitTests;

public sealed class SandboxExecutorTests
{
    [Fact]
    public void Fingerprint_DifferentToolSets_DifferentFingerprints()
    {
        // Arrange
        var t1 = AIFunctionFactory.Create(() => "a", name: "a");
        var t2 = AIFunctionFactory.Create(() => "b", name: "b");

        // Act
        var fpA = SandboxExecutor.RunSnapshot.ComputeFingerprint([t1], [], [], hostInputDirectory: null);
        var fpAB = SandboxExecutor.RunSnapshot.ComputeFingerprint([t1, t2], [], [], hostInputDirectory: null);

        // Assert
        Assert.NotEqual(fpA, fpAB);
    }

    [Fact]
    public void Fingerprint_OrderInsensitive_OnTools()
    {
        // Arrange
        var t1 = AIFunctionFactory.Create(() => "a", name: "a");
        var t2 = AIFunctionFactory.Create(() => "b", name: "b");

        // Act
        var fp1 = SandboxExecutor.RunSnapshot.ComputeFingerprint([t1, t2], [], [], hostInputDirectory: null);
        var fp2 = SandboxExecutor.RunSnapshot.ComputeFingerprint([t2, t1], [], [], hostInputDirectory: null);

        // Assert
        Assert.Equal(fp1, fp2);
    }

    [Fact]
    public void Fingerprint_DifferentMounts_DifferentFingerprints()
    {
        // Act
        var fpEmpty = SandboxExecutor.RunSnapshot.ComputeFingerprint([], [], [], hostInputDirectory: null);
        var fpMount = SandboxExecutor.RunSnapshot.ComputeFingerprint(
            [],
            [new FileMount("/host/a", "/input/a")],
            [],
            hostInputDirectory: null);

        // Assert
        Assert.NotEqual(fpEmpty, fpMount);
    }

    [Fact]
    public void Fingerprint_DifferentAllowedDomains_DifferentFingerprints()
    {
        // Act
        var fp1 = SandboxExecutor.RunSnapshot.ComputeFingerprint(
            [],
            [],
            [new AllowedDomain("https://a")],
            hostInputDirectory: null);
        var fp2 = SandboxExecutor.RunSnapshot.ComputeFingerprint(
            [],
            [],
            [new AllowedDomain("https://b")],
            hostInputDirectory: null);

        // Assert
        Assert.NotEqual(fp1, fp2);
    }

    [Fact]
    public void Fingerprint_DifferentHostInputDirectory_DifferentFingerprints()
    {
        // Act
        var fpNone = SandboxExecutor.RunSnapshot.ComputeFingerprint([], [], [], hostInputDirectory: null);
        var fpDir = SandboxExecutor.RunSnapshot.ComputeFingerprint([], [], [], hostInputDirectory: "/tmp/work");

        // Assert
        Assert.NotEqual(fpNone, fpDir);
    }
}
