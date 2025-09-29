// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Frozen;
using System.Collections.Generic;

namespace Microsoft.Agents.AI.Workflows.Declarative.Kit;

/// <summary>
/// %%% COMMENT
/// </summary>
public sealed class VariableType
{
    private static readonly Type s_typeRecord = typeof(IDictionary<string, VariableType?>);

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
            s_typeRecord,
            typeof(IList<VariableType?>),
        ];

    /// <summary>
    /// %%% COMMENT
    /// </summary>
    /// <param name="type"></param>
    public static implicit operator VariableType(Type type) => new(type);

    /// <summary>
    /// %%% COMMENT
    /// </summary>
    /// <typeparam name="TValue"></typeparam>
    /// <returns></returns>
    public static bool IsValid<TValue>() => IsValid(typeof(TValue));

    /// <summary>
    /// %%% COMMENT
    /// </summary>
    /// <param name="type"></param>
    /// <returns></returns>
    public static bool IsValid(Type type) => s_supportedTypes.Contains(type);

    /// <summary>
    /// %%% COMMENT
    /// </summary>
    /// <param name="fields"></param>
    /// <returns></returns>
    public static VariableType Record(params IEnumerable<(string Key, VariableType? Type)> fields) =>
        new(typeof(IDictionary<string, VariableType?>))
        {
            Schema = fields.ToFrozenDictionary(kv => kv.Key, kv => kv.Type),
        };

    /// <summary>
    /// %%% COMMENT
    /// </summary>
    /// <param name="type"></param>
    public VariableType(Type type)
    {
        this.Type = type;
    }

    /// <summary>
    /// COMMENT
    /// </summary>
    public Type Type { get; }

    /// <summary>
    /// %%% COMMENT
    /// </summary>
    public FrozenDictionary<string, VariableType?>? Schema { get; init; }

    /// <summary>
    /// %%% COMMENT
    /// </summary>
    public bool IsRecord => this.Type == s_typeRecord;

    /// <summary>
    /// %%% COMMENT
    /// </summary>
    public bool IsValid() => IsValid(this.Type);
}
