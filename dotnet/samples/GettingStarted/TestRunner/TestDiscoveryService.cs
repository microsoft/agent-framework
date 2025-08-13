// Copyright (c) Microsoft. All rights reserved.

using System.Reflection;
using System.Xml;

namespace GettingStarted.TestRunner;

/// <summary>
/// Service for discovering test classes, methods, and theory parameters.
/// </summary>
public class TestDiscoveryService
{
    private readonly Assembly _assembly;

    public TestDiscoveryService()
    {
        this._assembly = Assembly.GetExecutingAssembly();
    }

    /// <summary>
    /// Discovers all test folders and their contents.
    /// </summary>
    public List<TestFolder> DiscoverTestFolders()
    {
        var testFolders = new List<TestFolder>();
        var testClasses = this.GetTestClasses();

        // Group by physical directory structure
        var folderGroups = testClasses
            .GroupBy(t => GetPhysicalFolderName(t))
            .Where(g => !string.IsNullOrEmpty(g.Key)) // Exclude classes without clear folder structure
            .OrderBy(g => g.Key);

        foreach (var folderGroup in folderGroups)
        {
            var folder = new TestFolder
            {
                Name = folderGroup.Key,
                Description = ExtractFolderDescription(folderGroup.Key),
                Classes = folderGroup.Select(this.CreateTestClass).ToList()
            };
            testFolders.Add(folder);
        }

        return testFolders;
    }

    /// <summary>
    /// Gets all test classes in the assembly.
    /// </summary>
    private List<Type> GetTestClasses()
    {
        return this._assembly.GetTypes()
            .Where(t => t.IsClass && !t.IsAbstract)
            .Where(t => HasTestMethods(t))
            .Where(t => !t.Namespace?.Contains("TestRunner") == true) // Exclude our own classes
            .OrderBy(t => t.Name)
            .ToList();
    }

    /// <summary>
    /// Checks if a type has test methods.
    /// </summary>
    private static bool HasTestMethods(Type type)
    {
        return type.GetMethods(BindingFlags.Public | BindingFlags.Instance)
            .Any(m => m.GetCustomAttributes<FactAttribute>().Any() ||
                     m.GetCustomAttributes<TheoryAttribute>().Any());
    }

    /// <summary>
    /// Creates a TestClass model from a Type.
    /// </summary>
    private TestClass CreateTestClass(Type type)
    {
        var testClass = new TestClass
        {
            Name = type.Name,
            FullName = type.FullName ?? type.Name,
            Description = ExtractTypeDescription(type),
            Type = type,
            Methods = this.GetTestMethods(type)
        };

        return testClass;
    }

    /// <summary>
    /// Gets all test methods from a type.
    /// </summary>
    private List<TestMethod> GetTestMethods(Type type)
    {
        var methods = new List<TestMethod>();

        var testMethods = type.GetMethods(BindingFlags.Public | BindingFlags.Instance)
            .Where(m => m.GetCustomAttributes<FactAttribute>().Any() ||
                       m.GetCustomAttributes<TheoryAttribute>().Any())
            .OrderBy(m => m.Name);

        foreach (var method in testMethods)
        {
            var testMethod = new TestMethod
            {
                Name = method.Name,
                Description = ExtractMethodDescription(method),
                MethodInfo = method,
                IsTheory = method.GetCustomAttributes<TheoryAttribute>().Any(),
                TheoryData = this.GetTheoryData(method)
            };

            methods.Add(testMethod);
        }

        return methods;
    }

    /// <summary>
    /// Gets theory data for a test method.
    /// </summary>
    private List<TheoryTestCase> GetTheoryData(MethodInfo method)
    {
        var theoryCases = new List<TheoryTestCase>();

        if (!method.GetCustomAttributes<TheoryAttribute>().Any())
        {
            return theoryCases;
        }

        var inlineDataAttributes = method.GetCustomAttributes<InlineDataAttribute>();

        foreach (var inlineData in inlineDataAttributes)
        {
            var parameters = method.GetParameters();
            var values = inlineData.GetData(method).First();

            var theoryCase = new TheoryTestCase
            {
                DisplayName = FormatTheoryDisplayName(method, parameters, values),
                Parameters = parameters.Zip(values, (param, value) => new TheoryParameter
                {
                    Name = param.Name ?? "unknown",
                    Type = param.ParameterType,
                    Value = value
                }).ToList()
            };

            theoryCases.Add(theoryCase);
        }

        return theoryCases;
    }

