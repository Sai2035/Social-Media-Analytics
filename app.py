from flask import Flask, render_template, request, jsonify, redirect, url_for, session, g, Response
import logging
import json
import os
from dotenv import load_dotenv
from influencer_data import get_influencer_data, get_comments, analyze_sentiment, get_growth_data, db_save_influencer_data
from datetime import datetime, timedelta
import re
from apscheduler.schedulers.background import BackgroundScheduler
import pytz
import sqlite3
from passlib.hash import bcrypt
import traceback
import concurrent.futures
from services.database import init_db
import threading
import time

load_dotenv()
app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY')
if not app.secret_key:
    raise ValueError("FLASK_SECRET_KEY not found in environment variables")

app.config['SESSION_COOKIE_SECURE'] = False  # Set to False for local testing
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(minutes=30)

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler('app.log'), logging.StreamHandler()]  # Console + file
)

DB_FILE = "influencer_data.db"

profile_progress = {}
profile_results = {}

@app.template_filter('timestamp_to_date')
def timestamp_to_date(timestamp):
    """Convert timestamp to readable date"""
    if timestamp:
        if isinstance(timestamp, (int, float)):
            return datetime.fromtimestamp(timestamp).strftime('%b %d, %Y')
        elif isinstance(timestamp, str):
            try:
                # Try parsing ISO format
                dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                return dt.strftime('%b %d, %Y')
            except ValueError:
                return 'Unknown date'
    return 'Unknown date'

try:
    with open("influencer_by_niche.json", "r") as f:
        influencer_by_niche = json.load(f)
    logger.debug(f"Loaded niches: {list(influencer_by_niche.keys())}")
except FileNotFoundError:
    logger.error("influencer_by_niche.json not found.")
    influencer_by_niche = {"skincare": [], "fitness": [], "food": []}
except json.JSONDecodeError:
    logger.error("Invalid JSON in influencer_by_niche.json.")
    influencer_by_niche = {"skincare": [], "fitness": [], "food": []}

def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(DB_FILE, check_same_thread=False)
        g.db.row_factory = sqlite3.Row
    return g.db

def compute_growth_percent(conn, username):
    try:
        cursor = conn.cursor()
        
        cursor.execute(
            """
            SELECT engagement, timestamp FROM influencer_stats
            WHERE username = ? ORDER BY timestamp DESC LIMIT 1
            """,
            (username,),
        )
        latest = cursor.fetchone()
        if not latest:
            return 0.0

        latest_eng = latest[0] or 0.0
        latest_ts_str = latest[1]
       
        try:
            if latest_ts_str.endswith('Z'):
                latest_ts = datetime.fromisoformat(latest_ts_str.replace('Z', '+00:00'))
            else:
                latest_ts = datetime.fromisoformat(latest_ts_str).replace(tzinfo=pytz.UTC)
        except ValueError:
            logger.warning(f"Invalid timestamp format for {username}: {latest_ts_str}")
            return 0.0

        # Find a snapshot that is at least ~12 hours older than latest
        prev_ts = latest_ts - timedelta(hours=12)
        cursor.execute(
            """
            SELECT engagement, timestamp FROM influencer_stats
            WHERE username = ? AND timestamp <= ?
            ORDER BY timestamp DESC LIMIT 1
            """,
            (username, prev_ts.isoformat()),
        )
        prev = cursor.fetchone()
        if not prev:
            # Fallback: use the second-latest record if exists
            cursor.execute(
                """
                SELECT engagement, timestamp FROM influencer_stats
                WHERE username = ? ORDER BY timestamp DESC LIMIT 1 OFFSET 1
                """,
                (username,),
            )
            prev = cursor.fetchone()
            if not prev:
                return 0.0
        prev_eng = prev[0] or 0.0
        if prev_eng == 0:
            return 0.0
        return ((latest_eng - prev_eng) / prev_eng) * 100.0
    except Exception as e:
        logger.error(f"Error computing growth for {username}: {e}")
        return 0.0

@app.teardown_appcontext
def close_db(error):
    if hasattr(g, 'db'):
        g.db.close()

