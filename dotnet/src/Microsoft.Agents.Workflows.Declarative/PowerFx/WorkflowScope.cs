// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using Microsoft.Agents.Workflows.Declarative.Extensions;
using Microsoft.Bot.ObjectModel;
using Microsoft.PowerFx.Types;

namespace Microsoft.Agents.Workflows.Declarative.PowerFx;

/// <summary>
/// The set of variables for a specific action scope.
/// </summary>
internal sealed class WorkflowScope(string scopeName) : Dictionary<string, FormulaValue>
{
    public string Name => scopeName;

    public RecordValue BuildRecord()
    {
        return FormulaValue.NewRecordFromFields(GetFields());

        IEnumerable<NamedValue> GetFields()
        {
            foreach (KeyValuePair<string, FormulaValue> kvp in this)
            {
                yield return new NamedValue(kvp.Key, kvp.Value);
            }
        }
    }

    public RecordDataValue BuildState()
    {
        RecordDataValue.Builder recordBuilder = new();

        foreach (KeyValuePair<string, FormulaValue> kvp in this)
        {
            recordBuilder.Properties.Add(kvp.Key, kvp.Value.ToDataValue());
        }

        return recordBuilder.Build();
    }
}
