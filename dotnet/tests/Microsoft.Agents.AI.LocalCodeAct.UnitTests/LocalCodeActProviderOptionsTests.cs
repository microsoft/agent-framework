// Copyright (c) Microsoft. All rights reserved.

using System;

namespace Microsoft.Agents.AI.LocalCodeAct.UnitTests;

public sealed class LocalCodeActProviderOptionsTests
{
    [Fact]
    public void Constructor_RequiresPythonExecutablePath()
    {
        Assert.Throws<ArgumentException>(() => new LocalCodeActProviderOptions(""));
        Assert.Throws<ArgumentException>(() => new LocalCodeActProviderOptions("   "));
        _ = Assert.Throws<ArgumentNullException>(() => new LocalCodeActProviderOptions(null!));
    }

    [Fact]
    public void Constructor_AssignsPythonExecutablePath()
    {
        var options = new LocalCodeActProviderOptions("/usr/bin/python3");
        Assert.Equal("/usr/bin/python3", options.PythonExecutablePath);
    }

    [Fact]
    public void ValidationEnabled_DefaultsToTrue()
    {
        var options = new LocalCodeActProviderOptions("/usr/bin/python3");
        Assert.True(options.ValidationEnabled);
    }
}
