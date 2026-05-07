// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using System.Reflection;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Shared.DiagnosticIds;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI;

/// <summary>
/// A skill script backed by a delegate.
/// </summary>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
internal sealed class AgentInlineSkillScript : AgentSkillScript
{
    private readonly AIFunction _function;

    /// <summary>
    /// Initializes a new instance of the <see cref="AgentInlineSkillScript"/> class from a delegate.
    /// The delegate's parameters and return type are automatically marshaled via <see cref="AIFunctionFactory"/>.
    /// </summary>
    /// <param name="name">The script name.</param>
    /// <param name="method">A method to execute when the script is invoked. Parameters are automatically deserialized from JSON.</param>
    /// <param name="description">An optional description of the script.</param>
    /// <param name="serializerOptions">
    /// Optional <see cref="JsonSerializerOptions"/> used to marshal the delegate's parameters and return value.
    /// When <see langword="null"/>, <see cref="AIJsonUtilities.DefaultOptions"/> is used.
    /// </param>
    public AgentInlineSkillScript(string name, Delegate method, string? description = null, JsonSerializerOptions? serializerOptions = null)
        : base(Throw.IfNullOrWhitespace(name), description)
    {
        Throw.IfNull(method);

        var options = new AIFunctionFactoryOptions { Name = this.Name, SerializerOptions = serializerOptions };
        this._function = AIFunctionFactory.Create(method, options);
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="AgentInlineSkillScript"/> class from a <see cref="MethodInfo"/>.
    /// The method's parameters and return type are automatically marshaled via <see cref="AIFunctionFactory"/>.
    /// </summary>
    /// <param name="name">The script name.</param>
    /// <param name="method">The method to execute when the script is invoked.</param>
    /// <param name="target">The target instance for instance methods, or <see langword="null"/> for static methods.</param>
    /// <param name="description">An optional description of the script.</param>
    /// <param name="serializerOptions">
    /// Optional <see cref="JsonSerializerOptions"/> used to marshal the method's parameters and return value.
    /// When <see langword="null"/>, <see cref="AIJsonUtilities.DefaultOptions"/> is used.
    /// </param>
    public AgentInlineSkillScript(string name, MethodInfo method, object? target, string? description = null, JsonSerializerOptions? serializerOptions = null)
        : base(Throw.IfNullOrWhitespace(name), description)
    {
        Throw.IfNull(method);

        var options = new AIFunctionFactoryOptions { Name = this.Name, SerializerOptions = serializerOptions };
        this._function = AIFunctionFactory.Create(method, target, options);
    }

    /// <summary>
    /// Gets the JSON schema describing the parameters accepted by this script, or <see langword="null"/> if not available.
    /// </summary>
    public override JsonElement? ParametersSchema => this._function.JsonSchema;

    /// <inheritdoc/>
    public override async Task<object?> RunAsync(AgentSkill skill, JsonElement? arguments, IServiceProvider? serviceProvider, CancellationToken cancellationToken = default)
    {
        var funcArgs = ConvertToFunctionArguments(arguments);
        funcArgs.Services = serviceProvider;

        return await this._function.InvokeAsync(funcArgs, cancellationToken).ConfigureAwait(false);
    }

    /// <summary>
    /// Converts a raw <see cref="JsonElement"/> to <see cref="AIFunctionArguments"/> for delegate invocation.
    /// </summary>
    /// <exception cref="InvalidOperationException">
    /// Thrown when <paramref name="arguments"/> is provided but is not a JSON object.
    /// Inline skill scripts expect arguments as a JSON object whose properties map to the delegate's parameters.
    /// </exception>
    private static AIFunctionArguments ConvertToFunctionArguments(JsonElement? arguments)
    {
        if (arguments is null ||
            arguments.Value.ValueKind == JsonValueKind.Null ||
            arguments.Value.ValueKind == JsonValueKind.Undefined)
        {
            return [];
        }

        if (arguments.Value.ValueKind != JsonValueKind.Object)
        {
            throw new InvalidOperationException(
                $"Inline skill scripts expect arguments as a JSON object but received a JSON element of kind '{arguments.Value.ValueKind}'.");
        }

        var dict = new Dictionary<string, object?>();
        foreach (var property in arguments.Value.EnumerateObject())
        {
            dict[property.Name] = property.Value;
        }

        return new AIFunctionArguments(dict);
    }
}
