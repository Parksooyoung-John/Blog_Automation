from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sns_harness.agents.writer import candidate_plan
from sns_harness.models import (
    ApprovalStatus,
    CandidateType,
    HookType,
    QueueItem,
    QueueStatus,
    ReviewResult,
    SourceKind,
    SourcePost,
    ThreadsDraft,
)
from sns_harness.orchestrator import HarnessOrchestrator, pick_pair
from sns_harness.queues.notion import NotionQueue

SOURCE = SourcePost(
    source=SourceKind.NAVER,
    source_id="777",
    url="https://blog.naver.com/education_blog/777",
    title="연말정산 카드공제",
    content="카드 공제는 총급여의 25%를 넘는 금액부터 15%입니다.",
    published_at=datetime.now(UTC) - timedelta(hours=1),
)


HOOKS = [
    "카드 공제 25% 넘겨야 시작돼요",
    "연말정산 카드 이 실수 하셨죠",
    "신용카드 체크카드 공제율 차이는",
    "연말정산 서류 챙기다 막막했죠",
    "카드 공제 언제부터 받는지 아세요?",
]
CLAIMS = [
    "총급여 25% 초과분부터 공제",
    "문턱 금액 계산 착오 주의",
    "체크카드 공제율이 더 높음",
    "서류 준비 순서 정리가 우선",
    "공제 시작 시점은 소득마다 다름",
]


def drafts(scores: list[int], allow_link: bool = True) -> list[ThreadsDraft]:
    result = []
    for index, (entry, score) in enumerate(zip(candidate_plan(allow_link), scores, strict=True)):
        link = bool(entry["include_blog_link"])
        result.append(
            ThreadsDraft(
                format="single",
                posts=[f"후보 {index} 문장 {SOURCE.url if link else ''}".strip()],
                hook_type=HookType(entry["hook_type"]),
                hook_text=HOOKS[index],
                core_claim=CLAIMS[index],
                candidate_type=CandidateType(entry["candidate_type"]),
                blog_link_used=link,
                score=score,
            )
        )
    return result


class Writer:
    def __init__(self, scores: list[int], allow_link: bool = True) -> None:
        self.scores, self.allow_link = scores, allow_link

    def generate_candidates(self, source, *, allow_link):
        return drafts(self.scores, allow_link)


class Reviewer:
    def review(self, source, draft):
        return ReviewResult(approved=True, reviewed_draft=draft, quality_score=80)


class Source:
    def discover(self, limit=20):
        return [SOURCE.url]

    def fetch(self, url):
        return SOURCE


class Queue:
    def __init__(self) -> None:
        self.created: list[tuple[ReviewResult, int]] = []

    def find_by_source_key(self, key):
        return None

    def create(self, source, review, variant=0):
        self.created.append((review, variant))


def sync(scores: list[int]) -> tuple[Queue, dict[str, int]]:
    queue = Queue()
    stats = HarnessOrchestrator(Source(), Writer(scores), Reviewer(), queue).sync(
        now=datetime.now(UTC)
    )
    return queue, stats


def test_one_blog_yields_two_distinct_candidates_a_info_b_empathy() -> None:
    # 숫자·실수·비교(정보형), 공감(정보+공감형), 질문(블로그전환형)
    queue, stats = sync([8, 9, 7, 8, 7])
    first, second = (review.reviewed_draft for review, _ in queue.created)
    assert stats["created"] == 2 and [v for _, v in queue.created] == [0, 1]
    assert first.candidate_type is CandidateType.INFO and first.score == 9
    assert second.candidate_type is CandidateType.INFO_EMPATHY
    assert first.hook_type != second.hook_type and first.hook_text != second.hook_text


def test_below_seven_candidates_are_not_saved() -> None:
    queue, _ = sync([9, 6, 6, 6, 6])
    assert len(queue.created) == 1
    queue, stats = sync([6, 5, 4, 6, 3])
    assert queue.created == [] and stats["below_threshold"] == 1


