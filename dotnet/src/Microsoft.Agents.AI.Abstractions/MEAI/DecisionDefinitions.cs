// Licensed to the .NET Foundation under one or more agreements.
// The .NET Foundation licenses this file to you under the MIT license.

#pragma warning disable SA1402 // Definition and nested builder are one immutable API surface.
#pragma warning disable SA1649 // File name identifies the primary definition type.
#pragma warning disable CA1000 // The generic type is the natural home for the typed factory methods.
#pragma warning disable CA1032 // Decision materialization exposes protocol-specific failures.
#pragma warning disable S2302 // Protocol exception messages intentionally describe the response and configured options.

using System;
using System.Collections.Generic;
using System.Collections.ObjectModel;
using System.ComponentModel;
using System.Diagnostics.CodeAnalysis;
using System.IO;
using System.Linq;
using System.Linq.Expressions;
using System.Reflection;
using System.Text.Json;
using System.Text.Json.Serialization;
using System.Text.Json.Serialization.Metadata;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Shared.DiagnosticIds;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Extensions.AI;

/// <summary>
/// Declares the decision questions and application-owned result properties for a typed decision flow.
/// </summary>
/// <typeparam name="TResult">The application-owned result type.</typeparam>
[Experimental(DiagnosticIds.Experiments.AIDecisions, UrlFormat = DiagnosticIds.UrlFormat)]
public sealed class DecisionDefinition<TResult>
{
    private readonly ReadOnlyCollection<DecisionDefinitionQuestion<TResult>> _questions;

    private DecisionDefinition(
        JsonTypeInfo<TResult> resultTypeInfo,
        JsonSerializerOptions serializerOptions,
        IReadOnlyList<DecisionDefinitionQuestion<TResult>> questions)
    {
        ResultTypeInfo = resultTypeInfo;
        SerializerOptions = serializerOptions;
        _questions = new ReadOnlyCollection<DecisionDefinitionQuestion<TResult>>(questions.ToArray());
        Questions = new ReadOnlyCollection<DecisionQuestion>(_questions.Select(static question => question.Question).ToArray());
    }

    /// <summary>Gets the explicit JSON contract used to materialize the application result.</summary>
    public JsonTypeInfo<TResult> ResultTypeInfo { get; }

    /// <summary>Gets the serializer options associated with this definition.</summary>
    [JsonIgnore]
    public JsonSerializerOptions SerializerOptions { get; }

    /// <summary>Gets the immutable ordered questions declared by this definition.</summary>
    public IReadOnlyList<DecisionQuestion> Questions { get; }

    /// <summary>
    /// Creates a typed definition using the configured default JSON contract for <typeparamref name="TResult"/>.
    /// </summary>
    /// <param name="configure">The explicit question declaration callback.</param>
    /// <param name="serializerOptions">
    /// Optional JSON options used for property and enum metadata. A missing resolver is supplied from the MEAI defaults;
    /// explicit caller resolvers and converters are preserved without mutating the caller's options.
    /// </param>
    /// <returns>An immutable decision definition.</returns>
    public static DecisionDefinition<TResult> Create(
        Action<Builder> configure,
        JsonSerializerOptions? serializerOptions = null)
    {
        _ = Throw.IfNull(configure);
        serializerOptions = new JsonSerializerOptions(serializerOptions ?? AIJsonUtilities.DefaultOptions);
        serializerOptions.TypeInfoResolver ??= AIJsonUtilities.DefaultOptions.TypeInfoResolver;
        serializerOptions.MakeReadOnly();

        JsonTypeInfo<TResult> resultTypeInfo = GetResultTypeInfo(serializerOptions);
        return Create(resultTypeInfo, configure);
    }

    /// <summary>Creates a typed definition using an application-supplied JSON contract.</summary>
    /// <param name="resultTypeInfo">The JSON contract for <typeparamref name="TResult"/>.</param>
    /// <param name="configure">The explicit question declaration callback.</param>
    /// <returns>An immutable decision definition.</returns>
    public static DecisionDefinition<TResult> Create(
        JsonTypeInfo<TResult> resultTypeInfo,
        Action<Builder> configure)
    {
        _ = Throw.IfNull(resultTypeInfo);
        _ = Throw.IfNull(configure);

        Builder builder = new(resultTypeInfo);
        configure(builder);
        return builder.Build();
    }

