// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.LocalCodeAct.UnitTests;

/// <summary>
/// Integration tests that launch a real Python subprocess. Skipped automatically when
/// no Python interpreter is discoverable on PATH.
/// </summary>
public sealed class LocalExecuteCodeFunctionIntegrationTests
{
    private static readonly string? s_python = FindPython();

    private static void SkipIfNoPython()
    {
        if (s_python is null)
        {
            Assert.Skip("No Python interpreter found on PATH; skipping integration test.");
        }
    }

    [Fact]
    public async Task ExecuteCode_PrintsAndReturnsResultAsync()
    {
        SkipIfNoPython();

        var function = new LocalExecuteCodeFunction(s_python!);

        var args = new AIFunctionArguments
        {
            ["code"] = "print('hello world')\n1 + 2",
        };

        var result = await function.InvokeAsync(args, CancellationToken.None);

        Assert.NotNull(result);
        var combined = GetResultText(result);
        Assert.Contains("hello world", combined);
        Assert.Contains("3", combined);
    }

    [Fact]
    public async Task ExecuteCode_ValidationBlocksDisallowedImportAsync()
    {
        SkipIfNoPython();

        var function = new LocalExecuteCodeFunction(s_python!);

        var args = new AIFunctionArguments
        {
            ["code"] = "import subprocess",
        };

        await Assert.ThrowsAsync<CodeValidationException>(async () =>
            await function.InvokeAsync(args, CancellationToken.None));
    }

    [Fact]
    public async Task ExecuteCode_CapturesFilesInWritableMountAsync()
    {
        SkipIfNoPython();

        var hostDir = Directory.CreateTempSubdirectory("localcodeact-mount-").FullName;
        try
        {
            var options = new LocalCodeActProviderOptions
            {
                FileMounts = new[]
                {
                    new FileMount(hostDir, "/output", FileMountMode.ReadWrite),
                },
            };

            var function = new LocalExecuteCodeFunction(s_python!, options);

            // Use os.path.join via the actual host path - the mount path is descriptive metadata only
            var escapedPath = hostDir.Replace("\\", "\\\\", StringComparison.Ordinal);
            var args = new AIFunctionArguments
            {
                ["code"] = $"from pathlib import Path\nPath(r'{escapedPath}/out.txt').write_text('captured')",
            };

            var result = await function.InvokeAsync(args, CancellationToken.None);

            Assert.NotNull(result);
            AssertResultContainsDataContent(result, "/output/out.txt");
        }
        finally
        {
            Directory.Delete(hostDir, recursive: true);
        }
    }

    [Fact]
    public async Task ExecuteCode_UnknownToolNameReturnsErrorToGeneratedCodeAsync()
    {
        SkipIfNoPython();

        // No tools are registered, so any call_tool from generated code resolves to
        // the "Unknown tool" branch in ProcessBridge.HandleToolCallAsync.
        var function = new LocalExecuteCodeFunction(s_python!);

        var args = new AIFunctionArguments
        {
            ["code"] = @"
try:
    await call_tool('definitely_not_registered', x=1)
    print('NO_ERROR')
except Exception as exc:
    print('GOT_ERROR:' + type(exc).__name__ + ':' + str(exc))
",
        };

        var result = await function.InvokeAsync(args, CancellationToken.None);
        var combined = GetResultText(result);
        Assert.Contains("GOT_ERROR", combined);
        Assert.Contains("definitely_not_registered", combined);
        Assert.DoesNotContain("NO_ERROR", combined);
    }

