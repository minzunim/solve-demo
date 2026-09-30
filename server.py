"""업로드 → 처리 → 결과 보기.  실행: ./.venv/bin/uvicorn server:app --reload"""
import json, shutil, uuid, pathlib, traceback
import os
from fastapi import FastAPI, UploadFile, File, HTTPException, Header
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

import build, answers

ROOT = pathlib.Path(__file__).parent
DATA = ROOT / 'data'; DATA.mkdir(exist_ok=True)
MAX_MB = 30
DEMO_KEY = os.getenv('DEMO_KEY')          # 설정하면 업로드에 코드 필요
TTL_H   = int(os.getenv('TTL_HOURS', 24))  # 이 시간 뒤 업로드 자동 삭제

app = FastAPI()


@app.on_event('startup')
def sweep():
    """오래된 업로드 정리. 데모 디스크가 차는 걸 막는다."""
    import time
    n = 0
    for d in DATA.iterdir():
        if d.is_dir() and time.time() - d.stat().st_mtime > TTL_H * 3600:
            shutil.rmtree(d, ignore_errors=True); n += 1
    if n:
        print(f"오래된 업로드 {n}건 삭제")


@app.post('/api/upload')
async def upload(paper: UploadFile = File(...), key: UploadFile | None = File(None),
                 x_demo_key: str | None = Header(None)):
    if DEMO_KEY and x_demo_key != DEMO_KEY:
        raise HTTPException(401, '접근 코드가 필요합니다')
    if not paper.filename.lower().endswith('.pdf'):
        raise HTTPException(400, 'PDF 파일만 업로드할 수 있습니다')

    jid = uuid.uuid4().hex[:10]
    d = DATA / jid; d.mkdir()
    try:
        p = d / 'paper.pdf'
        size = 0
        with p.open('wb') as f:
            while chunk := await paper.read(1 << 20):
                size += len(chunk)
                if size > MAX_MB << 20:
                    raise HTTPException(413, f'{MAX_MB}MB 이하만 가능합니다')
                f.write(chunk)

        data = build.build(str(p), str(d))               # 문항 영역 추출
        data['title'] = pathlib.Path(paper.filename).stem

        if key and key.filename:
            k = d / 'key.pdf'
            k.write_bytes(await key.read())
            parsed, how, _ = answers.parse_key(str(k))
            r = answers.merge(parsed, str(d))
            data = json.loads((d / 'questions.json').read_text())
            data['answer_stat'] = {'매칭': r['매칭'], '없음': r['정답없음'], '방식': how}

        data['id'] = jid
        (d / 'questions.json').write_text(json.dumps(data, ensure_ascii=False, indent=1))
        return {'id': jid, 'quality': data['quality'],
                'blocks': len(data['blocks']), 'pages': len(data['pages']),
                'answers': data.get('answer_stat')}
    except HTTPException:
        shutil.rmtree(d, ignore_errors=True); raise
    except Exception:
        shutil.rmtree(d, ignore_errors=True)
        return JSONResponse({'error': traceback.format_exc(limit=2)}, 500)


@app.get('/api/{jid}/questions.json')
def meta(jid: str):
    f = DATA / _safe(jid) / 'questions.json'
    if not f.exists():
        raise HTTPException(404)
    return json.loads(f.read_text())


@app.get('/api/{jid}/pages/{name}')
def page(jid: str, name: str):
    f = DATA / _safe(jid) / 'pages' / _safe(name)
    if not f.exists():
        raise HTTPException(404)
    return FileResponse(f, headers={'Cache-Control': 'public, max-age=31536000'})


def _safe(s: str) -> str:
    if '/' in s or '\\' in s or '..' in s:
        raise HTTPException(400, '잘못된 경로')
    return s


app.mount('/', StaticFiles(directory=ROOT / 'static', html=True), name='static')
