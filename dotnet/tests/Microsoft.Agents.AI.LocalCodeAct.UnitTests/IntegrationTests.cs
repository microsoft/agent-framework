// Copyright (c) Microsoft Corporation. All rights reserved.
// Licensed under the MIT License.

using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Xunit;

namespace Microsoft.Agents.AI.LocalCodeAct.UnitTests;

public class IntegrationTests : IDisposable
{
    private readonly string _testDir;
    private readonly string? _pythonPath;

    public IntegrationTests()
    {
        _testDir = Path.Combine(Path.GetTempPath(), $"localcodeact_test_{Guid.NewGuid():N}");
        Directory.CreateDirectory(_testDir);

        // Try to find Python
        _pythonPath = FindPythonExecutable();
    }

    public void Dispose()
    {
        if (Directory.Exists(_testDir))
        {
            try
            {
                Directory.Delete(_testDir, recursive: true);
            }
            catch
            {
                // Best effort cleanup
            }
        }
    }

    private static string? FindPythonExecutable()
    {
        var candidates = new[] { "python3", "python", "python.exe", "python3.exe" };

        foreach (var candidate in candidates)
        {
            try
            {
                var startInfo = new System.Diagnostics.ProcessStartInfo
                {
                    FileName = candidate,
                    Arguments = "--version",
                    RedirectStandardOutput = true,
                    RedirectStandardError = true,
                    UseShellExecute = false,
                    CreateNoWindow = true
                };

                using var process = System.Diagnostics.Process.Start(startInfo);
                if (process != null)
                {
                    process.WaitForExit(1000);
                    if (process.ExitCode == 0)
                    {
                        return candidate;
                    }
                }
            }
            catch
            {
                // Try next candidate
            }
        }

        return null;
    }

    [Fact]
    public async Task ExecuteSimpleCode_ReturnsResult()
    {
        if (_pythonPath == null)
        {
            // Skip if Python not available
            return;
        }

        var function = new LocalExecuteCodeFunction(
            pythonExecutablePath: _pythonPath,
            tools: [],
            executionLimits: new ProcessExecutionLimits(TimeoutSeconds: 5)
        );

        var code = "result = 2 + 2";
        var args = JsonSerializer.SerializeToElement(new { code });

        var result = await function.InvokeAsync(args, CancellationToken.None);

        Assert.NotNull(result);
        var textContent = result.OfType<TextContent>().FirstOrDefault();
        Assert.NotNull(textContent);
        Assert.Contains("4", textContent!.Text);
    }

    [Fact]
    public async Task ExecuteCodeWithTimeout_Throws()
    {
        if (_pythonPath == null)
        {
            return;
        }

        var function = new LocalExecuteCodeFunction(
            pythonExecutablePath: _pythonPath,
            tools: [],
            executionLimits: new ProcessExecutionLimits(TimeoutSeconds: 1)
        );

        var code = "import time\ntime.sleep(10)\nresult = 'done'";
        var args = JsonSerializer.SerializeToElement(new { code });

        await Assert.ThrowsAnyAsync<Exception>(async () =>
        {
            await function.InvokeAsync(args, CancellationToken.None);
        });
    }

    [Fact]
    public async Task ExecuteCodeWithInvalidSyntax_ReturnsError()
    {
        if (_pythonPath == null)
        {
            return;
        }

        var function = new LocalExecuteCodeFunction(
            pythonExecutablePath: _pythonPath,
            tools: [],
            executionLimits: new ProcessExecutionLimits(TimeoutSeconds: 5)
        );

        var code = "this is not valid python syntax!@#$";
        var args = JsonSerializer.SerializeToElement(new { code });

        var result = await function.InvokeAsync(args, CancellationToken.None);

        Assert.NotNull(result);
        var textContent = result.OfType<TextContent>().FirstOrDefault();
        Assert.NotNull(textContent);
        Assert.Contains("SyntaxError", textContent!.Text);
    }

    [Fact]
    public async Task ExecuteCodeWithBlockedImport_FailsValidation()
    {
        if (_pythonPath == null)
        {
            return;
        }

        var function = new LocalExecuteCodeFunction(
            pythonExecutablePath: _pythonPath,
            tools: [],
            executionLimits: new ProcessExecutionLimits(TimeoutSeconds: 5)
        );

        var code = "import subprocess\nresult = 'test'";
        var args = JsonSerializer.SerializeToElement(new { code });

        await Assert.ThrowsAsync<CodeValidationException>(async () =>
        {
            await function.InvokeAsync(args, CancellationToken.None);
        });
    }

