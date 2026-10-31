"""Shared deterministic attachment rendering for web and Android."""
from io import BytesIO
from pathlib import Path
import platform
from PIL import Image, ImageOps
from pdf2image import convert_from_bytes, pdfinfo_from_bytes


def attachment_webp(uploaded):
    if uploaded.size > 20 * 1024 * 1024:
        raise ValueError('Choose a file smaller than 20 MB.')
    content = uploaded.read()
    if content.startswith(b'%PDF'):
        options = {'poppler_path': r'C:\poppler\Library\bin'} if platform.system() == 'Windows' else {}
        count = pdfinfo_from_bytes(content, timeout=20, **options)['Pages']
        if count > 8:
            raise ValueError('Use a PDF with up to 8 pages so every page remains readable in the image.')
        pages = convert_from_bytes(content, dpi=140, thread_count=1, timeout=60, **options)
    else:
        image = Image.open(BytesIO(content))
        image.load()
        pages = [ImageOps.exif_transpose(image)]
    normalized = []
    for page in pages:
        page.thumbnail((1600, 2000), Image.Resampling.LANCZOS)
        rgb = Image.new('RGB', page.size, 'white')
        rgba = page.convert('RGBA')
        rgb.paste(rgba, mask=rgba.getchannel('A'))
        normalized.append(rgb)
    canvas = Image.new('RGB', (max(p.width for p in normalized), sum(p.height for p in normalized)), 'white')
    top = 0
    for page in normalized:
        canvas.paste(page, ((canvas.width - page.width) // 2, top))
        top += page.height
    result = BytesIO()
    canvas.save(result, 'WEBP', quality=95, method=6)
    return result.getvalue(), Path(uploaded.name).stem + '.webp', canvas.size
