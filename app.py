from flask import Flask, render_template, request, send_file, jsonify
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO
import os
import logging
from dotenv import load_dotenv
import google.generativeai as genai
import requests
import json
import time
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
from random import choice, shuffle
from datetime import datetime, timedelta

load_dotenv()

app = Flask(__name__)

# Configure logging
logging.basicConfig(level=logging.INFO)

# Directory setup
STATIC_DIR = os.path.join(app.root_path, 'static')
FONTS_DIR = os.path.join(STATIC_DIR, 'fonts')
os.makedirs(FONTS_DIR, exist_ok=True)
os.makedirs(STATIC_DIR, exist_ok=True)

ROBOTO_PATH = os.path.join(FONTS_DIR, 'Roboto-Regular.ttf')
ROBOTO_BOLD_PATH = os.path.join(FONTS_DIR, 'Roboto-Bold.ttf')

# Create default logo
DEFAULT_LOGO_PATH = os.path.join(STATIC_DIR, 'logo.png')
if not os.path.exists(DEFAULT_LOGO_PATH):
    default_logo = Image.new('RGBA', (40, 40), (0, 0, 0, 0))
    default_logo.save(DEFAULT_LOGO_PATH)

# Configure Gemini AI
genai.configure(api_key=os.getenv('GEMINI_API_KEY'))
model = genai.GenerativeModel('gemini-pro')

fetched_article_ids = set()

class ArticleCache:
    def __init__(self):
        self.fetched_ids = {}  # Dict to store article ID and fetch time
        self.cache_expiry = timedelta(hours=24)  # Reset cache after 24 hours

    def add(self, article_id):
        self.fetched_ids[article_id] = datetime.now()
        self._cleanup()

    def contains(self, article_id):
        if article_id in self.fetched_ids:
            return datetime.now() - self.fetched_ids[article_id] < self.cache_expiry
        return False

    def _cleanup(self):
        now = datetime.now()
        self.fetched_ids = {
            id: time for id, time in self.fetched_ids.items() 
            if now - time < self.cache_expiry
        }

article_cache = ArticleCache()

class NewsCache:
    def __init__(self):
        self.fetched_ids = {}
        self.last_cleanup = datetime.now()
        self.cleanup_interval = timedelta(hours=24)

    def add(self, article_id: str) -> None:
        self.fetched_ids[article_id] = datetime.now()
        self._cleanup()

    def contains(self, article_id: str) -> bool:
        self._cleanup()
        return article_id in self.fetched_ids

    def _cleanup(self) -> None:
        if datetime.now() - self.last_cleanup > self.cleanup_interval:
            cutoff = datetime.now() - self.cleanup_interval
            self.fetched_ids = {
                id: time for id, time in self.fetched_ids.items()
                if time > cutoff
            }
            self.last_cleanup = datetime.now()

news_cache = NewsCache()

def wrap_text(text, font, max_width):
    """Text wrapping function"""
    lines = []
    for paragraph in text.split('\n'):
        if not paragraph:
            lines.append('')
            continue
        
        words = paragraph.split()
        current_line = []
        current_width = 0

        for word in words:
            word_width = font.getlength(word + ' ')
            if current_width + word_width > max_width:
                if current_line:
                    lines.append(' '.join(current_line))
                current_line = [word]
                current_width = word_width
            else:
                current_line.append(word)
                current_width += word_width

        if current_line:
            lines.append(' '.join(current_line))

    return lines

def calculate_text_height(lines, font_size, line_spacing):
    """Calculate total height needed for text block"""
    return len(lines) * int(font_size * line_spacing)

def draw_separator_line(draw, y_position, width, padding):
    """Draw a subtle separator line"""
    draw.line(
        [(padding, y_position), (width - padding, y_position)],
        fill='#8A8A8A',
        width=1
    )

@app.route('/')
def index():
    return render_template('index.html')

@app.route("/health")
def health():
    app.logger.info("Health check route accessed.")
    return "OK", 200

def smart_truncate(text, max_length):
    """Intelligently truncate text at sentence boundaries"""
    if len(text) <= max_length:
        return text
        
    # Find all sentence endings within limit
    end_markers = ['. ', '! ', '? ']
    positions = []
    
    for marker in end_markers:
        pos = 0
        while True:
            pos = text.find(marker, pos, max_length)
            if pos == -1:
                break
            positions.append(pos + len(marker))
            pos += len(marker)
    
    if not positions:
        # No sentence breaks found, try to break at last space
        last_space = text[:max_length].rfind(' ')
        if (last_space > 0):
            return text[:last_space].strip() + '.'
        return text[:max_length-1] + '.'
        
    # Get the last complete sentence
    last_sentence_end = max(positions)
    return text[:last_sentence_end].strip()