def is_company_email(email):
    allowed_domains = ['psgcas.ac.in']  # Allow your test domain
    domain = email.split('@')[-1]
    logger.debug(f"Checking email domain: {domain}")
    return domain in allowed_domains

def update_influencer_data():
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT username FROM influencer_stats WHERE timestamp > ?",
                       ((datetime.now(pytz.UTC) - timedelta(hours=24)).isoformat(),))
        recent_influencers = [row['username'] for row in cursor.fetchall()]
        logger.debug(f"Updating data for recently accessed influencers: {recent_influencers}")

        def process_influencer(username):
            try:
                info = get_influencer_data(username, post_limit=10)
                if info:
                    profile = info.get("profile", {})
                    posts = info.get("posts", [])
                    avg_engagement = profile.get("engagement_percent")
                    if avg_engagement is None:
                        avg_engagement = sum(p.get("engagement_percent", 0) for p in posts) / max(len(posts), 1) if posts else 0
                    comments = get_comments(username, posts=posts, post_limit=5)
                    sentiment = analyze_sentiment(comments)
                    db_save_influencer_data(username, info, avg_engagement, comments=comments, sentiment=sentiment)
                    logger.debug(f"Updated data for {username}")
                else:
                    logger.warning(f"No data fetched for {username}")
            except Exception as e:
                logger.error(f"Error processing {username}: {e}")

        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            executor.map(process_influencer, recent_influencers)
        logger.info("Completed scheduled update for recently accessed influencers")
    except Exception as e:
        logger.error(f"Error in scheduled update: {e}\n{traceback.format_exc()}")

scheduler = BackgroundScheduler()
scheduler.add_job(update_influencer_data, 'interval', hours=12)
scheduler.start()

@app.route("/welcome")
def welcome():
    return render_template("welcome.html")

@app.route("/")
def index():
    return render_template("welcome.html")

@app.route("/home")
def home():
    return render_template("index.html")

@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "GET":
        return render_template("signup.html")
    try:
        data = request.get_json(force=False) 
        logger.debug(f"Signup request data: {data}")
        if not data:
            logger.error("No data received in signup request")
            return jsonify({"error": "Invalid request data"}), 400
        email = data.get("email")
        password = data.get("password")
        if not email or not password:
            logger.error(f"Missing email or password in signup request: email={email}, password={'<hidden>' if password else None}")
            return jsonify({"error": "Email and password are required"}), 400
        
        if not is_company_email(email):
            logger.error(f"Invalid company email: {email}")
            return jsonify({"error": "Please use a company email"}), 400
        
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT email FROM users WHERE email = ?", (email,))
        if cursor.fetchone():
            logger.error(f"User already exists: {email}")
            return jsonify({"error": "User already exists"}), 400
        
        hashed_password = bcrypt.hash(password)
        logger.debug(f"Generated bcrypt hash for {email}: {hashed_password}")
        cursor.execute("INSERT INTO users (email, password) VALUES (?, ?)", (email, hashed_password))
        conn.commit()
        session['email'] = email
        logger.info(f"User signed up: {email}")
        return jsonify({"success": True})
    except Exception as e:
        logger.error(f"Error during signup for {email or 'unknown'}: {e}\n{traceback.format_exc()}")
        return jsonify({"error": f"Signup failed: {str(e)}"}), 500

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return render_template("login.html")
    try:
        data = request.get_json(force=False)
        logger.debug(f"Login request data: {data}")
        if not data:
            logger.error("No data received in login request")
            return jsonify({"error": "Invalid request data"}), 400
        email = data.get("email")
        password = data.get("password")
        if not email or not password:
            logger.error(f"Missing email or password in login request: email={email}, password={'<hidden>' if password else None}")
            return jsonify({"error": "Email and password are required"}), 400
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT password FROM users WHERE email = ?", (email,))
        result = cursor.fetchone()
        logger.debug(f"Login attempt for {email}, result: {result}")
        if result and result[0]:
            logger.debug(f"Stored password hash: {result[0]}")
            if bcrypt.verify(password, result[0]):
                session['email'] = email
                logger.info(f"User logged in: {email}")
                return jsonify({"success": True})
            else:
                logger.warning(f"Password verification failed for {email}")
        return jsonify({"error": "Invalid email or password"}), 401
    except Exception as e:
        logger.error(f"Error during login for {email or 'unknown'}: {e}\n{traceback.format_exc()}")
        return jsonify({"error": f"Login failed: {str(e)}"}), 500

