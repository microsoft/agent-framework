// Copyright (c) Microsoft. All rights reserved.

using System.Reflection;
using System.Text.RegularExpressions;
using System.Xml;

namespace GettingStarted.TestRunner;

/// <summary>
/// Service for parsing XML documentation comments and extracting descriptions.
/// </summary>
public static partial class XmlDocParser
{
    /// <summary>
    /// Extracts the XML documentation summary for a type.
    /// </summary>
    public static string ExtractTypeDescription(Type type)
    {
        try
        {
            var xmlDocPath = GetXmlDocumentationPath(type.Assembly);
            if (string.IsNullOrEmpty(xmlDocPath) || !File.Exists(xmlDocPath))
            {
                return string.Empty;
            }

            var doc = new XmlDocument();
            using var reader = XmlReader.Create(xmlDocPath, new XmlReaderSettings
            {
                DtdProcessing = DtdProcessing.Prohibit,
                XmlResolver = null
            });
            doc.Load(reader);

            var memberName = $"T:{type.FullName}";
            var memberNode = doc.SelectSingleNode($"//member[@name='{memberName}']");
            var summaryNode = memberNode?.SelectSingleNode("summary");

            if (summaryNode?.InnerXml != null)
            {
                return CleanXmlDocumentation(summaryNode.InnerXml);
            }
        }
        catch (Exception ex) when (ex is XmlException || ex is FileNotFoundException || ex is UnauthorizedAccessException)
        {
            // If XML parsing fails, return empty string
            // This is expected when XML documentation is not available
        }

        return string.Empty;
    }

    /// <summary>
    /// Extracts the XML documentation summary for a method.
    /// </summary>
    public static string ExtractMethodDescription(MethodInfo method)
    {
        try
        {
            var xmlDocPath = GetXmlDocumentationPath(method.DeclaringType?.Assembly);
            if (string.IsNullOrEmpty(xmlDocPath) || !File.Exists(xmlDocPath))
            {
                return string.Empty;
            }

            var doc = new XmlDocument();
            using var reader = XmlReader.Create(xmlDocPath, new XmlReaderSettings
            {
                DtdProcessing = DtdProcessing.Prohibit,
                XmlResolver = null
            });
            doc.Load(reader);

            var memberName = GetMethodMemberName(method);
            var memberNode = doc.SelectSingleNode($"//member[@name='{memberName}']");
            var summaryNode = memberNode?.SelectSingleNode("summary");

            if (summaryNode?.InnerXml != null)
            {
                return CleanXmlDocumentation(summaryNode.InnerXml);
            }
        }
        catch (Exception ex) when (ex is XmlException || ex is FileNotFoundException || ex is UnauthorizedAccessException)
        {
            // If XML parsing fails, return empty string
            // This is expected when XML documentation is not available
        }

        return string.Empty;
    }

    /// <summary>
    /// Gets the path to the XML documentation file for the given assembly.
    /// </summary>
    private static string GetXmlDocumentationPath(Assembly? assembly)
    {
        if (assembly?.Location == null)
        {
            return string.Empty;
        }

        var assemblyPath = assembly.Location;
        var xmlPath = Path.ChangeExtension(assemblyPath, ".xml");

        return File.Exists(xmlPath) ? xmlPath : string.Empty;
    }

    /// <summary>
    /// Generates the member name for XML documentation lookup for a method.
    /// </summary>
    private static string GetMethodMemberName(MethodInfo method)
    {
        var typeName = method.DeclaringType?.FullName ?? string.Empty;
        var methodName = method.Name;

        // Handle generic methods
        if (method.IsGenericMethod)
        {
            var genericArgCount = method.GetGenericArguments().Length;
            methodName += $"``{genericArgCount}";
        }

        // Handle method parameters
        var parameters = method.GetParameters();
        if (parameters.Length > 0)
        {
            var paramTypes = parameters.Select(p => GetParameterTypeName(p.ParameterType));
            methodName += $"({string.Join(",", paramTypes)})";
        }

        return $"M:{typeName}.{methodName}";
    }

    /// <summary>
    /// Gets the type name for XML documentation parameter representation.
    /// </summary>
    private static string GetParameterTypeName(Type type)
    {
        if (type.IsGenericParameter)
        {
            return $"``{type.GenericParameterPosition}";
        }

        if (type.IsGenericType)
        {
            var genericTypeName = type.GetGenericTypeDefinition().FullName;
            if (genericTypeName != null)
            {
                var backtickIndex = genericTypeName.IndexOf('`');
                if (backtickIndex > 0)
                {
                    genericTypeName = genericTypeName.Substring(0, backtickIndex);
                }

                var genericArgs = type.GetGenericArguments().Select(GetParameterTypeName);
                return $"{genericTypeName}{{{string.Join(",", genericArgs)}}}";
            }
        }

        return type.FullName ?? type.Name;
    }