    [Fact]
    public async Task ExecuteCodeWithBlockedBuiltin_FailsValidation()
    {
        if (_pythonPath == null)
        {
            return;
        }

        var function = new LocalExecuteCodeFunction(
            pythonExecutablePath: _pythonPath,
            tools: [],
            executionLimits: new ProcessExecutionLimits(TimeoutSeconds: 5)
        );

        var code = "result = eval('2 + 2')";
        var args = JsonSerializer.SerializeToElement(new { code });

        await Assert.ThrowsAsync<CodeValidationException>(async () =>
        {
            await function.InvokeAsync(args, CancellationToken.None);
        });
    }

    [Fact]
    public async Task ExecuteCodeWithCustomAllowedImports_Succeeds()
    {
        if (_pythonPath == null)
        {
            return;
        }

        var function = new LocalExecuteCodeFunction(
            pythonExecutablePath: _pythonPath,
            tools: [],
            executionLimits: new ProcessExecutionLimits(TimeoutSeconds: 5),
            allowedImports: ["json", "math"]
        );

        var code = "import json\nimport math\nresult = json.dumps({'pi': math.pi})";
        var args = JsonSerializer.SerializeToElement(new { code });

        var result = await function.InvokeAsync(args, CancellationToken.None);

        Assert.NotNull(result);
        var textContent = result.OfType<TextContent>().FirstOrDefault();
        Assert.NotNull(textContent);
        Assert.Contains("3.14", textContent!.Text);
    }

    [Fact]
    public async Task ExecuteCodeWithFileMounts_CapturesWrittenFiles()
    {
        if (_pythonPath == null)
        {
            return;
        }

        var inputDir = Path.Combine(_testDir, "input");
        var outputDir = Path.Combine(_testDir, "output");
        Directory.CreateDirectory(inputDir);
        Directory.CreateDirectory(outputDir);

        // Create input file
        var inputFile = Path.Combine(inputDir, "test.txt");
        File.WriteAllText(inputFile, "Hello from input");

        var fileMounts = new List<FileMount>
        {
            new(inputDir, "/input", FileMountMode.ReadOnly, null),
            new(outputDir, "/output", FileMountMode.ReadWrite, null)
        };

        var function = new LocalExecuteCodeFunction(
            pythonExecutablePath: _pythonPath,
            tools: [],
            executionLimits: new ProcessExecutionLimits(TimeoutSeconds: 5),
            fileMounts: fileMounts
        );

        var code = @"
import os
# Read from input
with open('/input/test.txt', 'r') as f:
    content = f.read()
# Write to output
with open('/output/result.txt', 'w') as f:
    f.write(f'Processed: {content}')
result = 'Files processed'
";
        var args = JsonSerializer.SerializeToElement(new { code });

        var result = await function.InvokeAsync(args, CancellationToken.None);

        Assert.NotNull(result);

        // Check that output file was captured
        var dataContent = result.OfType<DataContent>().FirstOrDefault();
        Assert.NotNull(dataContent);

        // Verify file content
        var outputFile = Path.Combine(outputDir, "result.txt");
        Assert.True(File.Exists(outputFile));
        var outputContent = File.ReadAllText(outputFile);
        Assert.Contains("Processed: Hello from input", outputContent);
    }

    [Fact]
    public async Task ExecuteCodeWithStdout_CapturesOutput()
    {
        if (_pythonPath == null)
        {
            return;
        }

        var function = new LocalExecuteCodeFunction(
            pythonExecutablePath: _pythonPath,
            tools: [],
            executionLimits: new ProcessExecutionLimits(TimeoutSeconds: 5)
        );

        var code = @"
print('Hello from stdout')
print('Line 2')
result = 'Done'
";
        var args = JsonSerializer.SerializeToElement(new { code });

        var result = await function.InvokeAsync(args, CancellationToken.None);

        Assert.NotNull(result);
        var textContent = result.OfType<TextContent>().FirstOrDefault();
        Assert.NotNull(textContent);
        Assert.Contains("Hello from stdout", textContent!.Text);
        Assert.Contains("Line 2", textContent.Text);
    }

    [Fact]
    public async Task Provider_InjectsToolIntoContext()
    {
        if (_pythonPath == null)
        {
            return;
        }

        var provider = new LocalCodeActProvider(
            pythonExecutablePath: _pythonPath,
            executionLimits: new ProcessExecutionLimits(TimeoutSeconds: 5)
        );

        var options = new ChatOptions();
        await provider.ProvideContextAsync(null!, options, CancellationToken.None);

        Assert.NotNull(options.Tools);
        Assert.Single(options.Tools);
        Assert.Equal("execute_code", options.Tools[0].Metadata.Name);
    }
}
