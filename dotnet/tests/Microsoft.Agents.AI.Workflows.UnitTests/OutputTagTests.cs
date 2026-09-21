// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Reflection;
using System.Text.Json;

namespace Microsoft.Agents.AI.Workflows.UnitTests;

public class OutputTagTests
{
    [Fact]
    public void Test_OutputTag_KnownValues()
    {
        Assert.Equal("intermediate", OutputTag.Intermediate.Value);
    }

    [Fact]
    public void Test_OutputTag_EqualityIsOrdinalOnValue()
    {
        Assert.Equal(OutputTag.Intermediate, OutputTag.Intermediate);
        Assert.True(OutputTag.Intermediate == OutputTag.Intermediate);

        // Same Value via independent construction (via JSON round-trip below) is equal.
        OutputTag rebuilt = JsonSerializer.Deserialize<OutputTag>("\"intermediate\"", WorkflowsJsonUtilities.DefaultOptions);
        Assert.Equal(OutputTag.Intermediate, rebuilt);
    }

    [Fact]
    public void Test_OutputTag_DefaultStructValueIsDistinct()
    {
        OutputTag def = default;
        Assert.Null(def.Value);
        Assert.NotEqual(OutputTag.Intermediate, def);
        Assert.Equal(0, def.GetHashCode());

        HashSet<OutputTag> set = [OutputTag.Intermediate];
        Assert.DoesNotContain(def, set);
    }

    [Fact]
    public void Test_OutputTag_GetHashCodeMatchesEquals()
    {
        OutputTag a = OutputTag.Intermediate;
        OutputTag b = JsonSerializer.Deserialize<OutputTag>("\"intermediate\"", WorkflowsJsonUtilities.DefaultOptions);

        Assert.True(a.Equals(b));
        Assert.Equal(b.GetHashCode(), a.GetHashCode());
    }

    [Fact]
    public void Test_OutputTag_JsonConverter_RoundtripsValueAsString()
    {
        string intermediateJson = JsonSerializer.Serialize(OutputTag.Intermediate, WorkflowsJsonUtilities.DefaultOptions);
        Assert.Equal("\"intermediate\"", intermediateJson);

        OutputTag back = JsonSerializer.Deserialize<OutputTag>("\"intermediate\"", WorkflowsJsonUtilities.DefaultOptions);
        Assert.Equal(OutputTag.Intermediate, back);

        OutputTag fromUnknown = JsonSerializer.Deserialize<OutputTag>("\"custom\"", WorkflowsJsonUtilities.DefaultOptions);
        Assert.Equal("custom", fromUnknown.Value);
    }

    [Fact]
    public void Test_OutputTag_ConstructorIsInternal()
    {
        ConstructorInfo? ctor = typeof(OutputTag).GetConstructor(
            BindingFlags.Instance | BindingFlags.NonPublic,
            binder: null,
            types: [typeof(string)],
            modifiers: null);

        Assert.NotNull(ctor);
        Assert.True(ctor!.IsAssembly);
        Assert.False(ctor.IsPublic);
    }
}
