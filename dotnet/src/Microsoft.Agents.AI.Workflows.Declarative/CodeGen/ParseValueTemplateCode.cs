// Copyright (c) Microsoft. All rights reserved.

using System.Linq;
using Microsoft.Bot.ObjectModel;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Workflows.Declarative.CodeGen;

internal partial class ParseValueTemplate
{
    public ParseValueTemplate(ParseValue model)
    {
        this.Model = this.Initialize(model);
        this.Variable = Throw.IfNull(this.Model.Variable);
    }

    public ParseValue Model { get; }
    public PropertyPath Variable { get; }

    private string GetVariableType()
    {
        return GetVariableType(this.Model.ValueType);

        static string GetVariableType(DataType? dataType) =>
            dataType switch
            {
                null => "null",
                StringDataType => "typeof(string)",
                BooleanDataType => "typeof(bool)",
                FloatDataType => "typeof(double)",
                NumberDataType => "typeof(decimal)",
                DateTimeDataType => "typeof(DateTime)",
                DateDataType => "typeof(DateTime)",
                TimeDataType => "typeof(TimeSpan)",
                RecordDataType recordType => $"\nVariableType.Record(\n{string.Join(",\n    ", recordType.Properties.Select(property => @$"( ""{property.Key}"", {GetVariableType(property.Value.Type)} )"))})",
                TableDataType tableType => $"\nVariableType.Record(\n{string.Join(",\n    ", tableType.Properties.Select(property => @$"( ""{property.Key}"", {GetVariableType(property.Value.Type)} )"))})",
                _ => throw new DeclarativeModelException($"Unsupported data type: {dataType}"),
            };
    }
}
