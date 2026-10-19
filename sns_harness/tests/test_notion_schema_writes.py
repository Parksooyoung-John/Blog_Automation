from unittest.mock import Mock

from sns_harness.queues.notion import DAILY_PROPERTY_DEFINITIONS, PROPERTY_TYPES, NotionQueue

KNOWN = set(PROPERTY_TYPES) | set(DAILY_PROPERTY_DEFINITIONS)


def queue() -> tuple[NotionQueue, Mock]:
    session = Mock()
    return NotionQueue("key", "db", session=session), session


def written(session: Mock) -> set[str]:
    return {
        name
        for call in session.patch.call_args_list
        for name in call.kwargs["json"]["properties"]
    }


def test_card_writes_only_use_properties_the_schema_declares() -> None:
    # 2026-10-19: the live Notion column was renamed 썸네일미리보기 -> 카드미리보기 and set_cards
    # started failing with HTTP 400 (property does not exist) — nothing in the code noticed.
    notion, session = queue()
    notion.set_cards("page", number=18, filenames=["18_카드뉴스_1.png", "18_카드뉴스_2.png"],
                     urls=["https://x/1.png", "https://x/2.png"])
    notion.set_thumbnail("page", number=18, filename="18_썸네일.png", url="https://x/t.png")
    notion.hold_thumbnail("page", "missing", status="누락")
    assert written(session) <= KNOWN, written(session) - KNOWN
    assert "카드미리보기" in written(session)


def test_card_urls_come_back_from_the_preview_column() -> None:
    prop = {"files": [
        {"type": "external", "external": {"url": "https://x/1.png"}},
        {"type": "external", "external": {"url": "https://x/2.png"}},
    ]}
    assert NotionQueue._card_urls(prop) == ["https://x/1.png", "https://x/2.png"]
    assert NotionQueue._card_urls({"files": prop["files"][:1]}) == []   # one image = old thumbnail
