# database.py
import sqlite3

def init_db():
    """Initializes the database and creates tables if they don't exist."""
    conn = sqlite3.connect('suno_contests.db')
    cursor = conn.cursor()

    # Add the max_submissions_per_user column with a default of 1
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS contests (
            contest_id TEXT PRIMARY KEY,
            public_channel_id INTEGER NOT NULL,
            review_channel_id INTEGER NOT NULL,
            allowed_platforms TEXT,
            max_submissions_per_user INTEGER DEFAULT 1,
            is_open INTEGER DEFAULT 1
        )
    ''')

    # No changes needed to the submissions table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS submissions (
            submission_id INTEGER PRIMARY KEY AUTOINCREMENT,
            contest_id TEXT NOT NULL,
            user_id INTEGER NOT NULL,
            user_name TEXT NOT NULL,
            song_name TEXT NOT NULL,
            platform TEXT NOT NULL,
            suno_url TEXT NOT NULL,
            public_message_id INTEGER,
            review_message_id INTEGER,
            FOREIGN KEY (contest_id) REFERENCES contests (contest_id)
        )
    ''')

    conn.commit()
    conn.close()
    print("Database initialized successfully.")

if __name__ == '__main__':
    init_db()
