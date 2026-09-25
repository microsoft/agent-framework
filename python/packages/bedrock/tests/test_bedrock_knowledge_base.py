# Copyright (c) Microsoft. All rights reserved.

"""Tests for Bedrock Knowledge Base tool and provider."""

import asyncio
from unittest.mock import MagicMock, patch

import pytest
from agent_framework import ContextProvider, FunctionTool


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
                {
                    "content": {"text": "Result 2"},
                    "score": 0.80,
                    "location": {"webLocation": {"url": "https://example.com"}},
                },
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
        mock_client.retrieve.return_value = {
            "retrievalResults": [
                {"content": {"text": "Fallback"}, "score": 0.7, "location": {}},
            ]
        }

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
                {
                    "result": {
                        "results": [
                            # AgenticRetrieveStream schema: content/metadata/sourceRetriever
                            # (no score, no location). Source URI comes from metadata._source_uri.
                            {
                                "content": {"mimeType": "text/plain", "text": "Agentic result"},
                                "metadata": {"_source_uri": "s3://b/doc", "_document_title": "Doc"},
                                "sourceRetriever": {"identifier": "TEST_KB"},
                            },
                        ]
                    }
                }
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
        # Agentic results must not fabricate a numeric score
        assert "score:" not in result
        # Response generation must be disabled (tool returns passages only)
        assert mock_client.agentic_retrieve_stream.call_args.kwargs["generateResponse"] is False
        mock_client.retrieve.assert_not_called()

    def test_client_uses_get_user_agent(self):
        from agent_framework_bedrock._knowledge_base import BedrockKnowledgeBaseTool

        # The client is built via a boto3 Session (shared _build_kb_client), so patch the
        # Session and assert the user-agent extra is set on the session.client() config.
        with patch("agent_framework_bedrock._knowledge_base.Boto3Session") as mock_session_cls:
            mock_session = MagicMock()
            mock_session_cls.return_value = mock_session
            _ = BedrockKnowledgeBaseTool(knowledge_base_id="TEST_KB", region_name="us-west-2")
            config = mock_session.client.call_args.kwargs["config"]
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

    def test_invoke_end_to_end(self):
        """Test the public FunctionTool.invoke() path with argument validation."""
        from agent_framework_bedrock._knowledge_base import BedrockKnowledgeBaseTool

        mock_client = MagicMock()
        mock_client.retrieve.return_value = {
            "retrievalResults": [
                {
                    "content": {"text": "Invoked result"},
                    "score": 0.88,
                    "location": {"s3Location": {"uri": "s3://b/invoke"}},
                }
            ]
        }

        tool = BedrockKnowledgeBaseTool(
            knowledge_base_id="TEST_KB",
            use_agentic_retrieval=False,
            client=mock_client,
        )

        # Call via the public invoke() API — exercises argument validation + Content parsing
        result = asyncio.run(tool.invoke(arguments={"query": "test invoke"}))
        # invoke() returns list[Content] by default
        assert len(result) > 0
        assert "Invoked result" in (result[0].text or "")


class TestExtractContentText:
    """Tests for the shared _extract_content_text helper (TEXT and ROW content types)."""

    def test_text_content(self):
        from agent_framework_bedrock._knowledge_base import _extract_content_text

        result = {"content": {"type": "TEXT", "text": "hello world"}}
        assert _extract_content_text(result) == "hello world"

    def test_text_content_default_type(self):
        from agent_framework_bedrock._knowledge_base import _extract_content_text

        # type omitted defaults to TEXT
        assert _extract_content_text({"content": {"text": "no type field"}}) == "no type field"

    def test_row_content_renders_columns(self):
        """A SQL knowledge base returns ROW content with no `text` field.

        Reading only `content.text` would emit an empty passage and discard every
        column value; the helper must render the row's columns instead.
        """
        from agent_framework_bedrock._knowledge_base import _extract_content_text

        result = {
            "content": {
                "type": "ROW",
                "row": [
                    {"columnName": "service", "columnValue": "checkout"},
                    {"columnName": "rto_minutes", "columnValue": "15"},
                ],
            }
        }
        rendered = _extract_content_text(result)
        assert "service: checkout" in rendered
        assert "rto_minutes: 15" in rendered

    def test_row_content_skips_empty_columns(self):
        from agent_framework_bedrock._knowledge_base import _extract_content_text

        result = {"content": {"type": "ROW", "row": [{}, {"columnName": "k", "columnValue": "v"}]}}
        assert _extract_content_text(result) == "k: v"

    def test_image_content_returns_placeholder(self):
        """IMAGE payload is in byteContent, not text; a text tool renders a placeholder.

        Returning content.text would emit an empty passage — a blank numbered result or
        a source header with no body.
        """
        from agent_framework_bedrock._knowledge_base import _extract_content_text

        result = {"content": {"type": "IMAGE", "byteContent": "<base64-bytes>"}}
        assert _extract_content_text(result) == "[image content omitted]"

    def test_audio_and_video_content_return_placeholders(self):
        """AUDIO/VIDEO are also binary (byteContent), not text — render placeholders."""
        from agent_framework_bedrock._knowledge_base import _extract_content_text

        assert _extract_content_text({"content": {"type": "AUDIO", "byteContent": "b"}}) == "[audio content omitted]"
        assert _extract_content_text({"content": {"type": "VIDEO", "byteContent": "b"}}) == "[video content omitted]"


