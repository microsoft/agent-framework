// Copyright (c) Microsoft. All rights reserved.

using System;
using Microsoft.Agents.AI.Workflows.Declarative.Entities;
using Microsoft.Bot.ObjectModel;
using Microsoft.PowerFx.Types;
using Xunit.Abstractions;

namespace Microsoft.Agents.AI.Workflows.Declarative.UnitTests.Entities;

/// <summary>
/// Tests for <see cref="EntityExtractor"/>.
/// </summary>
public sealed class EntityExtractorTest(ITestOutputHelper output) : WorkflowTest(output)
{
    [Fact]
    public void Parse_NullEntity_WithNonEmptyValue_ReturnsStringValue()
    {
        // Arrange
        EntityReference? entity = null;

        // Act
        EntityExtractionResult result = EntityExtractor.Parse(entity, "test value");

        // Assert
        Assert.True(result.IsValid);
        Assert.NotNull(result.Value);
        StringValue stringValue = Assert.IsType<StringValue>(result.Value);
        Assert.Equal("test value", stringValue.Value);
    }

    [Theory]
    [InlineData("")]
    [InlineData("   ")]
    [InlineData("\t")]
    public void Parse_NullEntity_WithEmptyValue_ReturnsBlankValue(string value)
    {
        // Arrange
        EntityReference? entity = null;

        // Act
        EntityExtractionResult result = EntityExtractor.Parse(entity, value);

        // Assert
        Assert.True(result.IsValid);
        Assert.IsType<BlankValue>(result.Value);
    }

    [Theory]
    [InlineData("true", true)]
    [InlineData("false", false)]
    [InlineData("True", true)]
    [InlineData("False", false)]
    [InlineData("TRUE", true)]
    [InlineData("FALSE", false)]
    public void Parse_BooleanEntity_ValidValue_ReturnsBoolean(string value, bool expected)
    {
        // Arrange
        EntityReference entity = CreateBooleanEntity();

        // Act
        EntityExtractionResult result = EntityExtractor.Parse(entity, value);

        // Assert
        Assert.True(result.IsValid);
        Assert.Equal(expected, (result.Value as BooleanValue)?.Value);
    }

    [Theory]
    [InlineData("invalid")]
    [InlineData("123")]
    [InlineData("yes")]
    public void Parse_BooleanEntity_InvalidValue_ReturnsError(string value)
    {
        // Arrange
        EntityReference entity = CreateBooleanEntity();

        // Act
        EntityExtractionResult result = EntityExtractor.Parse(entity, value);

        // Assert
        Assert.False(result.IsValid);
        Assert.Contains("Invalid boolean value", result.ErrorMessage);
    }

    [Theory]
    [InlineData("2023-12-25")]
    [InlineData("12/25/2023")]
    [InlineData("2023-12-25 10:30:00")]
    public void Parse_DateEntity_ValidValue_ReturnsDate(string value)
    {
        // Arrange
        EntityReference entity = CreateDateEntity();

        // Act
        EntityExtractionResult result = EntityExtractor.Parse(entity, value);

        // Assert
        Assert.True(result.IsValid);
        Assert.IsType<DateTimeValue>(result.Value);
    }

    [Theory]
    [InlineData("invalid date")]
    [InlineData("not-a-date")]
    public void Parse_DateEntity_InvalidValue_ReturnsError(string value)
    {
        // Arrange
        EntityReference entity = CreateDateEntity();

        // Act
        EntityExtractionResult result = EntityExtractor.Parse(entity, value);

        // Assert
        Assert.False(result.IsValid);
        Assert.Contains("Invalid date value", result.ErrorMessage);
    }

    [Theory]
    [InlineData("2023-12-25 10:30:00")]
    [InlineData("12/25/2023 10:30:00 AM")]
    public void Parse_DateTimeEntity_ValidValue_ReturnsDateTime(string value)
    {
        // Arrange
        EntityReference entity = CreateDateTimeEntity();

        // Act
        EntityExtractionResult result = EntityExtractor.Parse(entity, value);

        // Assert
        Assert.True(result.IsValid);
        Assert.IsType<DateTimeValue>(result.Value);
    }

