// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Dynamic;
using System.Linq;
using Microsoft.PowerFx.Types;

namespace Microsoft.Agents.AI.Workflows.Declarative.Extensions;

internal static class ExpandoObjectExtensions
{
    public static RecordType ToRecordType(this ExpandoObject value)
    {
        RecordType recordType = RecordType.Empty();

        foreach (KeyValuePair<string, object?> property in value)
        {
            recordType = recordType.Add(property.Key, property.Value.GetFormulaType());
        }

        return recordType;
    }

    public static RecordValue ToRecord(this ExpandoObject value) =>
        FormulaValue.NewRecordFromFields(
            value.Select(
                property => new NamedValue(property.Key, property.Value.ToFormula())));
}
