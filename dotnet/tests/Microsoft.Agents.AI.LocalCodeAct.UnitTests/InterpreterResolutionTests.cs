// Copyright (c) Microsoft. All rights reserved.

using System;
using System.IO;

namespace Microsoft.Agents.AI.LocalCodeAct.UnitTests;

public sealed class InterpreterResolutionTests
{
    [Theory]
    [InlineData("python.exe")]
    [InlineData("python3")]
    [InlineData(@".\python.exe")]
    [InlineData(@"..\python.exe")]
    [InlineData("C:python.exe")]
    [InlineData(@"\python.exe")]
    [InlineData("/usr/bin/python3")]
    public void Constructors_RejectNonFullyQualifiedPathsOnWindows(string executablePath)
    {
        Assert.SkipUnless(OperatingSystem.IsWindows(), "Windows executable-path validation is not used on Unix.");

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
    public void Constructors_RejectMissingAbsolutePathsOnWindows(bool validationDisabled)
    {
        Assert.SkipUnless(OperatingSystem.IsWindows(), "Windows executable-path validation is not used on Unix.");

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

    [Fact]
    public void Constructors_RejectDirectoryPathsOnWindows()
    {
        Assert.SkipUnless(OperatingSystem.IsWindows(), "Windows executable-path validation is not used on Unix.");

        // Arrange
        var directory = Directory.CreateTempSubdirectory("localcodeact-python-path-");
        try
        {
            var options = CreateOptions();

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

    [Theory]
    [InlineData("python3")]
    [InlineData("./python3")]
    [InlineData("/missing/python3")]
    public void Constructors_PreserveNonWindowsExecutableValues(string executablePath)
    {
        Assert.SkipWhen(OperatingSystem.IsWindows(), "Windows requires an existing fully qualified interpreter path.");

        // Arrange
        var options = CreateOptions();

        // Act
        using var provider = new LocalCodeActProvider(executablePath, options);
        var function = new LocalExecuteCodeFunction(executablePath, options);

        // Assert
        Assert.Single(provider.StateKeys);
        Assert.Equal("execute_code", function.Name);
    }

    private static LocalCodeActProviderOptions CreateOptions(bool validationDisabled = false) =>
        new()
        {
            ValidationDisabled = validationDisabled,
            RunnerScriptPath = "unused-runner.py",
            ValidatorScriptPath = "unused-validator.py",
        };
}
