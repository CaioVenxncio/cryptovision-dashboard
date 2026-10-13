from __future__ import annotations

from datetime import UTC, datetime

import pytest

from cryptovision.providers.http_client import HttpJsonClient, RetryPolicy, parse_retry_after


def test_backoff_doubles_and_is_capped():
    policy = RetryPolicy(backoff_base_seconds=1, backoff_max_seconds=5)
    assert [policy.backoff(n, jitter=1.0) for n in range(5)] == [1, 2, 4, 5, 5]
    assert policy.backoff(0, jitter=0.0) == 0.5


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        ("5", 5.0),
        (" 12 ", 12.0),
        ("Tue, 13 Oct 2026 12:00:30 GMT", 30.0),
        ("Tue, 13 Oct 2026 11:00:00 GMT", 0.0),
        ("Tue, 13 Oct 2026 12:00:10 -0000", 10.0),
        ("soon", None),
        (None, None),
    ],
)
def test_parse_retry_after(header, expected):
    now = datetime(2026, 10, 13, 12, 0, 0, tzinfo=UTC)
    assert parse_retry_after(header, now=now) == expected


def test_repr_hides_headers():
    client = HttpJsonClient(
        "https://example.invalid", headers={"x-secret": "hidden-value"}, timeout_seconds=1
    )
    assert "hidden-value" not in repr(client)
