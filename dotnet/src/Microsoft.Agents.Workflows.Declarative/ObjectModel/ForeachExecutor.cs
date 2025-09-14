// Copyright (c) Microsoft. All rights reserved.

using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.Workflows.Declarative.Extensions;
using Microsoft.Agents.Workflows.Declarative.Interpreter;
using Microsoft.Bot.ObjectModel;
using Microsoft.Bot.ObjectModel.Abstractions;
using Microsoft.PowerFx.Types;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.Workflows.Declarative.ObjectModel;

internal sealed class ForeachExecutor : DeclarativeActionExecutor<Foreach>
{
    public static class Steps
    {
        public static string Start(string id) => $"{id}_{nameof(Start)}";
        public static string Next(string id) => $"{id}_{nameof(Next)}";
        public static string End(string id) => $"{id}_{nameof(End)}";
    }

    private int _index;
    private FormulaValue[] _values;

    public ForeachExecutor(Foreach model, DeclarativeWorkflowState state)
        : base(model, state)
    {
        this._values = [];
    }

    public bool HasValue { get; private set; }

    protected override bool IsDiscreteAction => false;

    protected override async ValueTask<object?> ExecuteAsync(IWorkflowContext context, CancellationToken cancellationToken)
    {
        this._index = 0;

        if (this.Model.Items is null)
        {
            this._values = [];
            this.HasValue = false;
        }
        else
        {
            EvaluationResult<DataValue> expressionResult = this.State.ExpressionEngine.GetValue(this.Model.Items);
            if (expressionResult.Value is TableDataValue tableValue)
            {
                this._values = [.. tableValue.Values.Select(value => value.Properties.Values.First().ToFormula())];
            }
            else
            {
                this._values = [expressionResult.Value.ToFormula()];
            }
        }

        await this.ResetAsync(context, null, cancellationToken).ConfigureAwait(false);

        return default;
    }

    public async ValueTask TakeNextAsync(IWorkflowContext context, object? _, CancellationToken cancellationToken)
    {
        if (this.HasValue = this._index < this._values.Length)
        {
            FormulaValue value = this._values[this._index];

            await this.State.SetAsync(Throw.IfNull(this.Model.Value), value, context).ConfigureAwait(false);

            if (this.Model.Index is not null)
            {
                await this.State.SetAsync(this.Model.Index.Path, FormulaValue.New(this._index), context).ConfigureAwait(false);
            }

            this._index++;
        }
    }

    public async ValueTask ResetAsync(IWorkflowContext context, object? _, CancellationToken cancellationToken)
    {
        try
        {
            this.State.Reset(Throw.IfNull(this.Model.Value));
            if (this.Model.Index is not null)
            {
                this.State.Reset(this.Model.Index);
            }
        }
        finally
        {
            await context.RaiseCompletionEventAsync(this.Model).ConfigureAwait(false);
        }
    }
}
