// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace Microsoft.Agents.AI.Hosting.OpenAI.Responses.Converters;

/// <summary>
/// JSON converter for enums that uses snake_case naming convention.
/// </summary>
/// <typeparam name="T">The enum type to convert.</typeparam>
internal sealed class SnakeCaseEnumConverter<T> : JsonStringEnumConverter<T> where T : struct, Enum
{
    /// <summary>
    /// Creates a new instance of the <see cref="SnakeCaseEnumConverter{T}"/> class.
    /// </summary>
    public SnakeCaseEnumConverter() : base(JsonNamingPolicy.SnakeCaseLower)
    {
    }
}
