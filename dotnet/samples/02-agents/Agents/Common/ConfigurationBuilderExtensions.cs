// Copyright (c) Microsoft. All rights reserved.

namespace Common;

public static class ConfigurationBuilderExtensions
{
    public static IConfiguration AddAppSettings(this IConfigurationBuilder builder)
    {
        var environment = Environment.GetEnvironmentVariable("DOTNET_ENVIRONMENT")
            ?? Environment.GetEnvironmentVariable("ASPNETCORE_ENVIRONMENT")
            ?? "Production";

        return builder
            .SetBasePath(AppContext.BaseDirectory)
            .AddJsonFile("appsettings.json", optional: false, reloadOnChange: true)
            .AddJsonFile($"appsettings.{environment}.json", optional: true, reloadOnChange: true)
            .AddEnvironmentVariables()
            .Build();
    }
}
