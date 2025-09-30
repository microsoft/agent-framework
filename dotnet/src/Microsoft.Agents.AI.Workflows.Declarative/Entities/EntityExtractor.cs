// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Net.Mail;
using System.Text.RegularExpressions;
using Microsoft.Bot.ObjectModel;
using Microsoft.PowerFx.Types;

namespace Microsoft.Agents.AI.Workflows.Declarative.Entities;

internal static partial class EntityExtractor
{
    private const string NumberUnitRegExExpression = @"(?<value>[-+]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?|\d*\.\d+)";

#if NET
    [GeneratedRegex(NumberUnitRegExExpression, RegexOptions.IgnoreCase)]
    private static partial Regex NumberUnitRegex();
#else
    private static Regex NumberUnitRegex() => s_numberUnitRegex;
    private static readonly Regex s_numberUnitRegex = new(NumberUnitRegExExpression, RegexOptions.IgnoreCase | RegexOptions.Compiled);
#endif

    public static EntityExtractionResult Parse(EntityReference? entity, string value) =>
        entity switch
        {
            null => UndefinedEntity(value),
            AgePrebuiltEntity => TryParseNumberUnit(value, "age"),
            BooleanPrebuiltEntity => TryParseBoolean(value),
            CityPrebuiltEntity => TryParseString(value),
            ColorPrebuiltEntity => TryParseString(value),
            ContinentPrebuiltEntity => TryParseString(value),
            CountryOrRegionPrebuiltEntity => TryParseString(value),
            DatePrebuiltEntity => TryParseDate(value),
            DateTimeNoTimeZonePrebuiltEntity => TryParseDateTimeNoTimeZone(value),
            DateTimePrebuiltEntity => TryParseDateTime(value),
            DurationPrebuiltEntity => TryParseDuration(value),
            EmailPrebuiltEntity => TryParseEmail(value),
            EventPrebuiltEntity => TryParseString(value),
            LanguagePrebuiltEntity => TryParseString(value),
            MoneyPrebuiltEntity => TryParseNumberUnit(value, "money"),
            NumberPrebuiltEntity => TryParseNumber(value),
            PercentagePrebuiltEntity => TryParseNumberUnit(value, "percentage"),
            PhoneNumberPrebuiltEntity => TryParseString(value),
            PointOfInterestPrebuiltEntity => TryParseString(value),
            SpeedPrebuiltEntity => TryParseNumberUnit(value, "speed"),
            StatePrebuiltEntity => TryParseString(value),
            StreetAddressPrebuiltEntity => TryParseString(value),
            StringPrebuiltEntity => TryParseString(value),
            TemperaturePrebuiltEntity => TryParseNumberUnit(value, "temperature"),
            URLPrebuiltEntity => TryParseURL(value),
            WeightPrebuiltEntity => TryParseNumberUnit(value, "weight"),
            _ => UnsupportedEntity(entity),
        };

    private static EntityExtractionResult TryParseBoolean(string value)
    {
        if (bool.TryParse(value, out bool parsedValue))
        {
            return new EntityExtractionResult(FormulaValue.New(parsedValue));
        }

        return new EntityExtractionResult($"Invalid boolean value: {value}");
    }

    private static EntityExtractionResult TryParseDate(string value)
    {
        if (DateTime.TryParse(value, out DateTime parsedValue))
        {
            return new EntityExtractionResult(FormulaValue.New(parsedValue.Date));
        }

        return new EntityExtractionResult($"Invalid date value: {value}");
    }

    private static EntityExtractionResult TryParseDateTimeNoTimeZone(string value)
    {
        if (DateTime.TryParse(value, out DateTime parsedValue))
        {
            return new EntityExtractionResult(
                FormulaValue.New(
                    DateTime.SpecifyKind(parsedValue, DateTimeKind.Unspecified)));
        }

        return new EntityExtractionResult($"Invalid date value: {value}");
    }

    private static EntityExtractionResult TryParseDateTime(string value)
    {
        if (DateTime.TryParse(value, out DateTime parsedValue))
        {
            return new EntityExtractionResult(FormulaValue.New(parsedValue));
        }

        return new EntityExtractionResult($"Invalid date-time value: {value}");
    }

    private static EntityExtractionResult TryParseDuration(string value)
    {
        if (TimeSpan.TryParse(value, out TimeSpan parsedValue))
        {
            return new EntityExtractionResult(FormulaValue.New(parsedValue));
        }

        return new EntityExtractionResult($"Invalid duration value: {value}");
    }

    private static EntityExtractionResult TryParseEmail(string value)
    {
        try
        {
            MailAddress parsedValue = new(value);
            return new EntityExtractionResult(FormulaValue.New(parsedValue.Address));
        }
        catch
        {
            return new EntityExtractionResult($"Invalid email value: {value}");
        }
    }

    private static EntityExtractionResult TryParseNumberUnit(string value, string type)
    {
        Match m = NumberUnitRegex().Match(value);
        if (m.Success)
        {
            return new EntityExtractionResult(FormulaValue.New(m.Groups[0].Value));
        }

        return new EntityExtractionResult($"Invalid {type} value: {value}");
    }

    private static EntityExtractionResult TryParseNumber(string value)
    {
        if (double.TryParse(value, out double parsedValue))
        {
            return new EntityExtractionResult(FormulaValue.New(parsedValue));
        }

        return new EntityExtractionResult($"Invalid double value: {value}");
    }

    private static EntityExtractionResult TryParseString(string value)
    {
        if (!string.IsNullOrWhiteSpace(value))
        {
            return new EntityExtractionResult(FormulaValue.New(value));
        }

        return new EntityExtractionResult("Empty value");
    }

    private static EntityExtractionResult TryParseURL(string value)
    {
        if (Uri.TryCreate(value, UriKind.Absolute, out Uri? uriResult))
        {
            return new EntityExtractionResult(FormulaValue.New(uriResult.AbsoluteUri));
        }

        return new EntityExtractionResult($"Invalid double value: {value}");
    }

    private static EntityExtractionResult UndefinedEntity(string value)
    {
        if (string.IsNullOrWhiteSpace(value))
        {
            return new EntityExtractionResult(FormulaValue.NewBlank());
        }

        return new EntityExtractionResult(FormulaValue.New(value));
    }

    private static EntityExtractionResult UnsupportedEntity(EntityReference entity) =>
        new($"Unsupported entity: {entity.GetType().Name}");
}
