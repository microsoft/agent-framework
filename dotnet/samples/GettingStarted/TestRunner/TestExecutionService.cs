// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics;
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
    public async Task<TestResult> ExecuteTestAsync(string filter, bool verbose = false)
    {
        AnsiConsole.MarkupLine($"[blue]Executing test with filter: {filter}[/]");

        var arguments = BuildTestArguments(filter, verbose);

        return await AnsiConsole.Status()
            .Spinner(Spinner.Known.Dots)
            .StartAsync("Running test...", async ctx =>
            {
                var result = await RunDotnetTestAsync(arguments);

                ctx.Status = result.Success ? "Test completed successfully" : "Test failed";
                ctx.Spinner(result.Success ? Spinner.Known.Star : Spinner.Known.Dots);

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
    private static string BuildTestArguments(string filter, bool verbose)
    {
        var args = new List<string>
        {
            "test",
            "--no-build",
            "--verbosity", verbose ? "detailed" : "normal"
        };

        if (!string.IsNullOrEmpty(filter))
        {
            args.Add("--filter");
            args.Add($"\"{filter}\"");
        }

        if (verbose)
        {
            args.Add("--logger");
            args.Add("\"console;verbosity=detailed\"");
        }

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
                CreateNoWindow = true
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

#if NET472
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
            return $"DisplayName={className}.{methodName}(provider: {providerValue})";
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

/// <summary>
/// Represents the result of a test execution.
/// </summary>
public class TestResult
{
    public bool Success { get; set; }
    public int ExitCode { get; set; }
    public string Output { get; set; } = string.Empty;
    public string Error { get; set; } = string.Empty;
}
