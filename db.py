import sqlite3
import time

class Database:
    def __init__(self, db_path="monosearch.db"):
        self.db_path = db_path
        self.init_db()

    def get_conn(self):
        return sqlite3.connect(self.db_path)

    def init_db(self):
        with self.get_conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    requests_extra INTEGER DEFAULT 0,
                    premium_until INTEGER DEFAULT 0,
                    banned INTEGER DEFAULT 0,
                    free_today_count INTEGER DEFAULT 0,
                    last_free_date TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    count INTEGER,
                    found_count INTEGER,
                    created_at TEXT
                )
            """)
            conn.commit()

    def ensure_user(self, user_id, username):
        today = time.strftime("%Y-%m-%d")
        with self.get_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT user_id, free_today_count, last_free_date, banned FROM users WHERE user_id = ?", (user_id,))
            row = cur.fetchone()
            if not row:
                cur.execute(
                    "INSERT INTO users (user_id, username, requests_extra, premium_until, banned, free_today_count, last_free_date) VALUES (?, ?, 0, 0, 0, 0, ?)",
                    (user_id, username, today)
                )
                conn.commit()
            else:
                _, free_count, last_date, banned = row
                if banned:
                    return
                if last_date != today:
                    cur.execute("UPDATE users SET free_today_count = 0, last_free_date = ?, username = ? WHERE user_id = ?", (today, username, user_id))
                    conn.commit()

    def is_banned(self, user_id):
        with self.get_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT banned FROM users WHERE user_id = ?", (user_id,))
            row = cur.fetchone()
            return bool(row and row[0] == 1)

    def is_premium(self, user_id):
        with self.get_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT premium_until FROM users WHERE user_id = ?", (user_id,))
            row = cur.fetchone()
            if row and row[0] > int(time.time()):
                return True
            return False

    def consume_request(self, user_id):
        with self.get_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT requests_extra, free_today_count FROM users WHERE user_id = ?", (user_id,))
            row = cur.fetchone()
            if not row:
                return False
            extra, free_today = row
            if free_today < 3:
                cur.execute("UPDATE users SET free_today_count = free_today_count + 1 WHERE user_id = ?", (user_id,))
                conn.commit()
                return True
            if extra > 0:
                cur.execute("UPDATE users SET requests_extra = requests_extra - 1 WHERE user_id = ?", (user_id,))
                conn.commit()
                return True
            return False

    def add_requests(self, user_id, amount):
        with self.get_conn() as conn:
            conn.execute("UPDATE users SET requests_extra = MAX(0, requests_extra + ?) WHERE user_id = ?", (amount, user_id))
            conn.commit()

    def add_premium(self, user_id, days):
        now = int(time.time())
        with self.get_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT premium_until FROM users WHERE user_id = ?", (user_id,))
            row = cur.fetchone()
            current_prem = row[0] if row and row[0] > now else now
            new_prem = current_prem + (days * 86400)
            cur.execute("UPDATE users SET premium_until = ? WHERE user_id = ?", (new_prem, user_id))
            conn.commit()

    def revoke_premium(self, user_id):
        with self.get_conn() as conn:
            conn.execute("UPDATE users SET premium_until = 0 WHERE user_id = ?", (user_id,))
            conn.commit()

    def toggle_ban(self, user_id):
        with self.get_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT banned FROM users WHERE user_id = ?", (user_id,))
            row = cur.fetchone()
            if row:
                new_ban = 0 if row[0] == 1 else 1
                cur.execute("UPDATE users SET banned = ? WHERE user_id = ?", (new_ban, user_id))
                conn.commit()
                return new_ban
        return 0

    def get_user(self, user_id):
        with self.get_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT user_id, username, requests_extra, premium_until, banned FROM users WHERE user_id = ?", (user_id,))
            return cur.fetchone()

    def get_all_users(self):
        with self.get_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT user_id, username, requests_extra, premium_until, banned FROM users")
            return cur.fetchall()

    def get_stats(self):
        with self.get_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM users")
            total_users = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM users WHERE premium_until > ?", (int(time.time()),))
            prem_users = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM users WHERE banned = 1")
            banned_users = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM history")
            total_searches = cur.fetchone()[0]
            return total_users, prem_users, banned_users, total_searches

    def add_search(self, user_id, count, found_count):
        now = time.strftime("%Y-%m-%d %H:%M:%S")
        with self.get_conn() as conn:
            conn.execute("INSERT INTO history (user_id, count, found_count, created_at) VALUES (?, ?, ?, ?)", (user_id, count, found_count, now))
            conn.commit()

    def history(self, user_id):
        with self.get_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT found_count, created_at FROM history WHERE user_id = ? ORDER BY id DESC LIMIT 5", (user_id,))
            return cur.fetchall()
