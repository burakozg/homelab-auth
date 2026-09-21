"""The login page. Plain HTML/CSS, no JS, no CDN — self-contained on purpose:
this page has to render even when every other app on the LAN (and whatever
CDN a fancier page might reach for) is unreachable, since it's the front door
to all of them. Loosely styled after this fleet's other admin.html pages
(see shortlist/shortlist/api/static/admin.html) but much simpler — one form.
"""

from __future__ import annotations

import html


def render_login_page(*, rd: str, error: str | None = None) -> str:
    rd_attr = html.escape(rd, quote=True)
    error_html = (
        f'<p class="error">{html.escape(error)}</p>' if error else ""
    )
    return f"""<!doctype html>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<title>Log in</title>
<style>
  :root {{
    --bg: #f7f7f5; --panel: #fff; --ink: #1a1a18; --muted: #6b6b66;
    --line: #e2e2dd; --accent: #2f6f4f; --bad: #9c3328; --radius: 8px;
  }}
  @media (prefers-color-scheme: dark) {{
    :root {{
      --bg: #16161a; --panel: #1e1e23; --ink: #e8e8e4; --muted: #97978f;
      --line: #2e2e35; --accent: #6fbf95; --bad: #e08579;
    }}
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; min-height: 100vh; display: flex; align-items: center; justify-content: center;
    background: var(--bg); color: var(--ink);
    font: 15px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif;
  }}
  form {{
    background: var(--panel); border: 1px solid var(--line); border-radius: var(--radius);
    padding: 1.5rem; width: 100%; max-width: 20rem;
  }}
  h1 {{ font-size: 1rem; margin: 0 0 1rem; }}
  label {{ display: block; color: var(--muted); font-size: .85rem; margin: .75rem 0 .25rem; }}
  input[type=text], input[type=password] {{
    width: 100%; padding: .6rem .7rem; border: 1px solid var(--line);
    border-radius: var(--radius); background: var(--bg); color: var(--ink); font: inherit;
  }}
  button {{
    margin-top: 1.25rem; width: 100%; padding: .6rem .9rem; border: 1px solid var(--line);
    border-radius: var(--radius); background: var(--accent); color: var(--panel);
    font: inherit; font-weight: 600; cursor: pointer;
  }}
  .error {{ color: var(--bad); font-size: .85rem; margin: .75rem 0 0; }}
</style>
<form method="post" action="/login">
  <h1>Log in</h1>
  <label for="username">Username</label>
  <input type="text" id="username" name="username" autocomplete="username" required autofocus>
  <label for="password">Password</label>
  <input type="password" id="password" name="password" autocomplete="current-password" required>
  <input type="hidden" name="rd" value="{rd_attr}">
  {error_html}
  <button type="submit">Log in</button>
</form>
"""
