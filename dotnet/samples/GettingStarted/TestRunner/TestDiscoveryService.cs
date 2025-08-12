// Copyright (c) Microsoft. All rights reserved.

using System.Reflection;

namespace GettingStarted.TestRunner;

/// <summary>
/// Service for discovering test classes, methods, and theory parameters.
/// </summary>
public class TestDiscoveryService
{
    private readonly Assembly _assembly;

    public TestDiscoveryService()
    {
        _assembly = Assembly.GetExecutingAssembly();
    }

    /// <summary>
    /// Discovers all test folders and their contents.
    /// </summary>
    public List<TestFolder> DiscoverTestFolders()
    {
        var testFolders = new List<TestFolder>();
        var testClasses = GetTestClasses();

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
                Classes = folderGroup.Select(CreateTestClass).ToList()
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
        return _assembly.GetTypes()
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
            Type = type,
            Methods = GetTestMethods(type)
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
                MethodInfo = method,
                IsTheory = method.GetCustomAttributes<TheoryAttribute>().Any(),
                TheoryData = GetTheoryData(method)
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

        return $"{method.DeclaringType?.Name}.{method.Name}({string.Join(", ", paramStrings)})";
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
}
