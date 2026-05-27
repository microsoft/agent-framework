// Copyright (c) Microsoft Corporation. All rights reserved.
// Licensed under the MIT License.

using Microsoft.Extensions.AI;
using Microsoft.Agents.AI.LocalCodeAct;

/// <summary>
/// This sample demonstrates using LocalCodeActProvider with a local agent.
/// 
/// Prerequisites:
/// - Python 3.10+ installed at /usr/bin/python3 (or adjust the path)
/// - This sample is intended for containerized or VM environments with proper isolation
/// 
/// WARNING: This executes LLM-generated Python code. Do NOT run on developer workstations
/// or production hosts without external sandboxing (containers, VMs, etc.).
/// </summary>
internal static class Program
{
    private static async Task Main()
    {
        Console.WriteLine("LocalCodeAct Sample");
        Console.WriteLine("===================");
        Console.WriteLine();
        Console.WriteLine("This sample shows LocalCodeActProvider usage.");
        Console.WriteLine("NOTE: Requires Python 3.10+ and external sandboxing for safety.");
        Console.WriteLine();

        // Example 1: Create a provider with default settings
        using var provider = new LocalCodeActProvider(
            pythonExecutablePath: "/usr/bin/python3",
            executionLimits: new ProcessExecutionLimits
            {
                TimeoutSeconds = 5,
            });

        Console.WriteLine("✓ Created LocalCodeActProvider");
        Console.WriteLine($"  State Keys: {string.Join(", ", provider.StateKeys)}");
        Console.WriteLine();

        // Example 2: Create an execute_code function directly
        using var function = new LocalExecuteCodeFunction(
            pythonExecutablePath: "/usr/bin/python3",
            executionLimits: new ProcessExecutionLimits
            {
                TimeoutSeconds = 10,
            });

        Console.WriteLine("✓ Created LocalExecuteCodeFunction");
        Console.WriteLine($"  Name: {function.Metadata.Name}");
        Console.WriteLine($"  Description: {function.Metadata.Description}");
        Console.WriteLine($"  Parameters: {function.Metadata.Parameters?.Count ?? 0}");
        Console.WriteLine();

        // Example 3: Show execution modes
        var mode = ExecutionMode.Subprocess;
        Console.WriteLine($"✓ Execution Mode: {mode}");
        Console.WriteLine("  (Subprocess is the only mode in .NET)");
        Console.WriteLine();

        // Example 4: Show file mount configuration
        var mount = new FileMount
        {
            HostPath = "/tmp/data",
            MountPath = "/input",
            Mode = FileMountMode.ReadWrite,
        };

        Console.WriteLine("✓ File Mount Configuration:");
        Console.WriteLine($"  Host Path: {mount.HostPath}");
        Console.WriteLine($"  Mount Path: {mount.MountPath}");
        Console.WriteLine($"  Mode: {mount.Mode}");
        Console.WriteLine();

        Console.WriteLine("Sample complete!");
        Console.WriteLine();
        Console.WriteLine("NOTE: Actual code execution requires:");
        Console.WriteLine("  1. A configured AI model/client");
        Console.WriteLine("  2. An agent with LocalCodeActProvider");
        Console.WriteLine("  3. External container/VM sandboxing for safety");
    }
}
