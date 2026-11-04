"""Local article cache, independent from authentication data."""
from .config import APP_DIR
from .storage import read_json, write_json

CACHE_FILE = APP_DIR / '商家监控文章.local.json'


def load_articles():
    records = read_json(CACHE_FILE, [])
    if not isinstance(records, list):
        return {}
    return {tuple(record['key']): tuple(record['values']) for record in records
            if isinstance(record, dict) and isinstance(record.get('key'), list)
            and len(record['key']) == 3 and isinstance(record.get('values'), list)
            and len(record['values']) == 7}


def save_articles(feed):
    temporary = CACHE_FILE.with_suffix('.tmp')
    write_json(temporary, [{'key': list(key), 'values': list(values)} for key, values in feed.items()])
    temporary.replace(CACHE_FILE)
