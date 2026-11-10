"""Печать раскладки «Плоттер»: рендер рулона полосами (без Qt-окна) и отправка заданием через драйвер.

Лист = вся бумага: ширина рулона × (длина раскладки + верхняя кромка). Начало раскладки на бумаге — (edge, edge).
Полосный рендер нужен, потому что рулон 1118 × 3270 мм при 300 dpi — это почти 1,5 ГБ пикселей.
"""
import os

from PIL import Image

BAND_ROWS = 512
Image.MAX_IMAGE_PIXELS = None


def paper_px(layout, ppi):
    """Размер листа в пикселях (ширина, высота)."""
    w_mm, h_mm = layout.paper_size_mm()
    return round(w_mm / 25.4 * ppi), round(h_mm / 25.4 * ppi)


def load_item_image(item, ppi, pdf_render=None):
    """Картинка файла сразу нужного размера на рулоне (с учётом поворота), RGB. pdf_render(path, w_px, h_px)->PIL для PDF."""
    w_px = max(1, round(item.w / 25.4 * ppi))
    h_px = max(1, round(item.h / 25.4 * ppi))
    ext = os.path.splitext(item.path)[1].lower()
    if ext == ".pdf":
        if pdf_render is None:
            raise OSError("PDF: нет модуля отрисовки")
        im = pdf_render(item.path, w_px, h_px)
    elif ext in (".psd", ".psb"):
        from psd_tools import PSDImage
        im = PSDImage.open(item.path).composite()
    else:
        im = Image.open(item.path)
        im.draft("RGB", (w_px, h_px))              # JPEG: быстрое чтение уменьшенным
    if im.mode in ("RGBA", "LA", "P"):
        im = im.convert("RGBA")
        bg = Image.new("RGB", im.size, "white")
        bg.paste(im, mask=im.getchannel("A"))
        im = bg
    else:
        im = im.convert("RGB")
    im = im.resize((w_px, h_px), Image.LANCZOS)
    if item.rot:
        im = im.rotate(-item.rot, expand=True)       # PIL крутит против часовой, у нас по часовой
    return im


class BandRenderer:
    """Выдаёт полосы листа: render(a, b) -> RGB-картинка строк [a, b)."""

    def __init__(self, layout, ppi, pdf_render=None, mirror=False, negative=False):
        self.L, self.ppi, self.pdf_render = layout, float(ppi), pdf_render
        self.mirror, self.negative = mirror, negative
        self.W, self.H = paper_px(layout, ppi)
        self.items = []                                    # (item, x_px, y_px, w_px, h_px)
        e = layout.edge
        for it in layout.expand_copies():
            x = round((it.x + e) / 25.4 * ppi)
            y = round((it.y + e) / 25.4 * ppi)
            w = round(it.ow / 25.4 * ppi)
            h = round(it.oh / 25.4 * ppi)
            self.items.append((it, x, y, w, h))
        self._cache = {}

    def _img(self, key, it):
        im = self._cache.get(key)
        if im is None:
            im = load_item_image(it, self.ppi, self.pdf_render)
            self._cache[key] = im
        return im

    def render(self, a, b):
        band = Image.new("RGB", (self.W, b - a), "white")
        for n, (it, x, y, w, h) in enumerate(self.items):
            if y >= b or y + h <= a:
                continue
            im = self._img(n, it)
            y0 = max(a, y)
            y1 = min(b, y + h)
            part = im.crop((0, y0 - y, im.width, y1 - y))
            band.paste(part, (x, y0 - a))
            if y + h <= b:
                self._cache.pop(n, None)                    # файл закончился: освобождаем память
        if self.mirror:
            band = band.transpose(Image.FLIP_LEFT_RIGHT)
        if self.negative:
            from PIL import ImageOps
            band = ImageOps.invert(band)
        return band

    def full(self):
        """Весь лист целиком (для тестов и маленьких раскладок)."""
        return self.render(0, self.H)


def print_plotter(job_dc, renderer, band=BAND_ROWS, cancel=None, on_progress=None, transform=None):
    """job_dc — PrinterJob (уже открыт): страница рисуется полосами. transform(img)->img — цветопреобразование для полосы."""
    def fn(a, b):
        im = renderer.render(a, b)
        return transform(im) if transform else im
    return job_dc.page_banded(renderer.W, renderer.H, fn, band=band, cancel=cancel, on_progress=on_progress)
