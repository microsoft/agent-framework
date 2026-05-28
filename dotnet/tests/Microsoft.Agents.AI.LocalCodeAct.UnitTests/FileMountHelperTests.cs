// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.IO;
using System.Linq;
using Microsoft.Agents.AI.LocalCodeAct;
using Microsoft.Agents.AI.LocalCodeAct.Internal;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.LocalCodeAct.UnitTests;

/// <summary>
/// Unit tests for <see cref="FileMountHelper"/> covering the capture-limit branches
/// (per-file, per-mount, and total) that produce textual omission placeholders
/// instead of <see cref="DataContent"/>.
/// </summary>
public sealed class FileMountHelperTests
{
    [Fact]
    public void CaptureWrittenFiles_PerFileLimit_ReturnsTextPlaceholder()
    {
        var dir = Directory.CreateTempSubdirectory("fmh-perfile-").FullName;
        try
        {
            var mount = FileMountHelper.Normalize(new FileMount(dir, "/output", FileMountMode.ReadWrite));
            var pre = FileMountHelper.SnapshotWritableMounts(new[] { mount });

            File.WriteAllBytes(Path.Combine(dir, "big.bin"), new byte[2048]);

            // Per-file limit of 1024 bytes — file is 2048 -> should be omitted via TextContent.
            var limits = new ProcessExecutionLimits { MaxCapturedFileBytes = 1024 };
            var captured = FileMountHelper.CaptureWrittenFiles(new[] { mount }, pre, limits);

            var text = Assert.Single(captured.OfType<TextContent>());
            Assert.Contains("/output/big.bin", text.Text);
            Assert.Contains("per-file capture limit", text.Text);
            Assert.Empty(captured.OfType<DataContent>());
        }
        finally
        {
            Directory.Delete(dir, recursive: true);
        }
    }

    [Fact]
    public void CaptureWrittenFiles_PerMountLimit_OmitsSecondFile()
    {
        var dir = Directory.CreateTempSubdirectory("fmh-permount-").FullName;
        try
        {
            // WriteBytesLimit caps total bytes captured *for this mount*.
            var mount = FileMountHelper.Normalize(
                new FileMount(dir, "/output", FileMountMode.ReadWrite, writeBytesLimit: 600));
            var pre = FileMountHelper.SnapshotWritableMounts(new[] { mount });

            // Two files of 400 bytes each — first fits, second exceeds the 600-byte per-mount cap.
            File.WriteAllBytes(Path.Combine(dir, "a.bin"), new byte[400]);
            File.WriteAllBytes(Path.Combine(dir, "b.bin"), new byte[400]);

            var limits = new ProcessExecutionLimits(); // per-file/total caps high enough not to fire.
            var captured = FileMountHelper.CaptureWrittenFiles(new[] { mount }, pre, limits);

            Assert.Single(captured.OfType<DataContent>());
            var text = Assert.Single(captured.OfType<TextContent>());
            Assert.Contains("per-mount capture limit", text.Text);
            Assert.Contains("/output/b.bin", text.Text);
        }
        finally
        {
            Directory.Delete(dir, recursive: true);
        }
    }

    [Fact]
    public void CaptureWrittenFiles_TotalLimit_OmitsAcrossMounts()
    {
        var dirA = Directory.CreateTempSubdirectory("fmh-totalA-").FullName;
        var dirB = Directory.CreateTempSubdirectory("fmh-totalB-").FullName;
        try
        {
            var mountA = FileMountHelper.Normalize(new FileMount(dirA, "/a", FileMountMode.ReadWrite));
            var mountB = FileMountHelper.Normalize(new FileMount(dirB, "/b", FileMountMode.ReadWrite));
            var mounts = new[] { mountA, mountB };
            var pre = FileMountHelper.SnapshotWritableMounts(mounts);

            File.WriteAllBytes(Path.Combine(dirA, "a.bin"), new byte[500]);
            File.WriteAllBytes(Path.Combine(dirB, "b.bin"), new byte[500]);

            // Total capture limit set so the first file fits and the second triggers
            // the cross-mount total cap.
            var limits = new ProcessExecutionLimits { MaxTotalCapturedFileBytes = 600 };
            var captured = FileMountHelper.CaptureWrittenFiles(mounts, pre, limits);

            Assert.Single(captured.OfType<DataContent>());
            var text = Assert.Single(captured.OfType<TextContent>());
            Assert.Contains("total capture limit", text.Text);
        }
        finally
        {
            Directory.Delete(dirA, recursive: true);
            Directory.Delete(dirB, recursive: true);
        }
    }
}
