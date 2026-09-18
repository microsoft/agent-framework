// Copyright (c) Microsoft. All rights reserved.

using System;

namespace Microsoft.Agents.AI.LocalCodeAct.UnitTests;

public sealed class LocalCodeActProviderOptionsTests
{
    [Fact]
    public void ProviderConstructor_RequiresPythonExecutablePath()
    {
        Assert.Throws<ArgumentException>(() => new LocalCodeActProvider(""));
        Assert.Throws<ArgumentException>(() => new LocalCodeActProvider("   "));
        _ = Assert.Throws<ArgumentNullException>(() => new LocalCodeActProvider(null!));
    }

    [Fact]
    public void ExecuteCodeFunctionConstructor_RequiresPythonExecutablePath()
    {
        Assert.Throws<ArgumentException>(() => new LocalExecuteCodeFunction(""));
        Assert.Throws<ArgumentException>(() => new LocalExecuteCodeFunction("   "));
        _ = Assert.Throws<ArgumentNullException>(() => new LocalExecuteCodeFunction(null!));
    }

    [Fact]
    public void ValidationDisabled_DefaultsToFalse()
    {
        var options = new LocalCodeActProviderOptions();
        Assert.False(options.ValidationDisabled);
    }
}
