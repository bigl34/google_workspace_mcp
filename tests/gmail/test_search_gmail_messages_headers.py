"""Tests for search_gmail_messages header enrichment (include_headers flag)."""

from unittest.mock import Mock

import pytest

from gmail.gmail_helpers import GMAIL_METADATA_HEADERS
from gmail.gmail_tools import (
    GMAIL_SEARCH_HEADER_BATCH_SIZE,
    search_gmail_messages,
)


def _unwrap(tool):
    """Unwrap FunctionTool + decorators to the original async function."""
    fn = tool.fn if hasattr(tool, "fn") else tool
    while hasattr(fn, "__wrapped__"):
        fn = fn.__wrapped__
    return fn


def _headers(**overrides):
    header_map = {
        "Subject": "Example subject",
        "From": "sender@example.com",
        "Date": "Fri, 28 Mar 2026 10:00:00 -0400",
    }
    header_map.update(overrides)
    return [{"name": name, "value": value} for name, value in header_map.items()]


def _metadata_response(message_id: str, headers=None):
    return {
        "id": message_id,
        "payload": {"headers": headers or _headers()},
    }


class _FakeBatch:
    def __init__(self, callback):
        self._callback = callback
        self._requests = []

    @property
    def request_ids(self):
        return [request_id for request_id, _ in self._requests]

    def add(self, request, request_id):
        self._requests.append((request_id, request))

    def execute(self):
        for request_id, request in self._requests:
            try:
                response = request.execute()
                self._callback(request_id, response, None)
            except Exception as exc:
                self._callback(request_id, None, exc)


def _build_service(*, list_response, message_responses=None, batch_factory=None):
    message_responses = message_responses or {}

    service = Mock()
    batches = []

    def message_list(**kwargs):
        request = Mock()
        request.execute.return_value = list_response
        return request

    def message_get(**kwargs):
        request = Mock()
        response = message_responses[(kwargs["id"], kwargs["format"])]
        if isinstance(response, Exception):
            request.execute.side_effect = response
        else:
            request.execute.return_value = response
        return request

    def recording_batch_factory(callback):
        batch = _FakeBatch(callback)
        batches.append(batch)
        return batch

    service.users().messages().list.side_effect = message_list
    service.users().messages().get.side_effect = message_get
    service.new_batch_http_request.side_effect = (
        batch_factory or recording_batch_factory
    )
    # Batches created during the call, in order, for batch-boundary assertions.
    service.created_batches = batches
    return service


def _get_call_kwargs(service):
    """All kwargs passed to messages().get(), in call order."""
    return [
        call.kwargs
        for call in service.users.return_value.messages.return_value.get.call_args_list
    ]


def _list_response(message_ids, next_page_token=None):
    response = {
        "messages": [{"id": mid, "threadId": f"thread-{mid}"} for mid in message_ids]
    }
    if next_page_token:
        response["nextPageToken"] = next_page_token
    return response


async def _run_search(service, **kwargs):
    return await _unwrap(search_gmail_messages)(
        service=service,
        query="test query",
        user_google_email="user@example.com",
        **kwargs,
    )


def _formatted(result):
    """Return the human-readable rendering from the fork's result envelope."""
    assert isinstance(result, dict)
    return result["formattedResponse"]


@pytest.mark.asyncio
async def test_default_output_is_unchanged():
    """include_headers=False (the default) must produce today's exact format."""
    service = _build_service(list_response=_list_response(["msg-1", "msg-2"]))

    result = await _run_search(service)

    expected = "\n".join(
        [
            "Found 2 messages matching 'test query':",
            "",
            "📧 MESSAGES:",
            "  1. Message ID: msg-1",
            "     Web Link: https://mail.google.com/mail/u/0/#all/msg-1",
            "     Thread ID: thread-msg-1",
            "     Thread Link: https://mail.google.com/mail/u/0/#all/thread-msg-1",
            "",
            "  2. Message ID: msg-2",
            "     Web Link: https://mail.google.com/mail/u/0/#all/msg-2",
            "     Thread ID: thread-msg-2",
            "     Thread Link: https://mail.google.com/mail/u/0/#all/thread-msg-2",
            "",
            "💡 USAGE:",
            "  • Pass the Message IDs **as a list** to get_gmail_messages_content_batch()",
            "    e.g. get_gmail_messages_content_batch(message_ids=[...])",
            "  • Pass the Thread IDs to get_gmail_thread_content() (single) or get_gmail_threads_content_batch() (batch)",
        ]
    )
    assert _formatted(result) == expected


