"""PDF → 페이지 이미지 + 문항 영역(JSON).  AI 없이 좌표만으로 추출."""
import json, re, sys, pathlib
import pdfplumber, pypdfium2 as pdfium

NUM   = re.compile(r'(\d{1,2})\.')            # "21."
SETHD = re.compile(r'\[(\d+)[～~-](\d+)\]')    # "[43~45]"
PTS   = re.compile(r'\[(\d)점\]')

# ── 조판 설정 ──────────────────────────────────────────────
# PDF마다 달라지는 값. analyze.py(AI)가 채워주거나, 아래 기본값을 쓴다.
DEFAULT_CONFIG = {
    "num_pattern":   r"(\d{1,2})\.",   # 문항 번호 표기
    "num_min_size":  13.0,            # 번호로 칠 최소 글자 크기 (본문보다 커야 함)
    "set_pattern":   r"\[(\d+)[～~-](\d+)\]",   # 공유 지문 헤더
    "columns":       2,               # 단 개수
    "min_height":    20,              # 이보다 낮은 영역은 버림 (유령 조각)
    "footer_ratio":  0.85,            # 이 아래의 숫자는 페이지 번호로 간주
}

def load_config(path=None):
    """조판 설정. AI가 뽑아준 JSON이 있으면 그걸 쓰고, 없으면 기본값."""
    cfg = dict(DEFAULT_CONFIG)
    if path and pathlib.Path(path).exists():
        cfg.update(json.loads(pathlib.Path(path).read_text()))
        print(f"조판 설정 로드: {path}")
    return cfg


def _footer(w, h, ratio=0.85):
    return w['text'].isdigit() and w['top'] > h * ratio


def extract(path, cfg=None):
    cfg = cfg or DEFAULT_CONFIG
    NUM   = re.compile(cfg['num_pattern'])
    SETHD = re.compile(cfg['set_pattern'])
    NUM_SIZE, MIN_H = cfg['num_min_size'], cfg['min_height']
    pages, anchors = [], []
    with pdfplumber.open(path) as pdf:
        for pno, pg in enumerate(pdf.pages, 1):
            mid = pg.width / cfg['columns']
            if len(pg.chars) < 50:                       # 스캔본
                pages.append({'mid': mid, 'w': pg.width, 'h': pg.height,
                              'foot': {0: pg.height, 1: pg.height},
                              'head': {0: 0, 1: 0}, 'scan': True})
                continue
            words = [w for w in pg.extract_words(extra_attrs=['size'])
                     if not _footer(w, pg.height, cfg['footer_ratio'])]
            col = lambda w: 1 if w['x0'] >= mid else 0
            body = [w for w in words if w['size'] <= NUM_SIZE + 1]   # 러닝 헤더 제외
            pages.append({
                'mid': mid, 'w': pg.width, 'h': pg.height, 'scan': False,
                'foot': {c: max((w['bottom'] for w in words if col(w) == c),
                                default=pg.height) for c in (0, 1)},
                'head': {c: min((w['top'] for w in body if col(w) == c),
                                default=0) for c in (0, 1)},
            })
            txt_after = {}
            for w in words:
                if m := NUM.fullmatch(w['text']):
                    if w['size'] >= NUM_SIZE:
                        anchors.append((pno, col(w), w['top'], [int(m.group(1))]))
                elif m := SETHD.match(w['text']):
                    a, b = int(m.group(1)), int(m.group(2))
                    anchors.append((pno, col(w), w['top'], list(range(a, b + 1))))
    anchors.sort()

    def slot(pno, c):
        p = pages[pno - 1]
        return (0, p['mid']) if c == 0 else (p['mid'], p['w'])

    blocks = []
    for i, (pno, c, top, nos) in enumerate(anchors):
        nxt = anchors[i + 1] if i + 1 < len(anchors) else None
        regions, cp, cc, ct = [], pno, c, top - 4
        while True:
            x0, x1 = slot(cp, cc)
            same = nxt and nxt[0] == cp and nxt[1] == cc
            bot = nxt[2] - 4 if same else pages[cp - 1]['foot'][cc]
            if bot - ct > MIN_H:
                P = pages[cp - 1]
                regions.append({'page': cp, 'box': [round(x0 / P['w'], 4),
                                                    round(ct / P['h'], 4),
                                                    round((x1 - x0) / P['w'], 4),
                                                    round((bot - ct) / P['h'], 4)]})
            if same or not nxt:
                break
            cp, cc = (cp, 1) if cc == 0 else (cp + 1, 0)
            if (cp, cc) > (nxt[0], nxt[1]) or cp > len(pages):
                break
            ct = pages[cp - 1]['head'][cc] - 4
        if regions:
            blocks.append({'nos': nos, 'shared': len(nos) > 1, 'regions': regions})
    return blocks, pages


