// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.Workflows.Declarative.Extensions;
using Microsoft.Bot.ObjectModel;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.Workflows.Declarative.CodeGen;

internal partial class SetVariableTemplate
{
    internal SetVariableTemplate(SetVariable model)
    {
        this.Model = model;
        this.Id = model.GetId();
        this.Name = this.Id.FormatType();
        this.VariableName = Throw.IfNull(this.Model.Variable?.Path.VariableName);
        this.TopicName = Throw.IfNull(this.Model.Variable?.Path.VariableScopeName);
    }

    internal SetVariable Model { get; }

    internal string Id { get; }
    internal string Name { get; }
    internal string VariableName { get; }
    internal string TopicName { get; }

    internal static string Format(DataValue value) =>
        value switch
        {
            BlankDataValue blankValue => "null",
            BooleanDataValue booleanValue => $"{booleanValue.Value}",
            FloatDataValue decimalValue => $"{decimalValue.Value}",
            NumberDataValue numberValue => $"{numberValue.Value}",
            DateDataValue dateValue => $"new DateTime({dateValue.Value.Ticks}, DateTimeKind.{dateValue.Value.Kind})",
            DateTimeDataValue datetimeValue => $"new DateTimeOffset({datetimeValue.Value.Ticks}, TimeSpan.FromTicks({datetimeValue.Value.Offset}))",
            TimeDataValue timeValue => $"TimeSpan.FromTicks({timeValue.Value.Ticks})",
            StringDataValue stringValue => @"""{stringValue.Value}""",
            OptionDataValue optionValue => @"""{optionValue.Value}""",
            _ => $"[{value.GetType().Name}]",
        };
}
