"""Эталонные тесты: цвет (ICC, ΔE в Lab), раскладка листа, сохранение и загрузка проекта.
Профили берутся из системной папки Windows; нет профиля на этом ПК — соответствующий тест пропускается."""
import json
import math
import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageCms

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import color_tools as ct
import photo_crop as pc

ICC_DIR = Path(r"C:\Windows\System32\spool\drivers\color")
PATCHES = [(0, 0, 0), (255, 255, 255), (128, 128, 128), (255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 0),
           (0, 255, 255), (255, 0, 255), (200, 120, 90), (90, 140, 200), (60, 60, 60)]
NEUTRAL_AND_SKIN = [2, 9, 10, 11]                 # серый, кожа, небо, тёмно-серый: внутри охвата любого принтера
EPSON = ("EPSON L1800 Series Photo Glossy.icc", "EPSON ET-18100 L18050 Series Photo Glossy.icc")


def need_icc(*names):
    for n in names:
        if (ICC_DIR / n).is_file():
            return ICC_DIR / n
    pytest.skip("нет ICC-профиля на этом ПК: " + " / ".join(names))


def lab(rgb):
    """sRGB (0..255) -> CIE Lab (D65), независимо от lcms."""
    a = np.asarray(rgb, dtype=float) / 255
    a = np.where(a <= 0.04045, a / 12.92, ((a + 0.055) / 1.055) ** 2.4)
    m = np.array([[0.4124564, 0.3575761, 0.1804375], [0.2126729, 0.7151522, 0.0721750], [0.0193339, 0.1191920, 0.9503041]])
    xyz = a @ m.T / np.array([0.95047, 1.0, 1.08883])
    f = np.where(xyz > 216 / 24389, np.cbrt(xyz), (24389 / 27 * xyz + 16) / 116)
    return np.stack([116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]), 200 * (f[..., 1] - f[..., 2])], -1)


def delta_e(a, b):
    return np.linalg.norm(lab(a) - lab(b), axis=-1)


def patch_image(patches=PATCHES):
    im = Image.new("RGB", (len(patches), 1))
    im.putdata(patches)
    return im


def row(im):
    return np.asarray(im)[0]


def srgb_cm(flags=0):
    return {"profile": ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes(), "intent": 1, "flags": flags}


def test_delta_e_reference_values():
    assert delta_e((0, 0, 0), (0, 0, 0)) == 0
    assert delta_e((0, 0, 0), (255, 255, 255)) == pytest.approx(100, abs=0.1)
    assert lab((255, 255, 255))[0] == pytest.approx(100, abs=0.05)
    assert abs(lab((128, 128, 128))[1]) < 0.1 and lab((128, 128, 128))[0] == pytest.approx(53.6, abs=0.3)


def test_srgb_to_srgb_is_identity():
    im = patch_image()
    out = pc.apply_printer_profile(im, None, srgb_cm())
    assert np.abs(row(out).astype(int) - row(im).astype(int)).max() == 0


def test_srgb_identity_over_gradient_keeps_delta_e_tiny():
    grad = Image.new("RGB", (256, 1))
    grad.putdata([(v, 255 - v, (v * 3) % 256) for v in range(256)])
    out = pc.apply_printer_profile(grad, None, srgb_cm(pc.CMS_BPC))
    assert delta_e(row(grad), row(out)).max() < 0.5


def test_wide_gamut_profile_changes_numbers_but_round_trips():
    path = need_icc("ProPhoto.icm", "pRGB.icm")
    cm = pc.cm_build(path, "Относительный колориметрический", False, False)
    im = patch_image()
    out = pc.apply_printer_profile(im, None, cm)
    assert np.abs(row(out).astype(int) - row(im).astype(int)).max() > 20        # числа в профиле принтера другие
    back = ImageCms.profileToProfile(out, ImageCms.ImageCmsProfile(str(path)),
                                     ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")),
                                     renderingIntent=1, outputMode="RGB")
    assert delta_e(row(im), row(back)).max() < 3.0                              # обратно в sRGB: цвет тот же