@pytest.mark.asyncio
async def test_default_makes_no_metadata_fetches():
    service = _build_service(list_response=_list_response(["msg-1"]))

    await _run_search(service)

    assert service.users.return_value.messages.return_value.get.call_count == 0
    assert service.new_batch_http_request.call_count == 0


@pytest.mark.asyncio
async def test_include_headers_returns_subject_sender_and_date():
    service = _build_service(
        list_response=_list_response(["msg-1", "msg-2"]),
        message_responses={
            ("msg-1", "metadata"): _metadata_response(
                "msg-1", headers=_headers(Subject="First subject")
            ),
            ("msg-2", "metadata"): _metadata_response(
                "msg-2",
                headers=_headers(
                    Subject="Second subject",
                    From="other@example.com",
                    Date="Sat, 29 Mar 2026 09:00:00 -0400",
                ),
            ),
        },
    )

    result = await _run_search(service, include_headers=True)
    formatted = _formatted(result)

    assert "Subject: First subject" in formatted
    assert "Subject: Second subject" in formatted
    assert "From: sender@example.com" in formatted
    assert "From: other@example.com" in formatted
    assert "Date: Fri, 28 Mar 2026 10:00:00 -0400" in formatted
    assert "Date: Sat, 29 Mar 2026 09:00:00 -0400" in formatted
    # IDs and links are still present alongside the headers.
    assert "Message ID: msg-1" in formatted
    assert "Thread ID: thread-msg-1" in formatted
    assert result["messages"][0]["id"] == "msg-1"
    assert result["messages"][0]["headers"]["Subject"] == "First subject"
    assert result["messages"][0]["headersAvailable"] is True

    get_calls = _get_call_kwargs(service)
    assert [call["format"] for call in get_calls] == ["metadata", "metadata"]
    # Every fetch must request the metadata header allowlist, which is what
    # actually makes Subject/From/Date available on the response.
    for call in get_calls:
        assert call["metadataHeaders"] == GMAIL_METADATA_HEADERS
        for required in ("Subject", "From", "Date"):
            assert required in call["metadataHeaders"]


def test_batch_size_stays_under_measured_429_threshold():
    """Pin the chunk size itself, not just the splitting logic.

    Measured live against a real account: chunks of 25 (the general
    GMAIL_BATCH_SIZE) returned 429 "Too many concurrent requests for user"
    for 9 of 50 metadata gets, because the batch endpoint runs every get in
    a chunk concurrently server-side. Chunks of 10 returned 50/50 clean.
    Raising this constant back toward 25 reintroduces that failure, so it is
    asserted here rather than left to a comment.
    """
    assert 1 <= GMAIL_SEARCH_HEADER_BATCH_SIZE <= 10


@pytest.mark.asyncio
async def test_header_fetches_are_chunked_at_batch_size(monkeypatch):
    """Chunking is what keeps us under Gmail's per-user concurrency limit.

    Batches larger than GMAIL_SEARCH_HEADER_BATCH_SIZE reproducibly return
    429 "Too many concurrent requests for user", so the split must hold.
    """
    import gmail.gmail_tools as gmail_tools

    monkeypatch.setattr(gmail_tools, "GMAIL_REQUEST_DELAY", 0)

    message_ids = [f"msg-{i}" for i in range(GMAIL_SEARCH_HEADER_BATCH_SIZE + 1)]
    service = _build_service(
        list_response=_list_response(message_ids),
        message_responses={
            (mid, "metadata"): _metadata_response(mid) for mid in message_ids
        },
    )

    result = await _run_search(service, include_headers=True)
    formatted = _formatted(result)

    batch_sizes = [len(batch.request_ids) for batch in service.created_batches]
    assert batch_sizes == [GMAIL_SEARCH_HEADER_BATCH_SIZE, 1]
    # Chunk boundaries must not drop or duplicate any ID.
    batched_ids = [
        mid for batch in service.created_batches for mid in batch.request_ids
    ]
    assert batched_ids == message_ids
    assert len(_get_call_kwargs(service)) == len(message_ids)
    assert "Headers: unavailable" not in formatted
    assert formatted.count("Subject: Example subject") == len(message_ids)


@pytest.mark.asyncio
async def test_partial_metadata_failure_degrades_per_row(monkeypatch):
    import gmail.gmail_tools as gmail_tools

    monkeypatch.setattr(gmail_tools, "GMAIL_REQUEST_DELAY", 0)
    service = _build_service(
        list_response=_list_response(["msg-1", "msg-2"]),
        message_responses={
            ("msg-1", "metadata"): _metadata_response("msg-1"),
            ("msg-2", "metadata"): Exception("boom"),
        },
    )

    result = await _run_search(service, include_headers=True)
    formatted = _formatted(result)

    assert "Subject: Example subject" in formatted
    assert "Headers: unavailable (metadata fetch failed)" in formatted
    # The failing message's row survives with its IDs intact.
    assert "Message ID: msg-2" in formatted
    assert "Thread ID: thread-msg-2" in formatted


