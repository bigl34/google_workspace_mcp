"""Regression tests for insert_doc_tab response key handling.

The Google Docs batchUpdate response for an addDocumentTab request comes back
under the key ``addDocumentTab`` (matching the request field name), not
``createDocumentTab``. The original fork code looked for ``createDocumentTab``,
so tab_id extraction silently failed. These tests lock in the fix and its
backwards-compat fallback.

Verified against a real Google Doc via ``scripts/spike/spike_tab_operations.py``
in commit b374139.
"""

from unittest.mock import Mock

import pytest

from gdocs import docs_tools
from gdocs.managers.batch_operation_manager import BatchOperationManager


def _unwrap(tool):
    """Unwrap the decorated tool function to the original implementation.

    Mirrors the helper in tests/gdocs/test_advanced_doc_formatting.py so we
    stay consistent with the existing fork convention.
    """
    fn = tool.fn if hasattr(tool, "fn") else tool
    while hasattr(fn, "__wrapped__"):
        fn = fn.__wrapped__
    return fn


def _mock_service_with_reply(reply: dict) -> Mock:
    """Build a Docs service mock whose batchUpdate returns the given reply."""
    mock_service = Mock()
    mock_service.documents.return_value.batchUpdate.return_value.execute.return_value = {
        "replies": [reply],
        "documentId": "doc-abc",
    }
    return mock_service


@pytest.mark.asyncio
async def test_insert_doc_tab_extracts_tab_id_from_add_document_tab_reply():
    """The fix - reply["addDocumentTab"] is where Google puts the new tab's properties."""
    service = _mock_service_with_reply(
        {
            "addDocumentTab": {
                "tabProperties": {
                    "tabId": "t.xyz123",
                    "title": "My Tab",
                    "index": 0,
                }
            }
        }
    )

    result = await _unwrap(docs_tools.insert_doc_tab)(
        service=service,
        user_google_email="test@example.com",
        document_id="doc-abc",
        title="My Tab",
        index=0,
    )

    assert "t.xyz123" in result, f"Expected tab_id in result, got: {result}"
    assert "Tab ID: t.xyz123" in result


@pytest.mark.asyncio
async def test_insert_doc_tab_falls_back_to_create_document_tab_for_compat():
    """Backwards compat - if Google ever returns under createDocumentTab, still work."""
    service = _mock_service_with_reply(
        {
            "createDocumentTab": {
                "tabProperties": {
                    "tabId": "t.legacy",
                    "title": "Legacy Tab",
                }
            }
        }
    )

    result = await _unwrap(docs_tools.insert_doc_tab)(
        service=service,
        user_google_email="test@example.com",
        document_id="doc-abc",
        title="Legacy Tab",
        index=0,
    )

    assert "t.legacy" in result


@pytest.mark.asyncio
async def test_insert_doc_tab_omits_tab_id_when_reply_is_empty():
    """Guard - if the reply has neither key, the tool must not crash."""
    service = _mock_service_with_reply({})

    result = await _unwrap(docs_tools.insert_doc_tab)(
        service=service,
        user_google_email="test@example.com",
        document_id="doc-abc",
        title="Orphan Tab",
        index=0,
    )

    assert "Tab ID" not in result
    assert "doc-abc" in result


class TestBatchOperationManagerExtractCreatedTabs:
    """Companion tests for BatchOperationManager._extract_created_tabs, which
    had the identical bug at gdocs/managers/batch_operation_manager.py line 883.
    """

    def _manager(self) -> BatchOperationManager:
        return BatchOperationManager(service=Mock())

    def test_extracts_from_add_document_tab(self):
        manager = self._manager()
        result = {
            "replies": [
                {
                    "addDocumentTab": {
                        "tabProperties": {"tabId": "t.new", "title": "New Tab"}
                    }
                }
            ]
        }

        tabs = manager._extract_created_tabs(result)

        assert tabs == [{"tab_id": "t.new", "title": "New Tab"}]

    def test_extracts_from_create_document_tab_for_compat(self):
        manager = self._manager()
        result = {
            "replies": [
                {
                    "createDocumentTab": {
                        "tabProperties": {"tabId": "t.legacy", "title": "Legacy"}
                    }
                }
            ]
        }

        tabs = manager._extract_created_tabs(result)

        assert tabs == [{"tab_id": "t.legacy", "title": "Legacy"}]

    def test_mixed_replies_extracts_only_tab_replies(self):
        manager = self._manager()
        result = {
            "replies": [
                {"insertText": {}},
                {
                    "addDocumentTab": {
                        "tabProperties": {"tabId": "t.a", "title": "A"}
                    }
                },
                {},
                {
                    "addDocumentTab": {
                        "tabProperties": {"tabId": "t.b", "title": "B"}
                    }
                },
            ]
        }

        tabs = manager._extract_created_tabs(result)

        assert tabs == [
            {"tab_id": "t.a", "title": "A"},
            {"tab_id": "t.b", "title": "B"},
        ]
