"""SQLite storage for clients and their post history."""
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS clients (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    address TEXT DEFAULT '',
    phone TEXT DEFAULT '',
    website TEXT DEFAULT '',
    gbp_link TEXT DEFAULT '',
    notes TEXT DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS posts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id INTEGER NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'ok',
    layout TEXT DEFAULT '',
    last_used TEXT DEFAULT '',
    opener TEXT DEFAULT '',
    closer TEXT DEFAULT '',
    filename TEXT DEFAULT '',
    length INTEGER DEFAULT 0,
    post_type TEXT DEFAULT '',
    post_text TEXT DEFAULT '',
    cta_url TEXT DEFAULT '',
    match_status TEXT DEFAULT '',
    match_pct INTEGER,
    notes TEXT DEFAULT '',
    user_message TEXT DEFAULT '',
    raw_output TEXT DEFAULT '',
    image_path TEXT DEFAULT '',
    type_details TEXT DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_posts_client ON posts(client_id, id DESC);
"""

CLIENT_COLS = ("name", "address", "phone", "website", "gbp_link", "notes")
POST_COLS = (
    "client_id", "status", "layout", "last_used", "opener", "closer", "filename", "length",
    "post_type", "post_text", "cta_url", "match_status", "match_pct", "notes",
    "user_message", "raw_output", "image_path", "type_details",
)
_ready = set()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@contextmanager
def conn():
    path = str(config.db_path())
    c = sqlite3.connect(path)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    try:
        if path not in _ready:
            c.executescript(SCHEMA)
            cols = {r["name"] for r in c.execute("PRAGMA table_info(posts)")}
            if "type_details" not in cols:  # databases created before the post type option
                c.execute("ALTER TABLE posts ADD COLUMN type_details TEXT DEFAULT ''")
            _ready.add(path)
        yield c
        c.commit()
    finally:
        c.close()


def _row(r):
    return dict(r) if r else None


# ---- clients ----
def list_clients():
    with conn() as c:
        return [dict(r) for r in c.execute("SELECT * FROM clients ORDER BY name COLLATE NOCASE")]


def get_client(client_id):
    with conn() as c:
        return _row(c.execute("SELECT * FROM clients WHERE id=?", (client_id,)).fetchone())


def create_client(data: dict) -> dict:
    vals = [str(data.get(k, "") or "").strip() for k in CLIENT_COLS]
    with conn() as c:
        cur = c.execute(
            "INSERT INTO clients (name,address,phone,website,gbp_link,notes,created_at) VALUES (?,?,?,?,?,?,?)",
            (*vals, _now()),
        )
        new_id = cur.lastrowid
    return get_client(new_id)


def update_client(client_id, data: dict):
    sets = [k for k in CLIENT_COLS if k in data]
    if not sets:
        return get_client(client_id)
    with conn() as c:
        c.execute(
            f"UPDATE clients SET {', '.join(k + '=?' for k in sets)} WHERE id=?",
            (*[str(data[k] or "").strip() for k in sets], client_id),
        )
    return get_client(client_id)


def delete_client(client_id):
    with conn() as c:
        c.execute("DELETE FROM clients WHERE id=?", (client_id,))


# ---- posts ----
def add_post(**fields) -> int:
    cols = [k for k in POST_COLS if k in fields]
    with conn() as c:
        cur = c.execute(
            f"INSERT INTO posts ({','.join(cols)},created_at) VALUES ({','.join('?' * len(cols))},?)",
            (*[fields[k] for k in cols], _now()),
        )
        return cur.lastrowid


def update_post(post_id, **fields):
    cols = [k for k in POST_COLS if k in fields]
    if not cols:
        return
    with conn() as c:
        c.execute(
            f"UPDATE posts SET {', '.join(k + '=?' for k in cols)} WHERE id=?",
            (*[fields[k] for k in cols], post_id),
        )


def get_post(post_id):
    with conn() as c:
        return _row(c.execute("SELECT * FROM posts WHERE id=?", (post_id,)).fetchone())


def get_posts(client_id, limit=None, status="ok", exclude_id=None):
    """Newest first. status=None returns every status."""
    sql, args = "SELECT * FROM posts WHERE client_id=?", [client_id]
    if status:
        sql += " AND status=?"
        args.append(status)
    if exclude_id:
        sql += " AND id<>?"
        args.append(exclude_id)
    sql += " ORDER BY id DESC"
    if limit:
        sql += " LIMIT ?"
        args.append(limit)
    with conn() as c:
        return [dict(r) for r in c.execute(sql, args)]


def all_filenames(client_id, exclude_id=None):
    return [p["filename"] for p in get_posts(client_id, status=None, exclude_id=exclude_id) if p["filename"]]


def recent_layouts_global(limit=3, exclude_id=None):
    sql, args = "SELECT layout FROM posts WHERE status='ok' AND layout<>''", []
    if exclude_id:
        sql += " AND id<>?"
        args.append(exclude_id)
    sql += " ORDER BY id DESC LIMIT ?"
    args.append(limit)
    with conn() as c:
        return [r["layout"] for r in c.execute(sql, args)]


def delete_post(post_id):
    with conn() as c:
        c.execute("DELETE FROM posts WHERE id=?", (post_id,))