    private static AIFunctionFactoryOptions GetFunctionOptions(
        AIFunctionFactoryOptions? functionOptions,
        JsonSerializerOptions serializerOptions)
    {
        if (functionOptions is null)
        {
            return new AIFunctionFactoryOptions { SerializerOptions = serializerOptions };
        }

        if (functionOptions.SerializerOptions is not null)
        {
            return functionOptions;
        }

        return new AIFunctionFactoryOptions
        {
            SerializerOptions = serializerOptions,
            JsonSchemaCreateOptions = functionOptions.JsonSchemaCreateOptions,
            Name = functionOptions.Name,
            Description = functionOptions.Description,
            AdditionalProperties = functionOptions.AdditionalProperties,
            ConfigureParameterBinding = functionOptions.ConfigureParameterBinding,
            MarshalResult = functionOptions.MarshalResult,
            ExcludeResultSchema = functionOptions.ExcludeResultSchema,
        };
    }

    /// <summary>Creates an <see cref="AIFunction"/> that evaluates this definition for a caller-owned state type.</summary>
    /// <typeparam name="TState">The application-owned state type exposed as the function's input.</typeparam>
    /// <param name="client">The caller-owned decision client.</param>
    /// <param name="functionOptions">Optional standard function factory options.</param>
    /// <param name="decisionOptions">
    /// Optional decision options shallow-copied during construction and cloned for each invocation. Nested values and
    /// the raw-options factory remain caller/provider-owned.
    /// </param>
    /// <param name="stateTypeInfo">
    /// Optional explicit JSON contract for <typeparamref name="TState"/>. When omitted, the definition's serializer
    /// options must contain the state contract.
    /// </param>
    /// <returns>A function whose only model-facing input is <typeparamref name="TState"/> and whose result is <typeparamref name="TResult"/>.</returns>
    public AIFunction AsAIFunction<TState>(
        IDecisionClient client,
        AIFunctionFactoryOptions? functionOptions = null,
        DecisionOptions? decisionOptions = null,
        JsonTypeInfo<TState>? stateTypeInfo = null)
    {
        _ = Throw.IfNull(client);

        stateTypeInfo ??= GetStateTypeInfo<TState>();
        DecisionOptions? decisionOptionsSnapshot = decisionOptions?.Clone();
        DecisionFunctionInvoker<TState> invoker = new(client, this, stateTypeInfo, decisionOptionsSnapshot);

        return AIFunctionFactory.Create(
            invoker.InvokeAsync,
            GetFunctionOptions(functionOptions, stateTypeInfo.Options));
    }

    internal DecisionResponse<TResult> Bind(DecisionResponse response, DecisionRequest expectedRequest)
    {
        _ = Throw.IfNull(response);
        response.ValidateAgainst(expectedRequest);

        using MemoryStream stream = new();
        using (Utf8JsonWriter writer = new(stream))
        {
            writer.WriteStartObject();

            foreach (DecisionDefinitionQuestion<TResult> question in _questions)
            {
                DecisionAnswer answer = response.GetAnswer(question.Question.Id);
                switch (question.Kind)
                {
                    case DecisionKind.Binary:
                        writer.WriteNumber(question.PropertyName, ((BinaryDecisionAnswer)answer).TrueProbability);
                        break;

                    case DecisionKind.Choice:
                        ChoiceDecisionAnswer choice = (ChoiceDecisionAnswer)answer;
                        writer.WriteString(question.PropertyName, choice.SelectedCandidateId);
                        break;

                    case DecisionKind.Score:
                        ScoreDecisionAnswer score = (ScoreDecisionAnswer)answer;
                        if (question.UsesExpectedScore)
                        {
                            writer.WriteNumber(question.PropertyName, score.ExpectedScore);
                        }
                        else if (score.Score is double reportedScore)
                        {
                            writer.WriteNumber(question.PropertyName, reportedScore);
                        }
                        else
                        {
                            throw new DecisionProtocolException(
                                $"Question '{question.Question.Id}' does not contain a provider-reported score.");
                        }
                        break;

                    default:
                        throw new DecisionProtocolException($"Unsupported decision kind '{question.Kind}'.");
                }
            }

            writer.WriteEndObject();
        }

        byte[] resultJson = stream.ToArray();
        TResult result;
        try
        {
            result = JsonSerializer.Deserialize<TResult>(resultJson, ResultTypeInfo)!;
        }
        catch (Exception exception) when (exception is JsonException or NotSupportedException)
        {
            throw new DecisionProtocolException(
                "The decision response could not be materialized as the declared result type.",
                exception);
        }

        if (result is null)
        {
            throw new DecisionProtocolException("The decision response produced a null result.");
        }

        foreach (DecisionDefinitionQuestion<TResult> question in _questions)
        {
            DecisionAnswer answer = response.GetAnswer(question.Question.Id);
            object? actualValue = question.ValueAccessor(result);
            bool preserved = question.Kind switch
            {
                DecisionKind.Binary => actualValue is double actualBinary &&
                    actualBinary.Equals(((BinaryDecisionAnswer)answer).TrueProbability),
                DecisionKind.Choice => question.ChoiceValueMatches is not null &&
                    question.ChoiceValueMatches(actualValue, ((ChoiceDecisionAnswer)answer).SelectedCandidateId),
                DecisionKind.Score => actualValue is double actualScore &&
                    actualScore.Equals(question.UsesExpectedScore
                        ? ((ScoreDecisionAnswer)answer).ExpectedScore
                        : ((ScoreDecisionAnswer)answer).Score ?? double.NaN),
                _ => false,
            };

            if (!preserved)
            {
                throw new DecisionProtocolException(
                    $"The decision response value for result property '{question.Property.Name}' was not preserved by the configured JSON contract.");
            }
        }

        return new DecisionResponse<TResult>(result, response, this);
    }

