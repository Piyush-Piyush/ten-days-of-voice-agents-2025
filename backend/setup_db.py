# init_db.py
import sqlite3
import os

DB_DIR = "DATABASE"
DB_PATH = os.path.join(DB_DIR, "fraud.db")

os.makedirs(DB_DIR, exist_ok=True)

schema = """
CREATE TABLE IF NOT EXISTS fraud_cases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    userName TEXT NOT NULL,
    securityIdentifier TEXT,
    cardEnding TEXT,
    merchant TEXT,
    amount TEXT,
    location TEXT,
    timestamp TEXT,
    transactionCategory TEXT,
    transactionSource TEXT,
    securityQuestion TEXT,
    securityAnswer TEXT,
    status TEXT,
    note TEXT
);
"""

sample_insert = """
INSERT INTO fraud_cases
(userName, securityIdentifier, cardEnding, merchant, amount, location, timestamp,
 transactionCategory, transactionSource, securityQuestion, securityAnswer, status, note)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""

sample_data = (
    "Raj",              # userName
    "12345",             # securityIdentifier
    "**** 4242",         # cardEnding
    "ABC Industry",      # merchant
    "$129.99",           # amount
    "New York",          # location
    "2025-11-26 14:32",  # timestamp
    "e-commerce",        # transactionCategory
    "alibaba.com",       # transactionSource
    "What is your favorite color?",  # securityQuestion
    "blue",              # securityAnswer (lowercase expected)
    "pending_review",    # status
    ""                   # note
)

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.executescript(schema)
    cur.execute("SELECT COUNT(*) FROM fraud_cases WHERE userName = ?", (sample_data[0],))
    if cur.fetchone()[0] == 0:
        cur.execute(sample_insert, sample_data)
        print("Inserted sample case for user:", sample_data[0])
    else:
        print("Sample case already exists. Skipping insert.")
    conn.commit()
    conn.close()
    print("DB initialized at:", DB_PATH)

if __name__ == "__main__":
    init_db()
