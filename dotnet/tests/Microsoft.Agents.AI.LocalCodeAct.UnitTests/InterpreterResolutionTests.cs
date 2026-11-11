// Copyright (c) Microsoft. All rights reserved.

using System;
using System.IO;

namespace Microsoft.Agents.AI.LocalCodeAct.UnitTests;

public sealed class InterpreterResolutionTests
{
    [Theory]
    [InlineData("python.exe")]
    [InlineData("python3")]
    [InlineData("./python3")]
    [InlineData("../python3")]
    [InlineData(@".\python.exe")]
    [InlineData(@"..\python.exe")]
    [InlineData("C:python.exe")]
    [InlineData(@"\python.exe")]
    public void Constructors_RejectNonFullyQualifiedPaths(string executablePath)
    {
        foreach (var validationDisabled in new[] { false, true })
        {
            // Arrange
            var options = CreateOptions(validationDisabled);

            // Act
            var providerError = Assert.Throws<ArgumentException>(() => new LocalCodeActProvider(executablePath, options));
            var functionError = Assert.Throws<ArgumentException>(() => new LocalExecuteCodeFunction(executablePath, options));

            // Assert
            Assert.Equal("pythonExecutablePath", providerError.ParamName);
            Assert.Equal("pythonExecutablePath", functionError.ParamName);
        }
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public void Constructors_RejectRootRelativePathsOnWindows(bool validationDisabled)
    {
        Assert.SkipUnless(OperatingSystem.IsWindows(), "A leading slash is an absolute path on Unix.");

        // Arrange
        const string ExecutablePath = "/usr/bin/python3";
        var options = CreateOptions(validationDisabled);

        // Act
        var providerError = Assert.Throws<ArgumentException>(() => new LocalCodeActProvider(ExecutablePath, options));
        var functionError = Assert.Throws<ArgumentException>(() => new LocalExecuteCodeFunction(ExecutablePath, options));

        // Assert
        Assert.Equal("pythonExecutablePath", providerError.ParamName);
        Assert.Equal("pythonExecutablePath", functionError.ParamName);
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public void Constructors_RejectMissingAbsolutePaths(bool validationDisabled)
    {
        // Arrange
        var executablePath = Path.Combine(Path.GetTempPath(), $"localcodeact-missing-{Guid.NewGuid():N}.exe");
        var options = CreateOptions(validationDisabled);

        // Act
        var providerError = Assert.Throws<FileNotFoundException>(() => new LocalCodeActProvider(executablePath, options));
        var functionError = Assert.Throws<FileNotFoundException>(() => new LocalExecuteCodeFunction(executablePath, options));

        // Assert
        Assert.Equal(executablePath, providerError.FileName);
        Assert.Equal(executablePath, functionError.FileName);
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public void Constructors_RejectDirectoryPaths(bool validationDisabled)
    {
        // Arrange
        var directory = Directory.CreateTempSubdirectory("localcodeact-python-path-");
        try
        {
            var options = CreateOptions(validationDisabled);

            // Act
            var providerError = Assert.Throws<FileNotFoundException>(() => new LocalCodeActProvider(directory.FullName, options));
            var functionError = Assert.Throws<FileNotFoundException>(() => new LocalExecuteCodeFunction(directory.FullName, options));

            // Assert
            Assert.Equal(directory.FullName, providerError.FileName);
            Assert.Equal(directory.FullName, functionError.FileName);
        }
        finally
        {
            directory.Delete(recursive: true);
        }
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public void Constructors_AcceptExistingAbsolutePathsWithSpaces(bool validationDisabled)
    {
        // Arrange
        var directory = Directory.CreateTempSubdirectory("localcodeact-python-path-");
        try
        {
            var executablePath = Path.Combine(directory.FullName, "python interpreter.exe");
            // This constructor-only stand-in is never executed.
            File.WriteAllText(executablePath, string.Empty);
            var options = CreateOptions(validationDisabled);

            // Act
            using var provider = new LocalCodeActProvider(executablePath, options);
            var function = new LocalExecuteCodeFunction(executablePath, options);

            // Assert
            Assert.Single(provider.StateKeys);
            Assert.Equal("execute_code", function.Name);
        }
        finally
        {
            directory.Delete(recursive: true);
        }
    }

    private static LocalCodeActProviderOptions CreateOptions(bool validationDisabled = false) =>
        new()
        {
            ValidationDisabled = validationDisabled,
            RunnerScriptPath = "unused-runner.py",
            ValidatorScriptPath = "unused-validator.py",
        };
}
