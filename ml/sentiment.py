import logging
import nltk
from nltk.sentiment.vader import SentimentIntensityAnalyzer

logger = logging.getLogger(__name__)

def analyze_sentiment(comments):
    """Analyze sentiment of comments using NLTK VADER + emoji/keyword enhancement."""
    try:
        # Ensure VADER lexicon is available
        try:
            nltk.data.find('sentiment/vader_lexicon')
        except LookupError:
            nltk.download('vader_lexicon')

        if not comments:
            logger.debug("No comments provided for sentiment analysis")
            return {"positive": 0, "neutral": 0, "negative": 0}

        sia = SentimentIntensityAnalyzer()
        sentiment = {"positive": 0, "neutral": 0, "negative": 0}

        # --- ADD YOUR CUSTOM EMOJI AND SLANG ENHANCEMENTS ---
        positive_keywords = [
            "great", "awesome", "love", "amazing", "good", "fantastic", "wonderful", 
            "excellent", "perfect", "beautiful", "incredible", "outstanding", "brilliant",
            "superb", "marvelous", "fabulous", "nice", "cool", "sweet", "wow", "yes",
            "yeah", "yay", "haha", "lol", "lmao", "rofl", "hahaha", "fire", "slay",
            "periodt", "yasss", "queen", "slaps", "no cap", "lit", "vibes", "mood",
            "stunning", "gorgeous", "breathtaking", "phenomenal", "magnificent",
            "spectacular", "divine", "heavenly", "dreamy", "flawless", "impeccable",
            "best", "top", "favorite", "adore", "obsessed", "mind-blowing"
        ]
        positive_emojis = [
            "😍", "😘", "🥰", "😊", "😁", "😂", "🤣", "😆", "😄", "😃", "😀",
            "👍", "👏", "👌", "✌️", "🤞", "🤟", "🤘", "👋", "🙌", "👐", "🤲",
            "❤️", "🧡", "💛", "💚", "💙", "💜", "🤍", "🤎", "💕", "💖", "💗", "💘", "💝",
            "🔥", "✨", "⭐", "🌟", "💫", "🎉", "🎊", "🎈", "💯", "✅", "🏆", "🥇", "👑"
        ]
        negative_keywords = [
            "bad", "terrible", "hate", "awful", "poor", "disappointed", "worst",
            "disgusting", "horrible", "ugly", "annoying", "boring", "stupid", "dumb",
            "suck", "sucks", "crap", "trash", "garbage", "gross", "yuck", "no", "nope",
            "nah", "meh", "mid", "pathetic", "ridiculous", "absurd", "nonsense",
            "underwhelming", "bland", "cheap", "fake", "despise", "revolting"
        ]
        negative_emojis = [
            "😞", "😔", "😢", "😭", "😤", "😠", "😡", "🤬", "👎", "💔", "❌", "🚫", "☹️", "😣", "😖"
        ]

        
        for comment in comments:
            if not comment or not isinstance(comment, str):
                continue

            comment_lower = comment.lower()
            # Adjust VADER score based on emoji and keyword context
            adjustment = 0

            if any(word in comment_lower for word in positive_keywords) or \
               any(emoji in comment for emoji in positive_emojis):
                adjustment += 0.1  # small boost to positive

            if any(word in comment_lower for word in negative_keywords) or \
               any(emoji in comment for emoji in negative_emojis):
                adjustment -= 0.1  # small boost to negative

            # Get VADER sentiment
            scores = sia.polarity_scores(comment)
            compound = scores['compound'] + adjustment

            # Clip compound between [-1, 1]
            compound = max(-1, min(1, compound))

            # Classify
            if compound >= 0.05:
                sentiment["positive"] += 1
            elif compound <= -0.05:
                sentiment["negative"] += 1
            else:
                sentiment["neutral"] += 1

        total = sum(sentiment.values())
        if total > 0:
            sentiment = {k: round(v / total * 100, 2) for k, v in sentiment.items()}

        logger.debug(f"Sentiment analysis result: {sentiment}")
        return sentiment

    except Exception as e:
        logger.error(f"Error analyzing sentiment: {e}")
        return {"positive": 0, "neutral": 0, "negative": 0}
