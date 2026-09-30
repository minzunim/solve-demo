# 문항 추출 프로토타입 (AI 없음)

PDF → 페이지 이미지 + 문항 영역(bbox) 을 **좌표만으로** 추출합니다.
API 키 불필요, 오프라인 동작, 비용 0.

## 설치
```bash
python3 -m venv .venv
./.venv/bin/pip install pdfplumber pypdfium2 pillow
```

## 사용
```bash
./.venv/bin/python build.py <PDF경로>      # → out/questions.json + out/pages/*.webp
python3 -m http.server 8777                 # 뷰어 실행
open http://localhost:8777/viewer.html
```

## 뷰어 기능
- 문항 영역 오버레이 (파랑=문항, 보라 점선=공유 지문)
- 박스/목록 클릭 → 문항 선택, ← → 키로 페이지 이동
- 정답 직접 입력 (localStorage 저장)
- ✏️ 필기 → 획 중심점으로 문항 자동 귀속

## 동작 원리
문항 번호는 본문보다 글자가 큽니다(이 PDF: 13.5pt vs 11.5pt).
`크기 >= NUM_SIZE` + `^\d+\.$` 로 앵커를 찾고, **다음 앵커 직전까지**를 한 문항으로 묶습니다.

예외 처리 4가지 (build.py 상수로 조정):
- 단이 바뀌면 → 그 단 바닥까지
- 문항이 단/쪽을 넘어가면 → regions 배열로 복수 영역
- `[43~45]` 공유 지문 → 별도 블록 (shared=true)
- 페이지 번호·러닝 헤더 → 글자 크기/위치로 제외

## 한계
- **스캔본 불가** (`len(page.chars) < 50` 이면 빈 결과) → Vision AI 필요
- 조판이 다른 PDF는 `NUM_SIZE` 재조정 필요
- 양쪽 단을 가로지르는 큰 그림은 잘림

## 검증
`build.py` 실행 시 "빠진 번호"를 출력합니다. `없음`이 아니면 그 PDF는 검수 대상.
