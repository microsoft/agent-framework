// Copyright (c) Microsoft. All rights reserved.

using System;
using System.IO;
using System.Runtime.InteropServices;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Abstractions.UnitTests;

/// <summary>
/// Tests for the shared <see cref="PathValidation"/> helper. This project runs on both modern .NET and
/// .NET Framework, so it covers both the built-in check and the .NET Framework fallback.
/// </summary>
public sealed class PathValidationTests
{
    private static readonly bool s_isWindows = RuntimeInformation.IsOSPlatform(OSPlatform.Windows);

    [Theory]
    [InlineData(null)]
    [InlineData("")]
    [InlineData("   ")]
    [InlineData("docker")]
    [InlineData("docker.exe")]
    [InlineData("./docker")]
    [InlineData("../docker")]
    [InlineData(@".\docker.exe")]
    [InlineData(@"..\docker.exe")]
    [InlineData("C:docker.exe")]
    [InlineData(@"\docker.exe")]
    public void IsFullyQualifiedPath_ReturnsFalseForPartialPaths(string? path)
    {
        // Act
        var result = PathValidation.IsFullyQualifiedPath(path);

        // Assert
        Assert.False(result);
    }

    [Theory]
    [InlineData(@"C:\tools\docker.exe")]
    [InlineData("C:/tools/docker.exe")]
    [InlineData(@"c:\tools\docker.exe")]
    [InlineData(@"\\server\share\docker.exe")]
    [InlineData(@"\\?\C:\tools\docker.exe")]
    [InlineData(@"\\.\C:\tools\docker.exe")]
    public void IsFullyQualifiedPath_ReturnsTrueForWindowsFullPaths(string path)
    {
        Assert.SkipUnless(s_isWindows, "These are Windows path forms.");

        // Act
        var result = PathValidation.IsFullyQualifiedPath(path);

        // Assert
        Assert.True(result);
    }

    [Theory]
    [InlineData("/usr/bin/docker")]
    [InlineData("/")]
    public void IsFullyQualifiedPath_RootedUnixPath_IsFullOnlyOffWindows(string path)
    {
        // Act
        var result = PathValidation.IsFullyQualifiedPath(path);

        // Assert
        Assert.Equal(!s_isWindows, result);
    }

    [Fact]
    public void IsFullyQualifiedPath_ReturnsTrueForTempPath()
    {
        // Act
        var result = PathValidation.IsFullyQualifiedPath(Path.GetTempPath());

        // Assert
        Assert.True(result);
    }

    [Fact]
    public void ValidateFullyQualifiedPath_NullPath_ThrowsArgumentNullException()
    {
        // Act & Assert
        var exception = Assert.Throws<ArgumentNullException>(() => PathValidation.ValidateFullyQualifiedPath(null, "toolPath", "tool"));
        Assert.Equal("toolPath", exception.ParamName);
    }

    [Theory]
    [InlineData("")]
    [InlineData("   ")]
    [InlineData("docker")]
    [InlineData("./docker")]
    public void ValidateFullyQualifiedPath_PartialPath_ThrowsArgumentException(string path)
    {
        // Act & Assert
        var exception = Assert.Throws<ArgumentException>(() => PathValidation.ValidateFullyQualifiedPath(path, "toolPath", "tool"));
        Assert.Equal("toolPath", exception.ParamName);
    }

    [Fact]
    public void ValidateFullyQualifiedPath_MissingFullPath_DoesNotThrow()
    {
        // Arrange
        var missing = Path.Combine(Path.GetTempPath(), Guid.NewGuid().ToString("N"), "tool");

        // Act & Assert
        PathValidation.ValidateFullyQualifiedPath(missing, "toolPath", "tool");
    }

    [Fact]
    public void ValidateFullyQualifiedPathToExistingFile_PartialPath_ThrowsArgumentException()
    {
        // Act & Assert
        var exception = Assert.Throws<ArgumentException>(() => PathValidation.ValidateFullyQualifiedPathToExistingFile("docker", "toolPath", "tool"));
        Assert.Equal("toolPath", exception.ParamName);
        Assert.Contains("The tool path must be fully qualified.", exception.Message, StringComparison.Ordinal);
    }

    [Fact]
    public void ValidateFullyQualifiedPathToExistingFile_MissingFile_ThrowsFileNotFoundException()
    {
        // Arrange
        var missing = Path.Combine(Path.GetTempPath(), Guid.NewGuid().ToString("N"), "tool");

        // Act & Assert
        var exception = Assert.Throws<FileNotFoundException>(() => PathValidation.ValidateFullyQualifiedPathToExistingFile(missing, "toolPath", "tool"));
        Assert.Equal(missing, exception.FileName);
        Assert.Equal("The tool file was not found.", exception.Message);
    }

    [Fact]
    public void ValidateFullyQualifiedPathToExistingFile_Directory_ThrowsFileNotFoundException()
    {
        // Arrange
        var directory = Path.GetTempPath();

        // Act & Assert
        Assert.Throws<FileNotFoundException>(() => PathValidation.ValidateFullyQualifiedPathToExistingFile(directory, "toolPath", "tool"));
    }

    [Fact]
    public void ValidateFullyQualifiedPathToExistingFile_ExistingFile_DoesNotThrow()
    {
        // Arrange
        var file = Path.GetTempFileName();

        try
        {
            // Act & Assert
            PathValidation.ValidateFullyQualifiedPathToExistingFile(file, "toolPath", "tool");
        }
        finally
        {
            File.Delete(file);
        }
    }
}
