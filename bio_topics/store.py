import json
import sqlite3

from .util import canonical, digest, now


def connect(path):
    db = sqlite3.connect(path, timeout=30)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA foreign_keys=ON")
    return db


def initialize(db):
    db.executescript("""
    CREATE TABLE units(seq INTEGER PRIMARY KEY, id TEXT UNIQUE NOT NULL, kind TEXT NOT NULL,
      body TEXT NOT NULL, hash TEXT NOT NULL);
    CREATE TABLE jobs(seq INTEGER PRIMARY KEY, id TEXT UNIQUE NOT NULL,
      unit_id TEXT NOT NULL REFERENCES units(id), operator TEXT NOT NULL, questions TEXT NOT NULL,
      status TEXT NOT NULL DEFAULT 'pending', attempts INTEGER NOT NULL DEFAULT 0,
      error TEXT, receipt TEXT, receipt_hash TEXT, cache_key TEXT, updated TEXT);
    CREATE INDEX jobs_status ON jobs(status,seq);
    CREATE TABLE metadata(key TEXT PRIMARY KEY, value TEXT NOT NULL);
    """)


def set_meta(db, key, value):
    db.execute("INSERT OR REPLACE INTO metadata VALUES (?,?)", (key, canonical(value)))
    db.commit()


def get_meta(db, key):
    row = db.execute("SELECT value FROM metadata WHERE key=?", (key,)).fetchone()
    return json.loads(row[0]) if row else None


def counts(db):
    by_status = dict(db.execute("SELECT status,count(*) FROM jobs GROUP BY status"))
    total = sum(by_status.values())
    successful = by_status.get("evaluated", 0) + by_status.get("cached", 0)
    return {"planned": total, "successful": successful, "pending": by_status.get("pending", 0),
            "failed": by_status.get("failed", 0), "evaluated": by_status.get("evaluated", 0),
            "cached": by_status.get("cached", 0), "coverage": successful / total if total else 0}


class Cache:
    def __init__(self, path):
        self.db = connect(path)
        self.db.execute("CREATE TABLE IF NOT EXISTS cache(key TEXT PRIMARY KEY, receipt TEXT NOT NULL, hash TEXT NOT NULL)")
        self.db.commit()

    def get(self, key):
        row = self.db.execute("SELECT * FROM cache WHERE key=?", (key,)).fetchone()
        if row is None:
            return None
        receipt = json.loads(row["receipt"])
        if digest(receipt) != row["hash"]:
            raise ValueError("캐시 응답 해시 불일치")
        return receipt

    def put(self, key, receipt):
        self.db.execute("INSERT OR IGNORE INTO cache VALUES (?,?,?)", (key, canonical(receipt), digest(receipt)))
        self.db.commit()

    def close(self):
        self.db.close()