    [Theory]
    [InlineData("invalid datetime")]
    public void Parse_DateTimeEntity_InvalidValue_ReturnsError(string value)
    {
        // Arrange
        EntityReference entity = CreateDateTimeEntity();

        // Act
        EntityExtractionResult result = EntityExtractor.Parse(entity, value);

        // Assert
        Assert.False(result.IsValid);
        Assert.Contains("Invalid date-time value", result.ErrorMessage);
    }

    [Theory]
    [InlineData("2023-12-25 10:30:00")]
    [InlineData("12/25/2023 10:30:00")]
    public void Parse_DateTimeNoTimeZoneEntity_ValidValue_ReturnsDateTime(string value)
    {
        // Arrange
        EntityReference entity = CreateDateTimeNoTimeZoneEntity();

        // Act
        EntityExtractionResult result = EntityExtractor.Parse(entity, value);

        // Assert
        Assert.True(result.IsValid);
        DateTimeValue dateTimeValue = Assert.IsType<DateTimeValue>(result.Value);
        DateTime dateTime = dateTimeValue.GetConvertedValue(null);
        Assert.Equal(DateTime.Parse(value), dateTime);
    }

    [Theory]
    [InlineData("01:30:00")]
    [InlineData("1:30:00")]
    [InlineData("10.12:30:45")]
    public void Parse_DurationEntity_ValidValue_ReturnsDuration(string value)
    {
        // Arrange
        EntityReference entity = CreateDurationEntity();

        // Act
        EntityExtractionResult result = EntityExtractor.Parse(entity, value);

        // Assert
        Assert.True(result.IsValid);
        Assert.IsType<TimeValue>(result.Value);
    }

    [Theory]
    [InlineData("invalid duration")]
    [InlineData("not a timespan")]
    public void Parse_DurationEntity_InvalidValue_ReturnsError(string value)
    {
        // Arrange
        EntityReference entity = CreateDurationEntity();

        // Act
        EntityExtractionResult result = EntityExtractor.Parse(entity, value);

        // Assert
        Assert.False(result.IsValid);
        Assert.Contains("Invalid duration value", result.ErrorMessage);
    }

    [Theory]
    [InlineData("test@example.com")]
    [InlineData("user.name@domain.co.uk")]
    public void Parse_EmailEntity_ValidValue_ReturnsEmail(string value)
    {
        // Arrange
        EntityReference entity = CreateEmailEntity();

        // Act
        EntityExtractionResult result = EntityExtractor.Parse(entity, value);

        // Assert
        Assert.True(result.IsValid);
        Assert.Equal(value, (result.Value as StringValue)?.Value);
    }

    [Theory]
    [InlineData("invalid email")]
    [InlineData("@example.com")]
    [InlineData("test@")]
    public void Parse_EmailEntity_InvalidValue_ReturnsError(string value)
    {
        // Arrange
        EntityReference entity = CreateEmailEntity();

        // Act
        EntityExtractionResult result = EntityExtractor.Parse(entity, value);

        // Assert
        Assert.False(result.IsValid);
        Assert.Contains("Invalid email value", result.ErrorMessage);
    }

    [Theory]
    [InlineData("123")]
    [InlineData("456.78")]
    [InlineData("-123.45")]
    [InlineData("1,234.56")]
    public void Parse_NumberEntity_ValidValue_ReturnsNumber(string value)
    {
        // Arrange
        EntityReference entity = CreateNumberEntity();

        // Act
        EntityExtractionResult result = EntityExtractor.Parse(entity, value);

        // Assert
        Assert.True(result.IsValid);
        Assert.IsType<NumberValue>(result.Value);
    }

