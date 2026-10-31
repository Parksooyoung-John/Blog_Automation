# 마스터 돼지 자산 (대표사진용)

블로그 프로필 돼지가 유일한 마스터다. 다른 돼지는 쓰지 않고, 파일이 없으면 만들지 않고 멈춘다(`MISSING_MASTER_MASCOT`).

**특징**: 위로 선 귀 · 둥근 얼굴 · 밝은 분홍 · 머리 위 저금통 투입구 · 연두 새싹 · 목도리 없음 · 프로필과 같은 눈·코·볼 비율

**규격**: 투명 배경 PNG, 긴 변 1000px 이상, 돼지 전체가 잘리지 않을 것. 글자 없음.

| 파일 | 자세 |
|---|---|
| `face.png` | 프로필 얼굴. `profile_source.png`에서 `thumb_gate.py --cut-face`로 배경만 지운 것(AI 없음) |
| `calculator.png` | 계산기를 든 돼지 |
| `explain.png` | 설명하는 돼지 |
| `check.png` | 체크 표시를 든 돼지 |
| `warning.png` | 주의 표지판을 든 돼지 |
| `curious.png` | 궁금해하는 돼지 |

프로필과 같은지 눈으로 확인한 뒤 등록한다. 등록 뒤 파일이 바뀌면 `BLOCKED_MASCOT_INCONSISTENCY`로 멈춘다.

```bash
python -X utf8 thumb_gate.py --register-mascot
```

`face.png`만 있으면 같은 자세 3연속 규칙에 걸려 세 번째 글부터 막힌다. 나머지 자세는 프로필과 같은 돼지로 받아 넣는다.
