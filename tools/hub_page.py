"""The store PC's hub screen: what to confirm, who is up, what just happened.

Dark, large type, one action. The page is also written to 허브.html; the button posts to the hub.
"""
import html
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading
from urllib.parse import parse_qs

# hallmark: floor — tokens, focus-visible, reduced motion, clip. App screen for the kitchen, not a landing page.
CSS = """
:root {
  --ink: #f4efe4;
  --muted: #b7ad9c;
  --ground: #16130f;
  --line: #3a342c;
  --paper: #f3ead7;
  --paper-ink: #1c160f;
  --ok: #9dce8a;
  --wait: #e2b15a;
  --down: #e07a62;
  --font: "Apple SD Gothic Neo", "Malgun Gothic", "Noto Sans KR", sans-serif;
  --measure: 40rem;
}
* { box-sizing: border-box; }
html, body { overflow-x: clip; margin: 0; background: var(--ground); color: var(--ink); font-family: var(--font); }
body { font-size: 1.25rem; line-height: 1.4; }
main { max-width: var(--measure); margin: 0 auto; padding: 1.25rem 1rem 3rem; }
h1 { font-size: 2rem; font-weight: 700; line-height: 1.2; margin: 0.25rem 0 1rem; }
.mark { margin: 0; color: var(--muted); font-size: 1rem; }
.ticket { margin: 0 0 0.75rem; }
.ticket button, .empty {
  width: 100%; min-height: 3.5rem; border: 1px solid var(--paper); border-radius: 4px;
  background: var(--paper); color: var(--paper-ink); font: inherit; font-size: 1.5rem; text-align: left;
  padding: 0.8rem 1rem;
}
.ticket button { cursor: pointer; }
button:focus-visible, a:focus-visible { outline: 3px solid var(--wait); outline-offset: 3px; }
.empty { background: transparent; color: var(--muted); border-color: var(--line); }
.who { list-style: none; margin: 1.5rem 0; padding: 0; border-top: 1px solid var(--line); }
.who li { display: flex; justify-content: space-between; gap: 1rem; padding: 0.7rem 0; border-bottom: 1px solid var(--line); font-size: 1.35rem; }
.who b { font-weight: 600; }
[data-state="정상"] { color: var(--ok); }
[data-state="지연"] { color: var(--wait); }
[data-state="끊김"] { color: var(--down); }
.rail { list-style: none; margin: 0; padding: 0; }
.rail li { padding: 0.75rem 0; border-bottom: 1px solid var(--line); }
.rail .when { display: block; color: var(--muted); font-size: 1rem; }
.spend { color: var(--muted); font-size: 1rem; }
h2 { font-size: 1rem; font-weight: 600; color: var(--muted); margin: 1.5rem 0 0.25rem; }
@media (prefers-reduced-motion: reduce) {
  * { scroll-behavior: auto; }
}
"""


def _esc(value):
    return html.escape(str(value or ""), quote=True)


def render(view):
    """One screen: confirm buttons, four AI badges, the request timeline. `view` is hub.screen()."""
    tickets = view.get("confirms") or []
    if tickets:
        actions = "\n".join(
            f'<form class="ticket" method="post" action="/confirm">'
            f'<input type="hidden" name="id" value="{_esc(item["id"])}">'
            f'<button type="submit">확인 #{_esc(item["id"])} {_esc(item["text"])}</button></form>'
            for item in tickets
        )
    else:
        actions = '<p class="empty">지금 확인할 발주 없음</p>'
    badges = "\n".join(
        f'<li><span>{_esc(name)}</span> <b data-state="{_esc(state)}">{_esc(state)}</b></li>'
        for name, state in view.get("badges") or []
    )
    rail = "\n".join(
        f'<li><span class="when">{_esc(item["at"][11:16] if item.get("at") else "")} {_esc(item["id"])} {_esc(item["status"])}</span>'
        f'{_esc(item["from"])}에서 {_esc(item["to"])} {_esc(item["body"])}</li>'
        for item in view.get("timeline") or []
    ) or '<li><span class="when">아직 없음</span></li>'
    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>피클 허브</title>
<style>{CSS}</style>
</head>
<body>
<main>
<p class="mark">피클 허브</p>
<h1>확인할 일</h1>
{actions}
<h2>연결</h2>
<ul class="who">{badges}</ul>
<h2>요청</h2>
<ul class="rail">{rail}</ul>
<p class="spend">{_esc(view.get("spend") or "")}</p>
</main>
</body>
</html>
"""


def serve(get_html, confirm, host="127.0.0.1", port=8765):
    """Background server. confirm(id) writes `확인 #id` only when that task is still waiting."""

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            body = get_html().encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            if self.path.split("?", 1)[0] != "/confirm":
                self.send_error(404)
                return
            length = int(self.headers.get("Content-Length") or 0)
            form = parse_qs(self.rfile.read(length).decode("utf-8", "replace"))
            task_id = (form.get("id") or [""])[0]
            if task_id.isdigit():
                confirm(int(task_id))
            self.send_response(303)
            self.send_header("Location", "/")
            self.end_headers()

        def log_message(self, fmt, *args):
            return

    try:
        server = ThreadingHTTPServer((host, port), Handler)
    except OSError:
        return None
    threading.Thread(target=server.serve_forever, name="hub-page", daemon=True).start()
    return server
