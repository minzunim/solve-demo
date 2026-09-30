"""정답표 PDF → {문항번호: 정답}  →  out/questions.json 에 병합."""
import json, re, sys, pathlib, pdfplumber

CIRCLE = "①②③④⑤"
C2N    = {c: str(i + 1) for i, c in enumerate(CIRCLE)}

# "21 ④"  — 원문자는 배점 숫자와 헷갈릴 일이 없어 가장 안전
PAIR_CIRCLE = re.compile(r'(\d{1,2})\s*[.)]?\s*([①-⑤])')
# "21 4"   — 원문자가 없는 표용 (2차 시도)
PAIR_DIGIT  = re.compile(r'(\d{1,2})\s*[.)]\s*([1-5])\b')
# "21 ② 3" — 정답 뒤 배점. 문제지에서 뽑은 배점과 대조하는 용도
TRIPLE      = re.compile(r'(\d{1,2})\s*([\u2460-\u2464])\s*([1-5])\b')


def parse_key(path):
    """→ ({no: '1'~'5'}, 사용한_방식)"""
    with pdfplumber.open(path) as pdf:
        text = "\n".join(p.extract_text() or "" for p in pdf.pages)

    hits = [(int(n), C2N[c]) for n, c in PAIR_CIRCLE.findall(text)]
    how = "원문자"
    if not hits:
        hits = [(int(n), a) for n, a in PAIR_DIGIT.findall(text)]
        how = "숫자"
    if not hits:
        return {}, "실패", text

    key, dup = {}, []
    for n, a in hits:
        if n in key and key[n] != a:
            dup.append(n)
        key[n] = a
    if dup:
        print(f"  ⚠️ 번호 {sorted(set(dup))} 가 서로 다른 정답으로 두 번 나옵니다")
    return key, how, text


def check_points(key_text, data):
    """정답표 배점 vs 문제지에서 뽑은 배점. 둘 중 하나가 틀렸다는 강한 신호."""
    kp = {int(n): int(p) for n, _, p in TRIPLE.findall(key_text)}
    if not kp:
        return None
    dp = {b['nos'][0]: b['points'] for b in data['blocks'] if not b['shared']}
    bad = [(n, dp.get(n), kp[n]) for n in sorted(kp) if dp.get(n) != kp[n]]
    return {'불일치': bad, '합계': (sum(dp.values()), sum(kp.values()))}


def merge(key, out='out'):
    f = pathlib.Path(out) / 'questions.json'
    data = json.loads(f.read_text())
    nos = sorted({n for b in data['blocks'] for n in b['nos']})

    hit = miss = 0
    for b in data['blocks']:
        if b['shared']:
            continue
        n = b['nos'][0]
        if n in key:
            b['answer'] = key[n]; hit += 1
        else:
            miss += 1

    f.write_text(json.dumps(data, ensure_ascii=False, indent=1))
    extra = sorted(set(key) - set(nos))          # 정답표엔 있는데 문제지엔 없는 번호
    lack  = sorted(set(nos) - set(key))          # 그 반대
    return {'매칭': hit, '정답없음': miss, '정답표에만': extra, '문제지에만': lack}


if __name__ == '__main__':
    key, how, text = parse_key(sys.argv[1])
    print(f"정답표 파싱: {len(key)}개 ({how} 방식)")
    outdir = sys.argv[2] if len(sys.argv) > 2 else 'out'
    r = merge(key, outdir)
    print(f"매칭 {r['매칭']}  /  정답 없는 문항 {r['정답없음']}")
    if r['정답표에만']: print(f"  ⚠️ 정답표에만 있는 번호: {r['정답표에만']}")
    if r['문제지에만']: print(f"  ⚠️ 정답이 없는 문항:     {r['문제지에만']}")
    cp = check_points(text, json.loads((pathlib.Path(outdir) / 'questions.json').read_text()))
    if cp:
        d, k = cp['합계']
        print(f"배점 합계: 문제지 {d}점 / 정답표 {k}점")
        for n, a, b in cp['불일치']:
            print(f"  ⚠️ {n}번 배점: 문제지 {a}점 vs 정답표 {b}점")
    ok = not (r['정답없음'] or r['정답표에만'] or r['문제지에만'] or (cp and cp['불일치']))
    print("완전 일치 ✅" if ok else "→ 검수 필요")
