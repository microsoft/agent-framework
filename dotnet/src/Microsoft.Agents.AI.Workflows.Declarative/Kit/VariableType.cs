// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections;
using System.Collections.Frozen;
using System.Collections.Generic;
using System.Linq;
using Microsoft.Agents.AI.Workflows.Declarative.Extensions;
using Microsoft.Bot.ObjectModel;

namespace Microsoft.Agents.AI.Workflows.Declarative.Kit;

/// <summary>
/// Describes an allowed declarative variable/type used in workflow configuration (primitives, lists, or record-like objects).
/// A record is modeled as IDictionary&lt;string, VariableType?&gt; along with an immutable schema for its fields.
/// </summary>
public sealed class VariableType : IEquatable<VariableType>
{
    // Canonical CLR type used to mark a "record" (object with named fields and per-field types).
    internal static readonly Type RecordType = typeof(IDictionary<string, object?>);

    // Any list of primitive values or records.
    internal static readonly Type ListType = typeof(IEnumerable);

    // All supported root CLR types (only these may appear directly as VariableType.Type).
    private static readonly FrozenSet<Type> s_supportedTypes =
        [
            typeof(bool),
            typeof(int),
            typeof(long),
            typeof(float),
            typeof(decimal),
            typeof(double),
            typeof(string),
            typeof(DateTime),
            typeof(TimeSpan),
            RecordType,
            ListType,
        ];

    /// <summary>
    /// Implicitly wraps a CLR <paramref name="type"/> as a <see cref="VariableType"/> (no validation is performed here).
    /// Use <see cref="IsValid()"/> or <see cref="IsValid(Type)"/> to confirm support.
    /// </summary>
    public static implicit operator VariableType(Type type) => new(type);

    /// <summary>
    /// Returns true if <typeparamref name="TValue"/> is a supported variable type.
    /// </summary>
    public static bool IsValid<TValue>() => IsValid(typeof(TValue));

    /// <summary>
    /// Returns true if the provided CLR <paramref name="type"/> is one of the supported root types.
    /// </summary>
    public static bool IsValid(Type type) =>
        s_supportedTypes.Contains(type) ||
        ListType.IsAssignableFrom(type) ||
        RecordType.IsAssignableFrom(type);

    /// <summary>
    /// Creates a list (object) variable type with the supplied <paramref name="fields"/> schema.
    /// Each tuple's Key is the field name; Type is the declared VariableType (nullable to allow "unknown"/late binding).
    /// </summary>
    public static VariableType List(params IEnumerable<(string Key, VariableType Type)> fields) =>
        new(typeof(IEnumerable))
        {
            Schema = fields.ToFrozenDictionary(kv => kv.Key, kv => kv.Type),
        };

    /// <summary>
    /// Creates a record (object) variable type with the supplied <paramref name="fields"/> schema.
    /// Each tuple's Key is the field name; Type is the declared VariableType (nullable to allow "unknown"/late binding).
    /// </summary>
    public static VariableType Record(params IEnumerable<(string Key, VariableType Type)> fields) =>
        new(typeof(IDictionary<string, object?>))
        {
            Schema = fields.ToFrozenDictionary(kv => kv.Key, kv => kv.Type),
        };

    /// <summary>
    /// Initializes a new instance wrapping the given CLR <paramref name="type"/> (which should be one of the supported types).
    /// </summary>
    internal VariableType(DataType type)
    {
        this.Type = type.ToClrType();

        if (type is RecordDataType recordType)
        {
            this.Schema = CreateSchema(recordType.Properties);
        }
        else if (type is TableDataType tableDataType)
        {
            this.Schema = CreateSchema(tableDataType.Properties);
        }

        static FrozenDictionary<string, VariableType> CreateSchema(IEnumerable<KeyValuePair<string, PropertyInfo>> properties)
        {
            Dictionary<string, VariableType> schema = [];

            foreach (KeyValuePair<string, PropertyInfo> field in properties)
            {
                if (field.Value.Type is null)
                {
                    continue;
                }

                schema[field.Key] = new VariableType(field.Value.Type);
            }
            return schema.ToFrozenDictionary();
        }
    }

    /// <summary>
    /// Initializes a new instance wrapping the given CLR <paramref name="type"/> (which should be one of the supported types).
    /// </summary>
    public VariableType(Type type)
    {
        this.Type = type;
    }

    /// <summary>
    /// The underlying CLR type that categorizes this variable (primitive, list, or record type).
    /// </summary>
    public Type Type { get; }

    /// <summary>
    /// Schema for record types: immutable mapping of field name to field VariableType (null means unspecified).
    /// Null for non-record VariableTypes.
    /// </summary>
    public FrozenDictionary<string, VariableType>? Schema { get; init; }

    /// <summary>
    /// True if this instance represents a record/object with a field schema.
    /// </summary>
    public bool HasSchema => (this.Schema?.Count ?? 0) > 0;

    /// <summary>
    /// True if this instance represents a list
    /// </summary>
    public bool IsList => !this.IsRecord && ListType.IsAssignableFrom(this.Type);

    /// <summary>
    /// True if this instance represents a record/object
    /// </summary>
    public bool IsRecord => RecordType.IsAssignableFrom(this.Type);

    /// <summary>
    /// Instance convenience wrapper for <see cref="IsValid(Type)"/> on this VariableType's underlying CLR type.
    /// </summary>
    public bool IsValid() => IsValid(this.Type);

    /// <inheritdoc/>
    public override bool Equals(object? obj) =>
        obj switch
        {
            null => false,
            Type type => this.Type == type,
            VariableType other => this.Equals(other),
            _ => false,
        };

    /// <inheritdoc/>
    public override int GetHashCode() => HashCode.Combine(this.Type.GetHashCode(), this.Schema?.GetHashCode() ?? 0);

    /// <inheritdoc/>
    public bool Equals(VariableType? other) =>
        other is not null &&
        this.Type == other.Type &&
        this.Schema switch
        {
            null => other.Schema is null,
            _ when other.Schema is null => false,
            _ => this.Schema.Count == other.Schema.Count && this.Schema.Union(other.Schema).Count() == this.Schema.Count,
        };
}
