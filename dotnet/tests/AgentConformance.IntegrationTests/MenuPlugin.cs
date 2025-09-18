// Copyright (c) Microsoft. All rights reserved.

using System.ComponentModel;

namespace AgentConformance.IntegrationTests;

#pragma warning disable CA1812 // Avoid uninstantiated internal classes

/// <summary>
/// A test plugin used to verify function invocation.
/// </summary>
internal static class MenuPlugin
{
    [Description("Provides a list of specials from the menu.")]
    public static string GetSpecials() => """
        Special Soup: Clam Chowder
        Special Salad: Cobb Salad
        Special Drink: Chai Tea
        """;

    [Description("Provides the price of the requested menu item.")]
    public static string GetItemPrice(
        [Description("The name of the menu item.")]
        string menuItem) => "$9.99";
}
