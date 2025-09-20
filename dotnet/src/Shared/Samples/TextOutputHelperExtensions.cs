// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Shared.SampleUtilities;

/// <summary>
/// Extensions for <see cref="ITestOutputHelper"/> to make it more Console friendly.
/// </summary>
public static class TextOutputHelperExtensions
{
    /// <summary>
    /// Current interface ITestOutputHelper does not have a WriteLine method that takes an object. This extension method adds it to make it analogous to Console.WriteLine when used in Console apps.
    /// </summary>
    /// <param name="testOutputHelper">Target <see cref="ITestOutputHelper"/></param>
    /// <param name="target">Target object to write</param>
    public static void WriteLine(this ITestOutputHelper testOutputHelper, object target) =>
        testOutputHelper.WriteLine(target.ToString());

    /// <summary>
    /// Current interface ITestOutputHelper does not have a WriteLine method that takes no parameters. This extension method adds it to make it analogous to Console.WriteLine when used in Console apps.
    /// </summary>
    /// <param name="testOutputHelper">Target <see cref="ITestOutputHelper"/></param>
    public static void WriteLine(this ITestOutputHelper testOutputHelper) =>
        testOutputHelper.WriteLine(string.Empty);

    /// <summary>
    /// Current interface ITestOutputHelper does not have a Write method that takes no parameters. This extension method adds it to make it analogous to Console.Write when used in Console apps.
    /// </summary>
    /// <param name="testOutputHelper">Target <see cref="ITestOutputHelper"/></param>
    public static void Write(this ITestOutputHelper testOutputHelper) =>
        testOutputHelper.WriteLine(string.Empty);

    /// <summary>
    /// Current interface ITestOutputHelper does not have a Write method. This extension method adds it to make it analogous to Console.Write when used in Console apps.
    /// </summary>
    /// <param name="testOutputHelper">Target <see cref="ITestOutputHelper"/></param>
    /// <param name="target">Target object to write</param>
    public static void Write(this ITestOutputHelper testOutputHelper, object target) =>
        testOutputHelper.WriteLine(target.ToString());
}