    private JsonTypeInfo<TState> GetStateTypeInfo<TState>()
    {
        return SerializerOptions.GetTypeInfo(typeof(TState)) is JsonTypeInfo<TState> stateTypeInfo
            ? stateTypeInfo
            : throw new NotSupportedException(
                $"The configured JSON options do not contain a contract for state type '{typeof(TState)}'.");
    }

    private sealed class DecisionFunctionInvoker<TState>(
        IDecisionClient client,
        DecisionDefinition<TResult> definition,
        JsonTypeInfo<TState> stateTypeInfo,
        DecisionOptions? decisionOptionsSnapshot)
    {
        private readonly IDecisionClient _client = client;
        private readonly DecisionDefinition<TResult> _definition = definition;
        private readonly JsonTypeInfo<TState> _stateTypeInfo = stateTypeInfo;
        private readonly DecisionOptions? _decisionOptionsSnapshot = decisionOptionsSnapshot;

        [DisplayName("evaluate_decision")]
        [Description("Evaluate the declared decision for one application state.")]
        public async Task<TResult> InvokeAsync(
            [Description("The application state for the declared decision.")] TState state,
            CancellationToken cancellationToken)
        {
            DecisionResponse<TResult> response = await _client.GetResponseAsync(
                state,
                _stateTypeInfo,
                _definition,
                _decisionOptionsSnapshot?.Clone(),
                cancellationToken).ConfigureAwait(false);
            return response.Result;
        }
    }

    internal IReadOnlyDictionary<TEnum, double> GetDistribution<TEnum>(
        DecisionResponse<TResult> response,
        Expression<Func<TResult, TEnum>> selector)
        where TEnum : struct, Enum
    {
        DecisionDefinitionQuestion<TResult> question = FindQuestion(selector);
        if (question.Kind != DecisionKind.Choice ||
            question.EnumDefinition is not DecisionEnumDefinition<TEnum> definition)
        {
            throw new DecisionProtocolException("The selected result property is not a choice enum in this definition.");
        }

        ChoiceDecisionAnswer answer = (ChoiceDecisionAnswer)response.Evidence.GetAnswer(question.Question.Id);
        Dictionary<TEnum, double> values = new();
        foreach (DecisionProbability probability in answer.Probabilities)
        {
            values.Add(definition.Parse(probability.Id), probability.Value);
        }

        return new ReadOnlyDictionary<TEnum, double>(values);
    }

    private static JsonTypeInfo<TResult> GetResultTypeInfo(JsonSerializerOptions options)
    {
        if (options.GetTypeInfo(typeof(TResult)) is not JsonTypeInfo<TResult> resultTypeInfo)
        {
            throw new NotSupportedException(
                $"The configured JSON options do not contain a contract for result type '{typeof(TResult)}'.");
        }

        return resultTypeInfo;
    }

