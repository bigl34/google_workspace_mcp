from unittest.mock import Mock

import pytest

from gmail.gmail_tools import (
    delete_gmail_send_as,
    search_gmail_messages,
    update_gmail_send_as,
)


def _unwrap(tool):
    fn = tool.fn if hasattr(tool, "fn") else tool
    while hasattr(fn, "__wrapped__"):
        fn = fn.__wrapped__
    return fn


@pytest.mark.asyncio
async def test_search_returns_ids_and_cursor_as_structured_fields():
    service = Mock()
    service.users().messages().list().execute.return_value = {
        "messages": [{"id": "m1", "threadId": "t1"}],
        "nextPageToken": "cursor",
        "resultSizeEstimate": 99,
    }
    result = await _unwrap(search_gmail_messages)(
        service=service,
        query="in:inbox",
        user_google_email="user@example.com",
    )
    assert result["messages"][0]["id"] == "m1"
    assert result["nextPageToken"] == "cursor"
    assert result["hasMore"] is True


@pytest.mark.asyncio
async def test_send_as_update_defaults_to_dry_run():
    service = Mock()
    result = await _unwrap(update_gmail_send_as)(
        service=service,
        user_google_email="user@example.com",
        send_as_email="sales@example.com",
        display_name="Sales",
    )
    assert result["dryRun"] is True
    service.users().settings().sendAs().update.assert_not_called()


@pytest.mark.asyncio
async def test_primary_send_as_delete_is_rejected():
    service = Mock()
    with pytest.raises(Exception, match="primary identity"):
        await _unwrap(delete_gmail_send_as)(
            service=service,
            user_google_email="user@example.com",
            send_as_email="USER@example.com",
        )
