// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics;
using Microsoft.Extensions.Configuration;

namespace GettingStarted.TestRunner;

/// <summary>
/// Manages configuration validation and user secrets setup without UI concerns.
/// </summary>
public class ConfigurationManager
{
    private IConfiguration _configuration;

    public ConfigurationManager(IConfiguration configuration)
    {
        this._configuration = configuration;
    }

    /// <summary>
    /// Validates that all required configuration is present.
    /// </summary>
    public ConfigurationValidationResult ValidateConfiguration()
    {
        var missingConfigs = new List<string>();
        var missingConfigInfos = new List<ConfigurationMissingInfoResult>();
        var allConfigKeys = ConfigurationKeyExtractor.GetConfigurationKeys();

        // Check all required configuration keys dynamically
        foreach (var key in allConfigKeys)
        {
            if (ConfigurationKeyExtractor.IsRequiredKey(key) && string.IsNullOrEmpty(this._configuration[key]))
            {
                missingConfigs.Add(key);
                missingConfigInfos.Add(new ConfigurationMissingInfoResult
                {
                    Key = key,
                    FriendlyName = ConfigurationKeyExtractor.GetFriendlyDescription(key),
                    IsRequired = true,
                    IsSecret = ConfigurationKeyExtractor.IsSecretKey(key)
                });
            }
        }

        return new ConfigurationValidationResult
        {
            IsValid = missingConfigs.Count == 0,
            MissingKeys = missingConfigs,
            MissingConfigurations = missingConfigInfos
        };
    }

    /// <summary>
    /// Sets up configuration values from a dictionary.
    /// </summary>
    public async Task<ConfigurationUpdateResult> SetupConfigurationAsync(Dictionary<string, string> configValues)
    {
        var result = new ConfigurationUpdateResult { Success = true };

        // Save to user secrets
        foreach (var kvp in configValues)
        {
            var success = await this.SetUserSecretAsync(kvp.Key, kvp.Value);
            if (!success)
            {
                result.Success = false;
                result.FailedKeys.Add(kvp.Key);
            }
        }

        if (result.Success)
        {
            this.RefreshConfiguration();
        }

        return result;
    }

    /// <summary>
    /// Gets all configuration keys with their current status.
    /// </summary>
    public List<ConfigurationKeyInfo> GetAllConfigurationKeys()
    {
        var allConfigKeys = ConfigurationKeyExtractor.GetConfigurationKeys();
        var result = new List<ConfigurationKeyInfo>();

        foreach (var key in allConfigKeys)
        {
            var hasValue = this.HasCurrentConfigurationValue(key);
            var isRequired = ConfigurationKeyExtractor.IsRequiredKey(key);
            var currentValue = this.GetCurrentConfigurationValue(key);

            result.Add(new ConfigurationKeyInfo
            {
                Key = key,
                HasValue = hasValue,
                IsRequired = isRequired,
                CurrentValue = currentValue,
                FriendlyName = ConfigurationKeyExtractor.GetFriendlyDescription(key),
                IsSecret = ConfigurationKeyExtractor.IsSecretKey(key)
            });
        }

        return result;
    }

    /// <summary>
    /// Gets configuration metadata for a specific key, including display information.
    /// </summary>
    public ConfigurationKeyInfo GetConfigurationKeyInfo(string key)
    {
        var hasValue = this.HasCurrentConfigurationValue(key);
        var isRequired = ConfigurationKeyExtractor.IsRequiredKey(key);
        var isSecret = ConfigurationKeyExtractor.IsSecretKey(key);
        var currentValue = this.GetCurrentConfigurationValue(key);

        return new ConfigurationKeyInfo
        {
            Key = key,
            HasValue = hasValue,
            IsRequired = isRequired,
            IsSecret = isSecret,
            CurrentValue = currentValue,
            FriendlyName = ConfigurationKeyExtractor.GetFriendlyDescription(key)
        };
    }

    /// <summary>
    /// Updates a single configuration value.
    /// </summary>
    public async Task<bool> UpdateConfigurationValueAsync(string configKey, string value)
    {
        var success = await this.SetUserSecretAsync(configKey, value);
        if (success)
        {
            this.RefreshConfiguration();
        }
        return success;
    }

