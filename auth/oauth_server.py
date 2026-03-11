"""
Temporary Flask server that catches the Supabase OAuth redirect.

Flow:
1. Caller calls start_oauth_callback_server() → gets a threading.Event
2. The system browser opens the Supabase OAuth URL
3. After the user authorises, Supabase redirects to http://127.0.0.1:54321/auth/callback
4. The Flask route handles:
   - PKCE flow:     ?code=xxx  → exchange_code_for_session()
   - Implicit flow: no code    → return an HTML page that JS-posts the fragment tokens
5. done_event is set; caller reads get_received_session()
6. Caller calls stop_server() to clean up

The server runs in a daemon thread — it is killed automatically when the main
process exits, so no cleanup is required if the user closes the window early.
"""

from __future__ import annotations

import json
import threading

_done_event: threading.Event | None = None
_received_session: dict | None = None
_server_thread: threading.Thread | None = None
_shutdown_func = None

CALLBACK_PORT = 54321
CALLBACK_URL  = f"http://127.0.0.1:{CALLBACK_PORT}/auth/callback"

# ── HTML pages ────────────────────────────────────────────────────────────────

_SUCCESS_HTML = """<!DOCTYPE html>
<html>
<head><title>DishBoard — Signed in</title>
<style>
  body { font-family: -apple-system, sans-serif; background: #0a0a0a; color: #f0f0f0;
         display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0; }
  .box { text-align: center; padding: 40px; }
  h1   { color: #34d399; font-size: 28px; margin-bottom: 8px; }
  p    { color: #888; font-size: 15px; }
</style>
</head>
<body>
<div class="box">
  <h1>✓ Signed in!</h1>
  <p>You can close this window and return to DishBoard.</p>
</div>
</body>
</html>"""

_ERROR_HTML = """<!DOCTYPE html>
<html>
<head><title>DishBoard — Sign-in failed</title>
<style>
  body {{ font-family: -apple-system, sans-serif; background: #0a0a0a; color: #f0f0f0;
         display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0; }}
  .box {{ text-align: center; padding: 40px; }}
  h1   {{ color: #dc3545; font-size: 28px; margin-bottom: 8px; }}
  p    {{ color: #888; font-size: 15px; }}
</style>
</head>
<body>
<div class="box">
  <h1>Sign-in failed</h1>
  <p>{error}</p>
  <p>Please close this window and try again in DishBoard.</p>
</div>
</body>
</html>"""

# Implicit-flow fallback: JS reads the URL fragment and POSTs tokens back
_FRAGMENT_CAPTURE_HTML = f"""<!DOCTYPE html>
<html>
<head><title>DishBoard — Signing in…</title>
<style>
  body {{ font-family: -apple-system, sans-serif; background: #0a0a0a; color: #f0f0f0;
         display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0; }}
  .box {{ text-align: center; padding: 40px; }}
  p    {{ color: #888; font-size: 15px; }}
</style>
</head>
<body>
<div class="box"><p>Completing sign-in…</p></div>
<script>
  (function() {{
    var frag = window.location.hash.substring(1);
    if (!frag) return;
    var params = {{}};
    frag.split('&').forEach(function(p) {{
      var kv = p.split('=');
      params[decodeURIComponent(kv[0])] = decodeURIComponent(kv[1] || '');
    }});
    fetch('http://127.0.0.1:{CALLBACK_PORT}/auth/token', {{
      method: 'POST',
      headers: {{'Content-Type': 'application/json'}},
      body: JSON.stringify(params)
    }}).then(function() {{
      document.querySelector('p').textContent = 'Signed in! You can close this window.';
    }});
  }})();
</script>
</body>
</html>"""


# ── Public API ────────────────────────────────────────────────────────────────

def start_oauth_callback_server() -> threading.Event:
    """Start the Flask callback server in a daemon thread.

    Returns a threading.Event that is set when a session is received.
    The session dict (or None on failure) is available via get_received_session().
    """
    global _done_event, _received_session, _server_thread, _shutdown_func

    _done_event       = threading.Event()
    _received_session = None

    _server_thread = threading.Thread(target=_run_server, daemon=True)
    _server_thread.start()
    return _done_event


def get_received_session() -> dict | None:
    """Return the session dict captured by the callback, or None."""
    return _received_session


def stop_server() -> None:
    """Request shutdown of the Flask server (best-effort)."""
    global _shutdown_func
    if _shutdown_func:
        try:
            _shutdown_func()
        except Exception:
            pass
        _shutdown_func = None


# ── Flask server ──────────────────────────────────────────────────────────────

def _run_server() -> None:
    global _shutdown_func

    from flask import Flask, request, jsonify
    import logging

    # Suppress Flask startup logs
    log = logging.getLogger("werkzeug")
    log.setLevel(logging.ERROR)

    flask_app = Flask(__name__)

    @flask_app.route("/auth/callback")
    def callback():
        global _received_session
        code = request.args.get("code")

        if code:
            # PKCE flow — exchange code for session
            try:
                from auth.supabase_client import get_client
                from auth.session_manager import build_session_dict
                client   = get_client()
                response = client.auth.exchange_code_for_session({"auth_code": code})
                if response and response.user:
                    _received_session = build_session_dict(response)
                    _done_event.set()
                    return _SUCCESS_HTML
                else:
                    _done_event.set()
                    return _ERROR_HTML.format(error="No session returned."), 400
            except Exception as exc:
                _done_event.set()
                return _ERROR_HTML.format(error=str(exc)), 500
        else:
            # Implicit flow — return JS page that will POST the fragment tokens
            return _FRAGMENT_CAPTURE_HTML

    @flask_app.route("/auth/token", methods=["POST"])
    def receive_token():
        global _received_session
        data          = request.get_json(force=True, silent=True) or {}
        access_token  = data.get("access_token", "")
        refresh_token = data.get("refresh_token", "")

        if not access_token:
            return jsonify({"ok": False, "error": "no access_token"}), 400

        try:
            from auth.supabase_client import get_client
            client   = get_client()
            response = client.auth.set_session(access_token, refresh_token)
            if response and response.user:
                from auth.session_manager import build_session_dict
                _received_session = build_session_dict(response)
                _done_event.set()
                return jsonify({"ok": True})
        except Exception as exc:
            _done_event.set()
            return jsonify({"ok": False, "error": str(exc)}), 500

        _done_event.set()
        return jsonify({"ok": False, "error": "set_session failed"}), 500

    # Use werkzeug's make_server so we can shut it down programmatically
    from werkzeug.serving import make_server
    server = make_server("127.0.0.1", CALLBACK_PORT, flask_app)
    _shutdown_func = server.shutdown
    server.serve_forever()
