# 마스터 돼지 자세 12종 (대표사진용)

블로그 프로필 돼지(`profile_source.png`)가 기준이다. 자세는 프로필을 참조 이미지로 **한 번만** 만들어 여기 고정하고, 글마다 다시 만들지 않는다.

**유지**: 위로 선 귀 · 둥근 얼굴 · 눈·코·볼터치 · 머리 위 저금통 투입구 · 연두 새싹 · 기본 분홍과 3D 질감

**규격**: 1600×1600 투명 PNG · 머리와 발이 200~1400px(`--import-pose`가 맞춘다) · 가로 중앙 · 외곽이 잘리지 않을 것 · 옷 없이 소품만 · 배경·그림자·글자 없음. 잘린 자세로 만들지 않는다. 자르는 것은 카드 단계에서 한다.

| 파일 | 자세 | 쓰는 곳 | `- 돼지 주제:` |
|---|---|---|---|
| `pig_face.png` | 정면·기본 미소 | 일반 요약 | general |
| `pig_point_left.png` | 왼쪽 가리킴 | 핵심 숫자·결론 | |
| `pig_point_up.png` | 위 가리킴 | 한도·조건 강조 | |
| `pig_calculator.png` | 계산기 | 세액·공제 계산 | tax_calculation |
| `pig_document.png` | 서류 | 신청·제출서류 | application |
| `pig_phone.png` | 휴대폰 | 조회·신청 방법 | lookup |
| `pig_laptop.png` | 노트북 | 홈택스·온라인 절차 | online_process |
| `pig_thinking.png` | 고민 | 비교·선택 | comparison |
| `pig_surprised.png` | 놀람 | 실수·주의사항 | warning |
| `pig_check.png` | 체크판 | 체크리스트 | checklist |
| `pig_coin.png` | 동전 | 지원금·환급금 | refund_support |
| `pig_family.png` | 집과 하트 | 부양가족·맞벌이 | dependent_family |

**상반신**: 비교 카드는 `pig_bust_자세.png`(아래가 잘린 투명 PNG)를 먼저 쓰고, 없으면 전신을 쓴다. 지금은 `pig_bust_calculator.png`뿐이다. 다른 자세는 그 글이 나올 때 후보를 보여 주고 승인받아 추가한다. 소품은 `../props/`.

**등록 순서**

```bash
python -X utf8 thumb_gate.py --import-pose calculator 받은파일.png
python -X utf8 thumb_gate.py --register-mascot
```

얼굴이 프로필과 같은지는 코드가 판정하지 못한다. 후보를 눈으로 본 사용자가 승인한 파일만 등록한다. 등록부(`registry.json`)에 해시·버전·승인일·상태를 둔다. 승인 없이 파일이 바뀌면 `BLOCKED_MASCOT_INCONSISTENCY`로 멈추고, `--register-mascot`도 덮어쓰지 않는다. 새 버전은 사용자가 터미널에서 승인한다.

```bash
python -X utf8 thumb_gate.py --approve-asset calculator
```
