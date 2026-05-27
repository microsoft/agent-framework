// Copyright (c) Microsoft. All rights reserved.

using System;
using Microsoft.Agents.AI.LocalCodeAct;

namespace Microsoft.Agents.AI.LocalCodeAct.UnitTests;

public sealed class FileMountTests
{
    [Fact]
    public void Constructor_AssignsProperties()
    {
        var tempDir = System.IO.Directory.CreateTempSubdirectory("filemount-test-").FullName;
        try
        {
            var mount = new FileMount(tempDir, "/app/data", FileMountMode.ReadWrite, writeBytesLimit: 1024);

            Assert.Equal(tempDir, mount.HostPath);
            Assert.Equal("/app/data", mount.MountPath);
            Assert.Equal(FileMountMode.ReadWrite, mount.Mode);
            Assert.Equal(1024L, mount.WriteBytesLimit);
        }
        finally
        {
            System.IO.Directory.Delete(tempDir, recursive: true);
        }
    }

    [Fact]
    public void Constructor_DefaultsAreReadWriteWithNoLimit()
    {
        var tempDir = System.IO.Directory.CreateTempSubdirectory("filemount-test-").FullName;
        try
        {
            var mount = new FileMount(tempDir, "/app/data");
            Assert.Equal(FileMountMode.ReadWrite, mount.Mode);
            Assert.Null(mount.WriteBytesLimit);
        }
        finally
        {
            System.IO.Directory.Delete(tempDir, recursive: true);
        }
    }

    [Fact]
    public void Constructor_RequiresPaths()
    {
        Assert.Throws<ArgumentException>(() => new FileMount("", "/app/data"));
        Assert.Throws<ArgumentException>(() => new FileMount("/host/data", ""));
        _ = Assert.Throws<ArgumentNullException>(() => new FileMount(null!, "/app/data"));
        _ = Assert.Throws<ArgumentNullException>(() => new FileMount("/host/data", null!));
    }
}
