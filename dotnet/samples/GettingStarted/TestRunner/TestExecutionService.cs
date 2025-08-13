// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics;
using System.Reflection;
using Spectre.Console;

namespace GettingStarted.TestRunner;

/// <summary>
/// Service for executing tests using dotnet test command.
/// </summary>
public class TestExecutionService
{
    private static readonly char[] LineSeparators = { '\n' };
    /// <summary>
    /// Executes a test using the specified filter.
    /// </summary>
    public async Task<TestResult> ExecuteTestAsync(string filter)
    {
        AnsiConsole.MarkupLine($"[blue]Executing test with filter: {filter}[/]");

        var arguments = BuildTestArguments(filter);

        return await AnsiConsole.Status()
            .Spinner(Spinner.Known.Dots)
            .StartAsync("Running test...", async ctx =>
            {
                var result = await RunDotnetTestAsync(arguments);

                ctx.Status = result.Success ? "Test completed successfully" : "Test failed";
                ctx.Spinner(Spinner.Known.Dots);

                return result;
            });
    }

    /// <summary>
    /// Lists all tests matching the specified filter.
    /// </summary>
    public async Task<List<string>> ListTestsAsync(string? filter = null)
    {
        var arguments = BuildListTestsArguments(filter);

        var result = await RunDotnetTestAsync(arguments);

        if (!result.Success)
        {
            AnsiConsole.MarkupLine("[red]Failed to list tests[/]");
            return new List<string>();
        }

        return ParseTestList(result.Output);
    }

    /// <summary>
    /// Builds the dotnet test arguments.
    /// </summary>
    private static string BuildTestArguments(string filter)
    {
        var args = new List<string>
        {
            "test",
            "--no-build",
            "--verbosity", "minimal", // Always use detailed to capture console output
            "--framework", GetCurrentTargetFramework()
        };

        if (!string.IsNullOrEmpty(filter))
        {
            args.Add("--filter");
            args.Add($"\"{filter}\"");
        }

        // Always include console logger to show test output
        args.Add("--logger");
        args.Add("\"console;verbosity=detailed\""); // Always use detailed to capture console output

        return string.Join(" ", args);
    }

    /// <summary>
    /// Builds the arguments for listing tests.
    /// </summary>
    private static string BuildListTestsArguments(string? filter)
    {
        var args = new List<string>
        {
            "test",
            "--list-tests",
            "--verbosity", "quiet"
        };

        if (!string.IsNullOrEmpty(filter))
        {
            args.Add("--filter");
            args.Add($"\"{filter}\"");
        }

        return string.Join(" ", args);
    }

    /// <summary>
    /// Gets the current target framework for the running application.
    /// </summary>
    private static string GetCurrentTargetFramework()
    {
        // Get the target framework from the current assembly's target framework attribute
        var assembly = Assembly.GetExecutingAssembly();
        var targetFrameworkAttribute = assembly.GetCustomAttribute<System.Runtime.Versioning.TargetFrameworkAttribute>();

        if (targetFrameworkAttribute != null)
        {
            var frameworkName = targetFrameworkAttribute.FrameworkName;

            // Convert framework name to dotnet test format
            if (frameworkName.StartsWith(".NETCoreApp,Version=v", StringComparison.Ordinal))
            {
                var version = frameworkName.Substring(".NETCoreApp,Version=v".Length);
                return $"net{version}";
            }
            else if (frameworkName.StartsWith(".NETFramework,Version=v", StringComparison.Ordinal))
            {
                var version = frameworkName.Substring(".NETFramework,Version=v".Length);
                return $"net{version.Replace(".", "")}";
            }
        }

        // Fallback: try to detect from runtime information
        var runtimeVersion = Environment.Version;
        if (runtimeVersion.Major >= 5)
        {
            return $"net{runtimeVersion.Major}.{runtimeVersion.Minor}";
        }

        // Default fallback for .NET Framework
        return "net472";
    }

