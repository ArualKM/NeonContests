# database.py - Enhanced database schema with migrations

import sqlite3
import os
import logging
from datetime import datetime
from contextlib import contextmanager

logger = logging.getLogger('database')

DATABASE_PATH = os.getenv('DATABASE_PATH', 'suno_contests.db')
CURRENT_VERSION = 3  # Increment when adding new migrations

@contextmanager
def get_db_connection():
    """Context manager for database connections"""
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def get_db_version(conn):
    """Get current database schema version"""
    return conn.execute("PRAGMA user_version").fetchone()[0]

def set_db_version(conn, version):
    """Set database schema version"""
    conn.execute(f"PRAGMA user_version = {version}")

def init_db():
    """Initialize database with base schema"""
    with get_db_connection() as conn:
        # Base schema (version 0)
        conn.execute('''
            CREATE TABLE IF NOT EXISTS contests (
                contest_id TEXT PRIMARY KEY CHECK(length(contest_id) <= 30),
                public_channel_id INTEGER NOT NULL,
                review_channel_id INTEGER NOT NULL,
                allowed_platforms TEXT,
                max_submissions_per_user INTEGER DEFAULT 1 CHECK(max_submissions_per_user BETWEEN 1 AND 10),
                is_open INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                created_by INTEGER NOT NULL,
                UNIQUE(public_channel_id, review_channel_id)
            )
        ''')
        
        conn.execute('''
            CREATE TABLE IF NOT EXISTS submissions (
                submission_id INTEGER PRIMARY KEY AUTOINCREMENT,
                contest_id TEXT NOT NULL,
                user_id INTEGER NOT NULL,
                user_name TEXT NOT NULL,
                song_name TEXT NOT NULL CHECK(length(song_name) <= 100),
                platform TEXT NOT NULL,
                suno_url TEXT NOT NULL,
                public_message_id INTEGER,
                review_message_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (contest_id) REFERENCES contests (contest_id) ON DELETE CASCADE,
                UNIQUE(contest_id, user_id, suno_url)
            )
        ''')
        
        # Create indexes for better performance
        conn.execute('''
            CREATE INDEX IF NOT EXISTS idx_submissions_contest_user 
            ON submissions(contest_id, user_id)
        ''')
        
        conn.execute('''
            CREATE INDEX IF NOT EXISTS idx_submissions_created 
            ON submissions(created_at DESC)
        ''')
        
        logger.info("Base database schema created")

def migrate_db():
    """Run database migrations"""
    with get_db_connection() as conn:
        current_version = get_db_version(conn)
        
        migrations = [
            # Version 1: Add contest status and dates
            [
                """ALTER TABLE contests ADD COLUMN status TEXT DEFAULT 'active' 
                   CHECK(status IN ('draft', 'active', 'voting', 'closed'))""",
                """ALTER TABLE contests ADD COLUMN start_date TIMESTAMP""",
                """ALTER TABLE contests ADD COLUMN end_date TIMESTAMP""",
                """ALTER TABLE contests ADD COLUMN voting_end_date TIMESTAMP"""
            ],
            
            # Version 2: Add voting table and contest statistics
            [
                """CREATE TABLE IF NOT EXISTS votes (
                    vote_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    submission_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (submission_id) REFERENCES submissions(submission_id) ON DELETE CASCADE,
                    UNIQUE(submission_id, user_id)
                )""",
                """CREATE INDEX IF NOT EXISTS idx_votes_submission 
                   ON votes(submission_id)""",
                """ALTER TABLE contests ADD COLUMN description TEXT""",
                """ALTER TABLE contests ADD COLUMN prize_description TEXT"""
            ],
            
            # Version 3: Add audit log and rate limiting
            [
                """CREATE TABLE IF NOT EXISTS audit_log (
                    log_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    action TEXT NOT NULL,
                    details TEXT,
                    ip_address TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )""",
                """CREATE INDEX IF NOT EXISTS idx_audit_user_action 
                   ON audit_log(user_id, action, created_at DESC)""",
                """CREATE TABLE IF NOT EXISTS rate_limits (
                    user_id INTEGER PRIMARY KEY,
                    action TEXT NOT NULL,
                    count INTEGER DEFAULT 0,
                    window_start TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(user_id, action)
                )""",
                """ALTER TABLE submissions ADD COLUMN metadata TEXT"""  # JSON metadata
            ]
        ]
        
        # Apply migrations
        for target_version in range(current_version, len(migrations)):
            logger.info(f"Applying migration {target_version + 1}")
            
            try:
                conn.execute("BEGIN EXCLUSIVE")
                
                for sql in migrations[target_version]:
                    conn.execute(sql)
                
                set_db_version(conn, target_version + 1)
                conn.execute("COMMIT")
                
                logger.info(f"Migration {target_version + 1} completed successfully")
                
            except Exception as e:
                conn.execute("ROLLBACK")
                logger.error(f"Migration {target_version + 1} failed: {e}")
                raise