def points_of(path, blocks):
    """발문에서 [3점] 찾아 배점 부여. 없으면 2점."""
    out = {}
    with pdfplumber.open(path) as pdf:
        for b in blocks:
            if b['shared']:
                continue
            r = b['regions'][0]
            P = pdf.pages[r['page'] - 1]
            x, y, w, h = r['box']
            t = P.crop((x * P.width, y * P.height,
                        (x + w) * P.width, min((y + h) * P.height, P.height))
                       ).extract_text() or ''
            m = PTS.search(t)          # 발문이 공유 헤더에 있는 문항은 [3점]이 지문 끝에 붙음
            out[b['nos'][0]] = int(m.group(1)) if m else 2
    return out


def judge(blocks, nos, pages):
    """이 PDF를 좌표 방식으로 처리해도 되는지 판정. AI로 넘길지 여기서 갈린다."""
    if any(p['scan'] for p in pages):
        return {'verdict': 'AI필요', 'reason': '스캔본 — 텍스트 레이어 없음', 'ok': False}
    if not nos:
        return {'verdict': 'AI필요', 'reason': '문항을 하나도 못 찾음 — 조판이 다름', 'ok': False}
    gap = sorted(set(range(1, max(nos) + 1)) - set(nos))
    if gap:
        return {'verdict': '검수필요', 'reason': f'빠진 번호 {gap}', 'ok': False}
    # 공유 지문 헤더는 한 줄짜리(≈0.02)가 정상. 일반 문항만 검사한다
    tiny = [b['nos'] for b in blocks if not b['shared']
            and any(r['box'][3] < 0.025 for r in b['regions'])]
    if tiny:
        return {'verdict': '검수필요', 'reason': f'비정상적으로 작은 영역 {tiny[:5]}', 'ok': False}
    return {'verdict': '통과', 'reason': f'문항 {min(nos)}~{max(nos)} 연속, 빠짐 없음', 'ok': True}


def build(pdf_path, outdir='out', scale=1.6, config=None):
    cfg = load_config(config)
    out = pathlib.Path(outdir)
    (out / 'pages').mkdir(parents=True, exist_ok=True)
    blocks, pages = extract(pdf_path, cfg)
    pts = points_of(pdf_path, blocks)

    doc = pdfium.PdfDocument(pdf_path)
    meta = []
    for i, p in enumerate(doc, 1):
        img = p.render(scale=scale).to_pil()
        img.save(out / 'pages' / f'{i}.webp', 'WEBP', quality=82)
        meta.append({'n': i, 'img': f'pages/{i}.webp'})

    # 재추출 시 기존 정답을 보존한다 — 검수로 확정한 값을 날리면 안 된다
    prev = {}
    f = out / 'questions.json'
    if f.exists():
        old = json.loads(f.read_text())
        prev = {tuple(b['nos']): b.get('answer') for b in old.get('blocks', [])}

    kept = 0
    for b in blocks:
        b['points'] = pts.get(b['nos'][0]) if not b['shared'] else None
        b['answer'] = prev.get(tuple(b['nos']))
        if b['answer']:
            kept += 1
    if kept:
        print(f"기존 정답 {kept}개 유지")

    nos = sorted({n for b in blocks for n in b['nos']})
    data = {'title': pathlib.Path(pdf_path).stem,
            'scan': any(p['scan'] for p in pages),
            'quality': judge(blocks, nos, pages),
            'pages': meta, 'blocks': blocks}
    f.write_text(json.dumps(data, ensure_ascii=False, indent=1))

    q = data['quality']
    print(f"쪽 {len(meta)} / 블록 {len(blocks)} / 문항 {len(nos)}개"
          + (f" ({min(nos)}~{max(nos)})" if nos else ""))
    print(f"판정: {q['verdict']}  —  {q['reason']}")
    print(f"→ {out}/questions.json")
    return data


if __name__ == '__main__':
    build(sys.argv[1],
          sys.argv[2] if len(sys.argv) > 2 else 'out',
          config=sys.argv[3] if len(sys.argv) > 3 else None)