    [Theory]
    [InlineData("not a number")]
    [InlineData("abc")]
    public void Parse_NumberEntity_InvalidValue_ReturnsError(string value)
    {
        // Arrange
        EntityReference entity = CreateNumberEntity();

        // Act
        EntityExtractionResult result = EntityExtractor.Parse(entity, value);

        // Assert
        Assert.False(result.IsValid);
        Assert.Contains("Invalid double value", result.ErrorMessage);
    }

    [Theory]
    [InlineData("25 years")]
    [InlineData("30 years old")]
    [InlineData("45")]
    public void Parse_AgeEntity_ValidValue_ReturnsString(string value)
    {
        // Arrange
        EntityReference entity = CreateAgeEntity();

        // Act
        EntityExtractionResult result = EntityExtractor.Parse(entity, value);

        // Assert
        Assert.True(result.IsValid);
        Assert.IsType<StringValue>(result.Value);
    }

    [Theory]
    [InlineData("not an age")]
    public void Parse_AgeEntity_InvalidValue_ReturnsError(string value)
    {
        // Arrange
        EntityReference entity = CreateAgeEntity();

        // Act
        EntityExtractionResult result = EntityExtractor.Parse(entity, value);

        // Assert
        Assert.False(result.IsValid);
        Assert.Contains("Invalid age value", result.ErrorMessage);
    }

    [Theory]
    [InlineData("$100")]
    [InlineData("100 dollars")]
    [InlineData("123.45")]
    public void Parse_MoneyEntity_ValidValue_ReturnsString(string value)
    {
        // Arrange
        EntityReference entity = CreateMoneyEntity();

        // Act
        EntityExtractionResult result = EntityExtractor.Parse(entity, value);

        // Assert
        Assert.True(result.IsValid);
        Assert.IsType<StringValue>(result.Value);
    }

    [Theory]
    [InlineData("not money")]
    public void Parse_MoneyEntity_InvalidValue_ReturnsError(string value)
    {
        // Arrange
        EntityReference entity = CreateMoneyEntity();

        // Act
        EntityExtractionResult result = EntityExtractor.Parse(entity, value);

        // Assert
        Assert.False(result.IsValid);
        Assert.Contains("Invalid money value", result.ErrorMessage);
    }

    [Theory]
    [InlineData("50%")]
    [InlineData("75 percent")]
    [InlineData("99.5")]
    public void Parse_PercentageEntity_ValidValue_ReturnsString(string value)
    {
        // Arrange
        EntityReference entity = CreatePercentageEntity();

        // Act
        EntityExtractionResult result = EntityExtractor.Parse(entity, value);

        // Assert
        Assert.True(result.IsValid);
        Assert.IsType<StringValue>(result.Value);
    }

    [Theory]
    [InlineData("not a percentage")]
    public void Parse_PercentageEntity_InvalidValue_ReturnsError(string value)
    {
        // Arrange
        EntityReference entity = CreatePercentageEntity();

        // Act
        EntityExtractionResult result = EntityExtractor.Parse(entity, value);

        // Assert
        Assert.False(result.IsValid);
        Assert.Contains("Invalid percentage value", result.ErrorMessage);
    }

    [Theory]
    [InlineData("60 mph")]
    [InlineData("100 km/h")]
    [InlineData("25.5")]
    public void Parse_SpeedEntity_ValidValue_ReturnsString(string value)
    {
        // Arrange
        EntityReference entity = CreateSpeedEntity();

        // Act
        EntityExtractionResult result = EntityExtractor.Parse(entity, value);

        // Assert
        Assert.True(result.IsValid);
        Assert.IsType<StringValue>(result.Value);
    }

    [Theory]
    [InlineData("not a speed")]
    public void Parse_SpeedEntity_InvalidValue_ReturnsError(string value)
    {
        // Arrange
        EntityReference entity = CreateSpeedEntity();

        // Act
        EntityExtractionResult result = EntityExtractor.Parse(entity, value);

        // Assert
        Assert.False(result.IsValid);
        Assert.Contains("Invalid speed value", result.ErrorMessage);
    }

