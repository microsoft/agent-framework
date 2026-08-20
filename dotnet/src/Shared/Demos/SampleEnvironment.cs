// Copyright (c) Microsoft. All rights reserved.

#pragma warning disable IDE0005 // Using directive is unnecessary. - need to suppress this, since this file is used in both projects with implicit usings and without.

using System;
using System.Collections;
using System.IO;
using SystemEnvironment = System.Environment;

namespace SampleHelpers;

internal static class SampleEnvironment
{
    public static string? GetEnvironmentVariable(string key)
        => GetEnvironmentVariable(key, EnvironmentVariableTarget.Process);

    // Returns true when the process cannot safely prompt for console input. This is the case for
    // hosted-agent containers, CI runs, and any invocation with redirected/piped stdin. Callers must
    // never block on Console.ReadLine in these environments: a hosted agent that blocks on startup
    // never serves its /readiness endpoint and is reported as never becoming ready. Deployments can
    // also force this behavior explicitly by setting AF_DEMO_NONINTERACTIVE (useful when a host
    // allocates a pseudo-terminal so stdin is not detected as redirected).
    private static bool IsNonInteractive(EnvironmentVariableTarget target)
    {
        var forced = SystemEnvironment.GetEnvironmentVariable("AF_DEMO_NONINTERACTIVE", target);
        if (!string.IsNullOrEmpty(forced) &&
            forced?.ToUpperInvariant() is "1" or "Y" or "YES" or "TRUE")
        {
            return true;
        }

        try
        {
            return Console.IsInputRedirected;
        }
        catch (IOException)
        {
            // No console is attached at all (for example, some container hosts): treat as non-interactive.
            return true;
        }
    }

    public static string? GetEnvironmentVariable(string key, EnvironmentVariableTarget target)
    {
        // Allows for opting into showing all setting values in the console output, so that it is easy to troubleshoot sample setup issues.
        var showAllSampleValues = SystemEnvironment.GetEnvironmentVariable("AF_SHOW_ALL_DEMO_SETTING_VALUES", target);
        var shouldShowValue = showAllSampleValues?.ToUpperInvariant() == "Y";

        var value = SystemEnvironment.GetEnvironmentVariable(key, target);
        if (string.IsNullOrWhiteSpace(value))
        {
            // In non-interactive environments (a hosted-agent container, CI, or piped/redirected
            // stdin) there is no console to prompt at, and Console.ReadLine can block indefinitely
            // waiting for input that never arrives. For a hosted agent that means the app never
            // finishes starting and its /readiness endpoint never returns 200. Skip the interactive
            // prompt in that case and fall back to the default (null) instead of blocking.
            if (IsNonInteractive(target))
            {
                return value;
            }

            var color = Console.ForegroundColor;
            Console.ForegroundColor = ConsoleColor.Green;
            Console.Write("Setting '");
            Console.ForegroundColor = ConsoleColor.Yellow;
            Console.Write(key);
            Console.ForegroundColor = ConsoleColor.Green;
            Console.WriteLine("' is not set in environment variables.");

            Console.ForegroundColor = ConsoleColor.Green;
            Console.Write("Please provide the setting for '");
            Console.ForegroundColor = ConsoleColor.Yellow;
            Console.Write(key);
            Console.ForegroundColor = ConsoleColor.Green;
            Console.Write("'. Just press enter to accept the default. > ");
            Console.ForegroundColor = color;
            value = Console.ReadLine();
            value = string.IsNullOrWhiteSpace(value) ? null : value.Trim();

            Console.WriteLine();
        }
        else if (shouldShowValue)
        {
            var color = Console.ForegroundColor;
            Console.ForegroundColor = ConsoleColor.Green;
            Console.Write("Using setting: Source=");
            Console.ForegroundColor = ConsoleColor.Yellow;
            Console.Write("EnvironmentVariables");
            Console.ForegroundColor = ConsoleColor.Green;
            Console.Write(", Key='");
            Console.ForegroundColor = ConsoleColor.Yellow;
            Console.Write(key);
            Console.ForegroundColor = ConsoleColor.Green;
            Console.Write("', Value='");
            Console.ForegroundColor = ConsoleColor.Yellow;
            Console.Write(value);
            Console.ForegroundColor = ConsoleColor.Green;
            Console.WriteLine("'");
            Console.ForegroundColor = color;

            Console.WriteLine();
        }

        return value;
    }

    // Methods that directly call System.Environment

    public static IDictionary GetEnvironmentVariables()
        => SystemEnvironment.GetEnvironmentVariables();

    public static IDictionary GetEnvironmentVariables(EnvironmentVariableTarget target)
        => SystemEnvironment.GetEnvironmentVariables(target);

    public static void SetEnvironmentVariable(string variable, string? value)
        => SystemEnvironment.SetEnvironmentVariable(variable, value);

    public static void SetEnvironmentVariable(string variable, string? value, EnvironmentVariableTarget target)
        => SystemEnvironment.SetEnvironmentVariable(variable, value, target);

    public static string[] GetCommandLineArgs()
        => SystemEnvironment.GetCommandLineArgs();

    public static string CommandLine
        => SystemEnvironment.CommandLine;

    public static string CurrentDirectory
    {
        get => SystemEnvironment.CurrentDirectory;
        set => SystemEnvironment.CurrentDirectory = value;
    }

    public static string ExpandEnvironmentVariables(string name)
        => SystemEnvironment.ExpandEnvironmentVariables(name);

    public static string GetFolderPath(SystemEnvironment.SpecialFolder folder)
        => SystemEnvironment.GetFolderPath(folder);

    public static string GetFolderPath(SystemEnvironment.SpecialFolder folder, SystemEnvironment.SpecialFolderOption option)
        => SystemEnvironment.GetFolderPath(folder, option);

    public static int ProcessorCount
        => SystemEnvironment.ProcessorCount;

    public static bool Is64BitProcess
        => SystemEnvironment.Is64BitProcess;

    public static bool Is64BitOperatingSystem
        => SystemEnvironment.Is64BitOperatingSystem;

    public static string MachineName
        => SystemEnvironment.MachineName;

    public static string NewLine
        => SystemEnvironment.NewLine;

    public static OperatingSystem OSVersion
        => SystemEnvironment.OSVersion;

    public static string StackTrace
        => SystemEnvironment.StackTrace;

    public static int SystemPageSize
        => SystemEnvironment.SystemPageSize;

    public static bool HasShutdownStarted
        => SystemEnvironment.HasShutdownStarted;

#if NET
    public static int ProcessId
        => SystemEnvironment.ProcessId;

    public static string? ProcessPath
        => SystemEnvironment.ProcessPath;

    public static bool IsPrivilegedProcess
        => SystemEnvironment.IsPrivilegedProcess;
#endif
}