    [Fact]
    public async Task ExecuteCode_ToolThrowingExceptionPropagatesToGeneratedCodeAsync()
    {
        SkipIfNoPython();

        // Tool that always throws — exercises ProcessBridge.HandleToolCallAsync exception path
        // which sends a structured error response back to the subprocess.
        Func<string, string> faulty = message => throw new InvalidOperationException("intentional: " + message);
        var faultyTool = AIFunctionFactory.Create(faulty, name: "faulty");

        var options = new LocalCodeActProviderOptions
        {
            Tools = new[] { faultyTool },
        };
        var function = new LocalExecuteCodeFunction(s_python!, options);

        var args = new AIFunctionArguments
        {
            ["code"] = @"
try:
    await call_tool('faulty', message='boom')
    print('NO_ERROR')
except Exception as exc:
    print('GOT_ERROR:' + type(exc).__name__ + ':' + str(exc))
",
        };
        var result = await function.InvokeAsync(args, CancellationToken.None);
        var combined = GetResultText(result);
        Assert.Contains("GOT_ERROR", combined);
        Assert.Contains("InvalidOperationException", combined);
        Assert.Contains("intentional: boom", combined);
    }

    [Fact]
    public async Task Validator_TimeoutKillsProcessAndThrowsAsync()
    {
        SkipIfNoPython();

        // Custom validator script that ignores stdin and blocks forever so the
        // parent timeout fires and exercises the timeout catch in CodeValidator.
        var tempDir = Directory.CreateTempSubdirectory("localcodeact-vtimeout-").FullName;
        try
        {
            var scriptPath = Path.Combine(tempDir, "hang_validator.py");
            File.WriteAllText(scriptPath, "import time\nwhile True:\n    time.sleep(60)\n");

            var validator = new Internal.CodeValidator(
                s_python!,
                scriptPath,
                TimeSpan.FromSeconds(1),
                allowedImports: null,
                blockedImports: null,
                allowedBuiltins: null,
                blockedBuiltins: null);

            var ex = await Assert.ThrowsAsync<CodeValidationException>(
                async () => await validator.ValidateAsync("print('x')", CancellationToken.None));
            Assert.Contains("exceeded", ex.Message);
        }
        finally
        {
            Directory.Delete(tempDir, recursive: true);
        }
    }

    private static string GetResultText(object? result) =>
        result switch
        {
            IEnumerable<AIContent> contents => string.Join("\n", contents.OfType<TextContent>().Select(t => t.Text)),
            JsonElement element => element.GetRawText(),
            _ => result?.ToString() ?? string.Empty,
        };

    private static void AssertResultContainsDataContent(object? result, string expectedPath)
    {
        if (result is IEnumerable<AIContent> contents)
        {
            Assert.Contains(contents, c => c is DataContent);
            return;
        }

        var json = Assert.IsType<JsonElement>(result).GetRawText();
        Assert.Contains(expectedPath, json);
    }

    private static string? FindPython()
    {
        var configured = Environment.GetEnvironmentVariable("LOCAL_CODEACT_PYTHON");
        if (!string.IsNullOrWhiteSpace(configured) && IsUsablePython(configured))
        {
            return configured;
        }

        var executableNames = OperatingSystem.IsWindows()
            ? new[] { "python3.exe", "python.exe" }
            : new[] { "python3", "python" };

        foreach (var name in executableNames)
        {
            var path = Environment.GetEnvironmentVariable("PATH") ?? string.Empty;
            foreach (var dir in path.Split(Path.PathSeparator))
            {
                if (string.IsNullOrWhiteSpace(dir))
                {
                    continue;
                }

                var candidate = Path.Combine(dir, name);
                if (File.Exists(candidate) && IsUsablePython(candidate))
                {
                    return candidate;
                }
            }
        }

        return null;
    }

    private static bool IsUsablePython(string candidate)
    {
        try
        {
            using var process = Process.Start(new ProcessStartInfo
            {
                FileName = candidate,
                ArgumentList = { "--version" },
                UseShellExecute = false,
                RedirectStandardOutput = true,
                RedirectStandardError = true,
                CreateNoWindow = true,
            });
            if (process is null)
            {
                return false;
            }

            if (!process.WaitForExit(milliseconds: 5000))
            {
                process.Kill(entireProcessTree: true);
                return false;
            }

            return process.ExitCode == 0;
        }
        catch
        {
            return false;
        }
    }
}