def test_at_most_one_of_the_pair_carries_a_link() -> None:
    reviews = [
        ReviewResult(approved=True, reviewed_draft=draft, quality_score=80)
        for draft in drafts([9, 9, 9, 9, 9])
    ]
    link_draft = reviews[4].reviewed_draft
    forced = link_draft.model_copy(update={"hook_text": "또 다른 링크 훅 문장입니다."})
    reviews.append(reviews[4].model_copy(update={"reviewed_draft": forced}))
    picked = pick_pair(reviews)
    assert sum(r.reviewed_draft.blog_link_used for r in picked) <= 1
    # 정보형 첫 후보는 링크 없음, 링크 허용 안 된 계획에는 링크 후보 자체가 없다
    assert not any(d.blog_link_used for d in drafts([8] * 5, allow_link=False))


def test_pair_needs_two_differing_dimensions() -> None:
    base = drafts([9, 9, 9, 9, 9])[0]
    twin = base.model_copy(update={"hook_type": HookType.MISTAKE})   # only hook type differs
    reviews = [
        ReviewResult(approved=True, reviewed_draft=d, quality_score=80) for d in (base, twin)
    ]
    assert len(pick_pair(reviews)) == 1


def test_hook_type_and_candidate_metadata_are_stored() -> None:
    queue = NotionQueue("key", "db", session=type("S", (), {"headers": {}})())  # type: ignore[arg-type]
    expected = {
        HookType.NUMBER: "숫자형", HookType.MISTAKE: "실수방지형",
        HookType.COMPARISON: "비교형", HookType.EMPATHY: "공감형", HookType.QUESTION: "질문형",
    }
    for draft in drafts([8] * 5):
        props = queue._draft_properties(SOURCE, draft, QueueStatus.DRAFT, variant=1)
        assert props["Hook타입"]["select"]["name"] == expected[draft.hook_type]
        assert props["후보유형"]["select"]["name"] == draft.candidate_type.value
        assert props["승인상태"]["select"]["name"] == "검토대기"
        assert props["TistoryID"]["rich_text"][0]["text"]["content"] == "naver:777#2"
        assert props["원문키"]["rich_text"][0]["text"]["content"] == "naver:777"
        assert props["추천발행시점"]["rich_text"][0]["text"]["content"]
        assert props["AI점수"]["number"] == 8


def test_pending_review_item_is_never_scheduled_or_published() -> None:
    pending = QueueItem(
        page_id="p", status=QueueStatus.APPROVED, source_url=SOURCE.url,
        source_key="naver:777", source_hash=SOURCE.source_hash, title=SOURCE.title,
        draft=ThreadsDraft(format="single", posts=["본문"]),
        scheduled_at=datetime.now(UTC) - timedelta(minutes=1),
        approval_status=ApprovalStatus.PENDING,
    )

    class PublishQueue:
        scheduled: list[str] = []

        def approved_without_schedule(self):
            return [pending]

        def occupied_schedule_times(self, after):
            return set()

        def set_schedule(self, page_id, at):
            self.scheduled.append(page_id)

        def due(self, now, limit=1):
            return [pending]

    class Publisher:
        def publish(self, *args, **kwargs):
            raise AssertionError("pending item must not be published")

    queue = PublishQueue()
    result = HarnessOrchestrator(Source(), None, None, queue).publish_due(
        Publisher(), now=datetime.now(UTC), slots=("12:30",), timezone=UTC
    )
    assert result["published"] == 0 and queue.scheduled == []


def test_notion_queries_exclude_unapproved_review_states() -> None:
    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {"results": [], "has_more": False}

    class Session:
        headers: dict = {}
        payloads: list = []

        def post(self, url, *, json, timeout):
            self.payloads.append(json)
            return Response()

    session = Session()
    queue = NotionQueue("key", "db", session=session)  # type: ignore[arg-type]
    queue.approved_without_schedule()
    queue.due(datetime.now(UTC))
    gate = [{"property": "승인상태", "select": {"is_empty": True}},
            {"property": "승인상태", "select": {"equals": "승인"}}]
    for payload in session.payloads:
        assert {"or": gate} in payload["filter"]["and"]


def test_prefer_link_puts_blog_conversion_in_second_slot() -> None:
    reviews = [
        ReviewResult(approved=True, reviewed_draft=d, quality_score=80)
        for d in drafts([9, 8, 8, 9, 7])   # 공감(9)이 링크 후보(7)보다 높다
    ]
    assert pick_pair(reviews)[1].reviewed_draft.candidate_type is CandidateType.INFO_EMPATHY
    second = pick_pair(reviews, prefer_link=True)[1].reviewed_draft
    assert second.candidate_type is CandidateType.BLOG_CONVERSION and second.blog_link_used
