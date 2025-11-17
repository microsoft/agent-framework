// Copyright (c) Microsoft. All rights reserved.

using System.Reflection;
using Microsoft.Extensions.Configuration;

namespace Shared.Workflows;

internal static class Application
{
    /// <summary>
    /// Configuration key used to identify the Foundry project endpoint.
    /// </summary>
    public static class Settings
    {
        public const string FoundryEndpoint = "FOUNDRY_PROJECT_ENDPOINT";
        public const string FoundryModelMini = "FOUNDRY_MODEL_DEPLOYMENT_NAME";
        public const string FoundryModelFull = "FOUNDRY_MEDIA_DEPLOYMENT_NAME";
        public const string FoundryGroundingTool = "FOUNDRY_CONNECTION_GROUNDING_TOOL";
    }

    public static string GetInput(string[] args)
    {
        string? input = args.FirstOrDefault();

        try
        {
            Console.ForegroundColor = ConsoleColor.DarkGreen;

            Console.Write("\nINPUT: ");

            Console.ForegroundColor = ConsoleColor.White;

            if (!string.IsNullOrWhiteSpace(input))
            {
                Console.WriteLine(input);
                return input;
            }
            while (string.IsNullOrWhiteSpace(input))
            {
                input = Console.ReadLine();
            }

            return input.Trim();
        }
        finally
        {
            Console.ResetColor();
        }
    }

    public static string? GetRepoFolder()
    {
        DirectoryInfo? current = new(Directory.GetCurrentDirectory());

        while (current is not null)
        {
            if (Directory.Exists(Path.Combine(current.FullName, ".git")))
            {
                return current.FullName;
            }

            current = current.Parent;
        }

        return null;
    }

    public static string GetValue(this IConfiguration configuration, string settingName) =>
        configuration[settingName] ??
        throw new InvalidOperationException($"Undefined configuration setting: {settingName}");

    /// <summary>
    /// Initialize configuration and environment
    /// </summary>
    public static IConfigurationRoot InitializeConfig() =>
        new ConfigurationBuilder()
            .AddUserSecrets(Assembly.GetExecutingAssembly())
            .AddEnvironmentVariables()
            .Build();
}
