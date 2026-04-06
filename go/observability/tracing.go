package observability

import (
	"context"

	af "github.com/microsoft/agent-framework/go"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/codes"
	"go.opentelemetry.io/otel/trace"
)

func NewTracingAgentMiddleware(tp trace.TracerProvider) af.AgentMiddleware {
	tracer := tp.Tracer("agentframework")
	return af.AgentMiddlewareFunc(func(ctx context.Context, ac *af.AgentContext, next af.AgentHandler) error {
		ctx, span := tracer.Start(ctx, "agent.run",
			trace.WithAttributes(
				attribute.String("gen_ai.agent.name", ac.Agent.Name()),
				attribute.String("gen_ai.agent.id", ac.Agent.ID()),
				attribute.Int("gen_ai.request.message_count", len(ac.Messages)),
			),
		)
		defer span.End()

		err := next(ctx, ac)
		if err != nil {
			span.RecordError(err)
			span.SetStatus(codes.Error, err.Error())
			return err
		}

		if ac.Response != nil && ac.Response.Usage != nil {
			span.SetAttributes(
				attribute.Int("gen_ai.usage.input_tokens", ac.Response.Usage.InputTokens),
				attribute.Int("gen_ai.usage.output_tokens", ac.Response.Usage.OutputTokens),
			)
		}
		return nil
	})
}

func NewTracingChatMiddleware(tp trace.TracerProvider) af.ChatMiddleware {
	tracer := tp.Tracer("agentframework")
	return af.ChatMiddlewareFunc(func(ctx context.Context, cc *af.ChatContext, next af.ChatHandler) error {
		ctx, span := tracer.Start(ctx, "chat.get_response",
			trace.WithAttributes(
				attribute.Int("gen_ai.request.message_count", len(cc.Messages)),
			),
		)
		defer span.End()

		if cc.Options != nil && cc.Options.Model != "" {
			span.SetAttributes(attribute.String("gen_ai.request.model", cc.Options.Model))
		}

		err := next(ctx, cc)
		if err != nil {
			span.RecordError(err)
			span.SetStatus(codes.Error, err.Error())
			return err
		}

		if cc.Response != nil && cc.Response.Usage != nil {
			span.SetAttributes(
				attribute.Int("gen_ai.usage.input_tokens", cc.Response.Usage.InputTokens),
				attribute.Int("gen_ai.usage.output_tokens", cc.Response.Usage.OutputTokens),
			)
		}
		if cc.Response != nil {
			span.SetAttributes(
				attribute.String("gen_ai.response.id", cc.Response.ResponseID),
				attribute.Int("gen_ai.response.message_count", len(cc.Response.Messages)),
			)
		}
		return nil
	})
}
