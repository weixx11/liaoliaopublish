import json
from threading import Lock
from .config import LSB_SESSION_FILE, YILIAO_SESSION_FILE, ARTICLE_MAP_FILE, APP_DIR

SESSION_FILE = APP_DIR / "平台会话.local.json"
_session_lock = Lock()


def read_json(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def _sessions():
    if SESSION_FILE.exists():
        return json.loads(SESSION_FILE.read_text(encoding="utf-8"))
    return {
        "壹料": read_json(YILIAO_SESSION_FILE, {}),
        "料商宝": read_json(LSB_SESSION_FILE, {}),
    }


def load_session(platform):
    with _session_lock:
        sessions = _sessions()
        if not SESSION_FILE.exists() and any(sessions.values()):
            _write_sessions(sessions)
        return sessions.get(platform, {})


def _write_sessions(sessions):
    temporary = SESSION_FILE.with_suffix(".tmp")
    write_json(temporary, sessions)
    temporary.replace(SESSION_FILE)


def save_session(platform, credentials):
    with _session_lock:
        sessions = _sessions()
        sessions[platform] = credentials
        _write_sessions(sessions)


class LocalStore:
    def load_lsb_session(self):
        return load_session("料商宝")

    def save_lsb_session(self, uid, sid, cookies):
        save_session("料商宝", {"uid": uid, "sid": sid, "cookies": cookies})

    def articles(self):
        return read_json(ARTICLE_MAP_FILE, [])

    def add_article(self, platform, title, article_id):
        rows = self.articles()
        rows.insert(0, {"platform": platform, "title": title, "id": str(article_id)})
        write_json(ARTICLE_MAP_FILE, rows)
        return rows
