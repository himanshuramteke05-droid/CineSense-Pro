"""SQLite storage: users, quiz preferences and watch history (file: cinesense.db)."""
import hashlib
import json
import os
import sqlite3
import time
from contextlib import closing

DB = "cinesense.db"


def _con():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    return c


def init():
    with closing(_con()) as c, c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, name TEXT UNIQUE, salt BLOB,
            pw TEXT, dob TEXT, prefs TEXT DEFAULT '{}');
        CREATE TABLE IF NOT EXISTS history(id INTEGER PRIMARY KEY, uid INTEGER, mid INTEGER,
            title TEXT, genres TEXT, runtime INTEGER, rating INTEGER, ts REAL, note TEXT);
        CREATE TABLE IF NOT EXISTS marks(uid INTEGER, mid INTEGER, kind TEXT, data TEXT, ts REAL, PRIMARY KEY(uid, mid, kind));
        CREATE TABLE IF NOT EXISTS sent(uid INTEGER, mid INTEGER, PRIMARY KEY(uid, mid));""")
        try:
            c.execute("ALTER TABLE history ADD COLUMN poster TEXT DEFAULT ''")
        except sqlite3.OperationalError:
            pass
        try:
            c.execute("ALTER TABLE users ADD COLUMN email TEXT DEFAULT ''")
        except sqlite3.OperationalError:
            pass


def _hash(pw, salt):
    return hashlib.pbkdf2_hmac("sha256", pw.encode(), salt, 100_000).hex()


def register(name, pw, dob, email=""):
    salt = os.urandom(16)
    try:
        with closing(_con()) as c, c:
            c.execute("INSERT INTO users(name, salt, pw, dob, email) VALUES(?,?,?,?,?)",
                      (name.strip().lower(), salt, _hash(pw, salt), dob, email))
    except sqlite3.IntegrityError:
        return None
    return login(name, pw)


def login(name, pw):
    with closing(_con()) as c:
        r = c.execute("SELECT * FROM users WHERE name=?", (name.strip().lower(),)).fetchone()
    if r and _hash(pw, r["salt"]) == r["pw"]:
        return {"id": r["id"], "name": r["name"], "dob": r["dob"], "email": r["email"] or "", "prefs": json.loads(r["prefs"])}
    return None


def save_prefs(uid, prefs):
    with closing(_con()) as c, c:
        c.execute("UPDATE users SET prefs=? WHERE id=?", (json.dumps(prefs), uid))


def add_history(uid, m, rating, note="", poster=""):
    with closing(_con()) as c, c:
        c.execute("INSERT INTO history(uid, mid, title, genres, runtime, rating, ts, note, poster) VALUES(?,?,?,?,?,?,?,?,?)",
                  (uid, int(m.id), m.title, m.genres, int(m.runtime), float(rating), time.time(), note, poster))


def get_history(uid):
    with closing(_con()) as c:
        rows = c.execute("SELECT mid, title, genres, runtime, rating, ts, note, poster FROM history "
                         "WHERE uid=? ORDER BY ts", (uid,)).fetchall()
    return [dict(r) for r in rows]


def get_user(uid):
    with closing(_con()) as c:
        r = c.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
    return {"id": r["id"], "name": r["name"], "dob": r["dob"], "email": r["email"] or "", "prefs": json.loads(r["prefs"])} if r else None


def set_email(uid, email):
    with closing(_con()) as c, c:
        c.execute("UPDATE users SET email=? WHERE id=?", (email, uid))


def users_with_email():
    with closing(_con()) as c:
        return [dict(r) for r in c.execute("SELECT id FROM users WHERE email IS NOT NULL AND email != ''")]


def sent_ids(uid):
    with closing(_con()) as c:
        return {r[0] for r in c.execute("SELECT mid FROM sent WHERE uid=?", (uid,))}


def mark_sent(uid, mids):
    with closing(_con()) as c, c:
        c.executemany("INSERT OR IGNORE INTO sent(uid, mid) VALUES(?,?)", [(uid, m) for m in mids])


def set_mark(uid, mid, kind, on, data=None):
    """Letterboxd-style flags: kind is 'watchlist' or 'like'."""
    with closing(_con()) as c, c:
        if on:
            c.execute("INSERT OR REPLACE INTO marks(uid, mid, kind, data, ts) VALUES(?,?,?,?,?)",
                      (uid, int(mid), kind, json.dumps(data or {}), time.time()))
        else:
            c.execute("DELETE FROM marks WHERE uid=? AND mid=? AND kind=?", (uid, int(mid), kind))


def get_marks(uid):
    with closing(_con()) as c:
        rows = c.execute("SELECT kind, data FROM marks WHERE uid=? ORDER BY ts DESC", (uid,)).fetchall()
    out = {"watchlist": [], "like": []}
    for r in rows:
        out.setdefault(r["kind"], []).append(json.loads(r["data"]))
    return out
