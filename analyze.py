"""새 조판 PDF → AI가 조판 설정(JSON)을 뽑아낸다.  조판당 1회만 호출하면 된다.

    export ANTHROPIC_API_KEY=sk-...
    python analyze.py <PDF> config.json
    python build.py <PDF> out config.json      # 이후로는 AI 없이 재사용
"""
import base64, io, json, os, sys, pathlib
import pypdfium2 as pdfium

PROMPT = """이 시험지 페이지 이미지를 보고, 문항 영역을 좌표로 추출하기 위한 설정값을 찾아주세요.

아래 JSON만 출력하세요. 설명 금지.

{
  "num_pattern": "문항 번호를 잡는 파이썬 정규식. 번호 숫자를 그룹 1로 캡처할 것. 예: (\\\\d{1,2})\\\\.",
  "num_min_size": 문항 번호로 인정할 최소 글자 크기(pt). 본문보다 커야 함,
  "set_pattern": "여러 문항이 공유하는 지문 헤더 정규식. 시작/끝 번호를 그룹 1,2로. 예: \\\\[(\\\\d+)[～~-](\\\\d+)\\\\]. 없으면 매칭되지 않는 패턴",
  "columns": 단 개수 (1 또는 2),
  "min_height": 유효한 문항 영역의 최소 높이(pt). 보통 20,
  "footer_ratio": 페이지 번호가 시작되는 높이 비율. 보통 0.85,
  "confidence": "high" | "low",
  "notes": "본문과 번호의 글자 크기, 단 구성 등 근거를 한 줄로"
}

판단 기준:
- 문항 번호는 본문보다 글자가 큰 경우가 많습니다. 두 크기를 구분할 수 있는 경계값을 고르세요.
- 2단 조판이면 columns=2. 좌우 단의 시작 x좌표가 뚜렷이 나뉩니다.
- 번호 표기가 1. / 1) / [1] / 문1. 중 무엇인지 확인하세요.
- 공유 지문 헤더가 없는 시험지면 set_pattern 에 절대 매칭 안 되는 값을 넣으세요.
- 확신이 없으면 confidence 를 "low" 로 하세요. 그 경우 사람이 검수합니다."""


def analyze(pdf_path, pages=(1, 2)):
    import anthropic                                  # 키가 있을 때만 필요
    doc = pdfium.PdfDocument(pdf_path)
    content = []
    for n in pages:
        if n > len(doc):
            break
        buf = io.BytesIO()
        doc[n - 1].render(scale=2).to_pil().save(buf, 'PNG')
        content.append({"type": "image", "source": {
            "type": "base64", "media_type": "image/png",
            "data": base64.b64encode(buf.getvalue()).decode()}})
    content.append({"type": "text", "text": PROMPT})

    r = anthropic.Anthropic().messages.create(
        model="claude-opus-5", max_tokens=1000,
        messages=[{"role": "user", "content": content}])
    txt = r.content[0].text.strip().removeprefix('```json').removeprefix('```').removesuffix('```')
    return json.loads(txt)


if __name__ == '__main__':
    if not os.getenv('ANTHROPIC_API_KEY'):
        sys.exit("ANTHROPIC_API_KEY 가 없습니다.")
    cfg = analyze(sys.argv[1])
    dest = sys.argv[2] if len(sys.argv) > 2 else 'config.json'
    pathlib.Path(dest).write_text(json.dumps(cfg, ensure_ascii=False, indent=1))
    print(json.dumps(cfg, ensure_ascii=False, indent=1))
    print(f"\n→ {dest}")
    if cfg.get('confidence') != 'high':
        print("⚠️ confidence 가 high 가 아닙니다 — 결과를 반드시 눈으로 확인하세요")