def create_backup(backup_dir='backups'):
    """Create timestamped backup of database"""
    os.makedirs(backup_dir, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = os.path.join(backup_dir, f'suno_contests_{timestamp}.db')
    
    # Use SQLite backup API
    with sqlite3.connect(DATABASE_PATH) as source:
        with sqlite3.connect(backup_path) as backup:
            source.backup(backup)
    
    logger.info(f"Database backed up to {backup_path}")
    
    # Clean old backups (keep last 10)
    backups = sorted([f for f in os.listdir(backup_dir) if f.endswith('.db')])
    for old_backup in backups[:-10]:
        os.remove(os.path.join(backup_dir, old_backup))
        logger.info(f"Removed old backup: {old_backup}")

def verify_integrity():
    """Verify database integrity"""
    with get_db_connection() as conn:
        # Check foreign key integrity
        violations = conn.execute("PRAGMA foreign_key_check").fetchall()
        if violations:
            logger.error(f"Foreign key violations found: {violations}")
            return False
        
        # Check general integrity
        result = conn.execute("PRAGMA integrity_check").fetchone()
        if result[0] != 'ok':
            logger.error(f"Database integrity check failed: {result[0]}")
            return False
        
        logger.info("Database integrity check passed")
        return True

# --- Helper functions for common queries ---

def get_contest_stats(contest_id: str) -> dict:
    """Get statistics for a contest"""
    with get_db_connection() as conn:
        stats = {}
        
        # Basic contest info
        contest = conn.execute(
            "SELECT * FROM contests WHERE contest_id = ?", 
            (contest_id,)
        ).fetchone()
        
        if not contest:
            return None
        
        stats['contest'] = dict(contest)
        
        # Submission count
        stats['total_submissions'] = conn.execute(
            "SELECT COUNT(*) FROM submissions WHERE contest_id = ?",
            (contest_id,)
        ).fetchone()[0]
        
        # Unique participants
        stats['unique_participants'] = conn.execute(
            "SELECT COUNT(DISTINCT user_id) FROM submissions WHERE contest_id = ?",
            (contest_id,)
        ).fetchone()[0]
        
        # Platform breakdown
        platform_stats = conn.execute(
            """SELECT platform, COUNT(*) as count 
               FROM submissions 
               WHERE contest_id = ? 
               GROUP BY platform""",
            (contest_id,)
        ).fetchall()
        
        stats['platforms'] = {row['platform']: row['count'] for row in platform_stats}
        
        # If voting is enabled, get vote counts
        if contest['status'] in ['voting', 'closed']:
            stats['votes'] = conn.execute(
                """SELECT s.submission_id, s.song_name, s.user_name, 
                          COUNT(v.vote_id) as vote_count
                   FROM submissions s
                   LEFT JOIN votes v ON s.submission_id = v.submission_id
                   WHERE s.contest_id = ?
                   GROUP BY s.submission_id
                   ORDER BY vote_count DESC""",
                (contest_id,)
            ).fetchall()
        
        return stats

def log_action(user_id: int, action: str, details: str = None, ip_address: str = None):
    """Log user actions for audit trail"""
    with get_db_connection() as conn:
        conn.execute(
            """INSERT INTO audit_log (user_id, action, details, ip_address)
               VALUES (?, ?, ?, ?)""",
            (user_id, action, details, ip_address)
        )

def check_rate_limit(user_id: int, action: str, limit: int, window_minutes: int) -> bool:
    """Check if user has exceeded rate limit"""
    with get_db_connection() as conn:
        window_start = datetime.now().timestamp() - (window_minutes * 60)
        
        # Clean old entries
        conn.execute(
            """DELETE FROM rate_limits 
               WHERE window_start < datetime('now', '-' || ? || ' minutes')""",
            (window_minutes,)
        )
        
        # Check current count
        result = conn.execute(
            """SELECT count FROM rate_limits 
               WHERE user_id = ? AND action = ? AND window_start > ?""",
            (user_id, action, window_start)
        ).fetchone()
        
        if result and result['count'] >= limit:
            return False
        
        # Update count
        conn.execute(
            """INSERT INTO rate_limits (user_id, action, count, window_start)
               VALUES (?, ?, 1, ?)
               ON CONFLICT(user_id, action) 
               DO UPDATE SET count = count + 1""",
            (user_id, action, datetime.now().timestamp())
        )
        
        return True

if __name__ == '__main__':
    # Initialize and migrate database
    print("Initializing database...")
    init_db()
    
    print("Running migrations...")
    migrate_db()
    
    print("Creating backup...")
    create_backup()
    
    print("Verifying integrity...")
    if verify_integrity():
        print("Database setup completed successfully!")
    else:
        print("Database integrity check failed!")
        exit(1)