class TestBedrockKnowledgeBaseProvider:
    """Tests for the unified public provider (modes, tool exposure, injection, multimodal)."""

    @staticmethod
    def _standard_client(results):
        client = MagicMock()
        client.retrieve.return_value = {"retrievalResults": results}
        return client

    def test_is_context_provider_subclass(self):
        from agent_framework_bedrock import BedrockKnowledgeBaseProvider

        provider = BedrockKnowledgeBaseProvider(knowledge_base_id="TEST_KB", client=MagicMock())
        assert isinstance(provider, ContextProvider)

    def test_has_source_id(self):
        from agent_framework_bedrock import BedrockKnowledgeBaseProvider

        provider = BedrockKnowledgeBaseProvider(knowledge_base_id="TEST_KB", source_id="my-kb", client=MagicMock())
        assert provider.source_id == "my-kb"

    def test_invalid_mode_raises(self):
        from agent_framework_bedrock import BedrockKnowledgeBaseProvider

        with pytest.raises(ValueError, match="mode must be"):
            BedrockKnowledgeBaseProvider(knowledge_base_id="TEST_KB", mode="bogus", client=MagicMock())

    def test_default_mode_is_both(self):
        from agent_framework_bedrock import BedrockKnowledgeBaseProvider

        provider = BedrockKnowledgeBaseProvider(knowledge_base_id="TEST_KB", client=MagicMock())
        assert provider.mode == "both"

    def test_settings_public_export(self):
        # Comment 1: the settings type is public and exported.
        from agent_framework_bedrock import BedrockKnowledgeBaseSettings

        assert BedrockKnowledgeBaseSettings.__name__ == "BedrockKnowledgeBaseSettings"

    def test_tool_not_public(self):
        # Comment 5: only the provider is public; the tool is internal.
        import agent_framework_bedrock as pkg

        assert "BedrockKnowledgeBaseTool" not in pkg.__all__

    def test_inject_mode_injects_context_message(self):
        from agent_framework import Message, SessionContext

        from agent_framework_bedrock import BedrockKnowledgeBaseProvider

        client = self._standard_client([
            {"content": {"text": "Relevant passage"}, "score": 0.9, "location": {"s3Location": {"uri": "s3://b/doc"}}}
        ])
        provider = BedrockKnowledgeBaseProvider(
            knowledge_base_id="TEST_KB", mode="inject", use_agentic_retrieval=False, client=client
        )
        context = SessionContext(input_messages=[Message(role="user", contents=["What is our policy?"])])

        asyncio.run(provider.before_run(agent=MagicMock(), session=MagicMock(), context=context, state={}))

        assert "bedrock-kb" in context.context_messages
        injected = context.context_messages["bedrock-kb"]
        assert injected[0].role == "user"
        assert "Relevant passage" in injected[0].text
        assert "s3://b/doc" in injected[0].text
        # inject-only mode adds no tools
        assert not context.tools

    def test_tool_mode_exposes_tool_and_injects_nothing(self):
        from agent_framework import Message, SessionContext

        from agent_framework_bedrock import BedrockKnowledgeBaseProvider

        client = self._standard_client([{"content": {"text": "X"}, "score": 0.9, "location": {}}])
        provider = BedrockKnowledgeBaseProvider(
            knowledge_base_id="TEST_KB", mode="tool", use_agentic_retrieval=False, client=client
        )
        context = SessionContext(input_messages=[Message(role="user", contents=["question"])])

        asyncio.run(provider.before_run(agent=MagicMock(), session=MagicMock(), context=context, state={}))

        # tool mode adds a tool, injects no context, and does not retrieve during before_run
        assert len(context.tools) == 1
        assert "bedrock-kb" not in context.context_messages
        client.retrieve.assert_not_called()

    def test_both_mode_exposes_tool_and_injects(self):
        from agent_framework import Message, SessionContext

        from agent_framework_bedrock import BedrockKnowledgeBaseProvider

        client = self._standard_client([
            {"content": {"text": "Passage"}, "score": 0.9, "location": {"s3Location": {"uri": "s3://b/d"}}}
        ])
        provider = BedrockKnowledgeBaseProvider(
            knowledge_base_id="TEST_KB", mode="both", use_agentic_retrieval=False, client=client
        )
        context = SessionContext(input_messages=[Message(role="user", contents=["question"])])

        asyncio.run(provider.before_run(agent=MagicMock(), session=MagicMock(), context=context, state={}))

        assert len(context.tools) == 1
        assert "bedrock-kb" in context.context_messages
        assert "Passage" in context.context_messages["bedrock-kb"][0].text

    def test_min_score_filtering(self):
        from agent_framework_bedrock import BedrockKnowledgeBaseProvider

        client = self._standard_client([
            {"content": {"text": "High"}, "score": 0.9, "location": {}},
            {"content": {"text": "Low"}, "score": 0.2, "location": {}},
        ])
        provider = BedrockKnowledgeBaseProvider(
            knowledge_base_id="TEST_KB", mode="inject", min_score=0.5, use_agentic_retrieval=False, client=client
        )
        items = provider._retrieve_context_items("test")
        joined = "\n".join(str(i) for i in items)
        assert "High" in joined
        assert "Low" not in joined

    def test_before_run_skips_empty_input(self):
        from agent_framework import SessionContext

        from agent_framework_bedrock import BedrockKnowledgeBaseProvider

        client = self._standard_client([])
        provider = BedrockKnowledgeBaseProvider(
            knowledge_base_id="TEST_KB", mode="inject", use_agentic_retrieval=False, client=client
        )
        context = SessionContext(input_messages=[])

        asyncio.run(provider.before_run(agent=MagicMock(), session=MagicMock(), context=context, state={}))

        client.retrieve.assert_not_called()
        assert len(context.context_messages) == 0

    def test_multimodal_image_injected_as_content(self):
        # Comment 2: image/audio/video passages become multi-modal Content, not placeholders.
        from agent_framework import Content

        from agent_framework_bedrock import BedrockKnowledgeBaseProvider

        client = self._standard_client([
            {
                "content": {"type": "IMAGE", "byteContent": "bytes"},
                "score": 0.9,
                "location": {"s3Location": {"uri": "s3://b/pic.png"}},
            }
        ])
        provider = BedrockKnowledgeBaseProvider(
            knowledge_base_id="TEST_KB", mode="inject", use_agentic_retrieval=False, client=client
        )
        items = provider._retrieve_context_items("show me the diagram")
        media = [i for i in items if isinstance(i, Content)]
        assert media, "expected a multi-modal Content item for the image passage"
        assert media[0].uri == "s3://b/pic.png"
        assert media[0].media_type == "image/*"

    def test_agentic_retrieval_used_by_default(self):
        # Comment 4: the provider uses agentic retrieval (with fallback) on the inject path.
        from agent_framework_bedrock import BedrockKnowledgeBaseProvider

        client = MagicMock()
        client.agentic_retrieve_stream.return_value = {
            "stream": [
                {
                    "result": {
                        "results": [{"content": {"text": "Agentic passage"}, "metadata": {"_source_uri": "s3://b/a"}}]
                    }
                }
            ]
        }
        provider = BedrockKnowledgeBaseProvider(
            knowledge_base_id="TEST_KB", mode="inject", use_agentic_retrieval=True, client=client
        )
        items = provider._retrieve_context_items("compare a and b")
        joined = "\n".join(str(i) for i in items)
        assert "Agentic passage" in joined
        client.agentic_retrieve_stream.assert_called_once()
        client.retrieve.assert_not_called()