def is_valid_article(article):
    """Check if article has enough content and proper character counts"""
    return (
        article.get('title') and 
        article.get('description') and
        article.get('content') and
        len(article['title']) >= 20 and len(article['title']) <= 52 and  # Tag line limit
        len(article['description']) >= 100 and len(article['description']) <= 200 and  # Caption limit
        len(article.get('content', '')) >= 200 and len(article.get('content', '')) <= 500 and  # Main content limit
        not any(x in article['title'].upper() for x in ['N/A', 'NULL', 'UNDEFINED']) and
        article['title'].strip() and
        article['description'].strip() and
        article.get('content', '').strip() and
        article.get('article_id') not in fetched_article_ids  # Check if already fetched
    )

def is_recent_article(article, days=7):  # Changed from hours to days
    """Check if article is within specified days"""
    try:
        pub_date = datetime.fromisoformat(article['pubDate'].replace('Z', '+00:00'))
        return datetime.now(pub_date.tzinfo) - pub_date < timedelta(days=days)
    except (KeyError, ValueError):
        return True  # If we can't parse date, consider it valid

def fetch_single_news(api_key: str, category: str, page: int = 0) -> Optional[Dict[Any, Any]]:
    """Fetch news with pagination support"""
    base_url = "https://newsdata.io/api/1/news"
    params = {
        'apikey': api_key,
        'category': category,
        'language': 'en',
        'size': 10,
        'page': page
    }
    
    try:
        response = requests.get(base_url, params=params, timeout=15)
        response.raise_for_status()
        data = response.json()
        
        if not data.get('results'):
            return None
            
        # Filter and sort articles
        available_articles = []
        for article in data['results']:
            if (article.get('article_id') and 
                not news_cache.contains(article['article_id']) and 
                is_valid_article(article)):
                available_articles.append(article)
        
        if available_articles:
            selected = choice(available_articles)
            news_cache.add(selected['article_id'])
            return selected
            
        return None
        
    except Exception as e:
        app.logger.warning(f"Error fetching news: {str(e)}")
        return None

def validate_article_content(article: Dict[str, Any]) -> bool:
    """Validate article content and character lengths"""
    try:
        title = str(article.get('title', '')).strip()
        description = str(article.get('description', '')).strip()
        content = str(article.get('content', '')).strip()
        
        # Character length requirements
        return (
            len(title) >= 30 and len(title) <= 52 and  # Tag line
            len(description) >= 100 and len(description) <= 200 and  # Captions
            len(content) >= 200 and len(content) <= 500 and  # Main content
            title.isprintable() and
            description.isprintable() and
            content.isprintable()
        )
    except:
        return False

def fetch_news_with_retry(api_key: str) -> Dict[str, Any]:
    """Fetch news with strict content validation"""
    categories = ['technology', 'business', 'science', 'top', 'world']
    shuffle(categories)
    all_valid_articles = []
    
    for category in categories:
        try:
            response = requests.get(
                "https://newsdata.io/api/1/news",
                params={
                    'apikey': api_key,
                    'category': category,
                    'language': 'en',
                    'size': 10
                },
                timeout=15
            )
            
            if response.status_code == 429:
                time.sleep(2)
                continue
                
            data = response.json()
            
            if isinstance(data.get('results'), list):
                for article in data['results']:
                    if (isinstance(article, dict) and
                        validate_article_content(article) and
                        not news_cache.contains(article.get('article_id', ''))):
                        all_valid_articles.append(article)
            
            time.sleep(1)
            
        except Exception as e:
            app.logger.warning(f"Error fetching {category} news: {str(e)}")
            continue
    
    # Select random article from collected valid articles
    if all_valid_articles:
        selected = choice(all_valid_articles)
        news_cache.add(selected.get('article_id', str(time.time())))
        return {
            'title': str(selected['title']).strip(),
            'description': str(selected['description']).strip(),
            'content': str(selected.get('content', selected['description'])).strip(),
            'source_id': str(selected.get('source_id', 'NEWS')),
            'category': str(selected.get('category', 'Breaking News')),
            'article_id': str(selected.get('article_id', f'article_{time.time()}'))
        }
    
    # Fallback content with proper character counts
    return {
        'title': 'Innovation and Technology Shape Our Digital Future',
        'description': 'Breakthrough developments in artificial intelligence and sustainable technology continue to transform industries worldwide, creating new opportunities for growth and innovation.',
        'content': 'As we progress through 2025, technological innovations are revolutionizing how we live and work. From advanced AI systems to sustainable solutions, these breakthroughs are addressing global challenges while opening new frontiers for human achievement and progress.',
        'source_id': 'TECH',
        'category': 'technology',
        'article_id': f'fallback_{int(time.time())}'
    }

