// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Shared.Samples;
using Spectre.Console;

namespace GettingStarted.TestRunner;

/// <summary>
/// Interactive console application for running GettingStarted samples.
/// </summary>
public static class Program
{
    public static async Task<int> Main(string[] args)
    {
        try
        {
            // Initialize TestConfiguration using the existing pattern
            var configRoot = new ConfigurationBuilder()
                .AddJsonFile("appsettings.json", optional: true)
                .AddJsonFile("appsettings.Development.json", optional: true)
                .AddEnvironmentVariables()
                .AddUserSecrets<TestDiscoveryService>()
                .Build();

            TestConfiguration.Initialize(configRoot);

            // Build services manually
            var services = new ServiceCollection();
            services.AddSingleton<IConfiguration>(configRoot);
            services.AddSingleton<TestDiscoveryService>();
            services.AddSingleton<ConfigurationManager>();
            services.AddSingleton<TestExecutionService>();
            services.AddSingleton<InteractiveConsole>();

            var serviceProvider = services.BuildServiceProvider();
            var console = serviceProvider.GetRequiredService<InteractiveConsole>();

            // Check for command line arguments
            if (args.Length > 0 && args[0] == "--test" && args.Length > 1)
            {
                return await console.RunTestAsync(args[1]);
            }

            // Default to interactive mode
            return await console.RunInteractiveAsync();
        }
        catch (Exception ex)
        {
            AnsiConsole.WriteException(ex);
            return 1;
        }
    }
}
