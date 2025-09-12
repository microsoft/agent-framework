// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Diagnostics.CodeAnalysis;
using System.Runtime.CompilerServices;
using System.Text.Json;
using System.Text.Json.Serialization;
using System.Text.Json.Serialization.Metadata;
using System.Text.RegularExpressions;
using Microsoft.Agents.Workflows.Execution;

namespace Microsoft.Agents.Workflows.Checkpointing;

internal sealed class JsonWireSerializedValue(JsonMarshaller serializer, JsonElement data) : IDelayedDeserialization
{
    internal JsonElement Data => data;

    public TValue Deserialize<TValue>() => serializer.Marshal<TValue>(data);

    public object? Deserialize(Type targetType) => serializer.Marshal(targetType, data);

    public override bool Equals(object? obj)
    {
        if (obj == null)
        {
            return false;
        }

        if (obj is JsonWireSerializedValue otherValue)
        {
            return this.Data.Equals(otherValue.Data);
        }
        else if (obj is JsonElement element)
        {
            return this.Data.Equals(element);
        }
        else if (obj is not IDelayedDeserialization)
        {
            // Assume this has the target type of deserialization; serialize it using the explicit type
            // and compare.
            try
            {
                JsonElement otherElement = serializer.Marshal(obj, obj.GetType());

                // Unfortunately, JsonElement does not direclty compare to JsonElement
                // So turn them to strings and compare that
                return this.Data.ToString() == otherElement.ToString();
            }
            catch
            {
                return false;
            }
        }

        return false;
    }

    public override int GetHashCode()
    {
        return this.Data.GetHashCode();
    }
}

internal abstract class JsonConverterBase<T> : JsonConverter<T>
{
    protected abstract JsonTypeInfo<T> TypeInfo { get; }

    public override T? Read(ref Utf8JsonReader reader, Type typeToConvert, JsonSerializerOptions options)
    {
        SequencePosition position = reader.Position;

        T? maybeValue = JsonSerializer.Deserialize<T>(ref reader, this.TypeInfo);
        if (maybeValue is null)
        {
            throw new JsonException($"Could not deserialize a {typeof(T).Name} from JSON at position {position}");
        }

        return maybeValue;
    }

    public override void Write(Utf8JsonWriter writer, T value, JsonSerializerOptions options)
    {
        JsonSerializer.Serialize(writer, value, this.TypeInfo);
    }
}

internal abstract class JsonConverterDictionarySupportBase<T> : JsonConverterBase<T>
{
    protected abstract string Stringify([DisallowNull] T value);
    protected abstract T Parse(string propertyName);

    public override T ReadAsPropertyName(ref Utf8JsonReader reader, Type typeToConvert, JsonSerializerOptions options)
    {
        SequencePosition position = reader.Position;
        string? propertyName = reader.GetString();

        if (propertyName == null)
        {
            throw new JsonException($"Got null trying to read property name at position {position}");
        }

        return this.Parse(propertyName);
    }

    public override void WriteAsPropertyName(Utf8JsonWriter writer, [DisallowNull] T value, JsonSerializerOptions options)
    {
        string propertyName = this.Stringify(value);
        writer.WritePropertyName(propertyName);
    }
}

internal sealed class ExecutorIdentityConverter() : JsonConverterDictionarySupportBase<ExecutorIdentity>
{
    protected override JsonTypeInfo<ExecutorIdentity> TypeInfo
        => WorkflowsJsonUtilities.JsonContext.Default.ExecutorIdentity;

    protected override ExecutorIdentity Parse(string propertyName)
    {
        if (propertyName.Length == 0)
        {
            return ExecutorIdentity.None;
        }

        if (propertyName[0] == '@')
        {
            return new() { Id = propertyName.Substring(1) };
        }

        throw new JsonException($"Invalid ExecutorIdentity key Expecting empty string or a value that is prefixed with '@'. Got '{propertyName}'");
    }

    protected override string Stringify(ExecutorIdentity value)
    {
        return value == ExecutorIdentity.None
             ? string.Empty
             : $"@{value.Id}";
    }
}

internal sealed class ScopeKeyConverter : JsonConverterDictionarySupportBase<ScopeKey>
{
    protected override JsonTypeInfo<ScopeKey> TypeInfo => WorkflowsJsonUtilities.JsonContext.Default.ScopeKey;