def test_printer_profile_gamut_shift_in_lab():
    path = need_icc(*EPSON)
    cm = pc.cm_build(path, "Относительный колориметрический", True, False)
    im = patch_image()
    proof = pc.proof_preview(im, None, cm)
    de = delta_e(row(im), row(proof))
    assert all(de[i] < 3.0 for i in NEUTRAL_AND_SKIN)                           # нейтральные и телесные тона не плывут
    assert de[5] > 30 and de[4] > 30                                            # насыщенные синий и зелёный за охватом принтера
    assert row(proof)[1].tolist() == [255, 255, 255]                            # бумага остаётся белой (относит. колориметрия)


def test_gamut_preview_flags_out_of_gamut_pixels():
    path = need_icc(*EPSON)
    cm = pc.cm_build(path, "Относительный колориметрический", True, False)
    _, pct_gray = pc.gamut_preview(Image.new("RGB", (16, 16), (128, 128, 128)), None, cm)
    _, pct_blue = pc.gamut_preview(Image.new("RGB", (16, 16), (0, 0, 255)), None, cm)
    assert pct_gray < 1 and pct_blue > 90


def test_cm_build_validates_profile():
    with pytest.raises(ValueError):
        pc.cm_build("", "Перцепционный", False, False)
    cmyk = ICC_DIR / "RSWOP.icm"
    if cmyk.is_file():
        with pytest.raises(ValueError, match="RGB"):
            pc.cm_build(cmyk, "Перцепционный", False, False)


def test_cmyk_conversion_with_and_without_profile():
    cmyk = Image.new("CMYK", (2, 1))
    cmyk.putdata([(0, 0, 0, 0), (0, 0, 0, 255)])
    plain = pc.to_rgb(cmyk)
    assert plain.mode == "RGB" and row(plain)[0].tolist() == [255, 255, 255] and sum(row(plain)[1]) < 30
    icc = need_icc("RSWOP.icm").read_bytes()
    out = row(pc.to_rgb(cmyk, icc))
    assert delta_e(out[0], (255, 255, 255)) < 3                                 # чистая бумага
    assert out[1].max() < 70                                                    # 100 % чёрный в SWOP: тёмный
    cyan = Image.new("CMYK", (1, 1), (255, 0, 0, 0))
    r, g, b = row(pc.to_rgb(cyan, icc))[0]
    assert b > r + 80 and g > r + 40                                            # циан остаётся сине-зелёным, а не серым


def test_color_tools_neutral_is_identity():
    im = patch_image()
    assert (np.asarray(ct.selective_color(im, ())) == np.asarray(im)).all()
    assert list(ct.levels_lut((0.0, 1.0, 255.0, 0.0, 255.0))) == list(range(256))
    assert list(ct.curve_lut([(0, 0), (255, 255)])) == list(range(256))


# ---------------------------------------------------------------- раскладка листа

def opts(**kw):
    r = dict(pc.PRINT_DEFAULTS)
    r.update(kw)
    return pc.parse_print_opts(r)


def photos(fmt, n=1, W=2000, H=3000):
    return [{"path": "p%d.jpg" % i, "st": pc.CropState(), "paper": pc.paper_size(pc.FORMATS[fmt], None, W, H), "copies": 1}
            for i in range(n)]


def plan(fmt, sheet, n=1, W=2000, H=3000, **kw):
    o = opts(**kw)
    ph = photos(fmt, n, W, H)
    for p in ph:
        p["copies"] = o["copies"]                                                # как build_photos: копии в кадре = копии из настроек
    return pc.plan_layout(ph, lambda ori: pc.virtual_geometry(sheet[0], sheet[1], ori), o), o


def gap_between(a, b):
    dx = max(b["x"] - (a["x"] + a["w"]), a["x"] - (b["x"] + b["w"]))
    dy = max(b["y"] - (a["y"] + a["h"]), a["y"] - (b["y"] + b["h"]))
    return max(dx, dy)


def assert_valid_sheet(sheet, area, gap, dims, eps=1e-6):
    x0, y0, x1, y1 = area
    for c in sheet:
        assert x0 - eps <= c["x"] and y0 - eps <= c["y"] and c["x"] + c["w"] <= x1 + eps and c["y"] + c["h"] <= y1 + eps
        if dims:
            assert sorted((round(c["w"], 3), round(c["h"], 3))) == sorted(dims)      # размер кадра = формат (возможно, повёрнут)
    for i, a in enumerate(sheet):
        for b in sheet[i + 1:]:
            assert gap_between(a, b) >= gap - eps, "кадры пересекаются или ближе зазора"


