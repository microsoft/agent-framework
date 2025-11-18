// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using Microsoft.PowerFx;
using Microsoft.PowerFx.Types;

namespace Microsoft.Agents.AI.Workflows.Declarative.PowerFx.Functions;

internal static class MessageText
{
    public const string FunctionName = nameof(MessageText);

    public sealed class StringInput()
        : ReflectionFunction(FunctionName, FormulaType.String, FormulaType.String)
    {
        public static FormulaValue Execute(StringValue input) => input;
    }

    public sealed class RecordInput() : ReflectionFunction(FunctionName, FormulaType.String, RecordType.Empty())
    {
        public static FormulaValue Execute(RecordValue input) => FormulaValue.New(GetTextFromRecord(input));
    }

    public sealed class TableInput() : ReflectionFunction(FunctionName, FormulaType.String, TableType.Empty())
    {
        public static FormulaValue Execute(TableValue tableValue)
        {
            return FormulaValue.New(string.Join("\n", GetText()));

            IEnumerable<string> GetText()
            {
                foreach (DValue<RecordValue> row in tableValue.Rows)
                {
                    string text = GetTextFromRecord(row.Value);
                    if (!string.IsNullOrWhiteSpace(text))
                    {
                        yield return text;
                    }
                }
            }
        }
    }

    private static string GetTextFromRecord(RecordValue recordValue)
    {
        FormulaValue textValue = recordValue.GetField(TypeSchema.Message.Fields.Text);

        return textValue switch
        {
            StringValue stringValue => stringValue.Value.Trim(),
            _ => string.Empty,
        };
    }
}
