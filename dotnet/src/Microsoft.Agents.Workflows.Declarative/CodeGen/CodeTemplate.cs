// Copyright (c) Microsoft. All rights reserved.

using System;
using System.CodeDom.Compiler;
using System.Collections.Generic;
using System.Globalization;
using System.Text;
using Microsoft.Bot.ObjectModel;
using Microsoft.Extensions.AI;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.Workflows.Declarative.CodeGen;

internal abstract class CodeTemplate
{
    private StringBuilder? _generationEnvironmentField;
    private CompilerErrorCollection? _errorsField;
    private List<int>? _indentLengthsField;
    private bool _endsWithNewline;

    private string CurrentIndentField { get; } = string.Empty;

    /// <summary>
    /// Create the template output
    /// </summary>
    public abstract string TransformText();

    #region Agent Framework helpers

    public static string GetRole(AgentMessageRole? role) =>
        role switch
        {
            AgentMessageRole.Agent => $"{nameof(ChatRole)}.{nameof(ChatRole.Assistant)}",
            AgentMessageRole.User => $"{nameof(ChatRole)}.{nameof(ChatRole.User)}",
            _ => $"{nameof(ChatRole)}.{nameof(ChatRole.User)}",
        };

    #endregion

    #region Object Model helpers

    public static string VariableName(PropertyPath path) => Throw.IfNull(path.VariableName);
    public static string VariableScope(PropertyPath path) => Throw.IfNull(path.VariableScopeName);

    public static string Format(DataValue value) =>
        value switch
        {
            BlankDataValue => "null",
            BooleanDataValue booleanValue => $"{booleanValue.Value}",
            FloatDataValue decimalValue => $"{decimalValue.Value}",
            NumberDataValue numberValue => $"{numberValue.Value}",
            DateDataValue dateValue => $"new DateTime({dateValue.Value.Ticks}, DateTimeKind.{dateValue.Value.Kind})",
            DateTimeDataValue datetimeValue => $"new DateTimeOffset({datetimeValue.Value.Ticks}, TimeSpan.FromTicks({datetimeValue.Value.Offset}))",
            TimeDataValue timeValue => $"TimeSpan.FromTicks({timeValue.Value.Ticks})",
            StringDataValue stringValue => @$"""{stringValue.Value}""", // %%% INCOMPLETE: MULTILINE
            OptionDataValue optionValue => @$"""{optionValue.Value}""",
            _ => $"[{value.GetType().Name}]",
        };

    #endregion

    #region Properties
    /// <summary>
    /// The string builder that generation-time code is using to assemble generated output
    /// </summary>
    public StringBuilder GenerationEnvironment
    {
        get
        {
            return this._generationEnvironmentField ??= new StringBuilder();
        }
        set
        {
            this._generationEnvironmentField = value;
        }
    }
    /// <summary>
    /// The error collection for the generation process
    /// </summary>
    public CompilerErrorCollection Errors => this._errorsField ??= [];

    /// <summary>
    /// A list of the lengths of each indent that was added with PushIndent
    /// </summary>
    private List<int> indentLengths => this._indentLengthsField ??= [];

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
        this._currentIndentField += indent;
        this.indentLengths.Add(indent.Length);
    }

    /// <summary>
    /// Remove the last indent that was added with PushIndent
    /// </summary>
    public string PopIndent()
    {
        string returnValue = string.Empty;
        if (this.indentLengths.Count > 0)
        {
            int indentLength = this.indentLengths[this.indentLengths.Count - 1];
            this.indentLengths.RemoveAt(this.indentLengths.Count - 1);
            if (indentLength > 0)
            {
                returnValue = this.CurrentIndentField.Substring(this.CurrentIndentField.Length - indentLength);
                this._currentIndentField = this.CurrentIndentField.Remove(this.CurrentIndentField.Length - indentLength);
            }
        }
        return returnValue;
    }

    /// <summary>
    /// Remove any indentation
    /// </summary>
    public void ClearIndent()
    {
        this.indentLengths.Clear();
        this._currentIndentField = string.Empty;
    }

    #endregion

    #region ToString Helpers

    /// <summary>
    /// Utility class to produce culture-oriented representation of an object as a string.
    /// </summary>
    public class ToStringInstanceHelper
    {
        /// <summary>
        /// This is called from the compile/run appdomain to convert objects within an expression block to a string
        /// </summary>
        public string ToStringWithCulture(object objectToConvert) => $"{objectToConvert}";
    }

    /// <summary>
    /// Helper to produce culture-oriented representation of an object as a string
    /// </summary>
    public ToStringInstanceHelper ToStringHelper { get; } = new();

    #endregion
}
