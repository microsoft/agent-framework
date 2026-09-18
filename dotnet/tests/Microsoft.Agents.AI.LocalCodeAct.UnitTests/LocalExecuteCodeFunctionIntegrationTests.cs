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

    [Theory]
    [InlineData("import os\nos.system('id')")]
    [InlineData("import os as x\nx.system('id')")]
    [InlineData("import os\n_o = os\n_o.system('id')")]
    [InlineData("import os as x\na = x\nb = a\nb.popen('id')")]
    [InlineData("import os.path\nos.system('id')")]
    [InlineData("import os\nos.path.os.system('id')")]
    [InlineData("import os\nos.path.os.popen('id')")]
    [InlineData("import os.path as p\np.os.system('id')")]
    [InlineData("from os import path as p\np.os.popen('id')")]
    [InlineData("import pathlib\npathlib.os.system('id')")]
    [InlineData("import random\nrandom._os.system('id')")]
    [InlineData("from pathlib import os as o\no.system('id')")]
    [InlineData("from random import _os as o\no.system('id')")]
    [InlineData("import os\nq = os.path\nq.os.system('id')")]
    [InlineData("import os\nq = os.path.os\nq.system('id')")]
    [InlineData("import os\nq: object = os.path\nq.os.system('id')")]
    [InlineData("import os\nq, _ = (os.path, 1)\nq.os.system('id')")]
    [InlineData("import os\n[q, _] = [os.path, 1]\nq.os.system('id')")]
    [InlineData("import os\nq = [os.path][0]\nq.os.system('id')")]
    [InlineData("import os\nq = (os.path,)[0]\nq.os.system('id')")]
    [InlineData("import os\nq = {'path': os.path}['path']\nq.os.system('id')")]
    [InlineData("import os\nq = ([os] + [])[0]\nq.system('id')")]
    [InlineData("import os\nq = [value for value in [os]][0]\nq.system('id')")]
    [InlineData("import os\n_, *values = (1, 2, os)\nvalues[1].system('id')")]
    [InlineData("import os\nvalues = []\nvalues += [os]\nvalues[0].system('id')")]
    [InlineData("import os\nos.path.__dict__['os'].system('id')")]
    [InlineData("import os\nos.path.os.__dict__['system']('id')")]
    [InlineData("import os\ngetattr(os.path, 'os').system('id')")]
    [InlineData("import os\nos.environ['KEY'] = 'value'")]
    [InlineData("import os\nos.environ.update({'KEY': 'value'})")]
    [InlineData("import os\nprint(os.path.exists('file'))")]
    [InlineData("import os\ndef get_path():\n    return os.path\nget_path().os.system('id')")]
    [InlineData("import os\ndef identity(value):\n    return value\nidentity(os.path).os.system('id')")]
    [InlineData("import typing\ntyping.sys.modules['os'].system('id')")]
    [InlineData("import asyncio\nawait asyncio.create_subprocess_exec('id')")]
    [InlineData("import asyncio\nawait asyncio.open_connection('localhost', 80)")]
    [InlineData("from typing import sys as s\ns.modules['os'].system('id')")]
    [InlineData("from typing import __dict__ as namespace\nnamespace['__builtins__']['__import__']('os').system('id')")]
    [InlineData("__builtins__['__import__']('os').system('id')")]
    [InlineData("load = __import__\nload('os').system('id')")]
    [InlineData("namespace = globals\nnamespace()['__builtins__']['__import__']('os').system('id')")]
    [InlineData("from asyncio import create_subprocess_exec as start\nawait start('id')")]
    [InlineData("from asyncio import open_connection as connect\nawait connect('localhost', 80)")]
    [InlineData("import os\nmatch (os.environ,):\n    case (env,):\n        env['KEY'] = 'value'")]
    [InlineData("import os\ndef print(value):\n    return value\nq = print(os)\nq.system('id')")]
    [InlineData("import os\ndef list(value):\n    return value\nenv = list(os.environ)\nenv['KEY'] = 'value'")]
    [InlineData("import os\ndef use(print):\n    q = print(os)\n    q.system('id')\nuse(lambda value: value)")]
    [InlineData("import os\nos.environ.keys()._mapping['KEY'] = 'value'")]
    [InlineData("import os\nos.environ.items()._mapping['KEY'] = 'value'")]
    [InlineData("import os\nos.environ.values()._mapping['KEY'] = 'value'")]
    [InlineData("import os\na, _ = (os, 1)\na.system('id')")]
    [InlineData("import os\n[a, _] = [os, 1]\na.system('id')")]
    [InlineData("import os\nx: object = os\nx.system('id')")]
    public async Task ExecuteCode_ValidationBlocksDisallowedOsAccessBeforeRunnerStartsAsync(string code)
    {
        SkipIfNoPython();

        // Arrange
        var tempDir = Directory.CreateTempSubdirectory("localcodeact-runner-marker-").FullName;
        try
        {
            var markerPath = Path.Combine(tempDir, "runner-started");
            var runnerPath = Path.Combine(tempDir, "marker_runner.py");
            File.WriteAllText(
                runnerPath,
                $"from pathlib import Path\nPath({JsonSerializer.Serialize(markerPath)}).touch()\n");

            var function = new LocalExecuteCodeFunction(
                s_python!,
                new LocalCodeActProviderOptions { RunnerScriptPath = runnerPath });
            var args = new AIFunctionArguments
            {
                ["code"] = code,
            };

            // Act
            var exception = await Record.ExceptionAsync(
                async () => await function.InvokeAsync(args, CancellationToken.None));

            // Assert
            Assert.False(File.Exists(markerPath), "The runner started before validation completed.");
            var validationException = Assert.IsType<CodeValidationException>(exception);
            Assert.Contains("not allowed", validationException.Message, StringComparison.Ordinal);
        }
        finally
        {
            Directory.Delete(tempDir, recursive: true);
        }
    }

    [Theory]
    [InlineData("import os\nprint(os.environ.get('PATH') is not None)")]
    [InlineData("import os\nprint(os.environ['PATH'] if 'PATH' in os.environ else '')")]
    [InlineData("import os\nenv = os.environ\nprint(list(env))")]
    [InlineData("import os as x\nprint(x.path.join('a', 'b'))")]
    [InlineData("import os.path as p\nprint(p.join('a', 'b'))")]
    [InlineData("from os import path as p\nprint(p.basename('a/b'))")]
    [InlineData("import os\np = os.path\nprint(p.normpath('a/../b'))")]
    [InlineData("import os\np, env = (os.path, os.environ)\nprint(p.join('a', 'b'))\nprint(env.get('PATH'))")]
    [InlineData("import os\njoin = os.path.join\nprint(join('a', 'b'))")]
    public async Task ExecuteCode_AllowsPermittedOsAccessAsync(string code)
    {
        SkipIfNoPython();

        var function = new LocalExecuteCodeFunction(s_python!);

        var args = new AIFunctionArguments
        {
            ["code"] = code,
        };

        var result = await function.InvokeAsync(args, CancellationToken.None);
        Assert.NotNull(result);
    }

    [Fact]
    public async Task ExecuteCode_DefaultEnvironmentDoesNotInheritParentVariablesAsync()
    {
        SkipIfNoPython();

        // Arrange
        var variableName = $"AF_LOCALCODEACT_PARENT_{Guid.NewGuid():N}";
        var parentValue = $"parent-value-{Guid.NewGuid():N}";
        var originalValue = Environment.GetEnvironmentVariable(variableName);
        Environment.SetEnvironmentVariable(variableName, parentValue);

        try
        {
            var function = new LocalExecuteCodeFunction(s_python!);
            var args = new AIFunctionArguments
            {
                ["code"] = $"import os\nprint(os.environ.get('{variableName}', 'NOT_FOUND'))",
            };

            // Act
            var result = await function.InvokeAsync(args, CancellationToken.None);

            // Assert
            var combined = GetResultText(result);
            Assert.Contains("NOT_FOUND", combined, StringComparison.Ordinal);
            Assert.DoesNotContain(parentValue, combined, StringComparison.Ordinal);
        }
        finally
        {
            Environment.SetEnvironmentVariable(variableName, originalValue);
        }
    }

    [Fact]
    public async Task ExecuteCode_ExplicitEnvironmentDoesNotInheritOtherParentVariablesAsync()
    {
        SkipIfNoPython();

        // Arrange
        var parentVariableName = $"AF_LOCALCODEACT_PARENT_{Guid.NewGuid():N}";
        var childVariableName = $"AF_LOCALCODEACT_CHILD_{Guid.NewGuid():N}";
        var parentValue = $"parent-value-{Guid.NewGuid():N}";
        var childValue = $"child-value-{Guid.NewGuid():N}";
        var originalValue = Environment.GetEnvironmentVariable(parentVariableName);
        Environment.SetEnvironmentVariable(parentVariableName, parentValue);

        try
        {
            var options = new LocalCodeActProviderOptions
            {
                Environment = new Dictionary<string, string>
                {
                    [childVariableName] = childValue,
                },
            };
            var function = new LocalExecuteCodeFunction(s_python!, options);
            var args = new AIFunctionArguments
            {
                ["code"] =
                    $"import os\nprint(os.environ.get('{childVariableName}', 'NOT_FOUND'))\n" +
                    $"print(os.environ.get('{parentVariableName}', 'NOT_FOUND'))",
            };

            // Act
            var result = await function.InvokeAsync(args, CancellationToken.None);

            // Assert
            var combined = GetResultText(result);
            Assert.Contains(childValue, combined, StringComparison.Ordinal);
            Assert.Contains("NOT_FOUND", combined, StringComparison.Ordinal);
            Assert.DoesNotContain(parentValue, combined, StringComparison.Ordinal);
        }
        finally
        {
            Environment.SetEnvironmentVariable(parentVariableName, originalValue);
        }
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
