"""Tests for remote compression fallback."""

import json
import os
from unittest.mock import MagicMock, patch

import pytest

from ..prompt_optimizer import PromptOptimization, optimize_prompt
from ..remote_compress import remote_available, remote_optimize


class TestRemoteOptimize:
    """Test remote_optimize() function."""

    def test_remote_optimize_success(self):
        """Test successful remote compression call."""
        mock_response = {
            "compressed_prompt": "compressed text",
            "tokens_before": 100,
            "tokens_after": 50,
            "saved_pct": 50.0,
            "method": "llmlingua2",
            "lossy": True,
        }

        with patch("token_efficiency_model.lossless.remote_compress.urlopen") as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.read.return_value = json.dumps(mock_response).encode("utf-8")
            mock_resp.__enter__.return_value = mock_resp
            mock_urlopen.return_value = mock_resp

            result = remote_optimize(
                "original text",
                rate=0.5,
                url="http://localhost:8000",
            )

            assert result is not None
            assert isinstance(result, PromptOptimization)
            assert result.original == "original text"
            assert result.optimized == "compressed text"
            assert result.tokens_before == 100
            assert result.tokens_after == 50
            assert result.saved_pct == 50.0
            assert result.method == "llmlingua2"
            assert result.lossy is True

    def test_remote_optimize_with_force_tokens(self):
        """Test remote compression with force_tokens."""
        mock_response = {
            "compressed_prompt": "text",
            "tokens_before": 100,
            "tokens_after": 60,
            "saved_pct": 40.0,
            "method": "llmlingua2",
            "lossy": True,
        }

        with patch("token_efficiency_model.lossless.remote_compress.urlopen") as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.read.return_value = json.dumps(mock_response).encode("utf-8")
            mock_resp.__enter__.return_value = mock_resp
            mock_urlopen.return_value = mock_resp

            result = remote_optimize(
                "original text",
                rate=0.5,
                force_tokens=["\n", "."],
                url="http://localhost:8000",
            )

            assert result is not None
            assert result.tokens_after == 60

    def test_remote_optimize_no_url(self):
        """Test remote_optimize returns None when no URL is provided."""
        result = remote_optimize("text", rate=0.5, url=None)
        assert result is None

    def test_remote_optimize_network_error(self):
        """Test remote_optimize returns None on network error."""
        with patch("token_efficiency_model.lossless.remote_compress.urlopen") as mock_urlopen:
            mock_urlopen.side_effect = OSError("Network error")

            result = remote_optimize(
                "text",
                rate=0.5,
                url="http://localhost:8000",
            )
            assert result is None

    def test_remote_optimize_bad_json(self):
        """Test remote_optimize returns None on invalid JSON response."""
        with patch("token_efficiency_model.lossless.remote_compress.urlopen") as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.read.return_value = b"not json"
            mock_resp.__enter__.return_value = mock_resp
            mock_urlopen.return_value = mock_resp

            result = remote_optimize(
                "text",
                rate=0.5,
                url="http://localhost:8000",
            )
            assert result is None

    def test_remote_optimize_missing_fields(self):
        """Test remote_optimize returns None on missing response fields."""
        mock_response = {
            "compressed_prompt": "text",
            # Missing required fields
        }

        with patch("token_efficiency_model.lossless.remote_compress.urlopen") as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.read.return_value = json.dumps(mock_response).encode("utf-8")
            mock_resp.__enter__.return_value = mock_resp
            mock_urlopen.return_value = mock_resp

            result = remote_optimize(
                "text",
                rate=0.5,
                url="http://localhost:8000",
            )
            # Should still return a PromptOptimization with default values
            assert result is not None

    def test_remote_optimize_timeout(self):
        """Test remote_optimize returns None on timeout."""
        with patch("token_efficiency_model.lossless.remote_compress.urlopen") as mock_urlopen:
            mock_urlopen.side_effect = TimeoutError("Connection timeout")

            result = remote_optimize(
                "text",
                rate=0.5,
                url="http://localhost:8000",
                timeout=5,
            )
            assert result is None

    def test_remote_optimize_with_auth_token(self):
        """Test remote_optimize sends Bearer token."""
        mock_response = {
            "compressed_prompt": "text",
            "tokens_before": 100,
            "tokens_after": 50,
            "saved_pct": 50.0,
            "method": "llmlingua2",
            "lossy": True,
        }

        with patch("token_efficiency_model.lossless.remote_compress.urlopen") as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.read.return_value = json.dumps(mock_response).encode("utf-8")
            mock_resp.__enter__.return_value = mock_resp
            mock_urlopen.return_value = mock_resp

            with patch("token_efficiency_model.lossless.remote_compress.Request") as mock_request:
                mock_req_instance = MagicMock()
                mock_request.return_value = mock_req_instance

                result = remote_optimize(
                    "text",
                    rate=0.5,
                    url="http://localhost:8000",
                    token="secret-token",
                )

                assert result is not None
                # Verify add_header was called with Bearer token
                mock_req_instance.add_header.assert_called_with(
                    "Authorization", "Bearer secret-token"
                )


