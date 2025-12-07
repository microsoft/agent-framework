// Copyright (c) Microsoft. All rights reserved.

using System;
using System.CodeDom.Compiler;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;
using System.Text;
using Microsoft.Bot.ObjectModel;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Workflows.Declarative.CodeGen;

internal abstract class CodeTemplate
{
    private bool _endsWithNewline;

    private string CurrentIndentField { get; set; } = string.Empty;

    /// <summary>
    /// Create the template output
    /// </summary>
    public abstract string TransformText();

    #region Object Model helpers

    public static string VariableName(PropertyPath path) => Throw.IfNull(path.VariableName);
    public static string VariableScope(PropertyPath path) => Throw.IfNull(path.NamespaceAlias);

    public static string FormatBoolValue(bool? value, bool defaultValue = false) =>
        value ?? defaultValue ? "true" : "false";

    public static string FormatStringValue(string? value)
    {
        if (value is null)
        {
            return "null";
        }

        if (value.Contains('\n') || value.Contains('\r'))
        {
            return @$"""""""{Environment.NewLine}{value}{Environment.NewLine}""""""";
        }

        if (value.Contains('"') || value.Contains('\\'))
        {
            return @$"""""""{value}""""""";
        }

        return @$"""{value}""";
    }

    public static string FormatValue<TValue>(string? value)
    {
        if (typeof(TValue) == typeof(string))
        {
            return FormatStringValue(value);
        }

        if (value is null)
        {
            return "null";
        }

        if (typeof(TValue).IsEnum)
        {
            return $"{typeof(TValue).Name}.{value}";
        }

        return $"{value}";
    }

    public static string FormatDataValue(DataValue value) =>
        value switch
        {
            BlankDataValue => "null",
            BooleanDataValue booleanValue => FormatBoolValue(booleanValue.Value),
            FloatDataValue decimalValue => $"{decimalValue.Value}",
            NumberDataValue numberValue => $"{numberValue.Value}",
            DateDataValue dateValue => $"new DateTime({dateValue.Value.Ticks}, DateTimeKind.{dateValue.Value.Kind})",
            DateTimeDataValue datetimeValue => $"new DateTimeOffset({datetimeValue.Value.Ticks}, TimeSpan.FromTicks({datetimeValue.Value.Offset}))",
            TimeDataValue timeValue => $"TimeSpan.FromTicks({timeValue.Value.Ticks})",
            StringDataValue stringValue => FormatStringValue(stringValue.Value),
            OptionDataValue optionValue => @$"""{optionValue.Value}""",
            // Indenting is important here to make the generated code readable.  Don't change it without testing the output.
            RecordDataValue recordValue =>
                $"""
                [
                                {string.Join(",\n                ", recordValue.Properties.Select(p => $"[\"{p.Key}\"] = {FormatDataValue(p.Value)}"))}
                            ]
                """,
            _ => throw new DeclarativeModelException($"Unable to format '{value.GetType().Name}'"),
        };

    public static TTarget FormatEnum<TSource, TTarget>(TSource value, IDictionary<TSource, TTarget> map, TTarget? defaultValue = default)
    {
        if (map.TryGetValue(value, out TTarget? target))
        {
            return target;
        }

        if (defaultValue is null)
        {
            throw new DeclarativeModelException($"No default value suppied for '{typeof(TTarget).Name}'");
        }

        return defaultValue;
    }

    public static string GetTypeAlias<TValue>() => GetTypeAlias(typeof(TValue));

    public static string GetTypeAlias(Type type)
    {
        return type switch
        {
            Type t when t == typeof(bool) => "bool",
            Type t when t == typeof(byte) => "byte",
            Type t when t == typeof(sbyte) => "sbyte",
            Type t when t == typeof(char) => "char",
            Type t when t == typeof(decimal) => "decimal",
            Type t when t == typeof(double) => "double",
            Type t when t == typeof(float) => "float",
            Type t when t == typeof(int) => "int",
            Type t when t == typeof(uint) => "uint",
            Type t when t == typeof(long) => "long",
            Type t when t == typeof(ulong) => "ulong",
            Type t when t == typeof(nint) => "nint",
            Type t when t == typeof(nuint) => "nuint",
            Type t when t == typeof(short) => "short",
            Type t when t == typeof(ushort) => "ushort",
            Type t when t == typeof(string) => "string",
            Type t when t == typeof(object) => "object",
            _ => type.Name
        };
    }
    #endregion

    #region Properties
    /// <summary>
    /// The string builder that generation-time code is using to assemble generated output
    /// </summary>
    public StringBuilder GenerationEnvironment
    {
        get
        {
            return field ??= new StringBuilder();
        }
        set;
    }
    /// <summary>
    /// The error collection for the generation process
    /// </summary>
    public CompilerErrorCollection Errors => field ??= [];

    /// <summary>
    /// A list of the lengths of each indent that was added with PushIndent
    /// </summary>
    private List<int> IndentLengths { get => field ??= []; }