    public static readonly Regex ScopeKeyPropertyNamePattern = new(@"^(?<executorId>(?:(?:(?:\|\|)|(?:[^\|]))*))\|(?<scopeName>(?:@(?:(?:(?:\|\|)|(?:[^\|]))*))?)\|(?<key>(?:(?:(?:\|\|)|(?:[^\|]))*)?)$",
                                                                   RegexOptions.Compiled | RegexOptions.CultureInvariant);
    protected override ScopeKey Parse(string propertyName)
    {
        Match scopeKeyPatternMatch = ScopeKeyPropertyNamePattern.Match(propertyName);
        if (!scopeKeyPatternMatch.Success)
        {
            throw new JsonException($"Invalid ScopeKey property name format. Got '{propertyName}'.");
        }

        string executorId = scopeKeyPatternMatch.Groups["executorId"].Value;
        string scopeName = scopeKeyPatternMatch.Groups["scopeName"].Value;
        string key = scopeKeyPatternMatch.Groups["key"].Value;

        return new ScopeKey(Unescape(executorId)!,
                            Unescape(scopeName, allowNullAndPad: true),
                            Unescape(key)!);
    }

    [return: NotNull]
    private static string Escape(string? value, bool allowNullAndPad = false, [CallerArgumentExpression("value")] string componentName = "ScopeKey")
    {
        if (!allowNullAndPad && value == null)
        {
            throw new JsonException($"Invalid {componentName} '{value}'. Expecting non-null string.");
        }

        if (value == null)
        {
            return string.Empty;
        }

        if (allowNullAndPad)
        {
            return $"@{value.Replace(" | ", " || ")}";
        }

        return $"{value.Replace("|", "||")}";
    }

    private static string? Unescape([DisallowNull] string value, bool allowNullAndPad = false, [CallerArgumentExpression("value")] string componentName = "ScopeKey")
    {
        if (value.Length == 0)
        {
            if (!allowNullAndPad)
            {
                throw new JsonException($"Invalid {componentName} '{value}'. Expecting empty string or a value that is prefixed with '@'.");
            }

            return null;
        }

        if (allowNullAndPad && value[0] != '@')
        {
            throw new JsonException($"Invalid {componentName} component '{value}'. Expecting empty string or a value that is prefixed with '@'.");
        }

        if (allowNullAndPad)
        {
            value = value.Substring(1);
        }

        return value.Replace("||", "|");
    }

    protected override string Stringify([DisallowNull] ScopeKey value)
    {
        string? executorIdEscaped = Escape(value.ScopeId.ExecutorId);
        string? scopeNameEscaped = Escape(value.ScopeId.ScopeName, allowNullAndPad: true);
        string? keyEscaped = Escape(value.Key);

        return $"{executorIdEscaped}|{scopeNameEscaped}|{keyEscaped}";
    }
}

internal sealed class EdgeIdConverter : JsonConverterDictionarySupportBase<EdgeId>
{
    protected override JsonTypeInfo<EdgeId> TypeInfo => throw new NotImplementedException();

    protected override EdgeId Parse(string propertyName)
    {
        if (int.TryParse(propertyName, out int edgeId))
        {
            return new(edgeId);
        }

        throw new JsonException($"Cannot deserialize EdgeId from JSON propery name '{propertyName}'");
    }

    protected override string Stringify([DisallowNull] EdgeId value)
    {
        return value.EdgeIndex.ToString();
    }
}

internal sealed class PortableValueConverter(JsonMarshaller marshaller) : JsonConverter<PortableValue>
{
    public override PortableValue? Read(ref Utf8JsonReader reader, Type typeToConvert, JsonSerializerOptions options)
    {
        SequencePosition initial = reader.Position;

        JsonTypeInfo<PortableValue> baseTypeInfo = WorkflowsJsonUtilities.JsonContext.Default.PortableValue;
        PortableValue? maybeValue = JsonSerializer.Deserialize<PortableValue>(ref reader, baseTypeInfo);

        if (maybeValue is null)
        {
            throw new JsonException($"Could not deserialize a PortableValue from JSON at position {initial}.");
        }
        else if (maybeValue.Value is JsonElement element)
        {
            // This happens when we do not have the type information available to deserialize the value directly.
            // We need to wrap it in a JsonWireSerializedValue so that we can deserialize it
            return new PortableValue(maybeValue.TypeId, new JsonWireSerializedValue(marshaller, element));
        }
        else if (maybeValue.TypeId.IsMatch(maybeValue.Value.GetType()))
        {
            return maybeValue;
        }

        throw new JsonException($"Deserialized PortableValue contains a value of type {maybeValue.Value.GetType()} which does not match the expected type {maybeValue.TypeId} at position {initial}.");
    }