@app.route("/logout")
def logout():
    session.pop('email', None)
    logger.info("User logged out")
    return redirect(url_for('index'))

@app.route("/check_login")
def check_login():
    logged_in = 'email' in session
    logger.debug(f"Check login: {'email' in session}")
    return jsonify({"logged_in": logged_in})

@app.route("/creator", methods=["GET", "POST"])
def creator():
    if 'email' not in session:
        return redirect(url_for('login'))
    return render_template("creator.html")

@app.route("/analyze_influencer", methods=["POST"])
def analyze_influencer():
    if 'email' not in session:
        return jsonify({"error": "Not logged in"}), 401
    data = request.get_json()
    username = data.get("username")
    if not username:
        return jsonify({"error": "Username required"}), 400
    try:
        info = get_influencer_data(username, post_limit=3)
        if not info:
            return jsonify({"error": "No data"}), 404
        profile = info["profile"]
        posts = info["posts"]
        avg_likes = sum(p["likes"] for p in posts) / len(posts) if posts else 0
        avg_comments = sum(p["commentsCount"] for p in posts) / len(posts) if posts else 0
        avg_engagement = profile.get("engagement_percent") or (sum(p.get("engagement_percent", 0) for p in posts) / len(posts) if posts else 0)
        comments = get_comments(username, posts=posts, post_limit=5)
        sentiment = analyze_sentiment(comments)
        # Save now to create the latest snapshot, then compute growth vs previous
        db_save_influencer_data(username, info, avg_engagement, comments=comments, sentiment=sentiment)
        growth_percent = compute_growth_percent(get_db(), username)
        # Save again with growth updated for the latest snapshot
        db_save_influencer_data(username, info, avg_engagement, growth=growth_percent, comments=comments, sentiment=sentiment)
        return jsonify({
            "username": profile["username"],
            "full_name": profile["full_name"],
            "followers": profile["followers"],
            "following": profile["following"],
            "avg_likes": round(avg_likes, 2),
            "avg_comments": round(avg_comments, 2),
            "engagement_percent": round(avg_engagement, 2)
        })
    except Exception as e:
        logger.error(f"Error analyzing {username}: {e}\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500

@app.route("/brand")
def brand():
    if 'email' not in session:
        return redirect(url_for('login'))
    return render_template("brand.html")

@app.route("/profile/load/<username>")
def start_profile_loading(username):
    """Start background profile loading process"""
    logger.info(f"Load profile request for {username}")
    
    # Check if already loading
    if username in profile_progress and profile_progress[username].get("status") == "loading":
        return jsonify({"status": "already_loading", "message": "Profile is already being loaded"})
    
    # Check if already completed
    if username in profile_results:
        return jsonify({"status": "already_completed", "message": "Profile data already available"})
    
    # Initialize progress
    profile_progress[username] = {"status": "loading", "progress": 0, "message": "Starting..."}
    
    # Start background thread
    thread = threading.Thread(target=load_profile_data, args=(username,))
    thread.daemon = True
    thread.start()
    
    return jsonify({"status": "started", "message": "Profile loading started"})

def load_profile_data(username):
    """Background task for loading profile data with per-step timeouts and logging."""
    timeout_timer = None
    try:
        # Set up Flask application context for background thread
        with app.app_context():
            logger.info(f"=== THREAD START: Loading profile for {username} ===")
            print(f"=== THREAD START: Loading profile for {username} ===")
            
           
            def timeout_handler():
                if username in profile_progress:
                    profile_progress[username] = {
                        "status": "error",
                        "progress": 100,
                        "message": "Profile loading timed out after 10 minutes"
                    }
                    logger.error(f"Background task timeout for {username}")
                    print(f"Background task timeout for {username}")
            
            timeout_timer = threading.Timer(600, timeout_handler)  # 10 min
            timeout_timer.start()
            
            if username not in profile_progress:
                profile_progress[username] = {"status": "loading", "progress": 0, "message": "Starting..."}
            
            logger.info(f"Thread ID: {threading.current_thread().ident}")
            print(f"Thread ID: {threading.current_thread().ident}")
            
            profile_progress[username]["progress"] = 10
            profile_progress[username]["message"] = "Fetching profile data..."
            logger.info(f"Step 1: Starting fetch for {username}")
            print(f"Step 1: Starting fetch for {username}")
            
            def fetch_profile():
                logger.info(f"Inside fetch thread for {username}")
                return get_influencer_data(username, post_limit=10)
            
            fetch_thread = threading.Thread(target=lambda: setattr(fetch_thread, 'result', fetch_profile()))
            fetch_thread.daemon = True
            fetch_thread.start()
            fetch_thread.join(timeout=120)  # 2 min timeout
            if fetch_thread.is_alive():
                logger.error(f"Fetch thread still alive after timeout for {username}")
                print(f"Fetch thread still alive after timeout for {username}")
                raise TimeoutError("Profile data fetch timed out")
            info = getattr(fetch_thread, 'result', None)
            if not info:
                logger.error(f"No info returned from fetch for {username}")
                print(f"No info returned from fetch for {username}")
                raise ValueError("No data returned from profile fetch")
            
            logger.info(f"Step 1 COMPLETE: Fetched {len(info.get('posts', []))} posts for {username}")
            print(f"Step 1 COMPLETE: Fetched {len(info.get('posts', []))} posts for {username}")
            
            profile_progress[username]["progress"] = 30
            profile_progress[username]["message"] = "Analyzing comments..."
            
            logger.info(f"Step 2: Starting comments fetch for {username}")
            print(f"Step 2: Starting comments fetch for {username}")
            posts = info.get("posts", [])
            comments = []
            if posts:
                def fetch_comments_wrap():
                    logger.info(f"Inside comments thread for {username}")
                    return get_comments(username, posts=posts, post_limit=5)
                
                comment_thread = threading.Thread(target=lambda: setattr(comment_thread, 'c_result', fetch_comments_wrap()))
                comment_thread.daemon = True
                comment_thread.start()
                comment_thread.join(timeout=90)  # 1.5 min timeout
                if comment_thread.is_alive():
                    logger.warning(f"Comment thread still alive after timeout for {username}")
                    print(f"Comment thread still alive after timeout for {username}")
                    comments = []
                else:
                    comments = getattr(comment_thread, 'c_result', [])
                    logger.info(f"Step 2 COMPLETE: Fetched {len(comments)} comments for {username}")
                    print(f"Step 2 COMPLETE: Fetched {len(comments)} comments for {username}")
            
            logger.info(f"Starting sentiment analysis for {len(comments)} comments")
            print(f"Starting sentiment analysis for {len(comments)} comments")
            sentiment_data = analyze_sentiment(comments)
            logger.info(f"Sentiment result: {sentiment_data}")
            print(f"Sentiment result: {sentiment_data}")
            
            profile_progress[username]["progress"] = 60
            profile_progress[username]["message"] = "Calculating growth trends..."
            
            logger.info(f"Step 3: Fetching growth data for {username}")
            print(f"Step 3: Fetching growth data for {username}")
            growth_data = get_growth_data(username) or {"timestamps": [], "follower_growth": [], "engagement_trend": []}
            logger.info(f"Growth data keys: {list(growth_data.keys())}")
            print(f"Growth data keys: {list(growth_data.keys())}")
            
            profile_progress[username]["progress"] = 80
            profile_progress[username]["message"] = "Saving data..."
            
            logger.info(f"Step 4: Computing engagement and growth for {username}")
            print(f"Step 4: Computing engagement and growth for {username}")
            profile_data = info.get("profile", {})
            posts = info.get("posts", [])
            avg_engagement = profile_data.get("engagement_percent") or (sum(p.get("engagement_percent", 0) for p in posts) / max(len(posts), 1) if posts else 0)
            growth = compute_growth_percent(get_db(), username)
            logger.info(f"Avg engagement: {avg_engagement}, Growth: {growth}")
            print(f"Avg engagement: {avg_engagement}, Growth: {growth}")
            
            logger.info(f"Saving to DB for {username}")
            print(f"Saving to DB for {username}")
            db_save_influencer_data(username, info, avg_engagement, growth=growth, comments=comments, sentiment=sentiment_data)
            logger.info(f"DB save complete for {username}")
            print(f"DB save complete for {username}")
            
            profile_progress[username]["progress"] = 100
            profile_progress[username]["message"] = "Profile analysis complete!"
            
            profile_results[username] = {
                "profile": profile_data,
                "posts": posts,
                "sentiment": sentiment_data,
                "growth": growth_data,
                "avg_engagement": round(avg_engagement, 2),
                "comments": comments
            }
            
            profile_progress[username]["status"] = "complete"
            logger.info(f"=== THREAD COMPLETE: Profile loading done for {username} ===")
            print(f"=== THREAD COMPLETE: Profile loading done for {username} ====")
            
    except Exception as e:
        error_msg = f"Error in profile loading: {str(e)}"
        logger.error(error_msg + "\n" + traceback.format_exc())
        print(error_msg + "\n" + traceback.format_exc())
        if username in profile_progress:
            profile_progress[username] = {"status": "error", "progress": 100, "message": error_msg}
    finally:
        if timeout_timer:
            timeout_timer.cancel()
        def cleanup():
            time.sleep(300)
            profile_progress.pop(username, None)
            profile_results.pop(username, None)
        cleanup_thread = threading.Thread(target=cleanup)
        cleanup_thread.daemon = True
        cleanup_thread.start()

@app.route("/profile/result/<username>")
def profile_result(username):
    """Get the final result of profile loading"""
    logger.info(f"Checking profile result for {username}")
    print(f"Checking profile result for {username}")
    
    if username in profile_results:
        logger.info(f"Profile results found for {username}")
        print(f"Profile results found for {username}")
        return jsonify(profile_results[username])
    elif username in profile_progress and profile_progress[username]["status"] == "error":
        logger.info(f"Profile error found for {username}: {profile_progress[username]['message']}")
        print(f"Profile error found for {username}: {profile_progress[username]['message']}")
        return jsonify({"error": profile_progress[username]["message"]}), 400
    else:
        logger.warning(f"Profile not found or still loading for {username}")
        print(f"Profile not found or still loading for {username}")
        return jsonify({"error": "Profile not found or still loading"}), 404

@app.route("/debug")
def debug_profile():
    """Debug page for profile loading"""
    try:
        with open('debug_profile.html', 'r', encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        return "Debug page not found"

@app.route("/profile/progress/<username>")
def profile_progress_stream(username):
    """Server-Sent Events endpoint for profile loading progress"""
    def generate():
        while username in profile_progress:
            progress_info = profile_progress[username]
            data = json.dumps(progress_info)
            yield f"data: {data}\n\n"
            
            if progress_info.get("status") in ["complete", "error"]:
                break
            time.sleep(1)  # Send updates every second
    
    return Response(generate(), content_type='text/event-stream')

@app.route("/profile/check-progress/<username>")
def check_profile_progress(username):
    """Check current progress status"""
    if username in profile_progress:
        return jsonify(profile_progress[username])
    else:
        return jsonify({"status": "not_found", "progress": 0, "message": "No progress found"}), 404

@app.route("/profile/<username>")
def profile(username):
    if 'email' not in session:
        return redirect(url_for('login'))
    
    logger.info(f"Profile route called for {username}")
    
    
    if username in profile_results:
        logger.debug(f"Using completed profile results for {username}")
        result = profile_results[username]
        return render_template(
            "profile.html",
            profile=result["profile"],
            posts=result["posts"][:3], 
            sentiment=result["sentiment"],
            growth=result["growth"],
            avg_engagement=result["avg_engagement"],
            comments=result["comments"]
        )
    
    if username in profile_progress and profile_progress[username]["status"] == "loading":
        logger.debug(f"Profile {username} is still loading, showing loading page")
        return render_template("profile_loading.html", username=username)
    
   
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT influencer_data, engagement, followers, growth, timestamp, comments, sentiment
            FROM influencer_stats WHERE username = ? ORDER BY timestamp DESC LIMIT 1
        """, (username,))
        row = cursor.fetchone()
        
        logger.info(f"Database query for {username}: found row = {row is not None}")
        
        if row:
        
            timestamp_str = row['timestamp']
            try:
                if timestamp_str.endswith('Z'):
                    timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                else:
                    timestamp = datetime.fromisoformat(timestamp_str).replace(tzinfo=pytz.UTC)
            except ValueError:
                logger.warning(f"Invalid timestamp for {username}: {timestamp_str}")
                timestamp = datetime.now(pytz.UTC)
            
      
            time_diff = datetime.now(pytz.UTC) - timestamp
            logger.info(f"Time difference for {username}: {time_diff} (threshold: 12 hours)")
            print(f"Time difference for {username}: {time_diff} (threshold: 12 hours)")
            
            if time_diff < timedelta(hours=12):
                try:
                 
                    if isinstance(row['influencer_data'], str):
                        info = json.loads(row['influencer_data'])
                    elif isinstance(row['influencer_data'], dict):
                        info = row['influencer_data']
                    else:
                        info = {}
                    profile_data = info.get("profile", {})
                    posts = info.get("posts", [])
                    avg_engagement = row['engagement'] or 0
                    
                  
                    growth_data = {"timestamps": [], "follower_growth": [], "engagement_trend": []}
                    if row['growth']:
                        if isinstance(row['growth'], str):
                            try:
                                growth_data = json.loads(row['growth'])
                            except (json.JSONDecodeError, TypeError):
                                pass
                        elif isinstance(row['growth'], dict):
                            growth_data = row['growth']
                  
                    
              
                    comments = []
                    if row['comments']:
                        if isinstance(row['comments'], str):
                            try:
                                comments = json.loads(row['comments'])
                            except (json.JSONDecodeError, TypeError):
                                comments = []
                        elif isinstance(row['comments'], list):
                            comments = row['comments']
                    
                
                    sentiment_data = {"positive": 0, "neutral": 0, "negative": 0}
                    if row['sentiment']:
                        if isinstance(row['sentiment'], str):
                            try:
                                sentiment_data = json.loads(row['sentiment'])
                            except (json.JSONDecodeError, TypeError):
                                pass
                        elif isinstance(row['sentiment'], dict):
                            sentiment_data = row['sentiment']
                    
                 
                    has_comments = bool(comments)
                    has_sentiment = any(sentiment_data.values())
                    has_growth = growth_data.get('timestamps') and len(growth_data.get('timestamps', [])) > 0
                    
                    logger.debug(f"Found cached data for {username}: comments={len(comments)}, sentiment={sentiment_data}, growth_timestamps={len(growth_data.get('timestamps', []))}")
                    print(f"Found cached data for {username}: comments={len(comments)}, sentiment={sentiment_data}, growth_timestamps={len(growth_data.get('timestamps', []))}")
                    
                    if has_comments or has_sentiment or has_growth:
                        logger.debug(f"Showing complete cached data for {username}")
                        print(f"Showing complete cached data for {username}")
                        return render_template(
                            "profile.html",
                            profile=profile_data,
                            posts=posts[:3], 
                            sentiment=sentiment_data,
                            growth=growth_data,
                            avg_engagement=round(avg_engagement, 2),
                            comments=comments
                        )
                    else:
                        logger.info(f"Cached data for {username} is incomplete, triggering fresh load")
                        print(f"Cached data for {username} is incomplete, triggering fresh load")
                except (json.JSONDecodeError, TypeError) as e:
                    logger.warning(f"Invalid cached data for {username}: {e}")
        
      
        logger.info(f"No recent cached data found for {username}, showing loading page")
        print(f"No recent cached data found for {username}, showing loading page")
        return render_template("profile_loading.html", username=username)
        
    except Exception as e:
        logger.error(f"Error checking cache for {username}: {e}")
        return render_template("profile_loading.html", username=username)

@app.route("/get_niches", methods=["GET"])
def get_niches():
    try:
        return jsonify(list(influencer_by_niche.keys()))
    except Exception as e:
        logger.error(f"Error fetching niches: {e}\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500

@app.route("/get_influencers", methods=["POST"])
def get_influencers():
    try:
        data = request.get_json()
        logger.debug(f"Get influencers request data: {data}")
        niche = data.get("niche")
        if not niche or niche not in influencer_by_niche:
            logger.error(f"Invalid or missing niche: {niche}")
            return jsonify([])

        influencers = influencer_by_niche.get(niche, [])
        if not influencers:
            logger.warning(f"No influencers found for niche: {niche}")
            return jsonify([])

        enriched_influencers = []
        conn = get_db()
        for username in influencers:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT influencer_data, engagement, followers, growth, timestamp
                FROM influencer_stats WHERE username = ? ORDER BY timestamp DESC LIMIT 1
            """, (username,))
            row = cursor.fetchone()
            if row:
                # Parse timestamp safely
                timestamp_str = row['timestamp']
                try:
                    if timestamp_str.endswith('Z'):
                        timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                    else:
                        timestamp = datetime.fromisoformat(timestamp_str).replace(tzinfo=pytz.UTC)
                except ValueError:
                    logger.warning(f"Invalid timestamp for {username}: {timestamp_str}")
                    timestamp = datetime.now(pytz.UTC)
                
                if datetime.now(pytz.UTC) - timestamp < timedelta(hours=12):
                    if isinstance(row['influencer_data'], str):
                        info = json.loads(row['influencer_data'])
                    else:
                        info = row['influencer_data'] or {}
                    avg_engagement = row['engagement'] or 0
                    # Recompute growth
                    growth = compute_growth_percent(conn, username) or (row['growth'] or 0.0)
                else:
                    info = get_influencer_data(username, post_limit=3)
                    if not info:
                        logger.warning(f"No data fetched for {username}")
                        continue
                    posts = info.get("posts", [])
                    avg_engagement = sum(p.get("engagement_percent", 0) for p in posts) / max(len(posts), 1) if posts else 0
                    # Persist snapshot first
                    db_save_influencer_data(username, info, avg_engagement)
                    growth = compute_growth_percent(conn, username)
                    db_save_influencer_data(username, info, avg_engagement, growth=growth)
            else:
                info = get_influencer_data(username, post_limit=3)
                if not info:
                    logger.warning(f"No data fetched for {username}")
                    continue
                posts = info.get("posts", [])
                avg_engagement = sum(p.get("engagement_percent", 0) for p in posts) / max(len(posts), 1) if posts else 0
                # Save first snapshot
                db_save_influencer_data(username, info, avg_engagement)
                growth = compute_growth_percent(conn, username)
                db_save_influencer_data(username, info, avg_engagement, growth=growth)

            profile = info.get("profile", {})
            posts = info.get("posts", [])
            enriched_influencers.append({
                "username": username,
                "followers": profile.get("followers", 0),
                "following": profile.get("following", 0),
                "avg_likes": sum(p.get("likes", 0) for p in posts) / max(len(posts), 1) if posts else 0,
                "avg_comments": sum(p.get("commentsCount", 0) for p in posts) / max(len(posts), 1) if posts else 0,
                "avg_engagement_percent": round(avg_engagement, 2),
                "growth": round(growth, 2),
                "category": niche
            })
        enriched_influencers.sort(key=lambda x: x["avg_engagement_percent"], reverse=True)
        logger.debug(f"Returning {len(enriched_influencers)} influencers for niche: {niche}")
        return jsonify(enriched_influencers)
    except Exception as e:
        logger.error(f"Error getting influencers: {e}\n{traceback.format_exc()}")
        return jsonify([])

@app.route("/growth", methods=["POST"])
def growth():
    try:
        data = request.get_json()
        username = data.get("username")
        if not username:
            logger.error("Missing username in growth request")
            return jsonify({"error": "Username is required"}), 400

        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT influencer_data, engagement, followers, timestamp 
            FROM influencer_stats WHERE username = ? ORDER BY timestamp DESC LIMIT 1
        """, (username,))
        row = cursor.fetchone()
        growth_data = get_growth_data(username) or {"timestamps": [], "follower_growth": [], "engagement_trend": []}
        if row:
            # Parse timestamp safely
            timestamp_str = row['timestamp']
            try:
                if timestamp_str.endswith('Z'):
                    timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                else:
                    timestamp = datetime.fromisoformat(timestamp_str).replace(tzinfo=pytz.UTC)
            except ValueError:
                logger.warning(f"Invalid timestamp for {username}: {timestamp_str}")
                timestamp = datetime.now(pytz.UTC)
            
            if datetime.now(pytz.UTC) - timestamp < timedelta(hours=12):
                logger.debug(f"Using cached data for growth: {username}")
            else:
                info = get_influencer_data(username, post_limit=3)
                if info:
                    posts = info.get("posts", [])
                    avg_engagement = sum(p.get("engagement_percent", 0) for p in posts) / max(len(posts), 1) if posts else 0
                    comments = get_comments(username, posts=posts, post_limit=5)
                    sentiment_data = analyze_sentiment(comments)
                    db_save_influencer_data(username, info, avg_engagement, comments=comments, sentiment=sentiment_data)
        else:
            info = get_influencer_data(username, post_limit=3)
            if info:
                posts = info.get("posts", [])
                avg_engagement = sum(p.get("engagement_percent", 0) for p in posts) / max(len(posts), 1) if posts else 0
                comments = get_comments(username, posts=posts, post_limit=5)
                sentiment_data = analyze_sentiment(comments)
                db_save_influencer_data(username, info, avg_engagement, comments=comments, sentiment=sentiment_data)

        if not growth_data["timestamps"]:
            utc = pytz.UTC
            current_time = datetime.now(utc)
            timestamps = [(current_time - timedelta(days=i)).isoformat() for i in range(5)]
            cursor.execute("SELECT influencer_data, engagement, followers FROM influencer_stats WHERE username = ? ORDER BY timestamp DESC LIMIT 1", (username,))
            row = cursor.fetchone()
            if row and row['influencer_data']:
                try:
                    if isinstance(row['influencer_data'], str):
                        data_parsed = json.loads(row['influencer_data'])
                    else:
                        data_parsed = row['influencer_data']
                    followers = data_parsed.get('profile', {}).get('followers', 0)
                except (json.JSONDecodeError, TypeError, KeyError):
                    followers = 0
            else:
                followers = 0
            engagement = row['engagement'] if row else 0
            follower_growth = [followers * (1 - 0.05 * i / 5) for i in range(5)]
            engagement_trend = [engagement * (1 - 0.1 * i / 5) for i in range(5)]
            growth_data = {
                "timestamps": timestamps,
                "follower_growth": follower_growth,
                "engagement_trend": engagement_trend
            }
        growth_data["timestamps"] = [str(t) for t in growth_data.get("timestamps", [])]
        return jsonify(growth_data)
    except Exception as e:
        logger.error(f"Error getting growth data: {e}\n{traceback.format_exc()}")
        # Return fallback growth data instead of 500 error
        utc = pytz.UTC
        current_time = datetime.now(utc)
        timestamps = [(current_time - timedelta(days=i)).isoformat() for i in range(5)]
        growth_data = {
            "timestamps": [str(t) for t in timestamps],
            "follower_growth": [0] * 5,
            "engagement_trend": [0] * 5
        }
        return jsonify(growth_data), 200

if __name__ == "__main__":
    init_db()
    app.run(debug=False) 