// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics.CodeAnalysis;
using Microsoft.Extensions.AI;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI;

/// <summary>
/// Contains extension methods to allow storing and retrieving properties using the type name of the property as the key.
/// </summary>
public static class AdditionalPropertiesExtensions
{
    /// <summary>
    /// Adds an additional property using the type name of the property as the key.
    /// </summary>
    /// <typeparam name="T">The type of the property to add.</typeparam>
    /// <param name="additionalProperties">The dictionary of additional properties.</param>
    /// <param name="value">The value to add.</param>
    public static void Add<T>(this AdditionalPropertiesDictionary additionalProperties, T value)
    {
        _ = Throw.IfNull(additionalProperties);

        additionalProperties.Add(typeof(T).FullName!, value);
    }

    /// <summary>
    /// Attempts to add a property using the type name of the property as the key.
    /// </summary>
    /// <remarks>
    /// This method uses the full name of the type parameter as the key. If the key already exists,
    /// the value is not updated and the method returns <see langword="false"/>.
    /// </remarks>
    /// <typeparam name="T">The type of the property to add.</typeparam>
    /// <param name="additionalProperties">The dictionary of additional properties.</param>
    /// <param name="value">The value to add.</param>
    /// <returns>
    /// <see langword="true"/> if the value was added successfully; <see langword="false"/> if the key already exists.
    /// </returns>
    public static bool TryAdd<T>(this AdditionalPropertiesDictionary additionalProperties, T value)
    {
        _ = Throw.IfNull(additionalProperties);

        return additionalProperties.TryAdd(typeof(T).FullName!, value);
    }

    /// <summary>
    /// Attempts to retrieve a value from the additional properties dictionary using the type name of the property as the key.
    /// </summary>
    /// <remarks>
    /// This method uses the full name of the type parameter as the key when searching the dictionary.
    /// </remarks>
    /// <typeparam name="T">The type of the property to be retrieved.</typeparam>
    /// <param name="additionalProperties">The dictionary containing additional properties.</param>
    /// <param name="value">
    /// When this method returns, contains the value retrieved from the dictionary, if found and successfully converted to the requested type;
    /// otherwise, the default value of <typeparamref name="T"/>.
    /// </param>
    /// <returns>
    /// <see langword="true"/> if a non-<see langword="null"/> value was found
    /// in the dictionary and converted to the requested type; otherwise, <see langword="false"/>.
    /// </returns>
    public static bool TryGetValue<T>(this AdditionalPropertiesDictionary additionalProperties, [NotNullWhen(true)] out T? value)
    {
        _ = Throw.IfNull(additionalProperties);

        return additionalProperties.TryGetValue(typeof(T).FullName!, out value);
    }

    /// <summary>
    /// Determines whether the additional properties dictionary contains a property with the name of the provided type as the key.
    /// </summary>
    /// <typeparam name="T">The type of the property to check for.</typeparam>
    /// <param name="additionalProperties">The dictionary of additional properties.</param>
    /// <returns>
    /// <see langword="true"/> if the dictionary contains a property with the name of the provided type as the key; otherwise, <see langword="false"/>.
    /// </returns>
    public static bool Contains<T>(this AdditionalPropertiesDictionary additionalProperties)
    {
        _ = Throw.IfNull(additionalProperties);

        return additionalProperties.ContainsKey(typeof(T).FullName!);
    }

    /// <summary>
    /// Removes a property from the additional properties dictionary using the name of the provided type as the key.
    /// </summary>
    /// <typeparam name="T">The type of the property to remove.</typeparam>
    /// <param name="additionalProperties">The dictionary of additional properties.</param>
    /// <returns>
    /// <see langword="true"/> if the property was successfully removed; otherwise, <see langword="false"/>.
    /// </returns>
    public static bool Remove<T>(this AdditionalPropertiesDictionary additionalProperties)
    {
        _ = Throw.IfNull(additionalProperties);

        return additionalProperties.Remove(typeof(T).FullName!);
    }
}
