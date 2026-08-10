#!/usr/bin/env python3
"""보드 — 마크다운을 그대로 읽어 그리는 로컬 대시보드.

index.html 안의 <!-- AUTO:xxx --> ~ <!-- /AUTO:xxx --> 구간만
team-board 마크다운에서 만들어 끼워 넣는다. index.html은 쓰지 않는다.
요청이 올 때마다 파일을 다시 읽으므로 "새로고침 = 최신"이 성립한다.

    python3 board.py           # 서버 실행 + 브라우저 열기
    python3 board.py --check   # 생성이 정상인지 자체 점검
"""

import html
import http.server
import re
import socketserver
import sys
import webbrowser
from datetime import datetime
from pathlib import Path

BOARD = Path(__file__).resolve().parent / "index.html"
TEAM = Path("/Users/ok/Documents/게임기획-01/close-wild-hearts/team-board")
PORT = 8787

CIRCLED = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫"
STATUS = "🆕👀🔨✅❌⏸🚫"
CLOSED = "✅❌⏸🚫"


def inline(s):
    """마크다운 한 줄 → HTML 조각 (굵게·코드만 인정)."""
    s = html.escape(s.strip())
    s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
    s = re.sub(r"`(.+?)`", r"<code>\1</code>", s)
    return s


def plain(s, limit=0):
    s = re.sub(r"[*`]", "", s).strip()
    if limit and len(s) > limit:
        s = s[:limit].rstrip() + "…"
    return html.escape(s)


def krow(who, small, desc, st, st_cls=""):
    small = f"<small>{small}</small>" if small else ""
    cls = f' class="{st_cls}"' if st_cls else ""
    return (
        '<div class="krow">'
        f'<div class="who">{who}{small}</div>'
        f'<div class="desc">{desc}</div>'
        f'<div class="st"><b{cls}>{st}</b></div>'
        "</div>"
    )


def sprint_blocks(text):
    """CURRENT_SPRINT의 '## 🔖' 세션 블록 목록 (문서 순서 = 최신 먼저)."""
    blocks = []
    for part in re.split(r"^## 🔖 ", text, flags=re.M)[1:]:
        head, _, body = part.partition("\n")
        blocks.append((head.strip(), body))
    return blocks


def chip(text):
    """행 내용에서 상태 칩 하나를 고른다."""
    for p in ("P0", "P1"):
        if p in text:
            return p, "crit"
    if "Play" in text:
        return "Play 대기", "crit"
    for p in ("P2", "P3"):
        if p in text:
            return p, ""
    return "대기", ""


def render_next(sprint):
    blocks = sprint_blocks(sprint)
    if not blocks:
        return '<p class="sub" data-auto="next">CURRENT_SPRINT에서 세션 블록을 찾지 못했습니다.</p>'
    head, body = blocks[0]
    lines = body.splitlines()
    start = next((i for i, l in enumerate(lines) if "재개 SSOT" in l), None)

    rows = []
    if start is not None:
        for line in lines[start + 1 :]:
            line = line.strip()
            if not line.startswith(">"):
                break
            content = line.lstrip("> ").strip()
            if not content or content[0] not in CIRCLED:
                break
            num, rest = content[0], content[1:].strip()
            m = re.match(r"\*\*(.+?)\*\*\s*[—-]?\s*(.*)", rest)
            if m:
                title, desc = m.group(1), m.group(2)
            elif "—" in rest:
                title, _, desc = rest.partition("—")
            else:
                title, desc = "", rest
            st, cls = chip(rest)
            rows.append(
                krow(
                    f"{num} {plain(title)}" if title else num,
                    "",
                    inline(desc) or inline(rest),
                    st,
                    cls,
                )
            )

    if not rows:
        rows = ['<div class="krow"><div class="desc">재개 SSOT 항목이 비어 있습니다.</div></div>']
    sub = f'<p class="sub" data-auto="next">CURRENT_SPRINT 최신 블록에서 자동 생성 — {plain(head.replace("← 최신", ""), 90)}</p>'
    return sub + "\n" + "\n".join(rows)


def parse_items(text, pattern):
    """(번호, 제목, 상태이모지, 우선순위) 목록."""
    items = []
    matches = list(re.finditer(pattern, text, flags=re.M))
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[m.end() : end]
        title = m.group(2).strip()
        status = next((c for c in title for _ in [0] if c in STATUS), "")
        pm = re.search(r"\bP[0-3]\b", body)
        clean = "".join(c for c in title if c not in STATUS).strip()
        items.append((m.group(1), clean, status, pm.group(0) if pm else ""))
    return items


