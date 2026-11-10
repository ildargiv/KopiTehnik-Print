import os
from PIL import Image, ImageChops
import plotter_layout as pl
import plotter_print as pp


def make(tmp_path):
    a = tmp_path / "a.png"
    b = tmp_path / "b.png"
    Image.new("RGB", (200, 100), (255, 0, 0)).save(a)
    im = Image.new("RGB", (100, 200), (0, 0, 255))
    im.putpixel((0, 0), (0, 255, 0))
    im.save(b)
    return str(a), str(b)


def test_sheet_size_and_bands_equal_full(tmp_path):
    a, b = make(tmp_path)
    L = pl.Layout(roll_w=200, edge=5, gap=10)
    L.add(pl.Item(a, 100, 50, 200, 100, x=0, y=0))
    L.add(pl.Item(b, 50, 100, 100, 200, x=110, y=20, rot=90))
    r = pp.BandRenderer(L, 50)                       # 50 dpi
    assert (r.W, r.H) == pp.paper_px(L, 50)
    full = r.full()
    r2 = pp.BandRenderer(L, 50)
    out = Image.new("RGB", (r2.W, r2.H))
    for y in range(0, r2.H, 17):
        out.paste(r2.render(y, min(r2.H, y + 17)), (0, y))
    assert ImageChops.difference(full, out).getbbox() is None


def test_item_position_and_color(tmp_path):
    a, _ = make(tmp_path)
    L = pl.Layout(roll_w=200, edge=5, gap=10)
    L.add(pl.Item(a, 100, 50, 200, 100, x=0, y=0))
    r = pp.BandRenderer(L, 254)                      # 10 px/мм
    im = r.full()
    assert im.getpixel((5 * 10 + 5, 5 * 10 + 5)) == (255, 0, 0)     # внутри файла, сдвиг на кромку
    assert im.getpixel((3, 3)) == (255, 255, 255)                   # кромка белая


def test_rotation_is_clockwise(tmp_path):
    _, b = make(tmp_path)
    L = pl.Layout(roll_w=300, edge=0, gap=0)
    L.add(pl.Item(b, 50, 100, 100, 200, x=0, y=0, rot=90))
    im = pp.BandRenderer(L, 254).full()
    # зелёный пиксель был в левом верхнем углу; после поворота на 90° по часовой он в правом верхнем
    assert im.getpixel((999, 0))[1] > 200


def test_length_limit():
    L = pl.Layout(roll_w=914)
    L.add(pl.Item("x", 100, 3300))
    assert L.too_long()