    /// <summary>
    /// Cleans XML documentation text by removing XML tags and converting them to console markup.
    /// </summary>
    private static string CleanXmlDocumentation(string xmlText)
    {
        if (string.IsNullOrWhiteSpace(xmlText))
        {
            return string.Empty;
        }

        // Normalize whitespace and remove leading/trailing whitespace
        var cleaned = xmlText.Trim();

        // Convert <see cref="..."/> tags to blue highlighted references
        // Handle fully qualified type names (extract just the class name)
        cleaned = XmlDocSeeCrefFullyQualifiedTypesRegex().Replace(cleaned, "[blue]$1[/]");

        // Handle simple type references
        cleaned = XmlDocSeeCrefSimpleTypesRegex().Replace(cleaned, "[blue]$1[/]");

        // Convert <seealso cref="..."/> tags to dimmed cross-references
        cleaned = XmlDocSeeAlsoRegex().Replace(cleaned, "[dim]See also: [blue]$1[/][/]");

        // Convert <seealso cref="..."/> tags to dimmed cross-references with cref
        cleaned = XmlDocSeeAlsoCrefRegex().Replace(cleaned, "[dim]See also: [blue]$1[/][/]");

        // Convert <paramref name="..."/> tags to yellow highlighted parameters
        cleaned = XmlDocParamRefRegex().Replace(cleaned, "[yellow]$1[/]");

        // Handle <see langword="..."/> tags (like null, true, false)
        cleaned = XmlDocSeeLangwordRegex().Replace(cleaned, "[italic]$1[/]");

        // Convert <param name="...">...</param> tags to parameter documentation
        cleaned = XmlDocParamRegex().Replace(cleaned, "\n[yellow]$1[/]: $2");

        // Convert <typeparam name="...">...</typeparam> tags to type parameter documentation
        cleaned = XmlDocTypeParamRegex().Replace(cleaned, "\n[cyan]$1[/]: $2");

        // Remove any remaining XML tags
        cleaned = XmlDocRemoveTagsRegex().Replace(cleaned, "");

        // Clean up extra whitespace
        cleaned = XmlDocWhitespaceRegex().Replace(cleaned, " ");
        cleaned = cleaned.Trim();

        return cleaned;
    }

#if NET8_0_OR_GREATER
    [GeneratedRegex(@"<see cref=""[^""]*\.([^""\.\s]+)""\s*/>")]
    private static partial Regex XmlDocSeeCrefFullyQualifiedTypesRegex();

    [GeneratedRegex(@"<see cref=""([^""]+)""\s*/>")]
    private static partial Regex XmlDocSeeCrefSimpleTypesRegex();

    [GeneratedRegex(@"<seealso cref=""[^""]*\.([^""\.\s]+)""\s*/>")]
    private static partial Regex XmlDocSeeAlsoRegex();

    [GeneratedRegex(@"<seealso cref=""([^""]+)""\s*/>")]
    private static partial Regex XmlDocSeeAlsoCrefRegex();

    [GeneratedRegex(@"<paramref name=""([^""]+)""\s*/>")]
    private static partial Regex XmlDocParamRefRegex();

    [GeneratedRegex(@"<see langword=""([^""]+)""\s*/>")]
    private static partial Regex XmlDocSeeLangwordRegex();

    [GeneratedRegex(@"<param name=""([^""]+)"">([^<]*)</param>")]
    private static partial Regex XmlDocParamRegex();

    [GeneratedRegex(@"<typeparam name=""([^""]+)"">([^<]*)</typeparam>")]
    private static partial Regex XmlDocTypeParamRegex();

    [GeneratedRegex("<[^>]+>")]
    private static partial Regex XmlDocRemoveTagsRegex();

    [GeneratedRegex(@"\s+")]
    private static partial Regex XmlDocWhitespaceRegex();
#else
#pragma warning disable SYSLIB1045 // Use GeneratedRegexAttribute for regexes
    private static Regex XmlDocSeeCrefFullyQualifiedTypesRegex() => new(@"<see cref=""[^""]*\.([^""\.\s]+)""\s*/>");

    private static Regex XmlDocSeeCrefSimpleTypesRegex() => new(@"<see cref=""([^""]+)""\s*/>");

    private static Regex XmlDocSeeAlsoRegex() => new(@"<seealso cref=""[^""]*\.([^""\.\s]+)""\s*/>");

    private static Regex XmlDocSeeAlsoCrefRegex() => new(@"<seealso cref=""([^""]+)""\s*/>");

    private static Regex XmlDocParamRefRegex() => new(@"<paramref name=""([^""]+)""\s*/>");

    private static Regex XmlDocSeeLangwordRegex() => new(@"<see langword=""([^""]+)""\s*/>");

    private static Regex XmlDocParamRegex() => new(@"<param name=""([^""]+)"">([^<]*)</param>");

    private static Regex XmlDocTypeParamRegex() => new(@"<typeparam name=""([^""]+)"">([^<]*)</typeparam>");

    private static Regex XmlDocRemoveTagsRegex() => new("<[^>]+>");

    private static Regex XmlDocWhitespaceRegex() => new(@"\s+");
#pragma warning restore SYSLIB1045
#endif
}
