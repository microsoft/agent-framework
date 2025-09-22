// Copyright (c) Microsoft. All rights reserved.

#if !NET8_0_OR_GREATER

namespace System.Diagnostics.CodeAnalysis;

/// <summary>
/// Indicates that an API element is experimental and subject to change without notice.
/// </summary>
[ExcludeFromCodeCoverage]
[AttributeUsage(
    AttributeTargets.Class |
    AttributeTargets.Struct |
    AttributeTargets.Enum |
    AttributeTargets.Interface |
    AttributeTargets.Delegate |
    AttributeTargets.Method |
    AttributeTargets.Constructor |
    AttributeTargets.Property |
    AttributeTargets.Field |
    AttributeTargets.Event |
    AttributeTargets.Assembly)]
internal sealed class ExperimentalAttribute : Attribute
{
    /// <summary>
    /// Initializes a new instance of the <see cref="ExperimentalAttribute"/> class.
    /// </summary>
    /// <param name="diagnosticId">Human readable explanation for marking experimental API.</param>
    public ExperimentalAttribute(string diagnosticId)
    {
        DiagnosticId = diagnosticId;
    }

    /// <summary>
    ///  Gets the ID that the compiler will use when reporting a use of the API the attribute applies to.
    /// </summary>
    /// <value>The unique diagnostic ID.</value>
    /// <remarks>
    ///  The diagnostic ID is shown in build output for warnings and errors.
    ///  <para>This property represents the unique ID that can be used to suppress the warnings or errors, if needed.</para>
    /// </remarks>
    public string DiagnosticId { get; }

    /// <summary>
    ///  Gets or sets the URL for corresponding documentation.
    ///  The API accepts a format string instead of an actual URL, creating a generic URL that includes the diagnostic ID.
    /// </summary>
    /// <value>The format string that represents a URL to corresponding documentation.</value>
    /// <remarks>An example format string is <c>https://contoso.com/obsoletion-warnings/{0}</c>.</remarks>
    public string? UrlFormat { get; set; }
}

#endif