@pytest.mark.asyncio
async def test_transient_batch_failure_recovers_on_retry(monkeypatch):
    """A 429 inside the batch is retried sequentially and recovers."""
    import gmail.gmail_tools as gmail_tools

    monkeypatch.setattr(gmail_tools, "GMAIL_REQUEST_DELAY", 0)

    calls = {"count": 0}

    def flaky_get(**kwargs):
        request = Mock()
        calls["count"] += 1
        if calls["count"] == 1:
            request.execute.side_effect = Exception(
                "429 Too many concurrent requests for user."
            )
        else:
            request.execute.return_value = _metadata_response("msg-1")
        return request

    service = _build_service(list_response=_list_response(["msg-1"]))
    service.users().messages().get.side_effect = flaky_get

    result = await _run_search(service, include_headers=True)
    formatted = _formatted(result)

    assert "Subject: Example subject" in formatted
    assert "Headers: unavailable" not in formatted
    assert calls["count"] == 2


@pytest.mark.asyncio
async def test_missing_headers_use_placeholders():
    service = _build_service(
        list_response=_list_response(["msg-1"]),
        message_responses={
            ("msg-1", "metadata"): {"id": "msg-1", "payload": {"headers": []}},
        },
    )

    result = await _run_search(service, include_headers=True)
    formatted = _formatted(result)

    assert "Subject: (no subject)" in formatted
    assert "From: (unknown sender)" in formatted
    assert "Date: (unknown date)" in formatted


@pytest.mark.asyncio
async def test_malformed_metadata_degrades_per_row(monkeypatch):
    import gmail.gmail_tools as gmail_tools

    monkeypatch.setattr(gmail_tools, "GMAIL_REQUEST_DELAY", 0)
    service = _build_service(
        list_response=_list_response(["msg-1"]),
        message_responses={
            ("msg-1", "metadata"): {"id": "msg-1", "payload": None},
        },
    )

    result = await _run_search(service, include_headers=True)
    formatted = _formatted(result)

    assert "Subject: (no subject)" in formatted
    assert "From: (unknown sender)" in formatted
    assert "Date: (unknown date)" in formatted
    assert "Message ID: msg-1" in formatted


@pytest.mark.asyncio
async def test_unexpected_enrichment_failure_preserves_search_results(monkeypatch):
    import gmail.gmail_tools as gmail_tools

    async def fail_enrichment(service, message_ids):
        raise RuntimeError("unexpected enrichment failure")

    monkeypatch.setattr(gmail_tools, "_fetch_search_result_headers", fail_enrichment)
    service = _build_service(list_response=_list_response(["msg-1"]))

    result = await _run_search(service, include_headers=True)
    formatted = _formatted(result)

    assert "Headers: unavailable (metadata fetch failed)" in formatted
    assert "Message ID: msg-1" in formatted
    assert "Thread ID: thread-msg-1" in formatted


@pytest.mark.asyncio
async def test_pagination_preserved_with_include_headers():
    service = _build_service(
        list_response=_list_response(["msg-1"], next_page_token="tok-123"),
        message_responses={
            ("msg-1", "metadata"): _metadata_response("msg-1"),
        },
    )

    result = await _run_search(service, include_headers=True, page_token="tok-000")
    formatted = _formatted(result)

    assert "page_token='tok-123'" in formatted
    assert "Subject: Example subject" in formatted
    assert result["nextPageToken"] == "tok-123"
    list_kwargs = service.users.return_value.messages.return_value.list.call_args.kwargs
    assert list_kwargs["pageToken"] == "tok-000"


@pytest.mark.asyncio
async def test_batch_failure_falls_back_to_sequential(monkeypatch):
    import gmail.gmail_tools as gmail_tools

    monkeypatch.setattr(gmail_tools, "GMAIL_REQUEST_DELAY", 0)

    def _broken_batch(callback):
        raise RuntimeError("batch endpoint unavailable")

    service = _build_service(
        list_response=_list_response(["msg-1"]),
        message_responses={
            ("msg-1", "metadata"): _metadata_response("msg-1"),
        },
        batch_factory=_broken_batch,
    )

    result = await _run_search(service, include_headers=True)
    formatted = _formatted(result)

    assert "Subject: Example subject" in formatted
    assert "From: sender@example.com" in formatted
