# Copyright (c) Microsoft. All rights reserved.

"""Tests for Bedrock Knowledge Base tool and provider."""

import asyncio
from unittest.mock import MagicMock, patch

from agent_framework import FunctionTool
from agent_framework._sessions import ContextProvider


class TestBedrockKnowledgeBaseTool:
    def test_is_function_tool_subclass(self):
        from agent_framework_bedrock._knowledge_base import BedrockKnowledgeBaseTool

        mock_client = MagicMock()
        tool = BedrockKnowledgeBaseTool(knowledge_base_id="TEST_KB", client=mock_client)
        assert isinstance(tool, FunctionTool)

    def test_tool_has_correct_name_and_description(self):
        from agent_framework_bedrock._knowledge_base import BedrockKnowledgeBaseTool

        mock_client = MagicMock()
        tool = BedrockKnowledgeBaseTool(knowledge_base_id="TEST_KB", client=mock_client)
        assert tool.name == "bedrock_knowledge_base"
        assert "knowledge" in tool.description.lower()

    def test_retrieve_returns_formatted_results(self):
        from agent_framework_bedrock._knowledge_base import BedrockKnowledgeBaseTool

        mock_client = MagicMock()
        mock_client.retrieve.return_value = {
            "retrievalResults": [
                {"content": {"text": "Result 1"}, "score": 0.95, "location": {"s3Location": {"uri": "s3://b/k"}}},
                {"content": {"text": "Result 2"}, "score": 0.80, "location": {"webLocation": {"url": "https://example.com"}}},
            ]
        }

        tool = BedrockKnowledgeBaseTool(
            knowledge_base_id="TEST_KB",
            region_name="us-west-2",
            use_agentic_retrieval=False,
            client=mock_client,
        )

        result = asyncio.run(tool._retrieve(query="test query"))
        assert "Result 1" in result
        assert "Result 2" in result
        assert "s3://b/k" in result
        assert "0.950" in result

    def test_agentic_with_fallback(self):
        from agent_framework_bedrock._knowledge_base import BedrockKnowledgeBaseTool

        mock_client = MagicMock()
        mock_client.agentic_retrieve_stream.side_effect = Exception("Not available")
        mock_client.retrieve.return_value = {"retrievalResults": [
            {"content": {"text": "Fallback"}, "score": 0.7, "location": {}},
        ]}

        tool = BedrockKnowledgeBaseTool(
            knowledge_base_id="TEST_KB",
            use_agentic_retrieval=True,
            client=mock_client,
        )

        result = asyncio.run(tool._retrieve(query="test"))
        assert "Fallback" in result
        mock_client.agentic_retrieve_stream.assert_called_once()
        mock_client.retrieve.assert_called_once()

    def test_agentic_retrieve_success(self):
        from agent_framework_bedrock._knowledge_base import BedrockKnowledgeBaseTool

        mock_client = MagicMock()
        mock_client.agentic_retrieve_stream.return_value = {
            "stream": [
                {"result": {"results": [
                    {"content": {"text": "Agentic result"}, "score": 0.99, "location": {"s3Location": {"uri": "s3://b/doc"}}},
                ]}}
            ]
        }

        tool = BedrockKnowledgeBaseTool(
            knowledge_base_id="TEST_KB",
            use_agentic_retrieval=True,
            client=mock_client,
        )

        result = asyncio.run(tool._retrieve(query="complex question"))
        assert "Agentic result" in result
        assert "s3://b/doc" in result
        mock_client.retrieve.assert_not_called()

    def test_client_uses_get_user_agent(self):
        from agent_framework_bedrock._knowledge_base import BedrockKnowledgeBaseTool

        with patch("agent_framework_bedrock._knowledge_base.boto3.client") as mock_boto:
            mock_boto.return_value = MagicMock()
            _ = BedrockKnowledgeBaseTool(knowledge_base_id="TEST_KB", region_name="us-west-2")
            config = mock_boto.call_args.kwargs["config"]
            ua = getattr(config, "user_agent_extra", "")
            assert "bedrock-kb" in ua

    def test_no_results_returns_message(self):
        from agent_framework_bedrock._knowledge_base import BedrockKnowledgeBaseTool

        mock_client = MagicMock()
        mock_client.retrieve.return_value = {"retrievalResults": []}

        tool = BedrockKnowledgeBaseTool(
            knowledge_base_id="TEST_KB",
            use_agentic_retrieval=False,
            client=mock_client,
        )

        result = asyncio.run(tool._retrieve(query="unknown"))
        assert "No relevant documents found" in result


