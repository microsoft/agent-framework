// Copyright (c) Microsoft. All rights reserved.

#pragma warning disable IDE0005 // Using directive is unnecessary. - need to suppress this, since this file is used in both projects with implicit usings and without.

using System;
using System.Collections.Generic;
using IDictionary = System.Collections.IDictionary;
using SystemEnvironment = System.Environment;

namespace SampleHelpers;

internal static class SampleEnvironment
{
    private static readonly HashSet<string> s_affirmativeValues = new(StringComparer.OrdinalIgnoreCase) { "TRUE", "Y", "YES" };

    public static string? GetEnvironmentVariable(string key)
        => GetEnvironmentVariable(key, EnvironmentVariableTarget.Process);

    public static string? GetEnvironmentVariable(string key, EnvironmentVariableTarget target)
    {
        // Allows for opting into showing all setting values in the console output, so that it is easy to troubleshoot sample setup issues.
        string? showAllSampleValues = SystemEnvironment.GetEnvironmentVariable("AF_SHOW_ALL_DEMO_SETTING_VALUES", target);
        bool shouldShowValue = s_affirmativeValues.Contains(showAllSampleValues ?? string.Empty);

        string? value = SystemEnvironment.GetEnvironmentVariable(key, target);
        ConsoleColor color = Console.ForegroundColor;
        try
        {
            if (string.IsNullOrWhiteSpace(value))
            {
                Console.ForegroundColor = ConsoleColor.Green;
                Console.Write("Setting '");
                Console.ForegroundColor = ConsoleColor.Yellow;
                Console.Write(key);
                Console.ForegroundColor = ConsoleColor.Green;
                Console.WriteLine("' is not defined as an environment variable.");

                Console.ForegroundColor = ConsoleColor.Green;
                Console.Write("Please provide the desired value for '");
                Console.ForegroundColor = ConsoleColor.Yellow;
                Console.Write(key);
                Console.ForegroundColor = ConsoleColor.Green;
                Console.Write("' or press enter to accept the default: ");
                Console.ForegroundColor = ConsoleColor.Yellow;

                value = Console.ReadLine();
                value = string.IsNullOrWhiteSpace(value) ? null : value.Trim();
            }
            else if (shouldShowValue)
            {
                Console.ForegroundColor = ConsoleColor.Green;
                Console.Write("Using setting '");
                Console.ForegroundColor = ConsoleColor.Yellow;
                Console.Write(key);
                Console.ForegroundColor = ConsoleColor.Green;
                Console.Write("' with value='");
                Console.ForegroundColor = ConsoleColor.Yellow;
                Console.Write(value);
                Console.ForegroundColor = ConsoleColor.Green;
                Console.WriteLine("'");
            }

            Console.WriteLine();
        }
        finally
        {
            Console.ForegroundColor = color;
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
