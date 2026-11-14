"""Persistent job and mapping storage for a single DesignQA workspace."""
import json
import sqlite3
from contextlib import contextmanager


class Store:
    def __init__(self, root):
        root.mkdir(parents=True, exist_ok=True)
        self.path = root / "workspace.sqlite3"
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, data TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS mappings (scope TEXT PRIMARY KEY, data TEXT NOT NULL);
            """)
            for job in self.jobs(db):
                if job["state"] in {"queued", "running", "awaiting_frames", "awaiting_mapping"}:
                    job.update(state="interrupted", error={"message": "The worker restarted. Start a new analysis."})
                    self.put(job, db)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=15)
        try:
            with db:
                yield db
        finally:
            db.close()

    def jobs(self, db):
        return [json.loads(data) for (data,) in db.execute("SELECT data FROM jobs ORDER BY rowid DESC")]

    def put(self, job, db):
        db.execute("INSERT INTO jobs VALUES (?, ?) ON CONFLICT(id) DO UPDATE SET data=excluded.data",
                   (job["job_id"], json.dumps(job)))

    def get(self, job_id):
        with self.connect() as db:
            row = db.execute("SELECT data FROM jobs WHERE id=?", (job_id,)).fetchone()
            return json.loads(row[0]) if row else None

    def mapping(self, scope, values=None):
        with self.connect() as db:
            if values is not None:
                db.execute("INSERT OR REPLACE INTO mappings VALUES (?, ?)", (scope, json.dumps(values)))
                return values
            row = db.execute("SELECT data FROM mappings WHERE scope=?", (scope,)).fetchone()
            return json.loads(row[0]) if row else {}
