import os
import requests
import time
import logging
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.DEBUG)

APIFY_API_TOKEN = os.getenv("APIFY_API_TOKEN")
if not APIFY_API_TOKEN:
    logger.error("APIFY_API_TOKEN not found in environment variables")
    raise ValueError("APIFY_API_TOKEN not found in environment variables")

def fetch_instagram_data(usernames, post_limit=10):
    """Fetch Instagram profile and post data using Apify."""
    if isinstance(usernames, str):
        usernames = [usernames]
    
    # Use the official Instagram Profile Scraper actor
    payload = {
        "usernames": usernames,
        "resultsLimit": post_limit,
        "resultsType": "posts"
    }
    
    try:
        response = requests.post(
            "https://api.apify.com/v2/acts/apify~instagram-profile-scraper/runs",
            json=payload,
            headers={"Authorization": f"Bearer {APIFY_API_TOKEN}"},
            timeout=30
        )
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to start Instagram profile scraper: {e}")
        return None
    run_data = response.json()
    
    # Handle nested response structure
    if 'data' in run_data:
        run_data = run_data['data']
    
    if 'id' not in run_data:
        logger.error(f"Run data missing 'id': {run_data}")
        return None
    run_id = run_data['id']
    logger.info(f"Started run {run_id} for {usernames}")
    
    # Wait for completion with timeout
    max_wait_time = 300  # 5 minutes max wait
    wait_time = 0
    while wait_time < max_wait_time:
        try:
            status_response = requests.get(
                f"https://api.apify.com/v2/actor-runs/{run_id}",
                headers={"Authorization": f"Bearer {APIFY_API_TOKEN}"},
                timeout=10
            )
            status_data = status_response.json()
            
            # Handle nested response structure
            if 'data' in status_data:
                status_data = status_data['data']
            
            status = status_data.get('status')
            
            if status == 'SUCCEEDED':
                break
            elif status == 'FAILED':
                logger.error(f"Run failed: {status_data.get('errorMessage')}")
                return None
            elif status == 'ABORTED':
                logger.error(f"Run aborted: {status_data.get('errorMessage')}")
                return None
                
            time.sleep(5)
            wait_time += 5
        except requests.exceptions.RequestException as e:
            logger.error(f"Error checking run status: {e}")
            return None
    
    if wait_time >= max_wait_time:
        logger.error(f"Run timed out after {max_wait_time} seconds")
        return None
    
    try:
        dataset_id = status_data['defaultDatasetId']
        items_response = requests.get(
            f"https://api.apify.com/v2/datasets/{dataset_id}/items",
            headers={"Authorization": f"Bearer {APIFY_API_TOKEN}"},
            timeout=30
        )
        items_response.raise_for_status()
        items = items_response.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to retrieve dataset items: {e}")
        return None
    except KeyError as e:
        logger.error(f"Missing dataset ID in status data: {e}")
        return None
    
    if not items:
        logger.warning("No data in dataset")
        return None
    
    profile_data = items[0]
    profile = {
        "username": profile_data.get("username"),
        "fullName": profile_data.get("fullName", ""),
        "followers": profile_data.get("followersCount", 0),
        "following": profile_data.get("followsCount", 0),
        "posts_count": profile_data.get("postsCount", 0),
        "bio": profile_data.get("biography", ""),
        "profilePicUrl": profile_data.get("profilePicUrl")
    }
    posts = [
        {
            "id": post.get("id"),
            "shortCode": post.get("shortCode"),
            "caption": post.get("captionText", ""),
            "likes": post.get("likesCount", 0),
            "commentsCount": post.get("commentsCount", 0),
            "url": post.get("url") or (f"https://www.instagram.com/p/{post.get('shortCode')}/" if post.get("shortCode") else None),
            "displayUrl": post.get("displayUrl"),
            "engagement_percent": 0,  # Will be calculated later
            "timestamp": post.get("timestamp")
        }
        for post in profile_data.get("latestPosts", [])[:post_limit]
    ]
    result = {"profile": profile, "posts": posts}
    logger.info(f"Fetched data for {profile['username']}: {len(posts)} posts, {profile['followers']} followers")
    return result

