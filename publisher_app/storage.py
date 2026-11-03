import json
from .config import LSB_SESSION_FILE, ARTICLE_MAP_FILE


def read_json(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


class LocalStore:
    def load_lsb_session(self):
        return read_json(LSB_SESSION_FILE, {"uid": None, "sid": None, "cookies": {}})

    def save_lsb_session(self, uid, sid, cookies):
        write_json(LSB_SESSION_FILE, {"uid": uid, "sid": sid, "cookies": cookies})

    def articles(self):
        return read_json(ARTICLE_MAP_FILE, [])

    def add_article(self, platform, title, article_id):
        rows = self.articles()
        rows.insert(0, {"platform": platform, "title": title, "id": str(article_id)})
        write_json(ARTICLE_MAP_FILE, rows)
        return rows