@app.route('/fetch-news')
def fetch_news():
    """News fetching endpoint with error handling"""
    try:
        api_key = os.getenv('NEWSDATA_API_KEY')
        if not api_key:
            raise ValueError("API key not configured")

        article = fetch_news_with_retry(api_key)
        
        return jsonify({
            "tag_line": smart_truncate(str(article['title']).strip(), 52).upper(),
            "after_tag": smart_truncate(str(article['description']).strip(), 55),
            "main_content": smart_truncate(str(article.get('content', article['description'])).strip(), 500),
            "company_name": str(article.get('source_id', 'NEWS'))[:5].upper(),
            "side_note": str(article.get('category', 'Breaking News')).title()[:40],
            "first_caption": smart_truncate(str(article['description']).strip(), 200),
            "second_caption": smart_truncate(str(article.get('content', article['description'])).strip(), 200),
            "big_question": f"WHAT'S NEXT FOR {str(article.get('category', 'THIS STORY')).upper()}?"[:51]
        })

    except Exception as e:
        app.logger.error(f"Error in fetch-news: {str(e)}")
        return jsonify({
            "tag_line": "BREAKING: INNOVATION DRIVES CHANGE",
            "after_tag": "New developments reshape our future",
            "main_content": "Technological breakthroughs continue to emerge, transforming industries.",
            "company_name": "NEWS",
            "side_note": "Breaking News",
            "first_caption": "Innovation continues to accelerate across sectors.",
            "second_caption": "Experts predict more breakthrough developments ahead.",
            "big_question": "WHAT'S NEXT FOR INNOVATION?"
        })