    /// <summary>
    /// Formats the display name for a theory test case.
    /// </summary>
    private static string FormatTheoryDisplayName(MethodInfo method, ParameterInfo[] parameters, object[] values)
    {
        var paramStrings = parameters.Zip(values, (param, value) =>
            $"{param.Name}: {value}").ToArray();

        return $"{string.Join(", ", paramStrings)}";
    }

    /// <summary>
    /// Extracts folder name from namespace.
    /// </summary>
    private static string GetFolderName(string? namespaceName)
    {
        if (string.IsNullOrEmpty(namespaceName))
        {
            return "Root";
        }

        var parts = namespaceName.Split('.');
        return parts.Length > 1 ? parts[parts.Length - 1] : "Root";
    }

    /// <summary>
    /// Gets the physical folder name based on the type's location and namespace.
    /// Maps to the actual directory structure: Steps, Providers, Orchestration, Custom.
    /// </summary>
    private static string GetPhysicalFolderName(Type type)
    {
        var namespaceName = type.Namespace;

        if (string.IsNullOrEmpty(namespaceName))
        {
            return string.Empty; // Exclude from folder grouping
        }

        // Map known namespaces to their physical directories
        return namespaceName switch
        {
            "Steps" => "Steps",
            "Providers" => "Providers",
            "Orchestration" => "Orchestration",
            "Custom" => "Custom",
            _ => string.Empty // Exclude other namespaces (like GettingStarted, TestRunner, etc.)
        };
    }

    /// <summary>
    /// Extracts the XML documentation summary for a type.
    /// </summary>
    private static string ExtractTypeDescription(Type type)
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
        catch (Exception)
        {
            // Ignore XML documentation extraction errors
            return string.Empty;
        }

