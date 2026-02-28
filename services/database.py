# services/database.py (Updated to force-create table and log schema)
import sqlite3
import json
import logging
from datetime import datetime
import pytz

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.DEBUG)

DB_FILE = "influencer_data.db"

def init_db():
    """Initialize the database with required tables and ensure schema is up-to-date."""
    try:
        conn = sqlite3.connect(DB_FILE, check_same_thread=False)  # Allow cross-thread access for concurrency
        cursor = conn.cursor()
        # Enable WAL mode for better thread safety and concurrency
        cursor.execute("PRAGMA journal_mode=WAL;")
        logger.info("WAL mode enabled")
        
        # Always create users table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        logger.info("Users table ensured")
        
        # Check if influencer_stats exists and has correct schema
        try:
            cursor.execute("PRAGMA table_info(influencer_stats)")
            columns = {col[1] for col in cursor.fetchall()}
            logger.debug(f"Existing influencer_stats columns: {columns}")
            required_columns = {'id', 'username', 'influencer_data', 'engagement', 'followers', 'growth', 'timestamp', 'comments', 'sentiment'}
            
            # If table missing or columns incomplete, drop and recreate
            if 'id' not in columns or not required_columns.issubset(columns):
                logger.warning("influencer_stats table missing or incomplete - recreating")
                cursor.execute("DROP TABLE IF EXISTS influencer_stats")
                cursor.execute("""
                    CREATE TABLE influencer_stats (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        username TEXT NOT NULL,
                        influencer_data TEXT,
                        engagement REAL,
                        followers INTEGER,
                        growth REAL,
                        timestamp TEXT,
                        comments TEXT,
                        sentiment TEXT,
                        UNIQUE(username, timestamp)
                    )
                """)
                logger.info("influencer_stats table created with full schema")
            else:
                logger.info("influencer_stats table schema verified OK")
        except sqlite3.OperationalError:
            # Table doesn't exist - create it
            logger.info("influencer_stats table does not exist - creating")
            cursor.execute("""
                CREATE TABLE influencer_stats (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL,
                    influencer_data TEXT,
                    engagement REAL,
                    followers INTEGER,
                    growth REAL,
                    timestamp TEXT,
                    comments TEXT,
                    sentiment TEXT,
                    UNIQUE(username, timestamp)
                )
            """)
            logger.info("influencer_stats table created")
        
        conn.commit()
        logger.info("Database initialized or updated successfully with WAL mode")
    except Exception as e:
        logger.error(f"Error initializing database: {e}")
        raise
    finally:
        conn.close()

def save_influencer_data(username, influencer_data, engagement, growth=None, comments=None, sentiment=None):
    """Save influencer data to the database."""
    try:
        conn = sqlite3.connect(DB_FILE, check_same_thread=False)
        cursor = conn.cursor()
        profile = influencer_data.get("profile", {})
        followers = profile.get("followers", 0)
        timestamp = datetime.now(pytz.UTC).isoformat()  # Store UTC-aware timestamp
        cursor.execute("""
            INSERT OR REPLACE INTO influencer_stats 
            (username, influencer_data, engagement, followers, growth, timestamp, comments, sentiment)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            username,
            json.dumps(influencer_data),
            engagement,
            followers,
            growth if growth is not None else 0.0,
            timestamp,
            json.dumps(comments) if comments else None,
            json.dumps(sentiment) if sentiment else None
        ))
        conn.commit()
        logger.debug(f"Saved data for {username} at {timestamp}")
    except Exception as e:
        logger.error(f"Error saving data for {username}: {e}")
    finally:
        conn.close()

def get_influencer_data(username):
    """Retrieve the latest influencer data from the database."""
    try:
        conn = sqlite3.connect(DB_FILE, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("""
            SELECT influencer_data, engagement, followers, growth, timestamp, comments, sentiment
            FROM influencer_stats
            WHERE username = ?
            ORDER BY timestamp DESC
            LIMIT 1
        """, (username,))
        row = cursor.fetchone()
        if row:
            influencer_data = json.loads(row["influencer_data"]) if row["influencer_data"] else {}
            return {
                "influencer_data": influencer_data,
                "engagement": row["engagement"],
                "followers": row["followers"],
                "growth": row["growth"],
                "timestamp": row["timestamp"],
                "comments": json.loads(row["comments"]) if row["comments"] else [],
                "sentiment": json.loads(row["sentiment"]) if row["sentiment"] else {"positive": 0, "neutral": 0, "negative": 0}
            }
        return None
    except Exception as e:
        logger.error(f"Error retrieving data for {username}: {e}")
        return None
    finally:
        conn.close()

def get_growth_data(username):
    """Retrieve historical data for growth trends."""
    try:
        conn = sqlite3.connect(DB_FILE, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("""
            SELECT followers, engagement, timestamp
            FROM influencer_stats
            WHERE username = ?
            ORDER BY timestamp DESC
            LIMIT 5
        """, (username,))
        rows = cursor.fetchall()
        if rows:
            # Normalize timestamps to strings if needed
            timestamps = []
            for row in rows:
                ts = row["timestamp"]
                if hasattr(ts, 'isoformat'):
                    ts = ts.isoformat()
                timestamps.append(ts)
            return {
                "timestamps": timestamps,
                "follower_growth": [row["followers"] for row in rows],
                "engagement_trend": [row["engagement"] for row in rows]
            }
        return None
    except Exception as e:
        logger.error(f"Error retrieving growth data for {username}: {e}")
        return None
    finally:
        conn.close()