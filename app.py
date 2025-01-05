from flask import Flask, render_template, request, send_file
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO
import os
import logging

app = Flask(__name__)

# Configure logging
logging.basicConfig(level=logging.INFO)

# Directory setup (same as before)
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

def wrap_text(text, font, max_width):
    """Text wrapping function (same as before)"""
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

def draw_separator_line(draw, y_position, width, padding):
    """Draw a subtle separator line"""
    draw.line(
        [(padding, y_position), (width - padding, y_position)],
        fill='#8A8A8A',  # Light gray color
        width=1
    )

@app.route('/')
def index():
    return render_template('index.html')

@app.route("/health")
def health():
    app.logger.info("Health check route accessed.")
    return "OK", 200

@app.route('/generate', methods=['POST'])
def generate_image():
    try:
        # Get form data with new character limits
        tag_line = request.form.get('tag_line', '').upper()
        after_tag = request.form.get('after_tag', '')[:55]  # Limit to 55 characters
        main_content = request.form.get('main_content', '')[:300]  # Limit to 300 characters
        company_name = request.form.get('company_name', '').upper()
        side_note = request.form.get('side_note', '')[:30]
        first_caption = request.form.get('first_caption', '')
        second_caption = request.form.get('second_caption', '')
        big_question = request.form.get('big_question', '').upper()

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

        # Adjusted layout constants
        padding = 40
        max_width = 1080 - (padding * 2)
        current_y = padding + 40  # Reduced initial padding
        line_spacing = 1.1  # Slightly reduced line spacing
        section_spacing = 15  # Reduced section spacing

        # Draw tag line (right-aligned)
        wrapped_tag = wrap_text(tag_line, font_57, max_width)
        for line in wrapped_tag:
            line_width = font_57.getlength(line)
            draw.text((1080 - padding - line_width, current_y), line, font=font_57, fill='black')
            current_y += int(font_57.size * line_spacing)
        current_y += section_spacing
        draw_separator_line(draw, current_y - 5, 1080, padding)

        # Draw after tag
        wrapped_after = wrap_text(after_tag, font_37, max_width)
        for line in wrapped_after:
            draw.text((padding, current_y), line, font=font_37, fill='black')
            current_y += int(font_37.size * line_spacing)
        current_y += section_spacing
        draw_separator_line(draw, current_y - 5, 1080, padding)

        # Draw main content
        wrapped_main = wrap_text(main_content, font_31, max_width)
        for line in wrapped_main:
            draw.text((padding, current_y), line, font=font_31, fill='black')
            current_y += int(font_31.size * line_spacing)
        current_y += section_spacing
        draw_separator_line(draw, current_y - 5, 1080, padding)

        # Company name and side note section
        company_height = int(font_198.size * line_spacing)
        
        # Draw company name (left-aligned)
        draw.text((padding, current_y), company_name, font=font_198, fill='black')
        
        # Draw side note (right-aligned)
        wrapped_side = wrap_text(side_note, font_43, max_width/3)
        side_y = current_y
        for line in wrapped_side:
            line_width = font_43.getlength(line)
            draw.text((1080 - padding - line_width, side_y), line, font=font_43, fill='black')
            side_y += int(font_43.size * line_spacing)
        
        current_y += company_height + section_spacing
        draw_separator_line(draw, current_y - 5, 1080, padding)

        # Draw captions with reduced spacing
        wrapped_first = wrap_text(first_caption, font_31, max_width)
        for line in wrapped_first:
            draw.text((padding, current_y), line, font=font_31, fill='black')
            current_y += int(font_31.size * line_spacing)
        current_y += section_spacing
        draw_separator_line(draw, current_y - 5, 1080, padding)

        wrapped_second = wrap_text(second_caption, font_31, max_width)
        for line in wrapped_second:
            draw.text((padding, current_y), line, font=font_31, fill='black')
            current_y += int(font_31.size * line_spacing)
        current_y += section_spacing
        draw_separator_line(draw, current_y - 5, 1080, padding)

        # Draw big question with guaranteed space
        # Calculate remaining space
        remaining_space = 980 - current_y  # 980 to leave space for logo
        wrapped_question = wrap_text(big_question, font_57, max_width)
        question_height = len(wrapped_question) * int(font_57.size * line_spacing)
        
        # Adjust current_y if needed to ensure big question fits
        if remaining_space < question_height:
            # Redistribute space by pushing everything up
            current_y = 980 - question_height
        
        for line in wrapped_question:
            draw.text((padding, current_y), line, font=font_57, fill='black')
            current_y += int(font_57.size * line_spacing)

        # Add logo
        try:
            logo = Image.open(DEFAULT_LOGO_PATH)
            logo = logo.resize((40, 40))
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

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)