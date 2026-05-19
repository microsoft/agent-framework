package agentframework_test

import (
	"testing"

	af "github.com/microsoft/agent-framework/go"
	"github.com/stretchr/testify/assert"
)

func TestChatOptions(t *testing.T) {
	t.Run("WithTemperature sets temperature", func(t *testing.T) {
		opts := af.NewChatOptions(af.WithTemperature(0.7))
		assert.NotNil(t, opts.Temperature)
		assert.InDelta(t, 0.7, *opts.Temperature, 0.001)
	})

	t.Run("WithMaxTokens sets max tokens", func(t *testing.T) {
		opts := af.NewChatOptions(af.WithMaxTokens(100))
		assert.NotNil(t, opts.MaxTokens)
		assert.Equal(t, 100, *opts.MaxTokens)
	})

	t.Run("WithModel sets model", func(t *testing.T) {
		opts := af.NewChatOptions(af.WithModel("gpt-4o"))
		assert.Equal(t, "gpt-4o", opts.Model)
	})

	t.Run("zero value has nil pointers", func(t *testing.T) {
		opts := af.NewChatOptions()
		assert.Nil(t, opts.Temperature)
		assert.Nil(t, opts.MaxTokens)
		assert.Empty(t, opts.Model)
	})

	t.Run("multiple options compose", func(t *testing.T) {
		opts := af.NewChatOptions(
			af.WithTemperature(0.5),
			af.WithMaxTokens(200),
			af.WithModel("gpt-4o"),
		)
		assert.InDelta(t, 0.5, *opts.Temperature, 0.001)
		assert.Equal(t, 200, *opts.MaxTokens)
		assert.Equal(t, "gpt-4o", opts.Model)
	})
}

func TestRunOptions(t *testing.T) {
	t.Run("WithChatOption applies to inner ChatOptions", func(t *testing.T) {
		opts := af.NewRunOptions(af.WithChatOption(af.WithTemperature(0.9)))
		assert.NotNil(t, opts.ChatOptions.Temperature)
		assert.InDelta(t, 0.9, *opts.ChatOptions.Temperature, 0.001)
	})

	t.Run("zero value has empty ChatOptions", func(t *testing.T) {
		opts := af.NewRunOptions()
		assert.Nil(t, opts.ChatOptions.Temperature)
		assert.Nil(t, opts.ChatOptions.MaxTokens)
	})
}
