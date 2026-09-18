// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI.LocalCodeAct.UnitTests;

public sealed class ProcessExecutionLimitsTests
{
    [Fact]
    public void Defaults_AreReasonable()
    {
        var limits = new ProcessExecutionLimits();

        Assert.True(limits.TimeoutSeconds > 0);
        Assert.True(limits.MaxStdoutBytes > 0);
        Assert.True(limits.MaxStderrBytes > 0);
        Assert.True(limits.ValidationTimeoutSeconds > 0);
        Assert.True(limits.MaxResultBytes > 0);
    }

    [Fact]
    public void Properties_AreMutable()
    {
        var limits = new ProcessExecutionLimits
        {
            TimeoutSeconds = 60,
            MaxStdoutBytes = 1024,
            MaxStderrBytes = 512,
            ValidationTimeoutSeconds = 5,
            MaxResultBytes = 2048,
        };

        Assert.Equal(60, limits.TimeoutSeconds);
        Assert.Equal(1024, limits.MaxStdoutBytes);
        Assert.Equal(512, limits.MaxStderrBytes);
        Assert.Equal(5, limits.ValidationTimeoutSeconds);
        Assert.Equal(2048, limits.MaxResultBytes);
    }
}