    /// <summary>
    /// Removes a configuration value.
    /// </summary>
    public async Task<bool> RemoveConfigurationValueAsync(string configKey)
    {
        var success = await this.RemoveUserSecretAsync(configKey);
        if (success)
        {
            this.RefreshConfiguration();
        }
        return success;
    }

    /// <summary>
    /// Sets a user secret using dotnet CLI.
    /// </summary>
    private async Task<bool> SetUserSecretAsync(string key, string value)
    {
        try
        {
            var startInfo = new ProcessStartInfo
            {
                FileName = "dotnet",
                Arguments = $"user-secrets set \"{key}\" \"{value}\"",
                UseShellExecute = false,
                RedirectStandardOutput = true,
                RedirectStandardError = true,
                CreateNoWindow = true
            };

            using var process = Process.Start(startInfo);
            if (process == null)
            {
                return false;
            }

#if !NET8_0_OR_GREATER
            process.WaitForExit();
#else
            await process.WaitForExitAsync();
#endif

            return process.ExitCode == 0;
        }
        catch (Exception)
        {
            return false;
        }
    }

    /// <summary>
    /// Removes a user secret using dotnet CLI.
    /// </summary>
    private async Task<bool> RemoveUserSecretAsync(string key)
    {
        try
        {
            var startInfo = new ProcessStartInfo
            {
                FileName = "dotnet",
                Arguments = $"user-secrets remove \"{key}\"",
                UseShellExecute = false,
                RedirectStandardOutput = true,
                RedirectStandardError = true,
                CreateNoWindow = true
            };

            using var process = Process.Start(startInfo);
            if (process == null)
            {
                return false;
            }

#if !NET8_0_OR_GREATER
            process.WaitForExit();
#else
            await process.WaitForExitAsync();
#endif

            return process.ExitCode == 0;
        }
        catch (Exception)
        {
            return false;
        }
    }

    /// <summary>
    /// Refreshes the configuration to pick up any changes made through user secrets.
    /// </summary>
    private void RefreshConfiguration()
    {
        // Rebuild the configuration to pick up changes from user secrets
        var builder = new ConfigurationBuilder()
            .AddUserSecrets(typeof(Program).Assembly)
            .AddEnvironmentVariables();

        this._configuration = builder.Build();
    }

    /// <summary>
    /// Gets the current configuration value for display, with secrets masked.
    /// Always reads the latest configuration without caching.
    /// </summary>
    public string GetCurrentConfigurationValue(string key)
    {
        // Always refresh configuration to get the latest values
        this.RefreshConfiguration();

        var value = this._configuration[key];

        if (string.IsNullOrEmpty(value))
        {
            return NavigationConstants.ConfigurationMessages.NotSet;
        }

        // Only mask actual secrets (API keys), show other values as-is
        if (ConfigurationKeyExtractor.IsSecretKey(key))
        {
            var masked = MaskSecret(value);
            return masked ?? NavigationConstants.ConfigurationMessages.NotSet;
        }

        return value ?? NavigationConstants.ConfigurationMessages.NotSet;
    }

    /// <summary>
    /// Checks if a configuration key has a value.
    /// Always reads the latest configuration without caching.
    /// </summary>
    public bool HasCurrentConfigurationValue(string key)
    {
        // Always refresh configuration to get the latest values
        this.RefreshConfiguration();

        return !string.IsNullOrEmpty(this._configuration[key]);
    }

    /// <summary>
    /// Masks a secret value for display.
    /// </summary>
    private static string? MaskSecret(string? secret)
    {
        if (string.IsNullOrEmpty(secret))
        {
            return null;
        }

        if (secret.Length <= 8)
        {
            return "***";
        }

#if NET8_0_OR_GREATER
        return string.Concat(secret.AsSpan(0, 4), "***", secret.AsSpan(secret.Length - 4));
#else
        return secret.Substring(0, 4) + "***" + secret.Substring(secret.Length - 4);
#endif
    }
}
