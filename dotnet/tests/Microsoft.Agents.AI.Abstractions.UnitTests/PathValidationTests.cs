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
    public void ValidateFullyQualifiedExecutablePath_NoExtension_ThrowsOnWindowsOnly()
    {
        // Arrange
        var path = Path.Combine(Path.GetTempPath(), "tool");

        // Act
        var exception = Record.Exception(() => PathValidation.ValidateFullyQualifiedExecutablePath(path, "toolPath", "tool"));

        // Assert
        if (s_isWindows)
        {
            var argumentException = Assert.IsType<ArgumentException>(exception);
            Assert.Equal("toolPath", argumentException.ParamName);
            Assert.Contains("The tool path must include a file extension, such as .exe, on Windows.", argumentException.Message, StringComparison.Ordinal);
        }
        else
        {
            Assert.Null(exception);
        }
    }

    [Fact]
    public void ValidateFullyQualifiedExecutablePath_TrailingDot_ThrowsOnWindows()
    {
        Assert.SkipUnless(s_isWindows, "File extensions are only required on Windows.");

        // Arrange
        var path = Path.Combine(Path.GetTempPath(), "tool.");

        // Act & Assert
        var exception = Assert.Throws<ArgumentException>(() => PathValidation.ValidateFullyQualifiedExecutablePath(path, "toolPath", "tool"));
        Assert.Equal("toolPath", exception.ParamName);
    }

    [Fact]
    public void ValidateFullyQualifiedExecutablePath_WithExtension_DoesNotThrow()
    {
        // Arrange
        var path = Path.Combine(Path.GetTempPath(), Guid.NewGuid().ToString("N"), "tool.exe");

        // Act & Assert
        PathValidation.ValidateFullyQualifiedExecutablePath(path, "toolPath", "tool");
    }

    [Fact]
    public void ValidateFullyQualifiedPathToExistingExecutable_PartialPath_ThrowsArgumentException()
    {
        // Act & Assert
        var exception = Assert.Throws<ArgumentException>(() => PathValidation.ValidateFullyQualifiedPathToExistingExecutable("docker", "toolPath", "tool"));
        Assert.Equal("toolPath", exception.ParamName);
        Assert.Contains("The tool path must be fully qualified.", exception.Message, StringComparison.Ordinal);
    }

    [Fact]
    public void ValidateFullyQualifiedPathToExistingExecutable_ExistingFileWithoutExtension_ThrowsOnWindows()
    {
        Assert.SkipUnless(s_isWindows, "File extensions are only required on Windows.");

        // Arrange
        var directory = Directory.CreateDirectory(Path.Combine(Path.GetTempPath(), Guid.NewGuid().ToString("N"))).FullName;
        var file = Path.Combine(directory, "tool");
        File.WriteAllText(file, string.Empty);

        try
        {
            // Act & Assert
            var exception = Assert.Throws<ArgumentException>(() => PathValidation.ValidateFullyQualifiedPathToExistingExecutable(file, "toolPath", "tool"));
            Assert.Equal("toolPath", exception.ParamName);
        }
        finally
        {
            Directory.Delete(directory, recursive: true);
        }
    }

    [Fact]
    public void ValidateFullyQualifiedPathToExistingExecutable_MissingFile_ThrowsFileNotFoundException()
    {
        // Arrange
        var missing = Path.Combine(Path.GetTempPath(), Guid.NewGuid().ToString("N"), "tool.exe");

        // Act & Assert
        var exception = Assert.Throws<FileNotFoundException>(() => PathValidation.ValidateFullyQualifiedPathToExistingExecutable(missing, "toolPath", "tool"));
        Assert.Equal(missing, exception.FileName);
        Assert.Equal("The tool file was not found.", exception.Message);
    }

    [Fact]
    public void ValidateFullyQualifiedPathToExistingExecutable_Directory_ThrowsFileNotFoundException()
    {
        // Arrange
        var directory = Directory.CreateDirectory(Path.Combine(Path.GetTempPath(), Guid.NewGuid().ToString("N") + ".exe")).FullName;

        try
        {
            // Act & Assert
            Assert.Throws<FileNotFoundException>(() => PathValidation.ValidateFullyQualifiedPathToExistingExecutable(directory, "toolPath", "tool"));
        }
        finally
        {
            Directory.Delete(directory);
        }
    }

    [Fact]
    public void ValidateFullyQualifiedPathToExistingExecutable_ExistingFile_DoesNotThrow()
    {
        // Arrange
        var file = Path.GetTempFileName();

        try
        {
            // Act & Assert
            PathValidation.ValidateFullyQualifiedPathToExistingExecutable(file, "toolPath", "tool");
        }
        finally
        {
            File.Delete(file);
        }
    }

    [Fact]
    public void TryFindOnPath_SkipsRelativeEntries()
    {
        // Arrange
        // Create the folders under the current directory so the planted entry stays relative on any drive layout.
        var rootName = "af-path-search-" + Guid.NewGuid().ToString("N");
        var root = Path.Combine(Directory.GetCurrentDirectory(), rootName);
        var plantedDir = Directory.CreateDirectory(Path.Combine(root, "planted")).FullName;
        var trustedDir = Directory.CreateDirectory(Path.Combine(root, "trusted")).FullName;
        File.WriteAllText(Path.Combine(plantedDir, "tool.exe"), string.Empty);
        File.WriteAllText(Path.Combine(trustedDir, "tool.exe"), string.Empty);
        var relativePlantedDir = Path.Combine(rootName, "planted");

        try
        {
            // Act
            var foundWithTrusted = PathValidation.TryFindOnPath(
                string.Join(Path.PathSeparator.ToString(), relativePlantedDir, ".", string.Empty, trustedDir), "tool.exe", out var fullPath);
            var foundRelativeOnly = PathValidation.TryFindOnPath(relativePlantedDir, "tool.exe", out var relativeOnlyPath);

            // Assert
            Assert.True(File.Exists(Path.Combine(relativePlantedDir, "tool.exe")));
            Assert.True(foundWithTrusted);
            Assert.Equal(Path.Combine(trustedDir, "tool.exe"), fullPath);
            Assert.False(foundRelativeOnly);
            Assert.Null(relativeOnlyPath);
        }
        finally
        {
            Directory.Delete(root, recursive: true);
        }
    }

    [Theory]
    [InlineData(null)]
    [InlineData("")]
    public void TryFindOnPath_EmptyPath_ReturnsFalse(string? pathEnv)
    {
        // Act
        var found = PathValidation.TryFindOnPath(pathEnv, "tool.exe", out var fullPath);

        // Assert
        Assert.False(found);
        Assert.Null(fullPath);
    }

    [Fact]
    public void RemoveRelativePathEntries_KeepsOnlyFullPathsInOrder()
    {
        // Arrange
        var first = Path.Combine(Path.GetTempPath(), "first");
        var second = Path.Combine(Path.GetTempPath(), "second");
        var separator = Path.PathSeparator.ToString();
        var pathEnv = string.Join(separator, ".", first, string.Empty, "relative", Path.Combine("..", "up"), second, " ");

        // Act
        var result = PathValidation.RemoveRelativePathEntries(pathEnv);

        // Assert
        Assert.Equal(first + separator + second, result);
    }

    [Theory]
    [InlineData(null)]
    [InlineData("")]
    [InlineData(".")]
    public void RemoveRelativePathEntries_NoFullPaths_ReturnsEmpty(string? pathEnv)
    {
        // Act
        var result = PathValidation.RemoveRelativePathEntries(pathEnv);

        // Assert
        Assert.Equal(string.Empty, result);
    }
}
