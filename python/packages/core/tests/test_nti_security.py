# Copyright (c) Microsoft. All rights reserved.

from unittest.mock import MagicMock, patch
import pytest
from agent_framework.nti_security import NTISecurityWrapper

@patch("agent_framework.nti_security.TrustEngine")
@patch("agent_framework.nti_security.PqcKeyPair")
def test_nti_security_wrapper_init(mock_pqc, mock_trust):
    wrapper = NTISecurityWrapper(agent_id="test_agent")
    assert wrapper.agent_id == "test_agent"
    mock_trust.assert_called_once()
    mock_pqc.generate.assert_called_once()

@patch("agent_framework.nti_security.TrustEngine")
@patch("agent_framework.nti_security.PqcKeyPair")
def test_verify_message_allowed(mock_pqc, mock_trust):
    # Setup mocks
    mock_engine_instance = mock_trust.return_value
    mock_engine_instance.evaluate.return_value = '{"decision": "Allow"}'
    
    wrapper = NTISecurityWrapper(agent_id="test_agent")
    
    result = wrapper.verify_message(
        capability="test_cap",
        message={"data": "test"},
        sender_public_key="pub_key",
        sender_signature="sig"
    )
    
    assert result is True
    mock_engine_instance.evaluate.assert_called_once()
    
    # Verify the payload sent to the Rust engine contains the sender's info
    call_args = mock_engine_instance.evaluate.call_args[0][0]
    assert "test_cap" in call_args
    assert "pub_key" in call_args
    assert "sig" in call_args

@patch("agent_framework.nti_security.TrustEngine")
@patch("agent_framework.nti_security.PqcKeyPair")
def test_verify_message_denied(mock_pqc, mock_trust):
    mock_engine_instance = mock_trust.return_value
    mock_engine_instance.evaluate.return_value = '{"decision": "Deny"}'
    
    wrapper = NTISecurityWrapper(agent_id="test_agent")
    
    result = wrapper.verify_message(
        capability="test_cap",
        message={"data": "test"},
        sender_public_key="pub_key",
        sender_signature="sig"
    )
    
    assert result is False
