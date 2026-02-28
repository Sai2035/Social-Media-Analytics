# influencer_data.py
import logging
import json
import requests
from datetime import datetime
import pytz
from services.database import save_influencer_data, get_influencer_data as db_get_influencer_data, get_growth_data as db_get_growth_data
from services.apify_api import fetch_instagram_data, fetch_instagram_comments, fetch_instagram_posts

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.DEBUG)

def get_influencer_data(username, post_limit=3):
    """Fetch influencer data using Apify API with enhanced engagement calculation."""
    try:
        # Get basic profile data
        data = fetch_instagram_data(username, post_limit=post_limit)
        if not data:
            logger.warning(f"No data fetched for {username}")
            return None
        
        profile = data.get("profile", {})
        posts = data.get("posts", [])
        # Normalize keys from Apify (camelCase) to our templates' expected snake case
        # This keeps backward compatibility with existing templates such as `templates/profile.html`
        if profile:
            # Ensure consistent keys for template access
            if "full_name" not in profile:
                profile["full_name"] = profile.get("fullName") or profile.get("username") or ""
            if "profile_pic_url" not in profile:
                profile["profile_pic_url"] = profile.get("profilePicUrl")
            # Followers/following may already be normalized in apify_api; keep as-is but ensure ints
            if "followers" in profile and isinstance(profile["followers"], str):
                try:
                    profile["followers"] = int(profile["followers"].replace(",", ""))
                except Exception:
                    pass
            if "following" in profile and isinstance(profile["following"], str):
                try:
                    profile["following"] = int(profile["following"].replace(",", ""))
                except Exception:
                    pass
            # Provide posts_count for template if missing
            profile.setdefault("posts_count", len(posts) if isinstance(posts, list) else 0)
        
        # Normalize post field names expected by templates
        normalized_posts = []
        for p in posts or []:
            if isinstance(p, dict):
                # Map displayUrl -> display_url
                if "display_url" not in p and "displayUrl" in p:
                    p["display_url"] = p.get("displayUrl")
                # Map timestamp -> taken_at_timestamp
                if "taken_at_timestamp" not in p and "timestamp" in p:
                    p["taken_at_timestamp"] = p.get("timestamp")
            normalized_posts.append(p)
        posts = normalized_posts
        # Re-attach normalized structures back to data
        data["profile"] = profile
        data["posts"] = posts
        followers = profile.get("followers", 0)
        
        if followers == 0:
            followers = 1  # Prevent division by zero
        
        # Calculate basic engagement from profile scraper data
        for post in posts:
            likes = post.get("likes", 0)
            comments_count = post.get("commentsCount", 0)
            post["engagement_percent"] = min((likes + comments_count) / followers * 100, 100.0)

        # Enhance with detailed post data if available
        try:
            post_urls = [post.get("url") for post in posts if post.get("url")]
            if post_urls:
                logger.debug(f"Fetching detailed post data for {len(post_urls)} posts")
                detailed_posts = fetch_instagram_posts(post_urls[:5], results_limit=5)  # Limit for speed

                # Merge detailed data with existing posts
                for i, detailed in enumerate(detailed_posts):
                    if i < len(posts):
                        posts[i].update({
                            "likes": detailed.get("likes", posts[i].get("likes", 0)),
                            "commentsCount": detailed.get("commentsCount", posts[i].get("commentsCount", 0)),
                            "viewCount": detailed.get("viewCount", 0),
                            "playCount": detailed.get("playCount", 0)
                        })
                        # Ensure normalized keys remain present after update
                        if "display_url" not in posts[i] and detailed.get("displayUrl"):
                            posts[i]["display_url"] = detailed.get("displayUrl")
                        if "taken_at_timestamp" not in posts[i] and detailed.get("timestamp") is not None:
                            posts[i]["taken_at_timestamp"] = detailed.get("timestamp")
                        # Recalculate engagement with updated data
                        likes = posts[i].get("likes", 0)
                        comments_count = posts[i].get("commentsCount", 0)
                        posts[i]["engagement_percent"] = min((likes + comments_count) / followers * 100, 100.0)
        except Exception as post_error:
            logger.warning(f"Could not fetch detailed post data for {username}: {post_error}")
            # Continue with basic data

        # Calculate overall engagement
        profile["engagement_percent"] = sum(p.get("engagement_percent", 0) for p in posts) / max(len(posts), 1) if posts else 0

        logger.debug(f"Fetched data for {username}: {len(posts)} posts, {followers} followers, {profile['engagement_percent']:.2f}% engagement")
        return data

    except Exception as e:
        logger.error(f"Error fetching data for {username}: {e}")
        return None

