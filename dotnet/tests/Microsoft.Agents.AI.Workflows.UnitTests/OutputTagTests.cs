// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Reflection;
using System.Text.Json;
using FluentAssertions;

namespace Microsoft.Agents.AI.Workflows.UnitTests;

public class OutputTagTests
{
    [Fact]
    public void Test_OutputTag_KnownValues()
    {
        OutputTag.Intermediate.Value.Should().Be("intermediate");
    }

    [Fact]
    public void Test_OutputTag_EqualityIsOrdinalOnValue()
    {
        OutputTag.Intermediate.Should().Be(OutputTag.Intermediate);
        (OutputTag.Intermediate == OutputTag.Intermediate).Should().BeTrue();

        // Same Value via independent construction (via JSON round-trip below) is equal.
        OutputTag rebuilt = JsonSerializer.Deserialize<OutputTag>("\"intermediate\"", WorkflowsJsonUtilities.DefaultOptions);
        rebuilt.Should().Be(OutputTag.Intermediate);
    }

    [Fact]
    public void Test_OutputTag_DefaultStructValueIsDistinct()
    {
        OutputTag def = default;
        def.Value.Should().BeNull();
        def.Should().NotBe(OutputTag.Intermediate);
        def.GetHashCode().Should().Be(0);

        HashSet<OutputTag> set = [OutputTag.Intermediate];
        set.Contains(def).Should().BeFalse("default(OutputTag) must not collide with the well-known singleton in a HashSet");
    }

    [Fact]
    public void Test_OutputTag_GetHashCodeMatchesEquals()
    {
        OutputTag a = OutputTag.Intermediate;
        OutputTag b = JsonSerializer.Deserialize<OutputTag>("\"intermediate\"", WorkflowsJsonUtilities.DefaultOptions);

        a.Equals(b).Should().BeTrue();
        a.GetHashCode().Should().Be(b.GetHashCode());
    }

    [Fact]
    public void Test_OutputTag_JsonConverter_RoundtripsValueAsString()
    {
        string intermediateJson = JsonSerializer.Serialize(OutputTag.Intermediate, WorkflowsJsonUtilities.DefaultOptions);
        intermediateJson.Should().Be("\"intermediate\"");

        OutputTag back = JsonSerializer.Deserialize<OutputTag>("\"intermediate\"", WorkflowsJsonUtilities.DefaultOptions);
        back.Should().Be(OutputTag.Intermediate);

        OutputTag fromUnknown = JsonSerializer.Deserialize<OutputTag>("\"custom\"", WorkflowsJsonUtilities.DefaultOptions);
        fromUnknown.Value.Should().Be("custom");
    }

    [Fact]
    public void Test_OutputTag_ConstructorIsInternal()
    {
        ConstructorInfo? ctor = typeof(OutputTag).GetConstructor(
            BindingFlags.Instance | BindingFlags.NonPublic,
            binder: null,
            types: [typeof(string)],
            modifiers: null);

        ctor.Should().NotBeNull("OutputTag(string) must exist as an internal constructor");
        ctor!.IsAssembly.Should().BeTrue("OutputTag(string) must be `internal` so external assemblies cannot synthesize tags");
        ctor.IsPublic.Should().BeFalse();
    }
}
