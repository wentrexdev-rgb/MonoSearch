import sqlite3
from datetime import datetime, timezone

class Database:
    def __init__(self, path):
        self.path = path
        self.init()

    def connect(self):
        return sqlite3.connect(self.path)

    def init(self):
        with self.connect() as c:
            c.execute("""CREATE TABLE IF NOT EXISTS users(
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                extra_requests INTEGER NOT NULL DEFAULT 0,
                premium_until INTEGER NOT NULL DEFAULT 0,
                daily_used INTEGER NOT NULL DEFAULT 0,
                daily_date TEXT NOT NULL DEFAULT '',
                is_banned INTEGER NOT NULL DEFAULT 0
            )""")
            c.execute("""CREATE TABLE IF NOT EXISTS searches(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                requested INTEGER NOT NULL,
                found INTEGER NOT NULL,
                created_at TEXT NOT NULL
            )""")

    def ensure_user(self, user_id, username=""):
        with self.connect() as c:
            c.execute(
                "INSERT OR IGNORE INTO users(user_id, username) VALUES(?, ?)",
                (user_id, username or "")
            )
            if username:
                c.execute("UPDATE users SET username=? WHERE user_id=?", (username, user_id))

    def _reset_day(self, c, user_id):
        today = datetime.now(timezone.utc).date().isoformat()
        row = c.execute("SELECT daily_date FROM users WHERE user_id=?", (user_id,)).fetchone()
        if not row or row[0] != today:
            c.execute("UPDATE users SET daily_used=0, daily_date=? WHERE user_id=?", (today, user_id))
        return today

    def is_premium(self, user_id):
        self.ensure_user(user_id)
        now = int(datetime.now(timezone.utc).timestamp())
        with self.connect() as c:
            row = c.execute("SELECT premium_until FROM users WHERE user_id=?", (user_id,)).fetchone()
            return row and row[0] > now

    def consume_request(self, user_id):
        self.ensure_user(user_id)
        with self.connect() as c:
            banned = c.execute("SELECT is_banned FROM users WHERE user_id=?", (user_id,)).fetchone()
            if banned and banned[0] == 1:
                return False

            self._reset_day(c, user_id)
            extra = c.execute("SELECT extra_requests FROM users WHERE user_id=?", (user_id,)).fetchone()[0]
            if extra > 0:
                c.execute("UPDATE users SET extra_requests=extra_requests-1 WHERE user_id=?", (user_id,))
                return True
            used = c.execute("SELECT daily_used FROM users WHERE user_id=?", (user_id,)).fetchone()[0]
            if used >= 3:
                return False
            c.execute("UPDATE users SET daily_used=daily_used+1 WHERE user_id=?", (user_id,))
            return True

    def add_requests(self, user_id, amount):
        self.ensure_user(user_id)
        with self.connect() as c:
            c.execute("UPDATE users SET extra_requests=extra_requests+? WHERE user_id=?", (amount, user_id))

    def add_requests_by_id(self, user_id, amount):
        self.ensure_user(user_id)
        with self.connect() as c:
            c.execute("UPDATE users SET extra_requests=extra_requests+? WHERE user_id=?", (amount, user_id))

    def toggle_ban(self, user_id):
        with self.connect() as c:
            row = c.execute("SELECT is_banned FROM users WHERE user_id=?", (user_id,)).fetchone()
            if row:
                new_status = 0 if row[0] == 1 else 1
                c.execute("UPDATE users SET is_banned=? WHERE user_id=?", (new_status, user_id))
                return new_status
        return None

    def get_user(self, user_id):
        with self.connect() as c:
            return c.execute("SELECT user_id, username, extra_requests, premium_until, is_banned FROM users WHERE user_id=?", (user_id,)).fetchone()

    def get_all_users(self):
        with self.connect() as c:
            return c.execute("SELECT user_id, username, extra_requests, premium_until, is_banned FROM users ORDER BY user_id DESC").fetchall()

    def add_premium(self, user_id, days):
        self.ensure_user(user_id)
        now = int(datetime.now(timezone.utc).timestamp())
        with self.connect() as c:
            current = c.execute("SELECT premium_until FROM users WHERE user_id=?", (user_id,)).fetchone()[0]
            start = max(current, now)
            c.execute("UPDATE users SET premium_until=? WHERE user_id=?", (start + days*86400, user_id))

    def add_search(self, user_id, requested, found):
        with self.connect() as c:
            c.execute(
                "INSERT INTO searches(user_id,requested,found,created_at) VALUES(?,?,?,?)",
                (user_id, requested, found, datetime.now(timezone.utc).isoformat())
            )

    def history(self, user_id):
        with self.connect() as c:
            return c.execute(
                "SELECT found,created_at FROM searches WHERE user_id=? ORDER BY id DESC LIMIT 10",
                (user_id,)
            ).fetchall()