    public override void Write(Utf8JsonWriter writer, PortableValue value, JsonSerializerOptions options)
    {
        PortableValue proxyValue;
        if (value.IsDelayedDeserialization && !value.IsDeserialized)
        {
            if (value.Value is JsonWireSerializedValue jsonWireValue)
            {
                proxyValue = new(value.TypeId, jsonWireValue.Data);
            }
            else
            {
                // Users should never see this unless they're trying to cross wire formats
                throw new InvalidOperationException("Cannot serialize a PortableValue that has not been deserialized. Please deserialize it with .As/AsType() or Is/IsType() methods first.");
            }
        }
        else
        {
            JsonElement element = marshaller.Marshal(value.Value, value.Value.GetType());
            proxyValue = new(value.TypeId, element);
        }

        JsonTypeInfo<PortableValue> baseTypeInfo = WorkflowsJsonUtilities.JsonContext.Default.PortableValue;
        JsonSerializer.Serialize(writer, proxyValue, baseTypeInfo);
    }
}

/// <summary>
/// Defines methods for marshalling and unmarshalling objects to and from a wire format.
/// </summary>
/// <typeparam name="TWireContainer"></typeparam>
public interface IWireMarshaller<TWireContainer>
{
    /// <summary>
    /// Marshals the specified value of the given type into a wire format container.
    /// </summary>
    /// <param name="value"></param>
    /// <param name="type"></param>
    /// <returns></returns>
    TWireContainer Marshal(object value, Type type);

    /// <summary>
    /// Marshals the specified value into a wire format container.
    /// </summary>
    /// <typeparam name="TValue"></typeparam>
    /// <param name="value"></param>
    /// <returns></returns>
    TWireContainer Marshal<TValue>(TValue value);

    /// <summary>
    /// Unmarshals the specified wire format container into an object of the given type.
    /// </summary>
    /// <typeparam name="TValue"></typeparam>
    /// <param name="data"></param>
    /// <returns></returns>
    TValue Marshal<TValue>(TWireContainer data);

    /// <summary>
    /// Unmarshals the specified wire format container into an object of the specified target type.
    /// </summary>
    /// <param name="targetType"></param>
    /// <param name="data"></param>
    /// <returns></returns>
    object Marshal(Type targetType, TWireContainer data);
}

internal class JsonMarshaller : IWireMarshaller<JsonElement>
{
    private readonly JsonSerializerOptions _internalOptions;
    private readonly JsonSerializerOptions? _externalOptions;

    public JsonMarshaller(JsonSerializerOptions? serializerOptions = null)
    {
        this._internalOptions = new JsonSerializerOptions(WorkflowsJsonUtilities.DefaultOptions);
        this._internalOptions.Converters.Add(new PortableValueConverter(this));
        this._internalOptions.Converters.Add(new ExecutorIdentityConverter());
        this._internalOptions.Converters.Add(new ScopeKeyConverter());
        this._internalOptions.Converters.Add(new EdgeIdConverter());

        this._externalOptions = serializerOptions;
    }

    private JsonTypeInfo LookupTypeInfo(Type type)
    {
        if (!this._internalOptions.TryGetTypeInfo(type, out JsonTypeInfo? typeInfo))
        {
            if (this._externalOptions == null ||
                !this._externalOptions.TryGetTypeInfo(type, out typeInfo))
            {
                throw new InvalidOperationException($"No JSON type info is available for type '{type}'.");
            }
        }

        return typeInfo;
    }

    public JsonElement Marshal(object value, Type type)
        => JsonSerializer.SerializeToElement(value, this.LookupTypeInfo(type));

    public JsonElement Marshal<TValue>(TValue value)
        => JsonSerializer.SerializeToElement(value, this.LookupTypeInfo(typeof(TValue)));

    public TValue Marshal<TValue>(JsonElement data)
    {
        Type type = typeof(TValue);
        //Debug.Assert(type != typeof(PortableValue));

        object? value = JsonSerializer.Deserialize(data, this.LookupTypeInfo(type));

        if (value is null)
        {
            throw new InvalidOperationException($"Could not deserialize the value as the expected type {typeof(TValue)}.");
        }

        if (value is TValue typedValue)
        {
            return typedValue;
        }

        throw new InvalidOperationException($"Deserialized value is not of the expected type {typeof(TValue)}.");
    }

    public object Marshal(Type targetType, JsonElement data)
    {
        //Debug.Assert(targetType != typeof(PortableValue));

        object? value = JsonSerializer.Deserialize(data, this.LookupTypeInfo(targetType));

        if (value is null)
        {
            throw new InvalidOperationException($"Could not deserialize the value as the expected type {targetType}.");
        }

        if (targetType.IsInstanceOfType(value))
        {
            return value;
        }

        throw new InvalidOperationException($"Deserialized value is not of the expected type {targetType}.");
    }
}