    private static PropertyInfo GetDirectProperty<TValue>(Expression<Func<TResult, TValue>> selector)
    {
        _ = Throw.IfNull(selector);

        Expression body = selector.Body;
        if (body is UnaryExpression { NodeType: ExpressionType.Convert } conversion)
        {
            body = conversion.Operand;
        }

        if (body is not MemberExpression { Member: PropertyInfo property, Expression: ParameterExpression parameter } ||
            selector.Parameters.Count != 1 ||
            selector.Parameters[0] != parameter)
        {
            Throw.ArgumentException(
                nameof(selector),
                "The selector must access one direct instance property of the result type.");
            return null!;
        }

        return property;
    }

    private DecisionDefinitionQuestion<TResult> FindQuestion<TValue>(Expression<Func<TResult, TValue>> selector)
    {
        PropertyInfo property = GetDirectProperty(selector);
        return _questions.FirstOrDefault(question => question.Property == property) ??
            throw new DecisionProtocolException($"The result property '{property.Name}' is not declared in this definition.");
    }

    /// <summary>Builds a <see cref="DecisionDefinition{TResult}"/> through explicit property declarations.</summary>
    [Experimental(DiagnosticIds.Experiments.AIDecisions, UrlFormat = DiagnosticIds.UrlFormat)]
    public sealed class Builder
    {
        private readonly JsonTypeInfo<TResult> _resultTypeInfo;
        private readonly List<DecisionDefinitionQuestion<TResult>> _questions = [];

        private static DecisionEnumDefinition<TEnum> CreateEnumDefinition<[DynamicallyAccessedMembers(DynamicallyAccessedMemberTypes.PublicFields)] TEnum>(
            PropertyInfo property,
            JsonTypeInfo<TResult> resultTypeInfo,
            JsonPropertyInfo jsonProperty)
            where TEnum : struct, Enum
        {
            if (property.PropertyType.IsDefined(typeof(FlagsAttribute), inherit: false))
            {
                Throw.ArgumentException("selector", "Flags enums are not supported as closed decision choices.");
            }

            if (jsonProperty.CustomConverter is not null)
            {
                throw new NotSupportedException(
                    $"Property-specific JSON converters are not supported for decision enum property '{property.Name}'. " +
                    "Configure the enum converter at the JSON type/options level so candidate IDs and result materialization share one contract.");
            }

            JsonTypeInfo enumTypeInfo;
            try
            {
                enumTypeInfo = resultTypeInfo.Options.GetTypeInfo(typeof(TEnum));
            }
            catch (Exception exception) when (exception is NotSupportedException or InvalidOperationException)
            {
                throw new NotSupportedException(
                    $"The configured JSON options do not contain a contract for enum type '{typeof(TEnum)}'.",
                    exception);
            }

#if NET5_0_OR_GREATER
            TEnum[] enumValues = Enum.GetValues<TEnum>();
#else
            TEnum[] enumValues = Enum.GetValues(typeof(TEnum)).Cast<TEnum>().ToArray();
#endif
            List<DecisionEnumValue<TEnum>> values = new(enumValues.Length);
            foreach (TEnum value in enumValues)
            {
                JsonElement serialized = JsonSerializer.SerializeToElement(value, enumTypeInfo);
                if (serialized.ValueKind != JsonValueKind.String || serialized.GetString() is not string id)
                {
                    throw new NotSupportedException(
                        $"Enum type '{typeof(TEnum)}' must use string JSON serialization for decision choices.");
                }

                string enumName = Enum.GetName(typeof(TEnum), value)!;
                string description = typeof(TEnum).GetField(enumName)?.GetCustomAttribute<DescriptionAttribute>()?.Description ??
                    enumName;

                values.Add(new DecisionEnumValue<TEnum>(value, id, description));
            }

            return new DecisionEnumDefinition<TEnum>(values);
        }

