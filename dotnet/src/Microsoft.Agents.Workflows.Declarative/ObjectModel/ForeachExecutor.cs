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

    public ForeachExecutor(Foreach model)
        : base(model)
    {
        this._values = [];
    }

    public bool HasValue { get; private set; }

    protected override ValueTask<object?> ExecuteAsync(IWorkflowContext context, CancellationToken cancellationToken)
    {
        this._index = 0;

        if (this.Model.Items is null)
        {
            this._values = [];
            this.HasValue = false;
        }
        else
        {
            EvaluationResult<DataValue> expressionResult = this.State.ExpressionEngine.GetValue(this.Model.Items, this.State.Scopes);
            if (expressionResult.Value is TableDataValue tableValue)
            {
                this._values = [.. tableValue.Values.Select(value => value.Properties.Values.First().ToFormulaValue())];
            }
            else
            {
                this._values = [expressionResult.Value.ToFormulaValue()];
            }
        }

        this.Reset();

        return default;
    }

    public void TakeNext()
    {
        if (this.HasValue = this._index < this._values.Length)
        {
            FormulaValue value = this._values[this._index];

            this.State.Set(Throw.IfNull(this.Model.Value), value);

            if (this.Model.Index is not null)
            {
                this.State.Set(this.Model.Index.Path, FormulaValue.New(this._index));
            }

            this._index++;
        }
    }

    public void Reset()
    {
        this.State.Clear(Throw.IfNull(this.Model.Value));
        if (this.Model.Index is not null)
        {
            this.State.Clear(this.Model.Index);
        }
    }
}
