// Copyright (c) Microsoft. All rights reserved.

using System;
using System.IO;
using System.Reflection;
using System.Text.Json.Serialization;
using System.Text.RegularExpressions;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Workflows.Checkpointing;

/// <summary>
/// A representation of a type's identity, including its assembly and type names.
/// </summary>
public sealed class TypeId : IEquatable<TypeId>
{
    /// <inheritdoc cref="Assembly.FullName"/>
    public string AssemblyName { get; }

    /// <inheritdoc cref="Type.FullName"/>
    public string TypeName { get; }

    /// <summary>
    /// Initializes a new instance of the <see cref="TypeId"/> class.
    /// </summary>
    /// <param name="assemblyName"></param>
    /// <param name="typeName"></param>
    [JsonConstructor]
    public TypeId(string assemblyName, string typeName)
    {
        this.AssemblyName = Throw.IfNull(assemblyName);
        this.TypeName = Throw.IfNull(typeName);
    }

    /// <summary>
    /// Initializes a new instance of the TypeId class using the specified type.
    /// </summary>
    /// <param name="type">The type for which to create a unique identifier. Cannot be null.</param>
    public TypeId(Type type)
        : this(
              Throw.IfNullOrMemberNull(type.Assembly,
                                       type.Assembly.FullName),
              Throw.IfMemberNull(type,
                                 type.FullName))
    { }

    /// <inheritdoc />
    public override bool Equals(object? obj)
        => this.Equals(obj as TypeId);

    /// <inheritdoc />
    /// <remarks>
    /// Compares the type full name and the simple assembly name. Version, culture, and public key
    /// token are ignored both in <see cref="AssemblyName"/> and in any assembly-qualified generic
    /// arguments embedded in <see cref="TypeName"/>.
    /// </remarks>
    public bool Equals(TypeId? other)
    {
        if (other is null)
        {
            return false;
        }

        if (ReferenceEquals(this, other))
        {
            return true;
        }

        if (this.NormalizedTypeName != other.NormalizedTypeName)
        {
            return false;
        }

        if (string.Equals(this.AssemblyName, other.AssemblyName, StringComparison.Ordinal))
        {
            return true;
        }

        string? thisSimpleName = this.SimpleAssemblyName;
        string? otherSimpleName = other.SimpleAssemblyName;

        return thisSimpleName is not null
            && string.Equals(thisSimpleName, otherSimpleName, StringComparison.Ordinal);
    }

    /// <inheritdoc />
    /// <remarks>Hashes the normalized type name and the simple assembly name.</remarks>
    public override int GetHashCode()
        => HashCode.Combine(this.SimpleAssemblyName, this.NormalizedTypeName);

    /// <inheritdoc />
    public static bool operator ==(TypeId? left, TypeId? right) => left is null ? right is null : left.Equals(right);

    /// <inheritdoc />
    public static bool operator !=(TypeId? left, TypeId? right) => !(left == right);

    /// <summary>
    /// Determines whether the specified type matches both the assembly name and type name represented by this instance.
    /// </summary>
    /// <remarks>
    /// Compares the type full name and the simple assembly name. Version, culture, and public key
    /// token are ignored both in <see cref="AssemblyName"/> and in any assembly-qualified generic
    /// arguments embedded in <see cref="TypeName"/>.
    /// </remarks>
    /// <param name="type">The type to compare against the stored assembly and type names. Cannot be null.</param>
    /// <returns>true if the specified type's assembly simple name and normalized type full name are equal to those stored
    /// in this instance; otherwise, false.</returns>
    public bool IsMatch(Type type)
    {
        string? runtimeNormalizedTypeName = type.FullName is null ? null : NormalizeTypeName(type.FullName);
        if (this.NormalizedTypeName != runtimeNormalizedTypeName)
        {
            return false;
        }

        string? storedSimpleName = this.SimpleAssemblyName;
        string? runtimeSimpleName = type.Assembly.GetName().Name;

        return storedSimpleName is not null
            && string.Equals(storedSimpleName, runtimeSimpleName, StringComparison.Ordinal);
    }

    /// <summary>
    /// Determines whether the current instance matches the specified type parameter.
    /// </summary>
    /// <typeparam name="T">The type to compare against the current instance.</typeparam>
    /// <returns>true if the current instance matches the specified type; otherwise, false.</returns>
    public bool IsMatch<T>() => this.IsMatch(typeof(T));

    /// <summary>
    /// Determines whether the specified type or any of its base types match the criteria defined by this instance.
    /// </summary>
    /// <param name="type">The type to evaluate for a match, including its inheritance hierarchy.</param>
    /// <returns>true if the specified type or any of its base types satisfy the match criteria; otherwise, false.</returns>
    public bool IsMatchPolymorphic(Type type)
    {
        Type? candidateType = type;

        while (candidateType is not null)
        {
            if (this.IsMatch(candidateType))
            {
                return true;
            }

            candidateType = candidateType.BaseType;
        }

        return false;
    }

    /// <inheritdoc/>
    public override string ToString() => $"{this.TypeName}, {this.AssemblyName}";

    /// <summary>
    /// The simple assembly name parsed from <see cref="AssemblyName"/>, lazily computed and cached.
    /// </summary>
    internal string? SimpleAssemblyName
        => field ??= GetSimpleAssemblyName(this.AssemblyName);

    /// <summary>
    /// The type full name with embedded assembly-qualified generic arguments stripped of
    /// version, culture, and public key token. Lazily computed and cached.
    /// </summary>
    internal string NormalizedTypeName
        => field ??= NormalizeTypeName(this.TypeName);

    private static readonly Regex s_assemblyQualifierPattern = new(
        @", Version=[^,\]]+, Culture=[^,\]]+, PublicKeyToken=[^,\]]+",
        RegexOptions.Compiled | RegexOptions.CultureInvariant);

    /// <summary>
    /// Removes <c>, Version=...</c>, <c>, Culture=...</c>, and <c>, PublicKeyToken=...</c> triplets
    /// from <paramref name="typeName"/>. Returns the input unchanged when no triplet is present.
    /// </summary>
    internal static string NormalizeTypeName(string typeName)
    {
        if (typeName.IndexOf("Version=", StringComparison.Ordinal) < 0)
        {
            return typeName;
        }

        return s_assemblyQualifierPattern.Replace(typeName, string.Empty);
    }

    /// <summary>
    /// Returns the simple assembly name parsed from an <see cref="Assembly.FullName"/>-style string,
    /// or <see langword="null"/> when both parsing and the substring fallback fail.
    /// </summary>
    internal static string? GetSimpleAssemblyName(string assemblyFullName)
    {
        if (string.IsNullOrEmpty(assemblyFullName))
        {
            return null;
        }

        try
        {
            string? parsed = new AssemblyName(assemblyFullName).Name;
            if (!string.IsNullOrEmpty(parsed))
            {
                return parsed;
            }
        }
        catch (Exception ex) when (ex is FileLoadException or ArgumentException)
        {
            // Fall through to substring fallback.
        }

        int comma = assemblyFullName.IndexOf(',');
        string fallback = (comma < 0 ? assemblyFullName : assemblyFullName.Substring(0, comma)).Trim();
        return fallback.Length == 0 ? null : fallback;
    }
}