    [Theory]
    [InlineData("72°F")]
    [InlineData("20°C")]
    [InlineData("98.6")]
    public void Parse_TemperatureEntity_ValidValue_ReturnsString(string value)
    {
        // Arrange
        EntityReference entity = CreateTemperatureEntity();

        // Act
        EntityExtractionResult result = EntityExtractor.Parse(entity, value);

        // Assert
        Assert.True(result.IsValid);
        Assert.IsType<StringValue>(result.Value);
    }

    [Theory]
    [InlineData("not a temperature")]
    public void Parse_TemperatureEntity_InvalidValue_ReturnsError(string value)
    {
        // Arrange
        EntityReference entity = CreateTemperatureEntity();

        // Act
        EntityExtractionResult result = EntityExtractor.Parse(entity, value);

        // Assert
        Assert.False(result.IsValid);
        Assert.Contains("Invalid temperature value", result.ErrorMessage);
    }

    [Theory]
    [InlineData("150 lbs")]
    [InlineData("70 kg")]
    [InlineData("180.5")]
    public void Parse_WeightEntity_ValidValue_ReturnsString(string value)
    {
        // Arrange
        EntityReference entity = CreateWeightEntity();

        // Act
        EntityExtractionResult result = EntityExtractor.Parse(entity, value);

        // Assert
        Assert.True(result.IsValid);
        Assert.IsType<StringValue>(result.Value);
    }

    [Theory]
    [InlineData("not a weight")]
    public void Parse_WeightEntity_InvalidValue_ReturnsError(string value)
    {
        // Arrange
        EntityReference entity = CreateWeightEntity();

        // Act
        EntityExtractionResult result = EntityExtractor.Parse(entity, value);

        // Assert
        Assert.False(result.IsValid);
        Assert.Contains("Invalid weight value", result.ErrorMessage);
    }

    [Theory]
    [InlineData("https://www.example.com", "https://www.example.com/")]
    [InlineData("http://test.com/path", "http://test.com/path")]
    [InlineData("ftp://files.example.com", "ftp://files.example.com/")]
    public void Parse_URLEntity_ValidValue_ReturnsURL(string value, string expected)
    {
        // Arrange
        EntityReference entity = CreateURLEntity();

        // Act
        EntityExtractionResult result = EntityExtractor.Parse(entity, value);

        // Assert
        Assert.True(result.IsValid);
        Assert.Equal(expected, (result.Value as StringValue)?.Value);
    }

    [Theory]
    [InlineData("not a url")]
    [InlineData("invalid url")]
    public void Parse_URLEntity_InvalidValue_ReturnsError(string value)
    {
        // Arrange
        EntityReference entity = CreateURLEntity();

        // Act
        EntityExtractionResult result = EntityExtractor.Parse(entity, value);

        // Assert
        Assert.False(result.IsValid);
        Assert.Contains("Invalid double value", result.ErrorMessage);
    }

    [Theory]
    [InlineData("Seattle")]
    [InlineData("New York")]
    public void Parse_CityEntity_ValidValue_ReturnsString(string value)
    {
        // Arrange
        EntityReference entity = CreateCityEntity();

        // Act
        EntityExtractionResult result = EntityExtractor.Parse(entity, value);

        // Assert
        Assert.True(result.IsValid);
        Assert.Equal(value, (result.Value as StringValue)?.Value);
    }

    [Theory]
    [InlineData("")]
    [InlineData("   ")]
    public void Parse_CityEntity_EmptyValue_ReturnsError(string value)
    {
        // Arrange
        EntityReference entity = CreateCityEntity();

        // Act
        EntityExtractionResult result = EntityExtractor.Parse(entity, value);

        // Assert
        Assert.False(result.IsValid);
        Assert.Equal("Empty value", result.ErrorMessage);
    }