@pytest.mark.parametrize("fmt,count", [("10×15 см", 2), ("13×18 см", 2)])
def test_fill_a4_frame_count_margins_and_no_overlap(fmt, count):
    p, o = plan(fmt, (210, 297), fill=True)
    assert len(p["sheets"]) == 1 and len(p["sheets"][0]) == count
    assert p["area"] in ((5.0, 5.0, 205.0, 292.0), (5.0, 5.0, 292.0, 205.0))     # поля 5 мм со всех сторон
    short, long_, _ = pc.FORMATS[fmt]
    assert_valid_sheet(p["sheets"][0], p["area"], o["gap"], (short, long_))
    assert not p["warnings"]


def test_a4_frame_on_a4_needs_zero_margins():
    p, _ = plan("A4 (21×29,7 см)", (210, 297))
    assert p["warnings"] and "не помещается" in p["warnings"][0]                  # поля 5 мм: кадр шире области печати
    p0, o = plan("A4 (21×29,7 см)", (210, 297), margin_l="0", margin_t="0", margin_r="0", margin_b="0")
    assert not p0["warnings"] and len(p0["sheets"][0]) == 1
    assert_valid_sheet(p0["sheets"][0], p0["area"], o["gap"], (210, 297))


def test_fill_a4_with_larger_margin_loses_frames():
    p5, _ = plan("10×15 см", (210, 297), fill=True)
    p40, _ = plan("10×15 см", (210, 297), fill=True, margin_l="40", margin_r="40", margin_t="40", margin_b="40")
    assert len(p5["sheets"][0]) == 2 and len(p40["sheets"][0]) == 1


def test_not_fill_spills_to_next_sheet_in_order():
    p, o = plan("13×18 см", (210, 297), n=3)
    assert [len(s) for s in p["sheets"]] == [2, 1]
    assert [c["photo"] for s in p["sheets"] for c in s] == [0, 1, 2]
    for s in p["sheets"]:
        assert_valid_sheet(s, p["area"], o["gap"], (127, 178))


def test_borderless_single_frame_fills_paper_exactly():
    p, _ = plan("10×15 см", (102, 152), layout="Одно фото на листе", margin_l="0", margin_t="0", margin_r="0", margin_b="0", gap="0")
    assert len(p["sheets"]) == 1 and len(p["sheets"][0]) == 1
    c = p["sheets"][0][0]
    assert (c["x"], c["y"], c["w"], c["h"], c["rot"]) == (0.0, 0.0, 102.0, 152.0, False)
    assert tuple(p["area"]) == (0, 0, 102, 152) and not p["warnings"]


def test_borderless_with_bleed_extends_beyond_paper_symmetrically():
    p, _ = plan("10×15 см", (102, 152), layout="Одно фото на листе", margin_l="0", margin_t="0", margin_r="0", margin_b="0",
                gap="0", bleed="3")
    c = p["sheets"][0][0]
    assert (c["x"], c["y"], c["w"], c["h"]) == (-3.0, -3.0, 108.0, 158.0)
    assert (c["iw"], c["ih"]) == (108.0, 158.0) and p["warnings"]               # вылет за бумагу: предупреждение про условный край


def test_single_layout_copies_make_sheets():
    p, _ = plan("A4 (21×29,7 см)", (210, 297), layout="Одно фото на листе", copies="3")
    assert len(p["sheets"]) == 3 and all(len(s) == 1 for s in p["sheets"])


def test_photo_larger_than_sheet_warns():
    p, _ = plan("A3 (29,7×42 см)", (210, 297))
    assert p["warnings"] and "не помещается" in p["warnings"][0]


def test_pack_slots_never_overlaps_for_mixed_sizes():
    sizes = [(102, 152), (127, 178), (89, 127), (152, 102), (60, 60)] * 3
    area = (5.0, 5.0, 205.0, 292.0)
    placed_any = 0
    for sheet in pc.pack_slots(sizes, area, 3.0, True):
        placed = [{"x": x, "y": y, "w": w, "h": h} for _, x, y, w, h, _ in sheet]
        placed_any += len(placed)
        assert_valid_sheet(placed, area, 3.0, None)
    assert placed_any == len(sizes)                                             # ни один кадр не потерян