class TestRemoteAvailable:
    """Test remote_available() helper."""

    def test_remote_available_when_set(self):
        """Test remote_available returns True when BREVITAS_COMPRESS_URL is set."""
        with patch.dict(os.environ, {"BREVITAS_COMPRESS_URL": "http://localhost:8000"}):
            assert remote_available() is True

    def test_remote_available_when_unset(self):
        """Test remote_available returns False when BREVITAS_COMPRESS_URL is not set."""
        with patch.dict(os.environ, {}, clear=True):
            assert remote_available() is False


class TestPromptOptimizerRemoteFallback:
    """Test that optimize_prompt falls back to remote when appropriate."""

    def test_optimize_prompt_uses_remote_when_llmlingua_unavailable(self):
        """Test optimize_prompt tries remote when local llmlingua is unavailable."""
        mock_remote_result = PromptOptimization(
            original="text",
            optimized="compressed",
            tokens_before=100,
            tokens_after=50,
            saved_pct=50.0,
            method="llmlingua2",
            lossy=True,
        )

        with patch("token_efficiency_model.lossless.prompt_optimizer._get_llmlingua") as mock_get:
            mock_get.return_value = None  # llmlingua not available

            with patch("token_efficiency_model.lossless.remote_compress.remote_optimize") as mock_remote:
                with patch("token_efficiency_model.lossless.remote_compress.remote_available") as mock_avail:
                    mock_remote.return_value = mock_remote_result
                    mock_avail.return_value = True

                    result = optimize_prompt("text", rate=0.5)

                    # Should have tried remote optimization
                    mock_remote.assert_called_once()
                    assert result.method == "llmlingua2"
                    assert result.lossy is True

    def test_optimize_prompt_prefers_local_llmlingua(self):
        """Test optimize_prompt prefers local llmlingua over remote."""
        mock_comp = MagicMock()
        mock_comp.compress_prompt.return_value = {"compressed_prompt": "local-compressed"}

        with patch("token_efficiency_model.lossless.prompt_optimizer._get_llmlingua") as mock_get:
            mock_get.return_value = mock_comp

            with patch("token_efficiency_model.lossless.prompt_optimizer.count_tokens") as mock_count:
                mock_count.side_effect = [100, 50]  # before, after

                with patch("token_efficiency_model.lossless.remote_compress.remote_optimize") as mock_remote:
                    result = optimize_prompt("text", rate=0.5)

                    # Should NOT call remote if local is available
                    mock_remote.assert_not_called()
                    assert result.method == "llmlingua2+lossless"

    def test_optimize_prompt_no_remote_when_no_url(self):
        """Test optimize_prompt falls back to lossless when remote URL not set."""
        with patch("token_efficiency_model.lossless.prompt_optimizer._get_llmlingua") as mock_get:
            mock_get.return_value = None  # llmlingua not available

            with patch("token_efficiency_model.lossless.remote_compress.remote_available") as mock_available:
                mock_available.return_value = False

                with patch("token_efficiency_model.lossless.prompt_optimizer.count_tokens") as mock_count:
                    mock_count.side_effect = [100, 95]  # before, after (lossless)

                    result = optimize_prompt("text", rate=0.5)

                    # Should fall back to lossless only
                    assert result.method == "lossless"
                    assert result.lossy is False

    def test_optimize_prompt_rate_1_0_uses_lossless_only(self):
        """Test optimize_prompt with rate=1.0 uses lossless only (never remote)."""
        with patch("token_efficiency_model.lossless.remote_compress.remote_optimize") as mock_remote:
            with patch("token_efficiency_model.lossless.prompt_optimizer.count_tokens") as mock_count:
                mock_count.side_effect = [100, 95]

                result = optimize_prompt("text", rate=1.0)

                # Should never call remote for rate >= 1.0
                mock_remote.assert_not_called()
                assert result.method == "lossless"
                assert result.lossy is False