        private static JsonPropertyInfo GetJsonProperty(JsonTypeInfo<TResult> resultTypeInfo, PropertyInfo property)
        {
            JsonPropertyInfo? jsonProperty = resultTypeInfo.Properties.FirstOrDefault(
                candidate => candidate.AttributeProvider is PropertyInfo propertyInfo && propertyInfo == property);

            if (jsonProperty is null)
            {
                string expectedName = property.GetCustomAttribute<JsonPropertyNameAttribute>()?.Name ??
                    resultTypeInfo.Options.PropertyNamingPolicy?.ConvertName(property.Name) ??
                    property.Name;
                jsonProperty = resultTypeInfo.Properties.FirstOrDefault(
                    candidate => string.Equals(candidate.Name, expectedName, StringComparison.Ordinal));
            }

            if (jsonProperty is null)
            {
                Throw.ArgumentException(
                    nameof(property),
                    $"The selected property '{property.Name}' is not present in the configured JSON contract.");
            }

            return jsonProperty;
        }

        private static string GetInstructions(JsonPropertyInfo jsonProperty, PropertyInfo property, string? explicitInstructions)
        {
            if (explicitInstructions is not null)
            {
                return Throw.IfNullOrWhitespace(explicitInstructions);
            }

            string? description = (jsonProperty.AttributeProvider as PropertyInfo)?.GetCustomAttribute<DescriptionAttribute>(inherit: true)?.Description;
            if (description is not null)
            {
                return description;
            }

#if NET9_0_OR_GREATER
            description = jsonProperty.AssociatedParameter?.AttributeProvider?.GetCustomAttributes(typeof(DescriptionAttribute), inherit: true)
                .OfType<DescriptionAttribute>()
                .FirstOrDefault()
                ?.Description;
#else
            description = GetConstructorDescription(property);
#endif
            if (description is not null)
            {
                return description;
            }

            return property.PropertyType.GetCustomAttribute<DescriptionAttribute>(inherit: true)?.Description ??
                property.Name;
        }

        private static void EnsurePropertyCanBeDeclared(PropertyInfo property, Type expectedType)
        {
            if (property.GetMethod is null ||
                property.GetMethod.IsStatic ||
                property.PropertyType != expectedType)
            {
                Throw.ArgumentException("selector", $"The selected property must be a readable instance property of type '{expectedType}'.");
            }
        }

#if !NET9_0_OR_GREATER
        [UnconditionalSuppressMessage("Trimming", "IL2075", Justification = "The reflection convenience path checks preserved constructor binding metadata; source-generated metadata is used on newer TFMs.")]
#endif
        private static void EnsurePropertyCanBeMaterialized(
            PropertyInfo property,
            JsonPropertyInfo jsonProperty)
        {
            if (jsonProperty.Set is not null)
            {
                return;
            }

#if NET9_0_OR_GREATER
            if (jsonProperty.AssociatedParameter is not null)
            {
                return;
            }
#else
            ConstructorInfo[] constructors = property.DeclaringType?.GetConstructors() ?? [];
            if (Array.Exists(
                constructors,
                candidate => Array.Exists(
                    candidate.GetParameters(),
                    parameter => string.Equals(parameter.Name, property.Name, StringComparison.OrdinalIgnoreCase))))
            {
                return;
            }
#endif

            Throw.ArgumentException(
                "selector",
                $"The selected property '{property.Name}' is not writable or bound to a JSON constructor parameter.");
        }

#if !NET9_0_OR_GREATER
        [UnconditionalSuppressMessage("Trimming", "IL2075", Justification = "The reflection convenience path intentionally reads preserved constructor parameter metadata; source-generated metadata is used on newer TFMs.")]
        private static string? GetConstructorDescription(PropertyInfo property)
        {
            ConstructorInfo[] constructors = property.DeclaringType?.GetConstructors() ?? [];
            ConstructorInfo? constructor = Array.Find(
                constructors,
                candidate => Array.Exists(candidate.GetParameters(), parameter =>
                    string.Equals(parameter.Name, property.Name, StringComparison.OrdinalIgnoreCase)));
            return Array.Find(
                constructor?.GetParameters() ?? [],
                parameter => string.Equals(parameter.Name, property.Name, StringComparison.OrdinalIgnoreCase))
                ?.GetCustomAttribute<DescriptionAttribute>(inherit: true)
                ?.Description;
        }
#endif

