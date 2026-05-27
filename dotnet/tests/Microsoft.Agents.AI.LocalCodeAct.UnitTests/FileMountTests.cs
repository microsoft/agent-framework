// Copyright (c) Microsoft Corporation. All rights reserved.
// Licensed under the MIT License.

using Xunit;

namespace Microsoft.Agents.AI.LocalCodeAct.UnitTests;

/// <summary>
/// Tests for FileMount record.
/// </summary>
public sealed class FileMountTests
{
    [Fact]
    public void Constructor_WithRequiredProperties_Succeeds()
    {
        // Arrange & Act
        var mount = new FileMount
        {
            HostPath = "/tmp/data",
            MountPath = "/input",
        };

        // Assert
        Assert.Equal("/tmp/data", mount.HostPath);
        Assert.Equal("/input", mount.MountPath);
        Assert.Equal(FileMountMode.ReadWrite, mount.Mode);
        Assert.Null(mount.WriteBytesLimit);
    }

    [Fact]
    public void CustomValues_CanBeSet()
    {
        // Arrange & Act
        var mount = new FileMount
        {
            HostPath = "/data",
            MountPath = "/readonly",
            Mode = FileMountMode.ReadOnly,
            WriteBytesLimit = 1024,
        };

        // Assert
        Assert.Equal("/data", mount.HostPath);
        Assert.Equal("/readonly", mount.MountPath);
        Assert.Equal(FileMountMode.ReadOnly, mount.Mode);
        Assert.Equal(1024, mount.WriteBytesLimit);
    }
}