# ---------------------------------------------------------------- проект: сохранение и загрузка

@pytest.fixture
def session(tmp_path, monkeypatch):
    monkeypatch.setattr(pc, "load_settings", lambda: {})

    def make(name="agent_state.json"):
        return pc.AgentSession(persist=True, state_path=tmp_path / name, log_path=tmp_path / "agent.log")
    return make


def make_photos(tmp_path, n=3):
    out = []
    for i in range(n):
        p = tmp_path / ("photo%d.jpg" % i)
        Image.new("RGB", (60 + i * 10, 40), (i * 50, 100, 150)).save(p)
        out.append(p)
    return out


def test_project_round_trip_keeps_everything(session, tmp_path):
    files = make_photos(tmp_path)
    a = session()
    a.files, a.folder = list(files), tmp_path
    a.states = {f: pc.CropState() for f in files}
    st = a.states[files[1]]
    st.cx, st.cy, st.scale, st.angle, st.rotation, st.copies, st.orient, st.edited = 0.4, 0.6, 0.7, 3.5, 90, 4, "landscape", True
    st.adj = {"bright": 12, "sat": -5}
    a.idx = 1
    a.fmt_name, a.orient_name = "13×18 см", "Альбомная"
    a.mode_name = next(m for m in pc.MODES if m != a.mode_name)
    a.save["dpi"] = 240.0
    a.cm.update(on=True, icc="x.icc", bpc=True)
    a.popts.update(margin_l="7", fill=True)
    a.printer = "Test Printer"
    data = json.loads(json.dumps(a.to_project(), default=str))                   # через JSON, как на диске
    b = session("other.json")
    b.from_project(data)
    assert b.files == a.files and b.idx == 1 and b.folder == tmp_path
    assert (b.fmt_name, b.orient_name, b.mode_name) == (a.fmt_name, a.orient_name, a.mode_name)
    for f in files:
        for k in pc.CropState.__slots__:
            assert getattr(b.states[f], k) == getattr(a.states[f], k), (f.name, k)
    assert b.save["dpi"] == 240.0 and b.cm["on"] and b.cm["icc"] == "x.icc" and b.cm["bpc"]
    assert b.popts["margin_l"] == "7" and b.popts["fill"] is True and b.printer == "Test Printer"


def test_project_file_save_and_load_state(session, tmp_path):
    files = make_photos(tmp_path, 2)
    a = session()
    a.files, a.folder = list(files), tmp_path
    a.states = {f: pc.CropState() for f in files}
    a.states[files[0]].copies = 5
    a.idx = 0
    a.save_state()
    assert a.state_path.is_file() and not a.state_path.with_name(a.state_path.name + ".tmp").exists()
    b = session()
    assert b.load_state() and b.states[files[0]].copies == 5 and b.idx == 0


def test_project_skips_missing_files_and_sanitizes_bad_values(session, tmp_path):
    files = make_photos(tmp_path, 2)
    gone = tmp_path / "gone.jpg"
    d = {"version": 1, "files": [str(files[0]), str(gone), str(files[1])], "idx": 99, "format": "нет такого", "orient": "???",
         "states": {str(files[0]): {"cx": float("nan"), "scale": "bad", "copies": 1000, "rotation": 45, "adj": "oops"}}}
    s = session()
    s.from_project(json.loads(json.dumps(d)))
    assert s.files == [files[0], files[1]] and s.idx == 1                         # idx в пределах, отсутствующий файл выпал
    assert s.fmt_name in pc.FORMATS and s.orient_name in pc.ORIENTS               # неизвестные значения не принимаются
    st = s.states[files[0]]
    assert math.isfinite(st.cx) and st.scale == 1.0 and st.copies <= 99 and st.rotation == 0 and st.adj == {}


def test_load_state_missing_or_corrupt_returns_false(session, tmp_path):
    s = session()
    assert s.load_state() is False
    s.state_path.write_text("{не json", encoding="utf-8")
    assert s.load_state() is False