        private static Func<TResult, object?> CreateValueAccessor<TValue>(Expression<Func<TResult, TValue>> selector)
        {
#if NETFRAMEWORK
            Func<TResult, TValue> accessor = selector.Compile();
#else
            Func<TResult, TValue> accessor = selector.Compile(true);
#endif
            return result => accessor(result);
        }

        private static Func<object?, string, bool> CreateChoiceValueMatcher<TEnum>(
            DecisionEnumDefinition<TEnum> enumDefinition)
            where TEnum : struct, Enum =>
            (actualValue, candidateId) =>
                actualValue is TEnum actual &&
                EqualityComparer<TEnum>.Default.Equals(actual, enumDefinition.Parse(candidateId));

        internal Builder(JsonTypeInfo<TResult> resultTypeInfo)
        {
            _resultTypeInfo = resultTypeInfo;
        }

        /// <summary>Declares an enum-backed choice question.</summary>
        /// <typeparam name="TEnum">The result property enum type.</typeparam>
        /// <param name="selector">A direct result property selector.</param>
        /// <param name="instructions">Optional explicit question instructions.</param>
        public void Choice<[DynamicallyAccessedMembers(DynamicallyAccessedMemberTypes.PublicFields)] TEnum>(
            Expression<Func<TResult, TEnum>> selector,
            string? instructions = null)
            where TEnum : struct, Enum
        {
            PropertyInfo property = GetDirectProperty(selector);
            EnsurePropertyCanBeDeclared(property, typeof(TEnum));

            JsonPropertyInfo jsonProperty = GetJsonProperty(_resultTypeInfo, property);
            EnsurePropertyCanBeMaterialized(property, jsonProperty);
            DecisionEnumDefinition<TEnum> enumDefinition = CreateEnumDefinition<TEnum>(property, _resultTypeInfo, jsonProperty);
            AddQuestion(
                property,
                jsonProperty.Name,
                new ChoiceDecisionQuestion(jsonProperty.Name, GetInstructions(jsonProperty, property, instructions), enumDefinition.Candidates),
                enumDefinition,
                DecisionKind.Choice,
                valueAccessor: CreateValueAccessor(selector),
                choiceValueMatches: CreateChoiceValueMatcher(enumDefinition));
        }

        /// <summary>Declares a binary probability question backed by a <see cref="double"/> result property.</summary>
        /// <param name="selector">A direct result property selector.</param>
        /// <param name="instructions">Optional explicit question instructions.</param>
        public void BinaryProbability(
            Expression<Func<TResult, double>> selector,
            string? instructions = null)
        {
            PropertyInfo property = GetDirectProperty(selector);
            EnsurePropertyCanBeDeclared(property, typeof(double));

            JsonPropertyInfo jsonProperty = GetJsonProperty(_resultTypeInfo, property);
            EnsurePropertyCanBeMaterialized(property, jsonProperty);
            AddQuestion(
                property,
                jsonProperty.Name,
                new BinaryDecisionQuestion(jsonProperty.Name, GetInstructions(jsonProperty, property, instructions)),
                enumDefinition: null,
                DecisionKind.Binary,
                valueAccessor: CreateValueAccessor(selector));
        }

        /// <summary>Declares an ordinal score question with an explicit ordered rubric.</summary>
        /// <param name="selector">A direct result property selector.</param>
        /// <param name="levels">The caller-defined ordered score levels.</param>
        /// <param name="instructions">Optional explicit question instructions.</param>
        public void Score(
            Expression<Func<TResult, double>> selector,
            IReadOnlyList<DecisionScoreLevel> levels,
            string? instructions = null)
        {
            AddScore(selector, levels, instructions, usesExpectedScore: false);
        }

        /// <summary>Declares an ordinal score question projected from the complete observed distribution.</summary>
        /// <param name="selector">A direct result property selector.</param>
        /// <param name="levels">The caller-defined ordered score levels.</param>
        /// <param name="instructions">Optional explicit question instructions.</param>
        public void ExpectedScore(
            Expression<Func<TResult, double>> selector,
            IReadOnlyList<DecisionScoreLevel> levels,
            string? instructions = null)
        {
            AddScore(selector, levels, instructions, usesExpectedScore: true);
        }