    /// <summary>
    /// Gets the current indent we use when adding lines to the output
    /// </summary>
    public string CurrentIndent
    {
        get
        {
            return this.CurrentIndentField;
        }
    }
    /// <summary>
    /// Current transformation session
    /// </summary>
    public virtual IDictionary<string, object>? Session { get; set; }

    #endregion

    #region Transform-time helpers

    /// <summary>
    /// Write text directly into the generated output
    /// </summary>
    public void Write(string textToAppend)
    {
        if (string.IsNullOrEmpty(textToAppend))
        {
            return;
        }
        // If we're starting off, or if the previous text ended with a newline,
        // we have to append the current indent first.
        if ((this.GenerationEnvironment.Length == 0)
                    || this._endsWithNewline)
        {
            this.GenerationEnvironment.Append(this.CurrentIndentField);
            this._endsWithNewline = false;
        }
        // Check if the current text ends with a newline
        if (textToAppend.EndsWith(Environment.NewLine, StringComparison.CurrentCulture))
        {
            this._endsWithNewline = true;
        }
        // This is an optimization. If the current indent is "", then we don't have to do any
        // of the more complex stuff further down.
        if (this.CurrentIndentField.Length == 0)
        {
            this.GenerationEnvironment.Append(textToAppend);
            return;
        }
        // Everywhere there is a newline in the text, add an indent after it
        textToAppend = textToAppend.Replace(Environment.NewLine, Environment.NewLine + this.CurrentIndentField);
        // If the text ends with a newline, then we should strip off the indent added at the very end
        // because the appropriate indent will be added when the next time Write() is called
        if (this._endsWithNewline)
        {
            this.GenerationEnvironment.Append(textToAppend, 0, textToAppend.Length - this.CurrentIndentField.Length);
        }
        else
        {
            this.GenerationEnvironment.Append(textToAppend);
        }
    }

    /// <summary>
    /// Write text directly into the generated output
    /// </summary>
    public void WriteLine(string textToAppend)
    {
        this.Write(textToAppend);
        this.GenerationEnvironment.AppendLine();
        this._endsWithNewline = true;
    }

    /// <summary>
    /// Write formatted text directly into the generated output
    /// </summary>
    public void Write(string format, params object[] args)
    {
        this.Write(string.Format(CultureInfo.CurrentCulture, format, args));
    }

    /// <summary>
    /// Write formatted text directly into the generated output
    /// </summary>
    public void WriteLine(string format, params object[] args)
    {
        this.WriteLine(string.Format(CultureInfo.CurrentCulture, format, args));
    }

    /// <summary>
    /// Raise an error
    /// </summary>
    public void Error(string message)
    {
        CompilerError error = new()
        {
            ErrorText = message
        };
        this.Errors.Add(error);
    }

    /// <summary>
    /// Raise a warning
    /// </summary>
    public void Warning(string message)
    {
        CompilerError error = new()
        {
            ErrorText = message,
            IsWarning = true
        };
        error.ErrorText = message;
        error.IsWarning = true;
        this.Errors.Add(error);
    }

    /// <summary>
    /// Increase the indent
    /// </summary>
    public void PushIndent(string indent)
    {
        if (indent is null)
        {
            throw new ArgumentNullException(nameof(indent));
        }
        this.CurrentIndentField += indent;
        this.IndentLengths.Add(indent.Length);
    }

    /// <summary>
    /// Remove the last indent that was added with PushIndent
    /// </summary>
    public string PopIndent()
    {
        string returnValue = string.Empty;
        if (this.IndentLengths.Count > 0)
        {
            int indentLength = this.IndentLengths[this.IndentLengths.Count - 1];
            this.IndentLengths.RemoveAt(this.IndentLengths.Count - 1);
            if (indentLength > 0)
            {
                returnValue = this.CurrentIndentField.Substring(this.CurrentIndentField.Length - indentLength);
                this.CurrentIndentField = this.CurrentIndentField.Remove(this.CurrentIndentField.Length - indentLength);
            }
        }
        return returnValue;
    }

    /// <summary>
    /// Remove any indentation
    /// </summary>
    public void ClearIndent()
    {
        this.IndentLengths.Clear();
        this.CurrentIndentField = string.Empty;
    }

    #endregion

    #region ToString Helpers

    /// <summary>
    /// Utility class to produce culture-oriented representation of an object as a string.
    /// </summary>
    public sealed class ToStringInstanceHelper
    {
        /// <summary>
        /// This is called from the compile/run appdomain to convert objects within an expression block to a string
        /// </summary>
#pragma warning disable CA1822 // Required to be non-static for use in generated code
        public string ToStringWithCulture(object objectToConvert) => $"{objectToConvert}";
#pragma warning restore CA1822
    }

    /// <summary>
    /// Helper to produce culture-oriented representation of an object as a string
    /// </summary>
    public ToStringInstanceHelper ToStringHelper { get; } = new();

    #endregion
}
