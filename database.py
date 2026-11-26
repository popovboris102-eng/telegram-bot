import sqlite3
import random
import string
DB = "bot.db"
def init():
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, username TEXT, balance INTEGER DEFAULT 100, key TEXT)")
    cur.execute("CREATE TABLE IF NOT EXISTS history (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, type TEXT, prompt TEXT, result TEXT)")
    cur.execute("CREATE TABLE IF NOT EXISTS complaints (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, username TEXT, text TEXT, email TEXT, phone TEXT)")
    cur.execute("CREATE TABLE IF NOT EXISTS banned_users (user_id INTEGER PRIMARY KEY, reason TEXT, banned_at TEXT)")
    conn.commit()
    conn.close()
def create_user(user_id, username=""):
    init()
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("SELECT key FROM users WHERE user_id = ?", (user_id,))
    row = cur.fetchone()
    if row:
        conn.close()
        return row[0]
    key = ''.join(random.choices(string.ascii_letters + string.digits, k=10))
    cur.execute("INSERT INTO users (user_id, username, balance, key) VALUES (?, ?, ?, ?)", (user_id, username, 100, key))
    conn.commit()
    conn.close()
    return key
def get_balance(user_id):
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
    row = cur.fetchone()
    conn.close()
    if not row:
        create_user(user_id, "")
        return 100
    return row[0]
def add_balance(user_id, amount):
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
    if not cur.fetchone():
        cur.execute("INSERT INTO users (user_id, username, balance, key) VALUES (?, ?, ?, ?)", (user_id, "", amount, ""))
    else:
        cur.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
    conn.commit()
    conn.close()
def spend(user_id, amount):
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (amount, user_id))
    conn.commit()
    conn.close()
def save_history(user_id, type_, prompt, result):
    try:
        conn = sqlite3.connect(DB)
        cur = conn.cursor()
        cur.execute("INSERT INTO history (user_id, type, prompt, result) VALUES (?, ?, ?, ?)", (user_id, type_, prompt, str(result)[:1000]))
        conn.commit()
        conn.close()
    except:
        pass
def save_complaint(user_id, username, text, email, phone):
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("INSERT INTO complaints (user_id, username, text, email, phone) VALUES (?, ?, ?, ?, ?)", (user_id, username, text, email, phone))
    conn.commit()
    conn.close()