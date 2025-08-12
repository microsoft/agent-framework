// Copyright (c) Microsoft. All rights reserved.

using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using System.Reflection;
using Microsoft.Shared.Samples;

namespace GettingStarted.TestRunner;

/// <summary>
/// Extracts configuration keys from the TestConfiguration type using reflection.
/// </summary>
public static class ConfigurationKeyExtractor
{
    /// <summary>
    /// Gets all configuration keys from the TestConfiguration type.
    /// </summary>
    /// <returns>An array of configuration key strings in the format "Section:Property".</returns>
    public static string[] GetConfigurationKeys()
    {
        var keys = new List<string>();
        var testConfigType = typeof(TestConfiguration);

        // Get all static properties that return configuration sections
        var sectionProperties = testConfigType.GetProperties(BindingFlags.Public | BindingFlags.Static)
            .Where(p => p.PropertyType.IsClass && p.PropertyType != typeof(string))
            .ToArray();

        foreach (var sectionProperty in sectionProperties)
        {
            var sectionName = sectionProperty.Name;
            var sectionType = sectionProperty.PropertyType;

            // Get all properties from the configuration section
            var configProperties = sectionType.GetProperties(BindingFlags.Public | BindingFlags.Instance)
                .Where(p => p.CanRead && p.CanWrite)
                .ToArray();

            foreach (var configProperty in configProperties)
            {
                var configKey = $"{sectionName}:{configProperty.Name}";
                keys.Add(configKey);
            }
        }

        return keys.ToArray();
    }

    /// <summary>
    /// Gets configuration keys grouped by section.
    /// </summary>
    /// <returns>A dictionary where keys are section names and values are arrays of property names.</returns>
    public static Dictionary<string, string[]> GetConfigurationKeysBySection()
    {
        var result = new Dictionary<string, string[]>();
        var testConfigType = typeof(TestConfiguration);

        // Get all static properties that return configuration sections
        var sectionProperties = testConfigType.GetProperties(BindingFlags.Public | BindingFlags.Static)
            .Where(p => p.PropertyType.IsClass && p.PropertyType != typeof(string))
            .ToArray();

        foreach (var sectionProperty in sectionProperties)
        {
            var sectionName = sectionProperty.Name;
            var sectionType = sectionProperty.PropertyType;

            // Get all properties from the configuration section
            var configProperties = sectionType.GetProperties(BindingFlags.Public | BindingFlags.Instance)
                .Where(p => p.CanRead && p.CanWrite)
                .Select(p => p.Name)
                .ToArray();

            result[sectionName] = configProperties;
        }

        return result;
    }

    /// <summary>
    /// Checks if a configuration key represents a secret that should be masked.
    /// </summary>
    /// <param name="key">The configuration key to check.</param>
    /// <returns>True if the key represents a secret, false otherwise.</returns>
    public static bool IsSecretKey(string key)
    {
        var propertyInfo = GetPropertyInfoFromKey(key);
        return propertyInfo?.GetCustomAttribute<TestConfiguration.SensitiveAttribute>() != null;
    }

    /// <summary>
    /// Checks if a configuration key is required.
    /// </summary>
    /// <param name="key">The configuration key to check.</param>
    /// <returns>True if the key is required, false otherwise.</returns>
    public static bool IsRequiredKey(string key)
    {
        var propertyInfo = GetPropertyInfoFromKey(key);
        if (propertyInfo?.GetCustomAttribute<TestConfiguration.OptionalAttribute>() != null)
        {
            return false;
        }
        return propertyInfo?.GetCustomAttribute<RequiredAttribute>() != null;
    }

    /// <summary>
    /// Gets the friendly description for a configuration key from its Description attribute.
    /// </summary>
    /// <param name="key">The configuration key to get the description for.</param>
    /// <returns>The friendly description or a formatted version of the property name.</returns>
    public static string GetFriendlyDescription(string key)
    {
        var propertyInfo = GetPropertyInfoFromKey(key);
        var description = propertyInfo?.GetCustomAttribute<DescriptionAttribute>()?.Description;

        if (!string.IsNullOrEmpty(description))
        {
            return description!;
        }

        // Fallback: format the property name nicely
        var parts = key.Split(':');
        if (parts.Length == 2)
        {
            return $"{parts[0]} {FormatPropertyName(parts[1])}";
        }

        return key ?? string.Empty;
    }

    /// <summary>
    /// Gets the PropertyInfo for a configuration key.
    /// </summary>
    /// <param name="key">The configuration key in format "Section:Property".</param>
    /// <returns>The PropertyInfo if found, null otherwise.</returns>
    private static PropertyInfo? GetPropertyInfoFromKey(string key)
    {
        var parts = key.Split(':');
        if (parts.Length != 2)
        {
            return null;
        }

        var sectionName = parts[0];
        var propertyName = parts[1];

        var testConfigType = typeof(TestConfiguration);
        var sectionProperty = testConfigType.GetProperty(sectionName, BindingFlags.Public | BindingFlags.Static);

        if (sectionProperty == null)
        {
            return null;
        }

        var sectionType = sectionProperty.PropertyType;
        return sectionType.GetProperty(propertyName, BindingFlags.Public | BindingFlags.Instance);
    }

    /// <summary>
    /// Formats a property name by adding spaces before capital letters.
    /// </summary>
    /// <param name="propertyName">The property name to format.</param>
    /// <returns>The formatted property name.</returns>
    private static string FormatPropertyName(string propertyName)
    {
        if (string.IsNullOrEmpty(propertyName))
        {
            return propertyName ?? string.Empty;
        }

        var result = new System.Text.StringBuilder();
        result.Append(propertyName[0]);

        for (int i = 1; i < propertyName.Length; i++)
        {
            if (char.IsUpper(propertyName[i]))
            {
                result.Append(' ');
            }
            result.Append(propertyName[i]);
        }

        return result.ToString();
    }
}
