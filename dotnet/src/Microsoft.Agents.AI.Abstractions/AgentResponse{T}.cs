// Copyright (c) Microsoft. All rights reserved.

using System;
#if NET
using System.Buffers;
#endif

#if NET
using System.Text;
#endif
using System.Text.Json;
using System.Text.Json.Serialization;
using System.Text.Json.Serialization.Metadata;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI;

/// <summary>
/// Represents the response of the specified type <typeparamref name="T"/> to an <see cref="AIAgent"/> run request.
/// </summary>
/// <typeparam name="T">The type of value expected from the agent.</typeparam>
public class AgentResponse<T> : AgentResponse
{
    /// <summary>
    /// Initializes a new instance of the <see cref="AgentResponse{T}"/> class.
    /// </summary>
    public AgentResponse()
    {
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="AgentResponse{T}"/> class.
    /// </summary>
    /// <param name="response">The <see cref="AgentResponse"/> from which to populate this <see cref="AgentResponse{T}"/>.</param>
    /// <param name="responseFormat">The JSON response format configuration used to deserialize the agent's response.</param>
    public AgentResponse(AgentResponse response, NewChatResponseFormatJson? responseFormat = null) : base(response)
    {
        this.ResponseFormat = responseFormat;
    }

    /// <summary>
    /// Gets the result value of the agent response as an instance of <typeparamref name="T"/>.
    /// </summary>
    [JsonIgnore]
    public virtual T Result
    {
        get
        {
            return (T)this.Deserialize(this.ResponseFormat?.SchemaType ?? typeof(T), this.ResponseFormat?.SchemaSerializerOptions ?? AgentAbstractionsJsonUtilities.DefaultOptions);
        }
    }

    private NewChatResponseFormatJson? ResponseFormat { get; }

    private object Deserialize(Type targetType, JsonSerializerOptions serializerOptions)
    {
        _ = Throw.IfNull(serializerOptions);

        var structuredOutput = this.GetResultCore(targetType, serializerOptions, out var failureReason);
        return failureReason switch
        {
            FailureReason.ResultDidNotContainJson => throw new InvalidOperationException("The response did not contain JSON to be deserialized."),
            FailureReason.DeserializationProducedNull => throw new InvalidOperationException("The deserialized response is null."),
            _ => structuredOutput!,
        };
    }

    private object? GetResultCore(Type targetType, JsonSerializerOptions serializerOptions, out FailureReason? failureReason)
    {
        var json = this.Text;
        if (string.IsNullOrEmpty(json))
        {
            failureReason = FailureReason.ResultDidNotContainJson;
            return default;
        }

        object? deserialized = DeserializeFirstTopLevelObject(json!, serializerOptions.GetTypeInfo(targetType));

        if (deserialized is null)
        {
            failureReason = FailureReason.DeserializationProducedNull;
            return default;
        }

        failureReason = default;
        return deserialized;
    }

    private static object? DeserializeFirstTopLevelObject(string json, JsonTypeInfo typeInfo)
    {
#if NET
        // We need to deserialize only the first top-level object as a workaround for a common LLM backend
        // issue. GPT 3.5 Turbo commonly returns multiple top-level objects after doing a function call.
        // See https://community.openai.com/t/2-json-objects-returned-when-using-function-calling-and-json-mode/574348
        var utf8ByteLength = Encoding.UTF8.GetByteCount(json);
        var buffer = ArrayPool<byte>.Shared.Rent(utf8ByteLength);
        try
        {
            var utf8SpanLength = Encoding.UTF8.GetBytes(json, 0, json.Length, buffer, 0);
            var reader = new Utf8JsonReader(new ReadOnlySpan<byte>(buffer, 0, utf8SpanLength), new() { AllowMultipleValues = true });
            return JsonSerializer.Deserialize(ref reader, typeInfo);
        }
        finally
        {
            ArrayPool<byte>.Shared.Return(buffer);
        }
#else
        return JsonSerializer.Deserialize(json, typeInfo);
#endif
    }

    private enum FailureReason
    {
        ResultDidNotContainJson,
        DeserializationProducedNull,
    }
}
