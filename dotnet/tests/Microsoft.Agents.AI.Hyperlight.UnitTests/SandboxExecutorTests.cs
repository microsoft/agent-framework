// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using HyperlightSandbox.Api;
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
    public void Fingerprint_StructuredToolNames_DifferentFingerprints()
    {
        // Arrange
        var joinedName = AIFunctionFactory.Create(() => "joined", name: "a|b");
        var firstTool = AIFunctionFactory.Create(() => "first", name: "a");
        var secondTool = AIFunctionFactory.Create(() => "second", name: "b");

        // Act
        var joinedFingerprint = SandboxExecutor.RunSnapshot.ComputeFingerprint(
            [joinedName], [], [], hostInputDirectory: null);
        var separateFingerprint = SandboxExecutor.RunSnapshot.ComputeFingerprint(
            [firstTool, secondTool], [], [], hostInputDirectory: null);

        // Assert
        Assert.NotEqual(joinedFingerprint, separateFingerprint);
    }

    [Fact]
    public void Fingerprint_SameNameDifferentToolRegistryVersionIds_DifferentFingerprints()
    {
        // Arrange
        var t1 = AIFunctionFactory.Create(() => "a", name: "t");
        var t2 = AIFunctionFactory.Create(() => "b", name: "t");
        var firstVersion = Guid.Parse("11111111-1111-1111-1111-111111111111");
        var secondVersion = Guid.Parse("22222222-2222-2222-2222-222222222222");

        // Act
        var fp1 = SandboxExecutor.RunSnapshot.ComputeFingerprint(
            [t1],
            [],
            [],
            hostInputDirectory: null,
            toolRegistryVersion: firstVersion);
        var fp2 = SandboxExecutor.RunSnapshot.ComputeFingerprint(
            [t2],
            [],
            [],
            hostInputDirectory: null,
            toolRegistryVersion: secondVersion);

        // Assert
        Assert.NotEqual(fp1, fp2);
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
    public void Fingerprint_StructuredMountPaths_DifferentFingerprints()
    {
        // Act
        var joinedFingerprint = SandboxExecutor.RunSnapshot.ComputeFingerprint(
            [],
            [new FileMount("b|c->d", "a")],
            [],
            hostInputDirectory: null);
        var separateFingerprint = SandboxExecutor.RunSnapshot.ComputeFingerprint(
            [],
            [new FileMount("b", "a"), new FileMount("d", "c")],
            [],
            hostInputDirectory: null);

        // Assert
        Assert.NotEqual(joinedFingerprint, separateFingerprint);
    }

    [Fact]
    public void Fingerprint_DistinctMountPathComponents_DifferentFingerprints()
    {
        // Act
        var firstFingerprint = SandboxExecutor.RunSnapshot.ComputeFingerprint(
            [],
            [new FileMount("b->c", "a")],
            [],
            hostInputDirectory: null);
        var secondFingerprint = SandboxExecutor.RunSnapshot.ComputeFingerprint(
            [],
            [new FileMount("c", "a->b")],
            [],
            hostInputDirectory: null);

        // Assert
        Assert.NotEqual(firstFingerprint, secondFingerprint);
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
    public void Fingerprint_DistinctDomainTargetAndMethod_DifferentFingerprints()
    {
        // Act
        var firstFingerprint = SandboxExecutor.RunSnapshot.ComputeFingerprint(
            [],
            [],
            [new AllowedDomain("https://a/b", ["GET"])],
            hostInputDirectory: null);
        var secondFingerprint = SandboxExecutor.RunSnapshot.ComputeFingerprint(
            [],
            [],
            [new AllowedDomain("https://a", ["b/GET"])],
            hostInputDirectory: null);

        // Assert
        Assert.NotEqual(firstFingerprint, secondFingerprint);
    }

    [Fact]
    public void Fingerprint_StructuredDomainMethods_DifferentFingerprints()
    {
        // Act
        var joinedFingerprint = SandboxExecutor.RunSnapshot.ComputeFingerprint(
            [],
            [],
            [new AllowedDomain("https://a", ["GET,POST"])],
            hostInputDirectory: null);
        var separateFingerprint = SandboxExecutor.RunSnapshot.ComputeFingerprint(
            [],
            [],
            [new AllowedDomain("https://a", ["GET", "POST"])],
            hostInputDirectory: null);

        // Assert
        Assert.NotEqual(joinedFingerprint, separateFingerprint);
    }

    [Fact]
    public void Fingerprint_StructuredAllowedDomains_DifferentFingerprints()
    {
        // Act
        var joinedFingerprint = SandboxExecutor.RunSnapshot.ComputeFingerprint(
            [],
            [],
            [new AllowedDomain("a", ["GET|b/POST"])],
            hostInputDirectory: null);
        var separateFingerprint = SandboxExecutor.RunSnapshot.ComputeFingerprint(
            [],
            [],
            [new AllowedDomain("a", ["GET"]), new AllowedDomain("b", ["POST"])],
            hostInputDirectory: null);

        // Assert
        Assert.NotEqual(joinedFingerprint, separateFingerprint);
    }

    [Fact]
    public void Fingerprint_OrderInsensitive_OnMountsDomainsAndMethods()
    {
        // Arrange
        var firstMount = new FileMount("/host/a", "/input/a");
        var secondMount = new FileMount("/host/b", "/input/b");
        var firstDomain = new AllowedDomain("https://a", ["POST", "GET"]);
        var secondDomain = new AllowedDomain("https://b", ["DELETE"]);

        // Act
        var firstFingerprint = SandboxExecutor.RunSnapshot.ComputeFingerprint(
            [],
            [firstMount, secondMount],
            [firstDomain, secondDomain],
            hostInputDirectory: null);
        var secondFingerprint = SandboxExecutor.RunSnapshot.ComputeFingerprint(
            [],
            [secondMount, firstMount],
            [secondDomain, new AllowedDomain("https://a", ["GET", "POST"])],
            hostInputDirectory: null);

        // Assert
        Assert.Equal(firstFingerprint, secondFingerprint);
    }

    [Fact]
    public void Fingerprint_DifferentSandboxOptions_DifferentFingerprints()
    {
        // Arrange
        var baseline = SandboxExecutor.RunSnapshot.ComputeFingerprint([], [], [], hostInputDirectory: null);

        // Act
        var differentBackend = SandboxExecutor.RunSnapshot.ComputeFingerprint(
            [], [], [], hostInputDirectory: null, backend: SandboxBackend.Wasm);
        var differentModule = SandboxExecutor.RunSnapshot.ComputeFingerprint(
            [], [], [], hostInputDirectory: null, modulePath: "/guest/module.wasm");
        var differentHeap = SandboxExecutor.RunSnapshot.ComputeFingerprint(
            [], [], [], hostInputDirectory: null, heapSize: "20Mi");
        var differentStack = SandboxExecutor.RunSnapshot.ComputeFingerprint(
            [], [], [], hostInputDirectory: null, stackSize: "10Mi");

        // Assert
        Assert.NotEqual(baseline, differentBackend);
        Assert.NotEqual(baseline, differentModule);
        Assert.NotEqual(baseline, differentHeap);
        Assert.NotEqual(baseline, differentStack);
    }

    [Fact]
    public void Fingerprint_IsSha256Hex()
    {
        // Act
        var fingerprint = SandboxExecutor.RunSnapshot.ComputeFingerprint([], [], [], hostInputDirectory: null);

        // Assert
        Assert.Matches("^[0-9A-F]{64}$", fingerprint);
    }

    [Fact]
    public void RunSnapshot_CapturesMutableInputs()
    {
        // Arrange
        var tools = new List<AIFunction> { AIFunctionFactory.Create(() => "ok", name: "tool") };
        var mounts = new List<FileMount> { new("/host", "/input") };
        var methods = new List<string> { "GET" };
        var domains = new List<AllowedDomain> { new("https://example.com", methods) };
        var options = new HyperlightCodeActProviderOptions
        {
            HeapSize = "10Mi",
            StackSize = "5Mi",
            HostInputDirectory = "/host/input",
        };

        // Act
        var snapshot = new SandboxExecutor.RunSnapshot(tools, mounts, domains, options);
        tools.Clear();
        mounts.Clear();
        domains.Clear();
        methods.Add("POST");
        options.HeapSize = "20Mi";
        options.StackSize = "10Mi";
        options.HostInputDirectory = "/host/other";

        // Assert
        Assert.Single(snapshot.Tools);
        Assert.Single(snapshot.FileMounts);
        var domain = Assert.Single(snapshot.AllowedDomains);
        Assert.Equal(["GET"], domain.Methods);
        Assert.Equal("10Mi", snapshot.HeapSize);
        Assert.Equal("5Mi", snapshot.StackSize);
        Assert.Equal("/host/input", snapshot.HostInputDirectory);
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
