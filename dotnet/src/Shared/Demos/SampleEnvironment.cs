// Copyright (c) Microsoft. All rights reserved.

#pragma warning disable IDE0005 // Using directive is unnecessary. - need to suppress this, since this file is used in both projects with implicit usings and without.

using System;
using System.Collections;
using SystemEnvironment = System.Environment;

namespace SampleHelpers;

internal static class SampleEnvironment
{
    public static string? GetEnvironmentVariable(string key)
        => SampleEnvironment.GetEnvironmentVariable(key, EnvironmentVariableTarget.Process);

    public static string? GetEnvironmentVariable(string key, EnvironmentVariableTarget target)
    {
        // Allows for opting into showing all setting values in the console output, so that it is easy to troubleshoot sample setup issues.
        var showAllSampleValues = SystemEnvironment.GetEnvironmentVariable("AF_SHOW_ALL_DEMO_SETTING_VALUES", target);
        var shouldShowValue = showAllSampleValues?.ToUpperInvariant() == "Y";

        var value = SystemEnvironment.GetEnvironmentVariable(key, target);
        if (string.IsNullOrWhiteSpace(value))
        {
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
        => System.Environment.GetEnvironmentVariables();

    public static IDictionary GetEnvironmentVariables(EnvironmentVariableTarget target)
        => System.Environment.GetEnvironmentVariables(target);

    public static void SetEnvironmentVariable(string variable, string? value)
        => System.Environment.SetEnvironmentVariable(variable, value);

    public static void SetEnvironmentVariable(string variable, string? value, EnvironmentVariableTarget target)
        => System.Environment.SetEnvironmentVariable(variable, value, target);

    public static string[] GetCommandLineArgs()
        => System.Environment.GetCommandLineArgs();

    public static string CommandLine
        => System.Environment.CommandLine;

    public static string CurrentDirectory
    {
        get => System.Environment.CurrentDirectory;
        set => System.Environment.CurrentDirectory = value;
    }

    public static string ExpandEnvironmentVariables(string name)
        => System.Environment.ExpandEnvironmentVariables(name);

    public static string GetFolderPath(System.Environment.SpecialFolder folder)
        => System.Environment.GetFolderPath(folder);

    public static string GetFolderPath(System.Environment.SpecialFolder folder, System.Environment.SpecialFolderOption option)
        => System.Environment.GetFolderPath(folder, option);

    public static int ProcessorCount
        => System.Environment.ProcessorCount;

    public static bool Is64BitProcess
        => System.Environment.Is64BitProcess;

    public static bool Is64BitOperatingSystem
        => System.Environment.Is64BitOperatingSystem;

    public static string MachineName
        => System.Environment.MachineName;

    public static string NewLine
        => System.Environment.NewLine;

    public static OperatingSystem OSVersion
        => System.Environment.OSVersion;

    public static string StackTrace
        => System.Environment.StackTrace;

    public static int SystemPageSize
        => System.Environment.SystemPageSize;

    public static bool HasShutdownStarted
        => System.Environment.HasShutdownStarted;

#if NET9_0_OR_GREATER
    public static int ProcessId
        => System.Environment.ProcessId;

    public static string? ProcessPath
        => System.Environment.ProcessPath;

    public static bool IsPrivilegedProcess
        => System.Environment.IsPrivilegedProcess;
#endif
}
