from flask import Flask, render_template, request, send_file
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO
import os
import logging

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

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)