        private void AddScore(
            Expression<Func<TResult, double>> selector,
            IReadOnlyList<DecisionScoreLevel> levels,
            string? instructions,
            bool usesExpectedScore)
        {
            PropertyInfo property = GetDirectProperty(selector);
            EnsurePropertyCanBeDeclared(property, typeof(double));
            _ = Throw.IfNull(levels);

            JsonPropertyInfo jsonProperty = GetJsonProperty(_resultTypeInfo, property);
            EnsurePropertyCanBeMaterialized(property, jsonProperty);
            AddQuestion(
                property,
                jsonProperty.Name,
                new ScoreDecisionQuestion(jsonProperty.Name, GetInstructions(jsonProperty, property, instructions), levels),
                enumDefinition: null,
                DecisionKind.Score,
                usesExpectedScore,
                valueAccessor: CreateValueAccessor(selector));
        }

        internal DecisionDefinition<TResult> Build()
        {
            if (_questions.Count == 0)
            {
                Throw.ArgumentException("configure", "A decision definition must declare at least one question.");
            }

            return new DecisionDefinition<TResult>(
                _resultTypeInfo,
                _resultTypeInfo.Options,
                _questions);
        }

        private void AddQuestion(
            PropertyInfo property,
            string propertyName,
            DecisionQuestion question,
            object? enumDefinition,
            DecisionKind kind,
            bool usesExpectedScore = false,
            Func<TResult, object?>? valueAccessor = null,
            Func<object?, string, bool>? choiceValueMatches = null)
        {
            if (_questions.Exists(existing => existing.Property == property || string.Equals(existing.PropertyName, propertyName, StringComparison.Ordinal)))
            {
                Throw.ArgumentException("selector", "A result property or JSON property name can only be declared once.");
            }

            _questions.Add(new DecisionDefinitionQuestion<TResult>(
                property,
                propertyName,
                question,
                enumDefinition,
                kind,
                usesExpectedScore,
                valueAccessor ?? throw new InvalidOperationException("A direct property accessor is required."),
                choiceValueMatches));
        }
    }

}

/// <summary>Contains a typed result and the complete neutral evidence that produced it.</summary>
/// <typeparam name="TResult">The application-owned result type.</typeparam>
[Experimental(DiagnosticIds.Experiments.AIDecisions, UrlFormat = DiagnosticIds.UrlFormat)]
public sealed class DecisionResponse<TResult>
{
    private readonly DecisionDefinition<TResult> _definition;

    internal DecisionResponse(TResult result, DecisionResponse evidence, DecisionDefinition<TResult> definition)
    {
        Result = result;
        Evidence = evidence;
        _definition = definition;
    }

    /// <summary>Gets the application-owned materialized result.</summary>
    public TResult Result { get; }

    /// <summary>Gets the complete original response, including distributions and metadata.</summary>
    public DecisionResponse Evidence { get; }

    /// <summary>Gets the complete probability distribution for an enum-backed choice property.</summary>
    /// <typeparam name="TEnum">The enum property type.</typeparam>
    /// <param name="selector">The direct result property selector.</param>
    /// <returns>An immutable enum-to-probability snapshot.</returns>
    public IReadOnlyDictionary<TEnum, double> GetDistribution<TEnum>(
        Expression<Func<TResult, TEnum>> selector)
        where TEnum : struct, Enum =>
        _definition.GetDistribution(this, selector);
}

internal sealed class DecisionDefinitionQuestion<TResult>
{
    internal DecisionDefinitionQuestion(
        PropertyInfo property,
        string propertyName,
        DecisionQuestion question,
        object? enumDefinition,
        DecisionKind kind,
        bool usesExpectedScore,
        Func<TResult, object?> valueAccessor,
        Func<object?, string, bool>? choiceValueMatches)
    {
        Property = property;
        PropertyName = propertyName;
        Question = question;
        EnumDefinition = enumDefinition;
        Kind = kind;
        UsesExpectedScore = usesExpectedScore;
        ValueAccessor = valueAccessor;
        ChoiceValueMatches = choiceValueMatches;
    }

    internal PropertyInfo Property { get; }
    internal string PropertyName { get; }
    internal DecisionQuestion Question { get; }
    internal object? EnumDefinition { get; }
    internal DecisionKind Kind { get; }
    internal bool UsesExpectedScore { get; }
    internal Func<TResult, object?> ValueAccessor { get; }
    internal Func<object?, string, bool>? ChoiceValueMatches { get; }
}
