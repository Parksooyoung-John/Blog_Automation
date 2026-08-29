from pathlib import Path

from sns_harness.sources.tistory import TistorySource


def test_parse_numeric_canonical_and_json_ld() -> None:
    html = (Path(__file__).parent / "fixtures" / "post.html").read_text(encoding="utf-8")
    post = TistorySource("https://j2gblog.tistory.com").parse(
        html, "https://j2gblog.tistory.com/165"
    )

    assert post.tistory_id == "165"
    assert post.url == "https://j2gblog.tistory.com/165"
    assert post.title == "생애최초 취득세 감면 조건"
    assert "12억 원" in post.content
    assert "ignored" not in post.content
    assert post.tags == ["취득세"]
    assert len(post.source_hash) == 64


def test_rejects_non_numeric_entry_url() -> None:
    source = TistorySource("https://j2gblog.tistory.com")
    assert source._numeric_url("https://j2gblog.tistory.com/entry/title") is None
    assert source._numeric_url("https://other.example/165") is None
