import json
from unittest.mock import Mock

from zulip_hermes import bot_bridge as zulip_hermes_bot, mcp_server as zulip_mcp


def test_extract_upload_paths_normalizes_dedupes_and_rejects_traversal():
    content = " ".join(
        [
            "[doc](/user_uploads/1/ab/report.pdf)",
            "![img](https://example.zulipchat.com/user_uploads/1/ab/image.png?version=2)",
            "[dup](/user_uploads/1/ab/report.pdf)",
            "[bad](/user_uploads/../secret.txt)",
            "[not-upload](https://example.com/file.pdf)",
        ]
    )

    assert zulip_mcp.extract_upload_paths(content) == [
        "/user_uploads/1/ab/report.pdf",
        "/user_uploads/1/ab/image.png",
    ]


def test_upload_filename_is_safe_basename():
    assert zulip_mcp.upload_filename("/user_uploads/1/ab/report%20final.pdf") == "report final.pdf"
    assert zulip_mcp.upload_filename("/user_uploads/1/ab/../secret.txt") == "secret.txt"


def test_content_needles_strip_scope_operators_and_keep_phrases():
    assert zulip_mcp._content_needles_from_query(
        'stream:general pm-with:person@example.com sender:alice@example.com "exact phrase" deploy failed'
    ) == ["exact phrase", "deploy", "failed"]


def test_reassemble_hermes_chunks_merges_complete_series():
    messages = [
        {
            "id": 10,
            "sender": "Hermes",
            "sender_email": "bot@example.com",
            "timestamp": 1,
            "content": "hello (1/2)",
            "is_bot": True,
        },
        {
            "id": 11,
            "sender": "Hermes",
            "sender_email": "bot@example.com",
            "timestamp": 2,
            "content": "world (2/2)",
            "is_bot": True,
        },
    ]

    merged = zulip_mcp._reassemble_hermes_chunks(messages)

    assert merged == [
        {
            "id": 10,
            "sender": "Hermes",
            "sender_email": "bot@example.com",
            "timestamp": 1,
            "content": "hello\nworld",
            "is_bot": True,
            "chunk_ids": [10, 11],
            "chunk_count": 2,
            "newest_chunk_id": 11,
        }
    ]


def test_zulip_search_messages_uses_client_scan_when_fts_misses(monkeypatch):
    monkeypatch.setattr(zulip_mcp, "ZULIP_SITE_URL", "https://example.zulipchat.com")
    monkeypatch.setattr(zulip_mcp, "ZULIP_BOT_EMAIL", "bot@example.com")
    monkeypatch.setattr(zulip_mcp, "ZULIP_API_KEY", "test-key")

    fake_client = Mock()
    fake_client.get_messages.side_effect = [
        {"result": "success", "messages": [], "found_oldest": False, "found_newest": True},
        {
            "result": "success",
            "messages": [
                {
                    "id": 20,
                    "sender_full_name": "Alice",
                    "sender_email": "alice@example.com",
                    "timestamp": 1,
                    "content": "deploy failed after restart",
                },
            ],
            "found_oldest": True,
            "found_newest": True,
        },
    ]
    monkeypatch.setattr(zulip_mcp.zulip, "Client", lambda **_: fake_client)

    payload = json.loads(zulip_mcp.zulip_search_messages(stream="general", query="deploy failed"))

    assert payload["count"] == 1
    assert payload["client_content_scan"] is True
    assert payload["messages"][0]["content"] == "deploy failed after restart"


def test_free_response_streams_can_bypass_mention_requirement(monkeypatch):
    monkeypatch.setattr(zulip_hermes_bot, "ZULIP_REQUIRE_MENTION", True)
    monkeypatch.setattr(zulip_hermes_bot, "ZULIP_FREE_RESPONSE_STREAMS", {"bot-commands", "42"})

    assert zulip_hermes_bot.stream_requires_mention("general", 1) is True
    assert zulip_hermes_bot.stream_requires_mention("bot-commands", 1) is False
    assert zulip_hermes_bot.stream_requires_mention("other", 42) is False


def test_catchup_state_is_forward_only(tmp_path):
    state = zulip_hermes_bot.CatchupState(tmp_path / "watermarks.json")

    assert state.read() == {}
    state.advance("general", 100)
    state.advance("general", 99)
    state.advance("random", 5)

    assert state.read() == {"general": 100, "random": 5}
