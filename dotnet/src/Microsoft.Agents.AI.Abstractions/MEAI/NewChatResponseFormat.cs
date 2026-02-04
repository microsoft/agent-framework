// Copyright (c) Microsoft. All rights reserved.

using System;
using System.ComponentModel;
using System.Reflection;
using System.Text.Json;
using System.Text.Json.Serialization;
using System.Text.RegularExpressions;
using Microsoft.Extensions.AI;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI;

#pragma warning disable CA1052 // Static holder types should be Static or NotInheritable

/// <summary>Represents the response format that is desired by the caller.</summary>
[JsonPolymorphic(TypeDiscriminatorPropertyName = "$type")]
[JsonDerivedType(typeof(NewChatResponseFormatJson), typeDiscriminator: "json")]
public partial class NewChatResponseFormat
{
    private static readonly AIJsonSchemaCreateOptions s_inferenceOptions = new()
    {
        IncludeSchemaKeyword = true,
    };

    /// <summary>Initializes a new instance of the <see cref="ChatResponseFormat"/> class.</summary>
    /// <remarks>Prevents external instantiation. Close the inheritance hierarchy for now until we have good reason to open it.</remarks>
    private protected NewChatResponseFormat()
    {
    }

    /// <summary>Gets a singleton instance representing structured JSON data but without any particular schema.</summary>
    public static NewChatResponseFormatJson Json { get; } = new(schema: null);

    /// <summary>Creates a <see cref="NewChatResponseFormatJson"/> representing structured JSON data with the specified schema.</summary>
    /// <param name="schema">The JSON schema.</param>
    /// <param name="schemaName">An optional name of the schema. For example, if the schema represents a particular class, this could be the name of the class.</param>
    /// <param name="schemaDescription">An optional description of the schema.</param>
    /// <returns>The <see cref="NewChatResponseFormatJson"/> instance.</returns>
    public static NewChatResponseFormatJson ForJsonSchema(
        JsonElement schema, string? schemaName = null, string? schemaDescription = null) =>
        new(schema, schemaName, schemaDescription);

    /// <summary>Creates a <see cref="NewChatResponseFormatJson"/> representing structured JSON data with a schema based on <typeparamref name="T"/>.</summary>
    /// <typeparam name="T">The type for which a schema should be exported and used as the response schema.</typeparam>
    /// <param name="serializerOptions">The JSON serialization options to use.</param>
    /// <param name="schemaName">An optional name of the schema. By default, this will be inferred from <typeparamref name="T"/>.</param>
    /// <param name="schemaDescription">An optional description of the schema. By default, this will be inferred from <typeparamref name="T"/>.</param>
    /// <returns>The <see cref="NewChatResponseFormatJson"/> instance.</returns>
    /// <remarks>
    /// Many AI services that support structured output require that the JSON schema have a top-level 'type=object'.
    /// If <typeparamref name="T"/> is a primitive type like <see cref="string"/>, <see cref="int"/>, or <see cref="bool"/>,
    /// or if it's a type that serializes as a JSON array, attempting to use the resulting schema with such services may fail.
    /// In such cases, consider instead using a <typeparamref name="T"/> that wraps the actual type in a class or struct so that
    /// it serializes as a JSON object with the original type as a property of that object.
    /// </remarks>
    public static NewChatResponseFormatJson ForJsonSchema<T>(JsonSerializerOptions? serializerOptions = null, string? schemaName = null, string? schemaDescription = null) =>
        ForJsonSchema(typeof(T), serializerOptions, schemaName, schemaDescription);

    /// <summary>Creates a <see cref="NewChatResponseFormatJson"/> representing structured JSON data with a schema based on <paramref name="schemaType"/>.</summary>
    /// <param name="schemaType">The <see cref="Type"/> for which a schema should be exported and used as the response schema.</param>
    /// <param name="serializerOptions">The JSON serialization options to use.</param>
    /// <param name="schemaName">An optional name of the schema. By default, this will be inferred from <paramref name="schemaType"/>.</param>
    /// <param name="schemaDescription">An optional description of the schema. By default, this will be inferred from <paramref name="schemaType"/>.</param>
    /// <returns>The <see cref="NewChatResponseFormatJson"/> instance.</returns>
    /// <remarks>
    /// Many AI services that support structured output require that the JSON schema have a top-level 'type=object'.
    /// If <paramref name="schemaType"/> is a primitive type like <see cref="string"/>, <see cref="int"/>, or <see cref="bool"/>,
    /// or if it's a type that serializes as a JSON array, attempting to use the resulting schema with such services may fail.
    /// In such cases, consider instead using a <paramref name="schemaType"/> that wraps the actual type in a class or struct so that
    /// it serializes as a JSON object with the original type as a property of that object.
    /// </remarks>
    /// <exception cref="ArgumentNullException"><paramref name="schemaType"/> is <see langword="null"/>.</exception>
    public static NewChatResponseFormatJson ForJsonSchema(
        Type schemaType, JsonSerializerOptions? serializerOptions = null, string? schemaName = null, string? schemaDescription = null)
    {
        _ = Throw.IfNull(schemaType);

        var schema = AIJsonUtilities.CreateJsonSchema(
            schemaType,
            serializerOptions: serializerOptions ?? AIJsonUtilities.DefaultOptions,
            inferenceOptions: s_inferenceOptions);

        return new(
            schemaType,
            schema,
            schemaName ?? schemaType.GetCustomAttribute<DisplayNameAttribute>()?.DisplayName ?? InvalidNameCharsRegex().Replace(schemaType.Name, "_"),
            schemaDescription ?? schemaType.GetCustomAttribute<DescriptionAttribute>()?.Description,
            serializerOptions);
    }

    /// <summary>Regex that flags any character other than ASCII digits, ASCII letters, or underscore.</summary>
#if NET
    [GeneratedRegex("[^0-9A-Za-z_]")]
    private static partial Regex InvalidNameCharsRegex();
#else
    private static Regex InvalidNameCharsRegex() => s_invalidNameCharsRegex;
    private static readonly Regex s_invalidNameCharsRegex = new("[^0-9A-Za-z_]", RegexOptions.Compiled);
#endif
}