    /// <summary>
    /// Gets the project directory for test execution.
    /// </summary>
    private static string GetProjectDirectory()
    {
        // Get the directory where the current assembly is located
        var assemblyLocation = Assembly.GetExecutingAssembly().Location;
        var assemblyDirectory = Path.GetDirectoryName(assemblyLocation);

        // Navigate up to find the project directory (where .csproj file is located)
        var currentDirectory = assemblyDirectory;
        while (currentDirectory != null)
        {
            if (Directory.GetFiles(currentDirectory, "*.csproj").Length > 0)
            {
                return currentDirectory;
            }
            currentDirectory = Directory.GetParent(currentDirectory)?.FullName;
        }

        // Fallback to current directory if project file not found
        return Directory.GetCurrentDirectory();
    }

    /// <summary>
    /// Runs the dotnet test command.
    /// </summary>
    private static async Task<TestResult> RunDotnetTestAsync(string arguments)
    {
        try
        {
            var startInfo = new ProcessStartInfo
            {
                FileName = "dotnet",
                Arguments = arguments,
                UseShellExecute = false,
                RedirectStandardOutput = true,
                RedirectStandardError = true,
                CreateNoWindow = true,
                WorkingDirectory = GetProjectDirectory()
            };

            using var process = Process.Start(startInfo);
            if (process == null)
            {
                return new TestResult
                {
                    Success = false,
                    Output = "Failed to start dotnet process",
                    Error = "Process creation failed"
                };
            }

            var outputTask = process.StandardOutput.ReadToEndAsync();
            var errorTask = process.StandardError.ReadToEndAsync();

#if !NET8_0_OR_GREATER
            process.WaitForExit();
#else
            await process.WaitForExitAsync();
#endif

            var output = await outputTask;
            var error = await errorTask;

            return new TestResult
            {
                Success = process.ExitCode == 0,
                ExitCode = process.ExitCode,
                Output = output,
                Error = error
            };
        }
        catch (Exception ex)
        {
            return new TestResult
            {
                Success = false,
                Output = string.Empty,
                Error = ex.Message
            };
        }
    }

    /// <summary>
    /// Parses the test list output.
    /// </summary>
    private static List<string> ParseTestList(string output)
    {
        var tests = new List<string>();
        var lines = output.Split(LineSeparators, StringSplitOptions.RemoveEmptyEntries);

        foreach (var line in lines)
        {
            var trimmed = line.Trim();
            if (trimmed.Contains('.') && !trimmed.StartsWith("The following", StringComparison.OrdinalIgnoreCase) &&
                !trimmed.StartsWith("Build", StringComparison.OrdinalIgnoreCase) && !trimmed.StartsWith("Restore", StringComparison.OrdinalIgnoreCase))
            {
                tests.Add(trimmed);
            }
        }

        return tests;
    }

    /// <summary>
    /// Generates a filter string for a specific test method.
    /// </summary>
    public static string GenerateMethodFilter(TestMethod method)
    {
        return $"FullyQualifiedName~{method.MethodInfo.DeclaringType?.Name}.{method.Name}";
    }

    /// <summary>
    /// Generates a filter string for a specific theory test case.
    /// </summary>
    public static string GenerateTheoryFilter(TestMethod method, TheoryTestCase theoryCase)
    {
        var className = method.MethodInfo.DeclaringType?.Name;
        var methodName = method.Name;

        // Extract provider value from theory case
        var providerParam = theoryCase.Parameters.FirstOrDefault(p => p.Name == "provider");
        if (providerParam?.Value != null)
        {
            var providerValue = providerParam.Value.ToString();

            // Use precise filter combination for specific theory case targeting
            var fullyQualifiedName = $"{className}.{methodName}";
            var displayNamePattern = $"\\(provider: {providerValue}\\)";

            return $"FullyQualifiedName~{fullyQualifiedName}&DisplayName~{displayNamePattern}";
        }

        // Fallback to method filter if we can't construct theory filter
        return GenerateMethodFilter(method);
    }

    /// <summary>
    /// Generates a filter string for a test class.
    /// </summary>
    public static string GenerateClassFilter(TestClass testClass)
    {
        return $"FullyQualifiedName~{testClass.Name}";
    }

    /// <summary>
    /// Generates a filter string for a test folder/namespace.
    /// </summary>
    public static string GenerateFolderFilter(TestFolder folder)
    {
        return $"FullyQualifiedName~{folder.Name}";
    }
}