@app.route('/generate', methods=['POST'])
def generate_image():
    try:
        # Get form data with character limits
        tag_line = request.form.get('tag_line', '').upper()[:52]
        after_tag = request.form.get('after_tag', '')[:55]
        main_content = request.form.get('main_content', '')[:300]
        company_name = request.form.get('company_name', '').upper()[:5]
        side_note = request.form.get('side_note', '')[:40]
        first_caption = request.form.get('first_caption', '')[:200]
        second_caption = request.form.get('second_caption', '')[:200]
        big_question = request.form.get('big_question', '').upper()[:51]

        # Create image
        img = Image.new('RGB', (1080, 1080), '#A4A5A6')
        draw = ImageDraw.Draw(img)

        try:
            font_57 = ImageFont.truetype(ROBOTO_BOLD_PATH, 57)
            font_37 = ImageFont.truetype(ROBOTO_PATH, 37)
            font_31 = ImageFont.truetype(ROBOTO_PATH, 31)
            font_198 = ImageFont.truetype(ROBOTO_BOLD_PATH, 198)
            font_43 = ImageFont.truetype(ROBOTO_PATH, 43)
        except Exception as e:
            app.logger.error(f"Font loading error: {e}")
            return "Font loading error", 500

        # Layout constants
        padding = 40
        max_width = 1080 - (padding * 2)
        line_spacing = 1.1
        section_spacing = 15
        logo_space = 90  # Space reserved for logo at bottom

        # Pre-calculate text blocks and their heights
        tag_lines = wrap_text(tag_line, font_57, max_width)
        after_lines = wrap_text(after_tag, font_37, max_width)
        main_lines = wrap_text(main_content, font_31, max_width)
        first_caption_lines = wrap_text(first_caption, font_31, max_width)
        second_caption_lines = wrap_text(second_caption, font_31, max_width)
        big_question_lines = wrap_text(big_question, font_57, max_width)

        # Calculate heights
        tag_height = calculate_text_height(tag_lines, font_57.size, line_spacing)
        after_height = calculate_text_height(after_lines, font_37.size, line_spacing)
        main_height = calculate_text_height(main_lines, font_31.size, line_spacing)
        company_height = int(font_198.size * line_spacing)
        first_caption_height = calculate_text_height(first_caption_lines, font_31.size, line_spacing)
        second_caption_height = calculate_text_height(second_caption_lines, font_31.size, line_spacing)
        big_question_height = calculate_text_height(big_question_lines, font_57.size, line_spacing)

        # Calculate total content height
        total_height = (padding + tag_height + section_spacing + 
                       after_height + section_spacing +
                       main_height + section_spacing +
                       company_height + section_spacing +
                       first_caption_height + section_spacing +
                       second_caption_height + section_spacing +
                       big_question_height + logo_space)

        # Adjust spacing if content exceeds image height
        if total_height > 1080:
            section_spacing = 9  # Reduce section spacing
            # Recalculate total height
            total_height = (padding + tag_height + section_spacing + 
                          after_height + section_spacing +
                          main_height + section_spacing +
                          company_height + section_spacing +
                          first_caption_height + section_spacing +
                          second_caption_height + section_spacing +
                          big_question_height + logo_space)

        # Start drawing from top with calculated positions
        current_y = padding

        # Draw tag line (right-aligned)
        for line in tag_lines:
            line_width = font_57.getlength(line)
            draw.text((1080 - padding - line_width, current_y), line, font=font_57, fill='black')
            current_y += int(font_57.size * line_spacing)
        current_y += section_spacing
        draw_separator_line(draw, current_y - 5, 1080, padding)

        # Draw after tag
        for line in after_lines:
            draw.text((padding, current_y), line, font=font_37, fill='black')
            current_y += int(font_37.size * line_spacing)
        current_y += section_spacing
        draw_separator_line(draw, current_y - 5, 1080, padding)

        # Draw main content
        for line in main_lines:
            draw.text((padding, current_y), line, font=font_31, fill='black')
            current_y += int(font_31.size * line_spacing)
        current_y += section_spacing
        draw_separator_line(draw, current_y - 5, 1080, padding)

        # Company name and side note section
        draw.text((padding, current_y), company_name, font=font_198, fill='black')
        
        # Side note (right-aligned)
        wrapped_side = wrap_text(side_note, font_43, max_width/3)
        side_y = current_y
        for line in wrapped_side:
            line_width = font_43.getlength(line)
            draw.text((1080 - padding - line_width, side_y), line, font=font_43, fill='black')
            side_y += int(font_43.size * line_spacing)
        
        current_y += company_height + section_spacing
        draw_separator_line(draw, current_y - 5, 1080, padding)

        # Draw first caption
        for line in first_caption_lines:
            draw.text((padding, current_y), line, font=font_31, fill='black')
            current_y += int(font_31.size * line_spacing)
        current_y += section_spacing
        draw_separator_line(draw, current_y - 5, 1080, padding)

        # Draw second caption
        for line in second_caption_lines:
            draw.text((padding, current_y), line, font=font_31, fill='black')
            current_y += int(font_31.size * line_spacing)
        current_y += section_spacing
        draw_separator_line(draw, current_y - 5, 1080, padding)

        # Calculate remaining space for big question
        remaining_space = 1080 - logo_space - current_y
        
        # If remaining space is too small, adjust current_y
        if remaining_space < big_question_height:
            current_y = 1080 - logo_space - big_question_height

        # Draw big question
        for line in big_question_lines:
            draw.text((padding, current_y), line, font=font_57, fill='black')
            current_y += int(font_57.size * line_spacing)

        # Add logo
        try:
            logo = Image.open(DEFAULT_LOGO_PATH)
            logo = logo.resize((90, 90))
            img.paste(logo, (1080 - 50 - 40, 1080 - 50 - 40), logo if 'A' in logo.getbands() else None)
        except Exception as e:
            app.logger.error(f"Error adding logo: {e}")

        # Save and return image
        img_io = BytesIO()
        img.save(img_io, 'PNG', quality=95)
        img_io.seek(0)
        
        return send_file(img_io, mimetype='image/png')

    except Exception as e:
        app.logger.error(f"Error generating image: {e}")
        return "Error generating image", 500

# Add to app.py - New endpoint for caption generation
@app.route('/generate-social', methods=['POST'])
def generate_social():
    try:
        data = request.get_json()
        
        prompt = f"""Based on this news content:
        Headline: {data['tag_line']}
        Content: {data['main_content']}
        
        Generate:
        1. An engaging social media caption (max 200 characters)
        2. A set of relevant hashtags (max 15 hashtags)
        Format as JSON with "caption" and "hashtags" keys."""
        
        response = model.generate_content(prompt)
        content = response.text
        start = content.find('{')
        end = content.rfind('}') + 1
        if start >= 0 and end > start:
            return jsonify(json.loads(content[start:end]))
        
        raise ValueError("Invalid response format")
        
    except Exception as e:
        app.logger.error(f"Error generating social content: {str(e)}")
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)