def get_comments(username, posts=None, post_limit=2):  # Reduced to 2 for speed
    """Fetch comments for the influencer's recent posts."""
    try:
        if posts is None:
            data = fetch_instagram_data(username, post_limit=post_limit)
            if not data or not data.get("posts"):
                logger.warning(f"No posts found for {username} to fetch comments")
                return []
            posts = data["posts"]
        direct_urls = [post.get("url") for post in posts[:post_limit] if post.get("url")]
        if not direct_urls:
            logger.warning(f"No valid post URLs for {username}")
            return []
        logger.debug(f"Fetching comments for {username} with URLs: {direct_urls}")

        # Timeout via threading
        import threading
        result = [None]
        def target():
            try:
                result[0] = fetch_instagram_comments(direct_urls, results_limit=5, include_nested_comments=False)  # Reduced results
            except Exception as e:
                logger.error(f"Exception in comment fetch: {e}")
                result[0] = []

        thread = threading.Thread(target=target)
        thread.daemon = True
        thread.start()
        thread.join(timeout=180)  # Bumped to 3min
        if thread.is_alive():
            logger.warning(f"Comments fetching timeout for {username} after 3min - aborting")
            # Abort run on Apify if possible (optional)
            try:
                # client.abort_run(run_id) if you have run_id from fetch_instagram_comments
                pass
            except:
                pass
            return []  # Fallback empty
        comments_data = result[0] or []
        comments = [c.get("text", "") for c in comments_data if c.get("text")]
        logger.debug(f"Fetched {len(comments)} comments for {username}")

        # Fallback: If no comments, use post captions for sentiment
        if not comments and posts:
            logger.info(f"No comments for {username} - using {len(posts)} post captions as fallback")
            comments = [post.get("caption", "") for post in posts[:3] if post.get("caption")]

        return comments
    except Exception as e:
        logger.error(f"Error fetching comments for {username}: {e}")
        return []

def analyze_sentiment(comments):
    """Analyze sentiment of comments using simple keyword-based analysis."""
    try:
        # Import the simple sentiment analyzer
        from ml.sentiment import analyze_sentiment as simple_analyze
        return simple_analyze(comments)
    except ImportError:
        logger.warning("Simple sentiment analyzer not available, using fallback")
        # Fallback to basic keyword analysis
        if not comments:
            return {"positive": 0, "neutral": 0, "negative": 0}
        
        positive_keywords = ["great", "awesome", "love", "amazing", "good", "fantastic", "wonderful"]
        negative_keywords = ["bad", "terrible", "hate", "awful", "poor", "disappointed", "worst"]
        
        sentiment = {"positive": 0, "neutral": 0, "negative": 0}
        
        for comment in comments:
            if not comment or not isinstance(comment, str):
                continue
                
            comment_lower = comment.lower()
            pos_count = sum(1 for keyword in positive_keywords if keyword in comment_lower)
            neg_count = sum(1 for keyword in negative_keywords if keyword in comment_lower)
            
            if pos_count > neg_count:
                sentiment["positive"] += 1
            elif neg_count > pos_count:
                sentiment["negative"] += 1
            else:
                sentiment["neutral"] += 1
        
        total = sum(sentiment.values())
        if total > 0:
            sentiment = {k: round(v / total * 100, 2) for k, v in sentiment.items()}
        
        return sentiment
        
    except Exception as e:
        logger.error(f"Error analyzing sentiment: {e}")
        return {"positive": 0, "neutral": 0, "negative": 0}

def db_save_influencer_data(username, influencer_data, engagement, growth=None, comments=None, sentiment=None):
    """Save influencer data to the database."""
    try:
        save_influencer_data(username, influencer_data, engagement, growth, comments, sentiment)
        logger.debug(f"Data saved for {username}")
    except Exception as e:
        logger.error(f"Error saving influencer data for {username}: {e}")

# Note: get_growth_data is now imported from database.py as db_get_growth_data if needed, but keeping local version for compatibility
def get_growth_data(username):
    """Retrieve growth data from the database."""
    try:
        return db_get_growth_data(username)
    except Exception as e:
        logger.error(f"Error retrieving growth data for {username}: {e}")
        return None