        return string.Empty;
    }

    /// <summary>
    /// Extracts the XML documentation summary for a method.
    /// </summary>
    private static string ExtractMethodDescription(MethodInfo method)
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

            // Try multiple approaches to find the method documentation
            var memberNode = TryFindMethodNode(doc, method);
            var summaryNode = memberNode?.SelectSingleNode("summary");

            if (summaryNode?.InnerXml != null)
            {
                return CleanXmlDocumentation(summaryNode.InnerXml);
            }
        }
        catch (Exception)
        {
            // Ignore XML documentation extraction errors
            return string.Empty;
        }

        return string.Empty;
    }

    /// <summary>
    /// Attempts to find the XML documentation node for a method using multiple strategies.
    /// </summary>
    private static XmlNode? TryFindMethodNode(XmlDocument doc, MethodInfo method)
    {
        var declaringType = method.DeclaringType;
        if (declaringType == null)
        {
            return null;
        }

        var parameters = method.GetParameters();

        // Strategy 1: Try with exact parameter type names as they appear in XML
        var parameterTypes = parameters.Select(p => GetXmlTypeName(p.ParameterType)).ToArray();
        var memberName = $"M:{declaringType.FullName}.{method.Name}";
        if (parameters.Length > 0)
        {
            memberName += $"({string.Join(",", parameterTypes)})";
        }

        var memberNode = doc.SelectSingleNode($"//member[@name='{memberName}']");
        if (memberNode != null)
        {
            return memberNode;
        }

        // Strategy 2: Try without parameters (for overloaded methods, sometimes XML docs don't include params)
        memberName = $"M:{declaringType.FullName}.{method.Name}";
        memberNode = doc.SelectSingleNode($"//member[@name='{memberName}']");
        if (memberNode != null)
        {
            return memberNode;
        }

        // Strategy 3: Try with a broader search pattern
        var escapedMethodName = method.Name.Replace(".", "\\.");
        var pattern = $"//member[contains(@name, 'M:{declaringType.FullName}.{escapedMethodName}')]";
        memberNode = doc.SelectSingleNode(pattern);

        return memberNode;
    }

    /// <summary>
    /// Converts a .NET type to its XML documentation representation.
    /// </summary>
    private static string GetXmlTypeName(Type type)
    {
        if (type.IsGenericType)
        {
            var genericTypeName = type.GetGenericTypeDefinition().FullName;
            if (genericTypeName != null)
            {
                // Remove the generic arity suffix (e.g., `1, `2)
                var backtickIndex = genericTypeName.IndexOf('`');
                if (backtickIndex > 0)
                {
                    genericTypeName = genericTypeName.Substring(0, backtickIndex);
                }

                var genericArgs = type.GetGenericArguments().Select(GetXmlTypeName);
                return $"{genericTypeName}{{{string.Join(",", genericArgs)}}}";
            }
        }

        // Handle specific type mappings for XML documentation
        return type.FullName ?? type.Name;
    }

    /// <summary>
    /// Gets the path to the XML documentation file for an assembly.
    /// </summary>
    private static string GetXmlDocumentationPath(Assembly? assembly)
    {
        if (assembly?.Location == null)
        {
            return string.Empty;
        }

        var assemblyPath = assembly.Location;
        var xmlPath = Path.ChangeExtension(assemblyPath, ".xml");
        return xmlPath;
    }

    /// <summary>
    /// Converts XML documentation text to rich Spectre.Console markup by transforming XML documentation tags
    /// into appropriate console formatting with comprehensive support for all standard XML documentation elements.
    /// </summary>
    private static string CleanXmlDocumentation(string xmlText)
    {
        if (string.IsNullOrEmpty(xmlText))
        {
            return string.Empty;
        }

        var cleaned = xmlText;

        // Convert <see cref="..."/> tags to blue highlighted references
        // Handle fully qualified type names (extract just the class name)
        cleaned = System.Text.RegularExpressions.Regex.Replace(cleaned,
            @"<see cref=""[^""]*\.([^""\.\s]+)""\s*/>",
            "[blue]$1[/]");

        // Handle simple type references
        cleaned = System.Text.RegularExpressions.Regex.Replace(cleaned,
            @"<see cref=""([^""]+)""\s*/>",
            "[blue]$1[/]");

        // Convert <seealso cref="..."/> tags to dimmed cross-references
        cleaned = System.Text.RegularExpressions.Regex.Replace(cleaned,
            @"<seealso cref=""[^""]*\.([^""\.\s]+)""\s*/>",
            "[dim]See also: [blue]$1[/][/]");

        cleaned = System.Text.RegularExpressions.Regex.Replace(cleaned,
            @"<seealso cref=""([^""]+)""\s*/>",
            "[dim]See also: [blue]$1[/][/]");

        // Convert <paramref name="..."/> tags to yellow highlighted parameters
        cleaned = System.Text.RegularExpressions.Regex.Replace(cleaned,
            @"<paramref name=""([^""]+)""\s*/>",
            "[yellow]$1[/]");

        // Handle <see langword="..."/> tags (like null, true, false)
        cleaned = System.Text.RegularExpressions.Regex.Replace(cleaned,
            @"<see langword=""([^""]+)""\s*/>",
            "[italic]$1[/]");

        // Convert <param name="...">...</param> tags to parameter documentation
        cleaned = System.Text.RegularExpressions.Regex.Replace(cleaned,
            @"<param name=""([^""]+)"">([^<]*)</param>",
            "\n[yellow]$1[/]: $2");

        // Convert <typeparam name="...">...</typeparam> tags to type parameter documentation
        cleaned = System.Text.RegularExpressions.Regex.Replace(cleaned,
            @"<typeparam name=""([^""]+)"">([^<]*)</typeparam>",
            "\n[cyan]$1[/]: $2");

        // Convert <returns>...</returns> tags to return value descriptions
        cleaned = System.Text.RegularExpressions.Regex.Replace(cleaned,
            "<returns>([^<]*)</returns>",
            "\n[green]Returns:[/] $1");

        // Convert <exception cref="...">...</exception> tags to exception documentation
        cleaned = System.Text.RegularExpressions.Regex.Replace(cleaned,
            @"<exception cref=""[^""]*\.([^""\.\s]+)"">([^<]*)</exception>",
            "\n[red]Throws $1:[/] $2");

        cleaned = System.Text.RegularExpressions.Regex.Replace(cleaned,
            @"<exception cref=""([^""]+)"">([^<]*)</exception>",
            "\n[red]Throws $1:[/] $2");

        // Convert <value>...</value> tags to property value descriptions
        cleaned = System.Text.RegularExpressions.Regex.Replace(cleaned,
            "<value>([^<]*)</value>",
            "\n[blue]Value:[/] $1");

        // Convert <remarks>...</remarks> tags to additional notes
        cleaned = System.Text.RegularExpressions.Regex.Replace(cleaned,
            "<remarks>([^<]*)</remarks>",
            "\n[dim]Note:[/] $1");

        // Convert <c>...</c> tags to grey inline code
        cleaned = System.Text.RegularExpressions.Regex.Replace(cleaned,
            "<c>([^<]*)</c>",
            "[grey]$1[/]");

        // Convert <code>...</code> tags to grey code blocks
        cleaned = System.Text.RegularExpressions.Regex.Replace(cleaned,
            "<code[^>]*>([^<]*)</code>",
            "[grey]$1[/]");

        // Convert <para>...</para> tags to paragraph breaks
        cleaned = System.Text.RegularExpressions.Regex.Replace(cleaned,
            "<para>([^<]*)</para>",
            "\n\n$1");

        // Convert <example>...</example> tags to dimmed examples
        cleaned = System.Text.RegularExpressions.Regex.Replace(cleaned,
            "<example>([^<]*)</example>",
            "\n[dim]Example:[/] $1");

        // Handle list processing - this needs to be done before removing other tags
        cleaned = ProcessXmlLists(cleaned);

        // Remove any remaining XML tags that we haven't handled
        cleaned = System.Text.RegularExpressions.Regex.Replace(cleaned, "<[^>]+>", "");

        // Clean up whitespace while preserving intentional line breaks
        cleaned = System.Text.RegularExpressions.Regex.Replace(cleaned, "[ \\t]+", " ");
        cleaned = System.Text.RegularExpressions.Regex.Replace(cleaned, "\\n\\s*\\n", "\n\n");
        cleaned = cleaned.Trim();

        return cleaned;
    }

    /// <summary>
    /// Processes XML list elements and converts them to formatted text with appropriate bullet points or numbering.
    /// </summary>
    private static string ProcessXmlLists(string xmlText)
    {
        if (string.IsNullOrEmpty(xmlText))
        {
            return string.Empty;
        }

        var result = xmlText;

        // Process bullet lists
        result = System.Text.RegularExpressions.Regex.Replace(result,
            @"<list type=""bullet"">(.*?)</list>",
            match => ProcessListItems(match.Groups[1].Value, "• "),
            System.Text.RegularExpressions.RegexOptions.Singleline);

        // Process numbered lists
        result = System.Text.RegularExpressions.Regex.Replace(result,
            @"<list type=""number"">(.*?)</list>",
            match => ProcessListItems(match.Groups[1].Value, string.Empty),
            System.Text.RegularExpressions.RegexOptions.Singleline);

        // Process table lists (treat as bullet lists for simplicity)
        result = System.Text.RegularExpressions.Regex.Replace(result,
            @"<list type=""table"">(.*?)</list>",
            match => ProcessListItems(match.Groups[1].Value, "• "),
            System.Text.RegularExpressions.RegexOptions.Singleline);

        return result;
    }

    /// <summary>
    /// Processes individual list items and formats them with appropriate prefixes.
    /// </summary>
    private static string ProcessListItems(string listContent, string bulletPrefix)
    {
        if (string.IsNullOrEmpty(listContent))
        {
            return string.Empty;
        }

        var items = new List<string>();
        var itemNumber = 1;

        // Handle <item><description>...</description></item> format
        var descriptionMatches = System.Text.RegularExpressions.Regex.Matches(listContent,
            "<item><description>([^<]*)</description></item>",
            System.Text.RegularExpressions.RegexOptions.Singleline);

        foreach (System.Text.RegularExpressions.Match match in descriptionMatches)
        {
            var description = match.Groups[1].Value.Trim();
            if (!string.IsNullOrEmpty(description))
            {
                var prefix = !string.IsNullOrEmpty(bulletPrefix) ? bulletPrefix : $"{itemNumber}. ";
                items.Add($"\n{prefix}{description}");
                itemNumber++;
            }
        }

        // Handle <item><term>...</term><description>...</description></item> format
        var termMatches = System.Text.RegularExpressions.Regex.Matches(listContent,
            "<item><term>([^<]*)</term><description>([^<]*)</description></item>",
            System.Text.RegularExpressions.RegexOptions.Singleline);

        foreach (System.Text.RegularExpressions.Match match in termMatches)
        {
            var term = match.Groups[1].Value.Trim();
            var description = match.Groups[2].Value.Trim();
            if (!string.IsNullOrEmpty(term) || !string.IsNullOrEmpty(description))
            {
                var prefix = !string.IsNullOrEmpty(bulletPrefix) ? bulletPrefix : $"{itemNumber}. ";
                var formattedItem = !string.IsNullOrEmpty(term)
                    ? $"{prefix}[bold]{term}[/]: {description}"
                    : $"{prefix}{description}";
                items.Add($"\n{formattedItem}");
                itemNumber++;
            }
        }

        return items.Count > 0 ? string.Concat(items) : string.Empty;
    }

    /// <summary>
    /// Extracts the folder description from the README.md file in the specified folder.
    /// </summary>
    private static string ExtractFolderDescription(string folderName)
    {
        try
        {
            // Get the base directory of the assembly (where the test project is located)
            var assemblyLocation = Assembly.GetExecutingAssembly().Location;
            var projectDirectory = Path.GetDirectoryName(assemblyLocation);

            // Navigate up to find the project root (where .csproj file is located)
            while (projectDirectory != null && Directory.GetFiles(projectDirectory, "*.csproj").Length == 0)
            {
                projectDirectory = Directory.GetParent(projectDirectory)?.FullName;
            }

            if (projectDirectory == null)
            {
                return "No description available";
            }

            // Construct the path to the README.md file in the specified folder
            var readmePath = Path.Combine(projectDirectory, folderName, "README.md");

            if (!File.Exists(readmePath))
            {
                return "No description available";
            }

            // Read and parse the README.md content
            var content = File.ReadAllText(readmePath);
            return ParseMarkdownDescription(content);
        }
        catch (Exception)
        {
            // If anything goes wrong, return a default message
            return "No description available";
        }
    }

    /// <summary>
    /// Parses markdown content and extracts a clean description for display.
    /// </summary>
    private static string ParseMarkdownDescription(string markdownContent)
    {
        if (string.IsNullOrWhiteSpace(markdownContent))
        {
            return "No description available";
        }

        var lines = markdownContent.Split('\n');
        var descriptionLines = new List<string>();
        var foundFirstHeader = false;

        foreach (var line in lines)
        {
            var trimmedLine = line.Trim();

            // Skip the first header line (# Title)
            if (trimmedLine.Length > 0 && trimmedLine[0] == '#' && !foundFirstHeader)
            {
                foundFirstHeader = true;
                continue;
            }

            // Stop at subsequent headers
            if (trimmedLine.Length > 0 && trimmedLine[0] == '#' && foundFirstHeader)
            {
                break;
            }

            // Skip empty lines at the beginning
            if (!foundFirstHeader || string.IsNullOrWhiteSpace(trimmedLine))
            {
                continue;
            }

            // Add content lines
            descriptionLines.Add(trimmedLine);
        }

        if (descriptionLines.Count == 0)
        {
            return "No description available";
        }

        // Join the description lines and clean up any remaining markdown
        var description = string.Join(" ", descriptionLines);

        // Remove common markdown formatting
        description = System.Text.RegularExpressions.Regex.Replace(description, @"\*\*(.*?)\*\*", "$1"); // Bold
        description = System.Text.RegularExpressions.Regex.Replace(description, @"\*(.*?)\*", "$1");     // Italic
        description = System.Text.RegularExpressions.Regex.Replace(description, "`(.*?)`", "$1");       // Code
        description = System.Text.RegularExpressions.Regex.Replace(description, @"\[(.*?)\]\(.*?\)", "$1"); // Links

        return description.Trim();
    }
}
