# database.py - Database management and operations
import sqlite3
import os
import json
import logging
from datetime import datetime
from contextlib import contextmanager
from typing import Optional, Dict, Any, List
from config import Config

logger = logging.getLogger('database')

# Current database schema version
CURRENT_VERSION = 3

@contextmanager
def get_db():
    """Context manager for database connections with automatic cleanup"""
    conn = sqlite3.connect(Config.DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception as e:
        conn.rollback()
        logger.error(f"Database error: {e}")
        raise
    finally:
        conn.close()

def get_db_version(conn: sqlite3.Connection) -> int:
    """Get current database schema version"""
    return conn.execute("PRAGMA user_version").fetchone()[0]

def set_db_version(conn: sqlite3.Connection, version: int):
    """Set database schema version"""
    conn.execute(f"PRAGMA user_version = {version}")

def init_db():
    """Initialize database with base schema"""
    with get_db() as conn:
        # Base schema (version 0)
        conn.execute('''
            CREATE TABLE IF NOT EXISTS contests (
                contest_id TEXT PRIMARY KEY CHECK(length(contest_id) <= 30),
                public_channel_id INTEGER NOT NULL,
                review_channel_id INTEGER NOT NULL,
                allowed_platforms TEXT,
                max_submissions_per_user INTEGER DEFAULT 1 CHECK(max_submissions_per_user BETWEEN 1 AND 10),
                is_open INTEGER DEFAULT 1,
                status TEXT DEFAULT 'active' CHECK(status IN ('draft', 'active', 'voting', 'closed')),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                created_by INTEGER NOT NULL,
                description TEXT,
                start_date TIMESTAMP,
                end_date TIMESTAMP,
                voting_end_date TIMESTAMP,
                prize_description TEXT,
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
                metadata TEXT,
                FOREIGN KEY (contest_id) REFERENCES contests (contest_id) ON DELETE CASCADE,
                UNIQUE(contest_id, user_id, suno_url)
            )
        ''')
        
        conn.execute('''
            CREATE TABLE IF NOT EXISTS votes (
                vote_id INTEGER PRIMARY KEY AUTOINCREMENT,
                submission_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (submission_id) REFERENCES submissions(submission_id) ON DELETE CASCADE,
                UNIQUE(submission_id, user_id)
            )
        ''')
        
        conn.execute('''
            CREATE TABLE IF NOT EXISTS audit_log (
                log_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                action TEXT NOT NULL,
                details TEXT,
                ip_address TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        conn.execute('''
            CREATE TABLE IF NOT EXISTS rate_limits (
                user_id INTEGER,
                action TEXT NOT NULL,
                count INTEGER DEFAULT 0,
                window_start TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, action)
            )
        ''')
        
        # Create indexes for better performance
        indexes = [
            "CREATE INDEX IF NOT EXISTS idx_submissions_contest_user ON submissions(contest_id, user_id)",
            "CREATE INDEX IF NOT EXISTS idx_submissions_created ON submissions(created_at DESC)",
            "CREATE INDEX IF NOT EXISTS idx_votes_submission ON votes(submission_id)",
            "CREATE INDEX IF NOT EXISTS idx_audit_user_action ON audit_log(user_id, action, created_at DESC)",
            "CREATE INDEX IF NOT EXISTS idx_contests_status ON contests(status)",
            "CREATE INDEX IF NOT EXISTS idx_rate_limits_window ON rate_limits(window_start)"
        ]
        
        for index in indexes:
            conn.execute(index)
        
        logger.info("Database initialized successfully")

def migrate_db():
    """Run database migrations to update schema"""
    with get_db() as conn:
        current_version = get_db_version(conn)
        
        if current_version >= CURRENT_VERSION:
            logger.info(f"Database already at version {current_version}")
            return
        
        migrations = [
            # Version 1: Add voting support
            [
                """ALTER TABLE contests ADD COLUMN IF NOT EXISTS voting_enabled INTEGER DEFAULT 1""",
                """ALTER TABLE submissions ADD COLUMN IF NOT EXISTS vote_count INTEGER DEFAULT 0"""
            ],
            
            # Version 2: Add contest analytics
            [
                """CREATE TABLE IF NOT EXISTS contest_analytics (
                    analytics_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    contest_id TEXT NOT NULL,
                    date DATE NOT NULL,
                    views INTEGER DEFAULT 0,
                    unique_viewers INTEGER DEFAULT 0,
                    submissions_count INTEGER DEFAULT 0,
                    votes_count INTEGER DEFAULT 0,
                    FOREIGN KEY (contest_id) REFERENCES contests(contest_id) ON DELETE CASCADE,
                    UNIQUE(contest_id, date)
                )""",
                """CREATE INDEX IF NOT EXISTS idx_analytics_contest_date 
                   ON contest_analytics(contest_id, date DESC)"""
            ],
            
            # Version 3: Add user preferences and notifications
            [
                """CREATE TABLE IF NOT EXISTS user_preferences (
                    user_id INTEGER PRIMARY KEY,
                    notify_on_vote INTEGER DEFAULT 1,
                    notify_on_contest_end INTEGER DEFAULT 1,
                    preferred_platform TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )""",
                """CREATE TABLE IF NOT EXISTS notifications (
                    notification_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    type TEXT NOT NULL,
                    message TEXT NOT NULL,
                    read INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )""",
                """CREATE INDEX IF NOT EXISTS idx_notifications_user_unread 
                   ON notifications(user_id, read, created_at DESC)"""
            ]
        ]
        
        # Apply migrations
        for target_version in range(current_version, min(len(migrations), CURRENT_VERSION)):
            logger.info(f"Applying migration {target_version + 1}")
            
            try:
                conn.execute("BEGIN EXCLUSIVE")
                
                for sql in migrations[target_version]:
                    try:
                        conn.execute(sql)
                    except sqlite3.OperationalError as e:
                        # Handle "duplicate column" errors gracefully
                        if "duplicate column" in str(e).lower():
                            logger.warning(f"Column already exists, skipping: {e}")
                        else:
                            raise
                
                set_db_version(conn, target_version + 1)
                conn.execute("COMMIT")
                
                logger.info(f"Migration {target_version + 1} completed successfully")
                
            except Exception as e:
                conn.execute("ROLLBACK")
                logger.error(f"Migration {target_version + 1} failed: {e}")
                raise

def verify_integrity() -> bool:
    """Verify database integrity and foreign key constraints"""
    try:
        with get_db() as conn:
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
            
            # Check required tables exist
            required_tables = ['contests', 'submissions', 'votes', 'audit_log', 'rate_limits']
            cursor = conn.cursor()
            for table in required_tables:
                cursor.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                    (table,)
                )
                if not cursor.fetchone():
                    logger.error(f"Required table '{table}' is missing")
                    return False
            
            logger.info("Database integrity check passed")
            return True
            
    except Exception as e:
        logger.error(f"Error during integrity check: {e}")
        return False

def create_backup(backup_dir: str = None) -> Optional[str]:
    """Create timestamped backup of database"""
    if backup_dir is None:
        backup_dir = Config.BACKUP_DIR
    
    try:
        os.makedirs(backup_dir, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = os.path.join(backup_dir, f'suno_contests_{timestamp}.db')
        
        # Use SQLite backup API
        with sqlite3.connect(Config.DATABASE_PATH) as source:
            with sqlite3.connect(backup_path) as backup:
                source.backup(backup)
        
        logger.info(f"Database backed up to {backup_path}")
        
        # Clean old backups (keep last N)
        backups = sorted([
            f for f in os.listdir(backup_dir) 
            if f.startswith('suno_contests_') and f.endswith('.db')
        ])
        
        for old_backup in backups[:-Config.MAX_BACKUPS]:
            old_path = os.path.join(backup_dir, old_backup)
            os.remove(old_path)
            logger.info(f"Removed old backup: {old_backup}")
        
        return backup_path
        
    except Exception as e:
        logger.error(f"Backup failed: {e}")
        return None

def log_action(user_id: int, action: str, details: str = None, ip_address: str = None):
    """Log user actions for audit trail"""
    try:
        with get_db() as conn:
            conn.execute(
                """INSERT INTO audit_log (user_id, action, details, ip_address)
                   VALUES (?, ?, ?, ?)""",
                (user_id, action, details, ip_address)
            )
        logger.debug(f"Logged action: {action} by user {user_id}")
    except Exception as e:
        logger.error(f"Failed to log action: {e}")

def get_contest_stats(contest_id: str) -> Optional[Dict[str, Any]]:
    """Get comprehensive statistics for a contest"""
    try:
        with get_db() as conn:
            # Basic contest info
            contest = conn.execute(
                "SELECT * FROM contests WHERE contest_id = ?", 
                (contest_id,)
            ).fetchone()
            
            if not contest:
                return None
            
            stats = {'contest': dict(contest)}
            
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
                   GROUP BY platform
                   ORDER BY count DESC""",
                (contest_id,)
            ).fetchall()
            
            stats['platforms'] = {row['platform']: row['count'] for row in platform_stats}
            
            # Submission timeline
            timeline = conn.execute(
                """SELECT DATE(created_at) as date, COUNT(*) as count
                   FROM submissions
                   WHERE contest_id = ?
                   GROUP BY DATE(created_at)
                   ORDER BY date""",
                (contest_id,)
            ).fetchall()
            
            stats['submission_timeline'] = [
                {'date': row['date'], 'count': row['count']} 
                for row in timeline
            ]
            
            # If voting is enabled, get vote counts
            if contest['status'] in ['voting', 'closed']:
                vote_results = conn.execute(
                    """SELECT s.submission_id, s.song_name, s.user_name, 
                              s.platform, s.suno_url,
                              COUNT(v.vote_id) as vote_count
                       FROM submissions s
                       LEFT JOIN votes v ON s.submission_id = v.submission_id
                       WHERE s.contest_id = ?
                       GROUP BY s.submission_id
                       ORDER BY vote_count DESC, s.created_at ASC""",
                    (contest_id,)
                ).fetchall()
                
                stats['votes'] = [dict(row) for row in vote_results]
                
                # Total votes cast
                stats['total_votes'] = conn.execute(
                    """SELECT COUNT(*) FROM votes v
                       JOIN submissions s ON v.submission_id = s.submission_id
                       WHERE s.contest_id = ?""",
                    (contest_id,)
                ).fetchone()[0]
                
                # Unique voters
                stats['unique_voters'] = conn.execute(
                    """SELECT COUNT(DISTINCT v.user_id) FROM votes v
                       JOIN submissions s ON v.submission_id = s.submission_id
                       WHERE s.contest_id = ?""",
                    (contest_id,)
                ).fetchone()[0]
            
            return stats
            
    except Exception as e:
        logger.error(f"Error getting contest stats: {e}")
        return None

def check_rate_limit(user_id: int, action: str, limit: int, window_minutes: int) -> bool:
    """Check if user has exceeded rate limit"""
    try:
        with get_db() as conn:
            window_start = datetime.now().timestamp() - (window_minutes * 60)
            
            # Clean old entries
            conn.execute(
                "DELETE FROM rate_limits WHERE window_start < ?",
                (window_start,)
            )
            
            # Check current count
            result = conn.execute(
                """SELECT count FROM rate_limits 
                   WHERE user_id = ? AND action = ? AND window_start > ?""",
                (user_id, action, window_start)
            ).fetchone()
            
            if result and result['count'] >= limit:
                return False
            
            # Update or insert count
            conn.execute(
                """INSERT INTO rate_limits (user_id, action, count, window_start)
                   VALUES (?, ?, 1, ?)
                   ON CONFLICT(user_id, action) 
                   DO UPDATE SET count = count + 1""",
                (user_id, action, datetime.now().timestamp())
            )
            
            return True
            
    except Exception as e:
        logger.error(f"Rate limit check error: {e}")
        return True  # Allow on error to avoid blocking users

def get_user_submission_count(user_id: int, contest_id: str) -> int:
    """Get the number of submissions a user has in a contest"""
    try:
        with get_db() as conn:
            count = conn.execute(
                "SELECT COUNT(*) FROM submissions WHERE user_id = ? AND contest_id = ?",
                (user_id, contest_id)
            ).fetchone()[0]
            return count
    except Exception as e:
        logger.error(f"Error getting user submission count: {e}")
        return 0

def get_active_contests() -> List[Dict[str, Any]]:
    """Get all active contests"""
    try:
        with get_db() as conn:
            contests = conn.execute(
                """SELECT c.*, COUNT(s.submission_id) as submission_count
                   FROM contests c
                   LEFT JOIN submissions s ON c.contest_id = s.contest_id
                   WHERE c.status = 'active'
                   GROUP BY c.contest_id
                   ORDER BY c.created_at DESC"""
            ).fetchall()
            
            return [dict(row) for row in contests]
    except Exception as e:
        logger.error(f"Error getting active contests: {e}")
        return []

# Database maintenance functions
def vacuum_database():
    """Optimize database file size"""
    try:
        with sqlite3.connect(Config.DATABASE_PATH) as conn:
            conn.execute("VACUUM")
        logger.info("Database vacuumed successfully")
    except Exception as e:
        logger.error(f"Vacuum failed: {e}")

def analyze_database():
    """Update database statistics for query optimization"""
    try:
        with get_db() as conn:
            conn.execute("ANALYZE")
        logger.info("Database analyzed successfully")
    except Exception as e:
        logger.error(f"Analyze failed: {e}")