def render_issues(bugs, polish):
    rows = []
    order = {"P0": 0, "P1": 1, "P2": 2, "P3": 3, "": 4}

    open_bugs = [i for i in parse_items(bugs, r"^### (B-\d+) — (.+?)$") if i[2] not in CLOSED]
    open_bugs.sort(key=lambda i: order[i[3]])
    for num, title, status, pri in open_bugs:
        st, cls = (pri or status or "열림"), ("crit" if pri in ("P0", "P1") else "")
        rows.append(krow(num, "버그", f"{status} {html.escape(title)}".strip(), st, cls))

    open_polish = [i for i in parse_items(polish, r"^## (P-\d+)\. (.+?)$") if i[2] not in CLOSED]
    for num, title, status, pri in open_polish:
        rows.append(krow(num, "폴리싱", f"{status} {html.escape(title)}".strip(), pri or "열림"))

    sub = (
        f'<p class="sub" data-auto="issues">BUGS.md · POLISH.md에서 자동 생성 — '
        f"열린 버그 {len(open_bugs)}건 · 열린 폴리싱 {len(open_polish)}건 "
        "(해결 ✅ · 보류 ⏸ 제외).</p>"
    )
    return sub + "\n" + "\n".join(rows or ['<div class="krow"><div class="desc">열린 항목 없음.</div></div>'])


# [8/10 디렉터] "최근 완료" 구간 폐기 — 지나간 일은 보드에서 볼 이유가 없다.
# 이력은 CURRENT_SPRINT.md 세션 블록에 그대로 남아 있으므로 손실 없음. (옛 render_recent 삭제)


def render_stamp():
    # [8/10 디렉터] 새로고침마다 시각이 바뀌면 "언제 기준 내용인지"를 알 수 없다.
    # → 실행 시각(datetime.now) 대신 **읽어온 마크다운 3종의 마지막 수정 시각**으로 고정.
    #   문서가 안 바뀌면 몇 번을 새로고침해도 같은 시각이 뜬다 = 그 시각이 곧 내용의 기준점.
    srcs = ["CURRENT_SPRINT.md", "BUGS.md", "POLISH.md"]
    latest = max((TEAM / f).stat().st_mtime for f in srcs)
    ts = datetime.fromtimestamp(latest)
    weekday = "월화수목금토일"[ts.weekday()]
    return (
        f'<b data-auto="stamp">{ts:%Y-%m-%d}({weekday}) {ts:%H:%M:%S}</b> 기준 — '
        "마크다운을 읽어 그리는 로컬 보드 (이 시각 = 문서가 마지막으로 바뀐 때) · "
        "기간 표기는 커밋 이력 기준 근사"
    )


def zone(page, name, body):
    pat = re.compile(rf"(<!-- AUTO:{name}\b[^>]*-->).*?(<!-- /AUTO:{name} -->)", re.S)
    return pat.sub(lambda m: f"{m.group(1)}\n{body}\n{m.group(2)}", page, count=1)


def render():
    page = BOARD.read_text(encoding="utf-8")
    sprint = (TEAM / "CURRENT_SPRINT.md").read_text(encoding="utf-8")
    bugs = (TEAM / "BUGS.md").read_text(encoding="utf-8")
    polish = (TEAM / "POLISH.md").read_text(encoding="utf-8")
    page = zone(page, "stamp", render_stamp())
    page = zone(page, "next", render_next(sprint))
    page = zone(page, "issues", render_issues(bugs, polish))
    return page


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            body = render().encode("utf-8")
        except Exception as exc:  # 파싱 실패해도 화면은 떠야 원인이 보인다
            body = f"<pre>보드 생성 실패: {html.escape(repr(exc))}</pre>".encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


def check():
    out = render()
    for name in ("stamp", "next", "issues"):
        assert f'data-auto="{name}"' in out, f"{name} 구간이 생성되지 않았습니다"
    assert out.count('class="krow"') >= 10, "생성된 행이 너무 적습니다"
    assert "<!-- AUTO:next" in out and "</html>" in out, "템플릿이 깨졌습니다"
    print(f"OK — 행 {out.count('class=\"krow\"')}개 생성")


if __name__ == "__main__":
    if "--check" in sys.argv:
        check()
        raise SystemExit

    url = f"http://localhost:{PORT}/"
    socketserver.TCPServer.allow_reuse_address = True
    try:
        server = socketserver.TCPServer(("127.0.0.1", PORT), Handler)
    except OSError:
        print(f"이미 실행 중입니다 — {url}")
        webbrowser.open(url)
        raise SystemExit
    print(f"보드 실행 중: {url}   (종료 = Ctrl+C)")
    webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n종료했습니다.")
