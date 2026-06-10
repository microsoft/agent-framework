// Copyright (c) Microsoft. All rights reserved.

using System.ComponentModel;
using System.Text.Json.Nodes;
using Microsoft.Agents.AI.AGUI.A2UI;
using Microsoft.Extensions.AI;

namespace AGUIDojoServer.A2UI;

/// <summary>
/// Fixed-schema A2UI tools: pre-built component layouts for flight and hotel cards.
/// The agent only supplies the data; layout/styling is fixed in code. Demonstrates the
/// "controlled gen-UI" pattern — the author owns the UI shape, the agent owns the data.
/// </summary>
internal static class A2UIFixedSchemaTools
{
    private const string CatalogId = "https://a2ui.org/demos/dojo/fixed_catalog.json";
    private const string FlightSurfaceId = "flight-search-results";
    private const string HotelSurfaceId = "hotel-search-results";

    /// <summary>Creates the <c>search_flights</c> tool.</summary>
    public static AIFunction CreateSearchFlightsTool() => AIFunctionFactory.Create(
        SearchFlights,
        "search_flights",
        "Search for flights and display the results as rich cards. Each flight " +
        "must have: id, airline (e.g. 'United Airlines'), airlineLogo (use Google " +
        "favicon API like 'https://www.google.com/s2/favicons?domain=united.com&sz=128'), " +
        "flightNumber, origin, destination, date (e.g. 'Tue, Mar 18'), departureTime, " +
        "arrivalTime, duration (e.g. '4h 25m'), status ('On Time' or 'Delayed'), " +
        "and price (e.g. '$289').");

    /// <summary>Creates the <c>search_hotels</c> tool.</summary>
    public static AIFunction CreateSearchHotelsTool() => AIFunctionFactory.Create(
        SearchHotels,
        "search_hotels",
        "Search for hotels and display the results as rich cards with star ratings. " +
        "Each hotel must have: id, name (e.g. 'The Plaza'), location " +
        "(e.g. 'Midtown Manhattan, NYC'), rating (float 0-5, e.g. 4.5), and " +
        "price (per night, e.g. '$350'). Generate 3-4 realistic results.");

    private static string SearchFlights(
        [Description("Array of flight result objects.")] JsonArray flights)
        => RenderOperations(FlightSurfaceId, FlightSchema(), "flights", flights);

    private static string SearchHotels(
        [Description("Array of hotel result objects.")] JsonArray hotels)
        => RenderOperations(HotelSurfaceId, HotelSchema(), "hotels", hotels);

    /// <summary>
    /// Wraps the fixed layout + agent-supplied data as the A2UI operations envelope the
    /// AG-UI A2UI middleware detects in tool results.
    /// </summary>
    private static string RenderOperations(string surfaceId, JsonArray schema, string dataKey, JsonArray items)
        => A2UIToolkit.WrapAsOperationsEnvelope(A2UIToolkit.AssembleOps(
            "create",
            surfaceId,
            CatalogId,
            schema,
            new JsonObject { [dataKey] = items.DeepClone() }));

    // Flight search layout — the agent supplies the `flights` array; rendering is fixed.
    private static JsonArray FlightSchema() => new(
        new JsonObject
        {
            ["id"] = "root",
            ["component"] = "Row",
            ["children"] = new JsonObject { ["componentId"] = "flight-card", ["path"] = "/flights" },
            ["gap"] = 16,
        },
        new JsonObject
        {
            ["id"] = "flight-card",
            ["component"] = "FlightCard",
            ["airline"] = new JsonObject { ["path"] = "airline" },
            ["airlineLogo"] = new JsonObject { ["path"] = "airlineLogo" },
            ["flightNumber"] = new JsonObject { ["path"] = "flightNumber" },
            ["origin"] = new JsonObject { ["path"] = "origin" },
            ["destination"] = new JsonObject { ["path"] = "destination" },
            ["date"] = new JsonObject { ["path"] = "date" },
            ["departureTime"] = new JsonObject { ["path"] = "departureTime" },
            ["arrivalTime"] = new JsonObject { ["path"] = "arrivalTime" },
            ["duration"] = new JsonObject { ["path"] = "duration" },
            ["status"] = new JsonObject { ["path"] = "status" },
            ["price"] = new JsonObject { ["path"] = "price" },
            ["action"] = new JsonObject
            {
                ["event"] = new JsonObject
                {
                    ["name"] = "book_flight",
                    ["context"] = new JsonObject
                    {
                        ["flightNumber"] = new JsonObject { ["path"] = "flightNumber" },
                        ["origin"] = new JsonObject { ["path"] = "origin" },
                        ["destination"] = new JsonObject { ["path"] = "destination" },
                        ["price"] = new JsonObject { ["path"] = "price" },
                    },
                },
            },
        });

    // Hotel search layout — the agent supplies the `hotels` array; rendering is fixed.
    private static JsonArray HotelSchema() => new(
        new JsonObject
        {
            ["id"] = "root",
            ["component"] = "Row",
            ["children"] = new JsonObject { ["componentId"] = "hotel-card", ["path"] = "/hotels" },
            ["gap"] = 16,
        },
        new JsonObject
        {
            ["id"] = "hotel-card",
            ["component"] = "HotelCard",
            ["name"] = new JsonObject { ["path"] = "name" },
            ["location"] = new JsonObject { ["path"] = "location" },
            ["rating"] = new JsonObject { ["path"] = "rating" },
            ["pricePerNight"] = new JsonObject { ["path"] = "price" },
            ["action"] = new JsonObject
            {
                ["event"] = new JsonObject
                {
                    ["name"] = "book_hotel",
                    ["context"] = new JsonObject
                    {
                        ["hotelName"] = new JsonObject { ["path"] = "name" },
                        ["price"] = new JsonObject { ["path"] = "price" },
                    },
                },
            },
        });
}
