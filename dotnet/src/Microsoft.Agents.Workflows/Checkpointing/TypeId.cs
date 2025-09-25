// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Text.Json.Serialization;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.Workflows.Checkpointing;

/// <summary>
/// A representation of a type's identity, including its assembly and type names.
/// </summary>
public sealed class TypeId : IEquatable<TypeId>
{
    /// <inheritdoc cref="System.Reflection.Assembly.FullName"/>
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

        return this.AssemblyName == other.AssemblyName && this.TypeName == other.TypeName;
    }

    /// <inheritdoc />
    public override int GetHashCode() => HashCode.Combine(this.AssemblyName, this.TypeName);

    /// <inheritdoc />
    public static bool operator ==(TypeId? left, TypeId? right) => left is null ? right is null : left.Equals(right);

    /// <inheritdoc />
    public static bool operator !=(TypeId? left, TypeId? right) => !(left == right);

    /// <summary>
    /// Determines whether the specified type matches both the assembly name and type name represented by this instance.
    /// </summary>
    /// <param name="type">The type to compare against the stored assembly and type names. Cannot be null.</param>
    /// <returns>true if the specified type's assembly and type names are equal to those stored in this instance; otherwise,
    /// false.</returns>
    public bool IsMatch(Type type)
    {
        return this.AssemblyName == type.Assembly.FullName
            && this.TypeName == type.FullName;
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
}
