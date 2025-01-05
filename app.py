from flask import Flask, render_template, request, send_file
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO
import os
import textwrap

app = Flask(__name__)

FONTS_DIR = os.path.join(app.root_path, 'static', 'fonts')
os.makedirs(FONTS_DIR, exist_ok=True)
ROBOTO_PATH = os.path.join(FONTS_DIR, 'Roboto-Regular.ttf')

def wrap_text(text, font, max_width):
    """Wrap text to fit within a given width."""
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
            if current_width + word_width <= max_width:
                current_line.append(word)
                current_width += word_width
            else:
                if current_line:
                    lines.append(' '.join(current_line))
                current_line = [word]
                current_width = word_width

        if current_line:
            lines.append(' '.join(current_line))

    return lines

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/generate', methods=['POST'])
def generate_image():
    # Get form data
    tag_line = request.form.get('tag_line', '')
    after_tag = request.form.get('after_tag', '')
    main_content = request.form.get('main_content', '')
    company_name = request.form.get('company_name', '')
    side_note = request.form.get('side_note', '')[:30]  # Limit to 30 characters
    first_caption = request.form.get('first_caption', '')
    second_caption = request.form.get('second_caption', '')
    big_question = request.form.get('big_question', '')

    # Create image
    img = Image.new('RGB', (1080, 1080), '#A4A5A6')
    draw = ImageDraw.Draw(img)

    # Load fonts
    try:
        font_43 = ImageFont.truetype(ROBOTO_PATH, 43)
        font_23 = ImageFont.truetype(ROBOTO_PATH, 23)
        font_17 = ImageFont.truetype(ROBOTO_PATH, 17)
        font_184 = ImageFont.truetype(ROBOTO_PATH, 184)
        font_29 = ImageFont.truetype(ROBOTO_PATH, 29)
        font_6 = ImageFont.truetype(ROBOTO_PATH, 6)
    except Exception as e:
        return str(e), 500

    # Constants for layout
    padding = 40
    max_width = 1080 - (padding * 2)
    current_y = padding
    line_spacing = 1.2

    # Draw tag line with wrapping (right-aligned)
    wrapped_tag = wrap_text(tag_line, font_43, max_width)
    for line in wrapped_tag:
        line_width = font_43.getlength(line)
        draw.text((1080 - padding - line_width, current_y), line, font=font_43, fill='black')
        current_y += int(font_43.size * line_spacing)
    current_y += 20

    # Draw after tag with wrapping
    wrapped_after = wrap_text(after_tag, font_23, max_width)
    for line in wrapped_after:
        draw.text((padding, current_y), line, font=font_23, fill='black')
        current_y += int(font_23.size * line_spacing)
    current_y += 20

    # Draw main content with wrapping
    wrapped_main = wrap_text(main_content, font_17, max_width)
    for line in wrapped_main:
        draw.text((padding, current_y), line, font=font_17, fill='black')
        current_y += int(font_17.size * line_spacing)
    current_y += 50  # Additional spacing before company name

    # Draw company name (left)
    company_width = font_184.getlength(company_name)
    if company_width > max_width/2:
        company_name = textwrap.shorten(company_name, width=20, placeholder='...')
    
    draw.text((padding, current_y), company_name, font=font_184, fill='black')
    
    # Calculate company name height
    company_height = int(font_184.size * line_spacing)
    
    # Side note with wrapping (right-aligned)
    # Position side note to not overlap with company name
    side_y = current_y + company_height + 20  # Add extra spacing
    wrapped_side = wrap_text(side_note, font_29, max_width/2)
    for line in wrapped_side:
        line_width = font_29.getlength(line)
        draw.text((1080 - padding - line_width, side_y), line, font=font_29, fill='black')
        side_y += int(font_29.size * line_spacing)
    
    # Update current_y to be well below both company name and side note
    current_y = side_y + 100  # Add extra spacing

    # Draw captions with wrapping
    wrapped_first = wrap_text(first_caption, font_17, max_width)
    for line in wrapped_first:
        draw.text((padding, current_y), line, font=font_17, fill='black')
        current_y += int(font_17.size * line_spacing)
    current_y += 20  # Additional spacing between captions

    wrapped_second = wrap_text(second_caption, font_17, max_width)
    for line in wrapped_second:
        draw.text((padding, current_y), line, font=font_17, fill='black')
        current_y += int(font_17.size * line_spacing)
    current_y += 30  # Additional spacing before big question

    # Draw big question with wrapping
    if current_y < 900:
        wrapped_question = wrap_text(big_question, font_43, max_width)
        for line in wrapped_question:
            draw.text((padding, current_y), line, font=font_43, fill='black')
            current_y += int(font_43.size * line_spacing)

    # Add small logo in bottom right corner
    logo_text = "PRESET"
    logo_width = font_6.getlength(logo_text)
    draw.text((1080 - padding - logo_width, 1080 - padding), logo_text, font=font_6, fill='black')

    # Save image
    img_io = BytesIO()
    img.save(img_io, 'PNG')
    img_io.seek(0)
    
    return send_file(img_io, mimetype='image/png')

if __name__ == '__main__':
    app.run(debug=True)