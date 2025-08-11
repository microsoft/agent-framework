// Copyright (c) Microsoft. All rights reserved.

using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.Workflows.Declarative.Extensions;
using Microsoft.Agents.Workflows.Declarative.PowerFx;
using Microsoft.Bot.ObjectModel;
using Microsoft.Bot.ObjectModel.Abstractions;
using Microsoft.PowerFx.Types;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.Workflows.Declarative.Handlers;

internal sealed class ForeachAction : ProcessAction<Foreach>
{
    public static class Steps
    {
        public static string Start(string id) => $"{id}_{nameof(Start)}";
        public static string Next(string id) => $"{id}_{nameof(Next)}";
        public static string End(string id) => $"{id}_{nameof(End)}";
    }

    private int _index;
    private FormulaValue[] _values;

    public ForeachAction(Foreach model)
        : base(model)
    {
        this._values = [];
    }

    public bool HasValue { get; private set; }

    protected override Task HandleAsync(ProcessActionContext context, CancellationToken cancellationToken)
    {
        this._index = 0;

        if (this.Model.Items is null)
        {
            this._values = [];
            this.HasValue = false;
            return Task.CompletedTask;
        }

        EvaluationResult<DataValue> result = context.ExpressionEngine.GetValue(this.Model.Items, context.Scopes);
        TableDataValue tableValue = (TableDataValue)result.Value; // %%% CAST - TYPE ASSUMPTION (TableDataValue)
        this._values = [.. tableValue.Values.Select(value => value.Properties.Values.First().ToFormulaValue())];
        return Task.CompletedTask;
    }

    public void TakeNext(ProcessActionContext context)
    {
        if (this.HasValue = (this._index < this._values.Length))
        {
            FormulaValue value = this._values[this._index];

            context.Engine.SetScopedVariable(context.Scopes, Throw.IfNull(this.Model.Value), value);

            if (this.Model.Index is not null)
            {
                context.Engine.SetScopedVariable(context.Scopes, this.Model.Index.Path, FormulaValue.New(this._index));
            }

            this._index++;
        }
    }

    public void Reset(ProcessActionContext context)
    {
        context.Engine.ClearScopedVariable(context.Scopes, Throw.IfNull(this.Model.Value));
        if (this.Model.Index is not null)
        {
            context.Engine.ClearScopedVariable(context.Scopes, this.Model.Index);
        }
    }
}