class TestBedrockKnowledgeBaseProvider:
    def test_is_context_provider_subclass(self):
        from agent_framework_bedrock._knowledge_base_provider import BedrockKnowledgeBaseProvider

        mock_client = MagicMock()
        provider = BedrockKnowledgeBaseProvider(knowledge_base_id="TEST_KB", client=mock_client)
        assert isinstance(provider, ContextProvider)

    def test_has_source_id(self):
        from agent_framework_bedrock._knowledge_base_provider import BedrockKnowledgeBaseProvider

        mock_client = MagicMock()
        provider = BedrockKnowledgeBaseProvider(
            knowledge_base_id="TEST_KB", source_id="my-kb", client=mock_client
        )
        assert provider.source_id == "my-kb"

    def test_retrieve_returns_formatted_context(self):
        from agent_framework_bedrock._knowledge_base_provider import BedrockKnowledgeBaseProvider

        mock_client = MagicMock()
        mock_client.retrieve.return_value = {
            "retrievalResults": [
                {"content": {"text": "Passage 1"}, "score": 0.9, "location": {"s3Location": {"uri": "s3://b/doc.pdf"}}},
                {"content": {"text": "Passage 2"}, "score": 0.5, "location": {}},
            ]
        }

        provider = BedrockKnowledgeBaseProvider(
            knowledge_base_id="TEST_KB",
            client=mock_client,
        )

        context = asyncio.run(provider._retrieve("test query"))
        assert "Passage 1" in context
        assert "s3://b/doc.pdf" in context

    def test_min_score_filtering(self):
        from agent_framework_bedrock._knowledge_base_provider import BedrockKnowledgeBaseProvider

        mock_client = MagicMock()
        mock_client.retrieve.return_value = {
            "retrievalResults": [
                {"content": {"text": "High"}, "score": 0.9, "location": {}},
                {"content": {"text": "Low"}, "score": 0.2, "location": {}},
            ]
        }

        provider = BedrockKnowledgeBaseProvider(
            knowledge_base_id="TEST_KB",
            min_score=0.5,
            client=mock_client,
        )

        context = asyncio.run(provider._retrieve("test"))
        assert "High" in context
        assert "Low" not in context

    def test_has_before_run_method(self):
        from agent_framework_bedrock._knowledge_base_provider import BedrockKnowledgeBaseProvider

        mock_client = MagicMock()
        provider = BedrockKnowledgeBaseProvider(knowledge_base_id="TEST_KB", client=mock_client)
        assert hasattr(provider, "before_run")
        assert asyncio.iscoroutinefunction(provider.before_run)

    def test_before_run_injects_context(self):
        from agent_framework import Message
        from agent_framework._sessions import SessionContext
        from agent_framework_bedrock._knowledge_base_provider import BedrockKnowledgeBaseProvider

        mock_client = MagicMock()
        mock_client.retrieve.return_value = {
            "retrievalResults": [
                {"content": {"text": "Relevant passage"}, "score": 0.9, "location": {"s3Location": {"uri": "s3://b/doc"}}},
            ]
        }

        provider = BedrockKnowledgeBaseProvider(
            knowledge_base_id="TEST_KB",
            client=mock_client,
        )

        # Create a SessionContext with an input message
        context = SessionContext(
            input_messages=[Message(role="user", contents=["What is our policy?"])],
        )

        # Verify context_messages is empty before
        assert len(context.context_messages) == 0

        # Run before_run
        asyncio.run(provider.before_run(
            agent=MagicMock(),
            session=MagicMock(),
            context=context,
            state={},
        ))

        # Verify context was injected via extend_messages
        assert "bedrock-kb" in context.context_messages
        injected = context.context_messages["bedrock-kb"]
        assert len(injected) == 1
        assert "Relevant passage" in injected[0].text
        assert "s3://b/doc" in injected[0].text

    def test_before_run_skips_empty_input(self):
        from agent_framework._sessions import SessionContext
        from agent_framework_bedrock._knowledge_base_provider import BedrockKnowledgeBaseProvider

        mock_client = MagicMock()
        provider = BedrockKnowledgeBaseProvider(knowledge_base_id="TEST_KB", client=mock_client)

        # Empty input messages
        context = SessionContext(input_messages=[])

        asyncio.run(provider.before_run(
            agent=MagicMock(),
            session=MagicMock(),
            context=context,
            state={},
        ))

        # Should not call retrieve
        mock_client.retrieve.assert_not_called()
        assert len(context.context_messages) == 0
