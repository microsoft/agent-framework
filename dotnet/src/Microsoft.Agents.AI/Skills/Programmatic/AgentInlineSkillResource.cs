// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Diagnostics.CodeAnalysis;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Shared.DiagnosticIds;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI;

/// <summary>
/// A skill resource defined in code, backed by either a static value or a delegate.
/// </summary>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
internal sealed class AgentInlineSkillResource : AgentSkillResource
{
    private readonly object? _value;
    private readonly AIFunction? _function;

    /// <summary>
    /// Initializes a new instance of the <see cref="AgentInlineSkillResource"/> class with a static value.
    /// The value is returned as-is when <see cref="ReadAsync"/> is called.
    /// </summary>
    /// <param name="name">The resource name.</param>
    /// <param name="value">The static resource value.</param>
    /// <param name="description">An optional description of the resource.</param>
    public AgentInlineSkillResource(string name, object value, string? description = null)
        : base(name, description)
    {
        this._value = Throw.IfNull(value);
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="AgentInlineSkillResource"/> class with a delegate.
    /// The delegate is invoked via an <see cref="AIFunction"/> each time <see cref="ReadAsync"/> is called,
    /// producing a dynamic (computed) value.
    /// </summary>
    /// <param name="name">The resource name.</param>
    /// <param name="method">A method that produces the resource value when requested.</param>
    /// <param name="description">An optional description of the resource.</param>
    public AgentInlineSkillResource(string name, Delegate method, string? description = null)
        : base(name, description)
    {
        Throw.IfNull(method);
        this._function = AIFunctionFactory.Create(method, name: this.Name);
    }

    /// <inheritdoc/>
    public override async Task<object?> ReadAsync(IServiceProvider? serviceProvider = null, CancellationToken cancellationToken = default)
    {
        if (this._function is not null)
        {
            return await this._function.InvokeAsync(new AIFunctionArguments() { Services = serviceProvider }, cancellationToken).ConfigureAwait(false);
        }

        return this._value;
    }
}
