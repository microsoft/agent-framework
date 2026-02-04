// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Diagnostics;
using System.Text.Json;
using System.Text.Json.Serialization;
using Microsoft.Extensions.AI;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI;

/// <summary>Represents a response format for structured JSON data.</summary>
[DebuggerDisplay("{DebuggerDisplay,nq}")]
public sealed class NewChatResponseFormatJson : NewChatResponseFormat
{
    /// <summary>Initializes a new instance of the <see cref="NewChatResponseFormatJson"/> class with the specified schema.</summary>
    /// <param name="schema">The schema to associate with the JSON response.</param>
    /// <param name="schemaName">A name for the schema.</param>
    /// <param name="schemaDescription">A description of the schema.</param>
    [JsonConstructor]
    public NewChatResponseFormatJson(
        JsonElement? schema, string? schemaName = null, string? schemaDescription = null)
    {
        if (schema is null && (schemaName is not null || schemaDescription is not null))
        {
            Throw.ArgumentException(
                schemaName is not null ? nameof(schemaName) : nameof(schemaDescription),
                "Schema name and description can only be specified if a schema is provided.");
        }

        this.Schema = schema;
        this.SchemaName = schemaName;
        this.SchemaDescription = schemaDescription;
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="NewChatResponseFormatJson"/> class with a schema derived from the specified type.
    /// </summary>
    /// <param name="schemaType">The <see cref="Type"/> from which the schema was derived.</param>
    /// <param name="schema">The JSON schema to associate with the JSON response.</param>
    /// <param name="schemaName">An optional name for the schema.</param>
    /// <param name="schemaDescription">An optional description of the schema.</param>
    /// <param name="serializerOptions">The JSON serializer options to use for deserialization.</param>
    public NewChatResponseFormatJson(
        Type schemaType, JsonElement schema, string? schemaName = null, string? schemaDescription = null, JsonSerializerOptions? serializerOptions = null)
    {
        this.SchemaType = schemaType;
        this.Schema = schema;
        this.SchemaName = schemaName;
        this.SchemaDescription = schemaDescription;
        this.SchemaSerializerOptions = serializerOptions;
    }

    /// <summary>
    /// Gets the <see cref="Type"/> from which the JSON schema was derived, or <see langword="null"/> if the schema was not derived from a type.
    /// </summary>
    [JsonIgnore]
    public Type? SchemaType { get; }

    /// <summary>Gets the JSON schema associated with the response, or <see langword="null"/> if there is none.</summary>
    public JsonElement? Schema { get; }

    /// <summary>Gets a name for the schema.</summary>
    public string? SchemaName { get; }

    /// <summary>Gets a description of the schema.</summary>
    public string? SchemaDescription { get; }

    /// <summary>
    /// Gets the JSON serializer options to use when deserializing responses that conform to this schema, or <see langword="null"/> if default options should be used.
    /// </summary>
    [JsonIgnore]
    public JsonSerializerOptions? SchemaSerializerOptions { get; }

    /// <summary>Gets a string representing this instance to display in the debugger.</summary>
    [DebuggerBrowsable(DebuggerBrowsableState.Never)]
    private string DebuggerDisplay => this.Schema?.ToString() ?? "JSON";

    /// <summary>
    /// Implicitly converts a <see cref="NewChatResponseFormatJson"/> to a <see cref="ChatResponseFormatJson"/>.
    /// </summary>
    /// <param name="format">The <see cref="NewChatResponseFormatJson"/> instance to convert.</param>
    public static implicit operator ChatResponseFormatJson(NewChatResponseFormatJson format)
    {
        return new ChatResponseFormatJson(format.Schema, format.SchemaName, format.SchemaDescription);
    }
}