def fetch_instagram_comments(direct_urls, results_limit=13, include_nested_comments=False):
    """Fetch comments for Instagram posts using Apify."""
    payload = {
        "directUrls": direct_urls,
        "resultsLimit": results_limit,
        "includeNestedComments": include_nested_comments
    }
    
    try:
        response = requests.post(
            "https://api.apify.com/v2/acts/apify~instagram-comment-scraper/runs",
            json=payload,
            headers={"Authorization": f"Bearer {APIFY_API_TOKEN}"},
            timeout=30
        )
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to start Instagram comment scraper: {e}")
        return []
    run_data = response.json()
    
    # Handle nested response structure
    if 'data' in run_data:
        run_data = run_data['data']
    
    run_id = run_data['id']
    logger.info(f"Started comments run {run_id} for {len(direct_urls)} URLs")
    
    # Wait for completion with timeout
    max_wait_time = 180  # 3 minutes max wait for comments
    wait_time = 0
    while wait_time < max_wait_time:
        try:
            status_response = requests.get(
                f"https://api.apify.com/v2/actor-runs/{run_id}",
                headers={"Authorization": f"Bearer {APIFY_API_TOKEN}"},
                timeout=10
            )
            status_data = status_response.json()
            
            # Handle nested response structure
            if 'data' in status_data:
                status_data = status_data['data']
            
            status = status_data.get('status')
            
            if status == 'SUCCEEDED':
                break
            elif status == 'FAILED':
                logger.error(f"Comments run failed: {status_data.get('errorMessage')}")
                return []
            elif status == 'ABORTED':
                logger.error(f"Comments run aborted: {status_data.get('errorMessage')}")
                return []
                
            time.sleep(5)
            wait_time += 5
        except requests.exceptions.RequestException as e:
            logger.error(f"Error checking comments run status: {e}")
            return []
    
    if wait_time >= max_wait_time:
        logger.error(f"Comments run timed out after {max_wait_time} seconds")
        return []
    
    dataset_id = status_data['defaultDatasetId']
    items_response = requests.get(
        f"https://api.apify.com/v2/datasets/{dataset_id}/items",
        headers={"Authorization": f"Bearer {APIFY_API_TOKEN}"}
    )
    items = items_response.json()
    comments = [
        {
            "text": item.get("text", ""),
            "author": item.get("ownerUsername", ""),
            "likes": item.get("likesCount", 0),
            "timestamp": item.get("timestamp")
        }
        for item in items
    ]
    logger.info(f"Fetched {len(comments)} comments")
    return comments

def fetch_instagram_posts(direct_urls, results_limit=50):
    """Fetch detailed Instagram post data using Apify."""
    payload = {
        "directUrls": direct_urls,
        "resultsLimit": results_limit
    }
    
    try:
        response = requests.post(
            "https://api.apify.com/v2/acts/apify~instagram-post-scraper/runs",
            json=payload,
            headers={"Authorization": f"Bearer {APIFY_API_TOKEN}"},
            timeout=30
        )
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to start Instagram post scraper: {e}")
        return []
    run_data = response.json()
    
    # Handle nested response structure
    if 'data' in run_data:
        run_data = run_data['data']
    
    run_id = run_data['id']
    logger.info(f"Started post run {run_id} for {len(direct_urls)} URLs")
    
    # Wait for completion with timeout
    max_wait_time = 180  # 3 minutes max wait for posts
    wait_time = 0
    while wait_time < max_wait_time:
        try:
            status_response = requests.get(
                f"https://api.apify.com/v2/actor-runs/{run_id}",
                headers={"Authorization": f"Bearer {APIFY_API_TOKEN}"},
                timeout=10
            )
            status_data = status_response.json()
            
            # Handle nested response structure
            if 'data' in status_data:
                status_data = status_data['data']
            
            status = status_data.get('status')
            
            if status == 'SUCCEEDED':
                break
            elif status == 'FAILED':
                logger.error(f"Post run failed: {status_data.get('errorMessage')}")
                return []
            elif status == 'ABORTED':
                logger.error(f"Post run aborted: {status_data.get('errorMessage')}")
                return []
                
            time.sleep(5)
            wait_time += 5
        except requests.exceptions.RequestException as e:
            logger.error(f"Error checking post run status: {e}")
            return []
    
    if wait_time >= max_wait_time:
        logger.error(f"Post run timed out after {max_wait_time} seconds")
        return []
    
    dataset_id = status_data['defaultDatasetId']
    items_response = requests.get(
        f"https://api.apify.com/v2/datasets/{dataset_id}/items",
        headers={"Authorization": f"Bearer {APIFY_API_TOKEN}"}
    )
    items = items_response.json()
    posts = [
        {
            "id": item.get("id"),
            "shortCode": item.get("shortCode"),
            "caption": item.get("caption", ""),
            "likes": item.get("likesCount", 0),
            "commentsCount": item.get("commentsCount", 0),
            "url": item.get("url"),
            "displayUrl": item.get("displayUrl"),
            "timestamp": item.get("timestamp"),
            "viewCount": item.get("viewCount", 0),
            "playCount": item.get("playCount", 0)
        }
        for item in items
    ]
    logger.info(f"Fetched {len(posts)} detailed posts")
    return posts