    [Theory]
    [InlineData("Washington")]
    [InlineData("California")]
    public void Parse_StateEntity_ValidValue_ReturnsString(string value)
    {
        // Arrange
        EntityReference entity = CreateStateEntity();

        // Act
        EntityExtractionResult result = EntityExtractor.Parse(entity, value);

        // Assert
        Assert.True(result.IsValid);
        Assert.Equal(value, (result.Value as StringValue)?.Value);
    }

    [Theory]
    [InlineData("USA")]
    [InlineData("United Kingdom")]
    public void Parse_CountryOrRegionEntity_ValidValue_ReturnsString(string value)
    {
        // Arrange
        EntityReference entity = CreateCountryOrRegionEntity();

        // Act
        EntityExtractionResult result = EntityExtractor.Parse(entity, value);

        // Assert
        Assert.True(result.IsValid);
        Assert.Equal(value, (result.Value as StringValue)?.Value);
    }

    [Theory]
    [InlineData("Europe")]
    [InlineData("Asia")]
    public void Parse_ContinentEntity_ValidValue_ReturnsString(string value)
    {
        // Arrange
        EntityReference entity = CreateContinentEntity();

        // Act
        EntityExtractionResult result = EntityExtractor.Parse(entity, value);

        // Assert
        Assert.True(result.IsValid);
        Assert.Equal(value, (result.Value as StringValue)?.Value);
    }

    [Theory]
    [InlineData("123 Main Street")]
    [InlineData("456 Oak Avenue")]
    public void Parse_StreetAddressEntity_ValidValue_ReturnsString(string value)
    {
        // Arrange
        EntityReference entity = CreateStreetAddressEntity();

        // Act
        EntityExtractionResult result = EntityExtractor.Parse(entity, value);

        // Assert
        Assert.True(result.IsValid);
        Assert.Equal(value, (result.Value as StringValue)?.Value);
    }

    [Theory]
    [InlineData("+1-555-1234")]
    [InlineData("(555) 123-4567")]
    public void Parse_PhoneNumberEntity_ValidValue_ReturnsString(string value)
    {
        // Arrange
        EntityReference entity = CreatePhoneNumberEntity();

        // Act
        EntityExtractionResult result = EntityExtractor.Parse(entity, value);

        // Assert
        Assert.True(result.IsValid);
        Assert.Equal(value, (result.Value as StringValue)?.Value);
    }

    [Theory]
    [InlineData("red")]
    [InlineData("blue")]
    public void Parse_ColorEntity_ValidValue_ReturnsString(string value)
    {
        // Arrange
        EntityReference entity = CreateColorEntity();

        // Act
        EntityExtractionResult result = EntityExtractor.Parse(entity, value);

        // Assert
        Assert.True(result.IsValid);
        Assert.Equal(value, (result.Value as StringValue)?.Value);
    }

    [Theory]
    [InlineData("English")]
    [InlineData("Spanish")]
    public void Parse_LanguageEntity_ValidValue_ReturnsString(string value)
    {
        // Arrange
        EntityReference entity = CreateLanguageEntity();

        // Act
        EntityExtractionResult result = EntityExtractor.Parse(entity, value);

        // Assert
        Assert.True(result.IsValid);
        Assert.Equal(value, (result.Value as StringValue)?.Value);
    }

    [Theory]
    [InlineData("Conference")]
    [InlineData("Meeting")]
    public void Parse_EventEntity_ValidValue_ReturnsString(string value)
    {
        // Arrange
        EntityReference entity = CreateEventEntity();

        // Act
        EntityExtractionResult result = EntityExtractor.Parse(entity, value);

        // Assert
        Assert.True(result.IsValid);
        Assert.Equal(value, (result.Value as StringValue)?.Value);
    }

    [Theory]
    [InlineData("Starbucks")]
    [InlineData("Museum")]
    public void Parse_PointOfInterestEntity_ValidValue_ReturnsString(string value)
    {
        // Arrange
        EntityReference entity = CreatePointOfInterestEntity();

        // Act
        EntityExtractionResult result = EntityExtractor.Parse(entity, value);

        // Assert
        Assert.True(result.IsValid);
        Assert.Equal(value, (result.Value as StringValue)?.Value);
    }

