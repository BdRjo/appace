"""
Arabic PDF helper — ReportLab + arabic_reshaper + python-bidi
Renders Arabic text correctly (right-to-left, connected letters).
"""
import os

FONT_PATH      = os.path.join(os.path.dirname(__file__), '..', 'static', 'fonts', 'ArabicFont.ttf')
FONT_BOLD_PATH = os.path.join(os.path.dirname(__file__), '..', 'static', 'fonts', 'ArabicFontBold.ttf')

_registered = False

def register_arabic_font():
    global _registered
    if _registered:
        return True
    try:
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        if os.path.exists(FONT_PATH):
            pdfmetrics.registerFont(TTFont('ArabicFont', FONT_PATH))
        if os.path.exists(FONT_BOLD_PATH):
            pdfmetrics.registerFont(TTFont('ArabicFontBold', FONT_BOLD_PATH))
        _registered = True
        return True
    except Exception:
        return False

def ar(text):
    """
    Reshape + bidi Arabic text for correct ReportLab rendering.
    arabic_reshaper connects letters; bidi reverses for LTR engine.
    """
    if not text:
        return ''
    text = str(text)
    try:
        import arabic_reshaper
        from bidi.algorithm import get_display
        reshaped = arabic_reshaper.reshape(text)
        return get_display(reshaped)
    except ImportError:
        # Fallback: reverse words (better than nothing)
        words = text.split()
        return ' '.join(reversed(words))

def ar_cell(text):
    """
    For table cells — same as ar() but handles None gracefully.
    """
    if text is None:
        return '—'
    return ar(str(text))

def arabic_font(bold=False):
    reg = register_arabic_font()
    if reg:
        return 'ArabicFontBold' if (bold and os.path.exists(FONT_BOLD_PATH)) else 'ArabicFont'
    return 'Helvetica-Bold' if bold else 'Helvetica'