    [Theory]
    [InlineData("test string")]
    [InlineData("any text")]
    public void Parse_StringEntity_ValidValue_ReturnsString(string value)
    {
        // Arrange
        EntityReference entity = CreateStringEntity();

        // Act
        EntityExtractionResult result = EntityExtractor.Parse(entity, value);

        // Assert
        Assert.True(result.IsValid);
        Assert.Equal(value, (result.Value as StringValue)?.Value);
    }

    private static BooleanPrebuiltEntity CreateBooleanEntity() =>
        new BooleanPrebuiltEntity.Builder().Build();

    private static DatePrebuiltEntity CreateDateEntity() =>
        new DatePrebuiltEntity.Builder().Build();

    private static DateTimePrebuiltEntity CreateDateTimeEntity() =>
        new DateTimePrebuiltEntity.Builder().Build();

    private static DateTimeNoTimeZonePrebuiltEntity CreateDateTimeNoTimeZoneEntity() =>
        new DateTimeNoTimeZonePrebuiltEntity.Builder().Build();

    private static DurationPrebuiltEntity CreateDurationEntity() =>
        new DurationPrebuiltEntity.Builder().Build();

    private static EmailPrebuiltEntity CreateEmailEntity() =>
        new EmailPrebuiltEntity.Builder().Build();

    private static NumberPrebuiltEntity CreateNumberEntity() =>
        new NumberPrebuiltEntity.Builder().Build();

    private static AgePrebuiltEntity CreateAgeEntity() =>
        new AgePrebuiltEntity.Builder().Build();

    private static MoneyPrebuiltEntity CreateMoneyEntity() =>
        new MoneyPrebuiltEntity.Builder().Build();

    private static PercentagePrebuiltEntity CreatePercentageEntity() =>
        new PercentagePrebuiltEntity.Builder().Build();

    private static SpeedPrebuiltEntity CreateSpeedEntity() =>
        new SpeedPrebuiltEntity.Builder().Build();

    private static TemperaturePrebuiltEntity CreateTemperatureEntity() =>
        new TemperaturePrebuiltEntity.Builder().Build();

    private static WeightPrebuiltEntity CreateWeightEntity() =>
        new WeightPrebuiltEntity.Builder().Build();

    private static URLPrebuiltEntity CreateURLEntity() =>
        new URLPrebuiltEntity.Builder().Build();

    private static CityPrebuiltEntity CreateCityEntity() =>
        new CityPrebuiltEntity.Builder().Build();

    private static StatePrebuiltEntity CreateStateEntity() =>
        new StatePrebuiltEntity.Builder().Build();

    private static CountryOrRegionPrebuiltEntity CreateCountryOrRegionEntity() =>
        new CountryOrRegionPrebuiltEntity.Builder().Build();

    private static ContinentPrebuiltEntity CreateContinentEntity() =>
        new ContinentPrebuiltEntity.Builder().Build();

    private static StreetAddressPrebuiltEntity CreateStreetAddressEntity() =>
        new StreetAddressPrebuiltEntity.Builder().Build();

    private static PhoneNumberPrebuiltEntity CreatePhoneNumberEntity() =>
        new PhoneNumberPrebuiltEntity.Builder().Build();

    private static ColorPrebuiltEntity CreateColorEntity() =>
        new ColorPrebuiltEntity.Builder().Build();

    private static LanguagePrebuiltEntity CreateLanguageEntity() =>
        new LanguagePrebuiltEntity.Builder().Build();

    private static EventPrebuiltEntity CreateEventEntity() =>
        new EventPrebuiltEntity.Builder().Build();

    private static PointOfInterestPrebuiltEntity CreatePointOfInterestEntity() =>
        new PointOfInterestPrebuiltEntity.Builder().Build();

    private static StringPrebuiltEntity CreateStringEntity() =>
        new StringPrebuiltEntity.Builder().Build();
}
