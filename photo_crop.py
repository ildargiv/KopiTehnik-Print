# -*- coding: utf-8 -*-
"""
PhotoCrop — кадрирование фотографий под форматы фотопечати (10×15, A5, A4 и др.)

Возможности:
  * загрузка целой папки (по желанию — с подпапками);
  * рамка кадрирования с жёстко заданными пропорциями формата печати:
      - перетаскивание — сдвиг (рамку можно вынести за край фото — там будут белые поля),
      - углы — размер,
      - кружок над рамкой — поворот на любой угол (Shift — шаг 15°),
      - колесо мыши — масштаб, Shift+колесо или клавиши [ ] — наклон на 1°,
      - двойной клик — сброс, R — книжная/альбомная;
  * индивидуальная рамка и поворот для каждого снимка;
  * режим «Вписать целиком» — фото без обрезки, с белыми полями;
  * индикатор реального разрешения печати (dpi) с цветовой подсказкой;
  * цветовой профиль принтера (ICC): преобразование при сохранении и имитация печати на экране;
  * печать на принтер Windows: несколько фото на листе, копии, метки реза, подписи, настройки драйвера;
  * управление ИИ-агентом без окна: `photo_crop.py agent …`, `agent --serve`, `mcp` (см. AGENT.md);
  * пакетное сохранение: пересчёт до точного размера при заданном DPI,
    JPEG/PNG/TIFF, сохранение EXIF и цветового профиля.

Запуск:  python photo_crop.py      (нужен Python 3.8+ и Pillow: pip install pillow)
"""
import base64
import hashlib
import ctypes
import io
import json
import math
import os
import queue
import re
import shutil
import struct
import sys
import tempfile
import threading
import time
from pathlib import Path

try:
    import tkinter as tk
    from tkinter import ttk, filedialog, messagebox, simpledialog
except Exception:                 # нет Tk (например, режим агента на сервере) — окно не понадобится
    tk = ttk = filedialog = messagebox = simpledialog = None
_RAW_MESSAGEBOX = messagebox

try:
    from PIL import Image, ImageOps, ImageCms, ImageDraw, ImageFont, ImageEnhance, ImageFilter, ImageChops
except ImportError:
    if tk is not None and not (len(sys.argv) > 1 and sys.argv[1] in ("agent", "mcp")):
        _r = tk.Tk()
        _r.withdraw()
        messagebox.showerror("PhotoCrop", "Не установлена библиотека Pillow.\n\nВыполните в командной строке:\n    pip install pillow")
    else:
        sys.stderr.write("PhotoCrop: не установлена библиотека Pillow (pip install pillow)\n")
    sys.exit(1)
try:
    from PIL import ImageTk
except Exception:
    ImageTk = None

Image.MAX_IMAGE_PIXELS = 400_000_000      # ~400 Мпикс: выше — предупреждение Pillow, от 800 Мпикс — отказ (защита от «бомб» и нехватки памяти)
_RS = getattr(Image, "Resampling", Image)
RESAMPLE_HQ = _RS.LANCZOS
RESAMPLE_FAST = _RS.BILINEAR
RESAMPLE_CUBIC = _RS.BICUBIC
AFFINE = getattr(Image, "Transform", Image).AFFINE

# Форматы печати: название -> (короткая сторона мм, длинная сторона мм, метка для имени файла).
# Чтобы добавить свой формат, просто допишите строку.
FORMATS = {
    "10×15 см": (102, 152, "10x15"),
    "A5 (14,8×21 см)": (148, 210, "A5"),
    "A4 (21×29,7 см)": (210, 297, "A4"),
    "9×13 см": (89, 127, "9x13"),
    "13×18 см": (127, 178, "13x18"),
    "15×21 см": (152, 216, "15x21"),
    "20×30 см": (203, 305, "20x30"),
    "30×40 см": (305, 406, "30x40"),
    "A3 (29,7×42 см)": (297, 420, "A3"),
    "A3+ (32,9×48,3 см)": (329, 483, "A3plus"),
    "A2 (42×59,4 см)": (420, 594, "A2"),
}
ORIENTS = {"Авто (по фото)": None, "Книжная": "portrait", "Альбомная": "landscape"}
MODES = {"Кадрировать (заполнить лист)": "crop", "Вписать целиком (белые поля)": "fit"}
FILETYPES = {"JPEG": ".jpg", "PNG": ".png", "TIFF": ".tif"}
EXTS = {".jpg", ".jpeg", ".jpe", ".png", ".tif", ".tiff", ".bmp", ".webp"}
try:                                  # снимки с iPhone (HEIC/HEIF): нужна библиотека pillow-heif
    import pillow_heif
    pillow_heif.register_heif_opener()
    EXTS |= {".heic", ".heif"}
    HEIC_OK = True
except Exception:
    HEIC_OK = False
PREVIEW_MAX = 2000
WHEEL_STEP = 1.01   # один щелчок колеса = 1 % размера рамки (Shift+колесо — наклон)
# способы цветопреобразования (числа littlecms): имя -> intent
INTENTS = {"Относительный колориметрический": 1, "Перцепционный": 0,
           "Насыщенность": 2, "Абсолютный колориметрический": 3}
CMS_BPC, CMS_SOFTPROOF, CMS_GAMUTCHECK = 0x2000, 0x4000, 0x1000   # компенсация точки чёрного / имитация печати
UNDO_LIMIT = 500   # шагов отмены
MIN_SCALE, MAX_SCALE = 0.05, 3.0   # размер рамки относительно максимально вписанной в фото

SETTINGS_PATH = Path(os.environ.get("APPDATA", str(Path.home()))) / "PhotoCrop" / "settings.json"


# ---------------------------------------------------------------- логика

class CropState:
    """Положение рамки для одного снимка (в долях, не зависит от формата)."""
    __slots__ = ("cx", "cy", "scale", "angle", "orient", "rotation", "edited", "copies", "adj")

    def __init__(self):
        self.cx = 0.5        # центр рамки, доля ширины
        self.cy = 0.5        # центр рамки, доля высоты
        self.scale = 1.0     # размер рамки относительно максимально вписанной
        self.angle = 0.0     # наклон рамки по часовой стрелке, градусы
        self.orient = None   # None = как выбрано глобально; "portrait" / "landscape"
        self.rotation = 0    # поворот самого фото по часовой: 0/90/180/270
        self.edited = False
        self.copies = 1      # сколько копий печатать
        self.adj = {}        # индивидуальная коррекция снимка (bright, contrast, sat, gamma, bw, sharp…)

    def copy(self):
        c = CropState()
        for k in self.__slots__:
            setattr(c, k, getattr(self, k))
        c.adj = dict(self.adj)
        return c


def paper_size(fmt, orient, W, H):
    """Размер листа (ширина, высота) в мм с учётом ориентации."""
    short, long_, _ = fmt
    portrait = (H >= W) if orient is None else (orient == "portrait")
    return (short, long_) if portrait else (long_, short)


def rot(vx, vy, deg):
    """Поворот вектора на угол по часовой стрелке (ось Y направлена вниз, как на экране)."""
    a = math.radians(deg)
    c, s = math.cos(a), math.sin(a)
    return vx * c - vy * s, vx * s + vy * c


def frame_geom(W, H, paper, st):
    """Рамка: (центр x, центр y, ширина, высота, угол) в пикселях изображения."""
    r = paper[0] / paper[1]
    maxw = min(W, H * r)
    w = max(1.0, maxw * st.scale)
    return st.cx * W, st.cy * H, w, w / r, st.angle


def snap_move(W, H, g, thr):
    """Прилипание рамки к краям и центру снимка. g = (cx, cy, w, h, ang); thr — порог в пикселях снимка.
    Возвращает (dx, dy, направляющие [("v", x) | ("h", y)])."""
    pts = frame_corners(*g)
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    res, guides = [0.0, 0.0], []
    for axis, vals, size, centre in ((0, (min(xs), max(xs)), W, g[0]), (1, (min(ys), max(ys)), H, g[1])):
        best = None
        for v, target in ((vals[0], 0.0), (vals[1], float(size)), (centre, size / 2.0)):
            d = target - v
            if abs(d) <= thr and (best is None or abs(d) < abs(best[0])):
                best = (d, target)
        if best:
            res[axis] = best[0]
            guides.append(("v" if axis == 0 else "h", best[1]))
    return res[0], res[1], guides


def frame_corners(cx, cy, w, h, ang):
    """Углы рамки по порядку: левый-верхний, правый-верхний, правый-нижний, левый-нижний."""
    pts = []
    for lx, ly in ((-w / 2, -h / 2), (w / 2, -h / 2), (w / 2, h / 2), (-w / 2, h / 2)):
        dx, dy = rot(lx, ly, ang)
        pts.append((cx + dx, cy + dy))
    return pts


def frame_inside(W, H, g):
    return all(-0.5 <= x <= W + 0.5 and -0.5 <= y <= H + 0.5 for x, y in frame_corners(*g))


def point_in_frame(g, x, y):
    cx, cy, w, h, ang = g
    lx, ly = rot(x - cx, y - cy, -ang)
    return abs(lx) <= w / 2 and abs(ly) <= h / 2


def normalize(st):
    """Рамка может выходить за фото, но центр остаётся на снимке."""
    st.scale = min(MAX_SCALE, max(MIN_SCALE, st.scale))
    st.cx = min(1.0, max(0.0, st.cx))
    st.cy = min(1.0, max(0.0, st.cy))
    st.angle = ((st.angle + 180.0) % 360.0) - 180.0


def _sanitize_state(st):
    """Состояние из файла проекта/автосохранения может быть повреждено: приводим к допустимому."""
    try:
        for k in ("cx", "cy", "scale", "angle"):
            v = float(getattr(st, k))
            setattr(st, k, v if math.isfinite(v) else (1.0 if k == "scale" else 0.0 if k == "angle" else 0.5))
        st.copies = max(1, min(99, int(st.copies)))
        st.rotation = int(st.rotation) % 360 if int(st.rotation) % 90 == 0 else 0
        st.adj = clean_adj(st.adj if isinstance(st.adj, dict) else {})
        st.edited = bool(st.edited)
        normalize(st)
    except Exception:
        for k, v in zip(("cx", "cy", "scale", "angle", "copies", "rotation"), (0.5, 0.5, 1.0, 0.0, 1, 0)):
            setattr(st, k, v)
        st.adj = {}


def angle_from_mouse(cx, cy, mx, my, snap_step=None):
    """Угол рамки, при котором ручка поворота (над верхним краем) смотрит на курсор."""
    a = math.degrees(math.atan2(mx - cx, -(my - cy)))
    if snap_step:
        a = round(a / snap_step) * snap_step
    elif abs(a) < 1.5:
        a = 0.0
    return a


def frame_resize_center(center, mouse, ang, r, maxw):
    """Размер рамки при перетаскивании за угол: центр остаётся на месте. Возвращает scale."""
    lx, ly = rot(mouse[0] - center[0], mouse[1] - center[1], -ang)
    w = max(abs(lx) * 2, abs(ly) * 2 * r)
    w = min(max(w, maxw * MIN_SCALE), maxw * MAX_SCALE)
    return w / maxw


def frame_resize_edge(anchor, edge, mouse, ang, r, maxw):
    """Размер рамки при перетаскивании за середину стороны: противоположная сторона неподвижна,
    рамка растёт в ту сторону, куда тянут. edge: 'n','e','s','w'. Возвращает (cx, cy, scale)."""
    lx, ly = rot(mouse[0] - anchor[0], mouse[1] - anchor[1], -ang)
    if edge in ("e", "w"):
        sgn = 1 if edge == "e" else -1
        w = lx * sgn
    else:
        sgn = 1 if edge == "s" else -1
        w = ly * sgn * r
    w = min(max(w, maxw * MIN_SCALE), maxw * MAX_SCALE)
    h = w / r
    dx, dy = rot(sgn * w / 2, 0, ang) if edge in ("e", "w") else rot(0, sgn * h / 2, ang)
    return anchor[0] + dx, anchor[1] + dy, w / maxw


def effective_dpi(W, H, paper, st, mode):
    if mode == "fit":
        return min(W / (paper[0] / 25.4), H / (paper[1] / 25.4))
    _, _, w, _, _ = frame_geom(W, H, paper, st)
    return w / (paper[0] / 25.4)


def low_res_list(jobs, o, thr=150.0):
    """Фото, у которых при выбранном кадре и формате получится меньше thr dpi: [(имя, dpi)] от худшего."""
    bad = []
    for f, st in jobs:
        try:
            W, H = true_size(f, st.rotation)
            paper = paper_size(o["fmt"], st.orient if st.orient else o["orient"], W, H)
            d = effective_dpi(W, H, paper, st, o["mode"])
            if d < thr:
                bad.append((Path(f).name, round(d)))
        except Exception:
            continue
    return sorted(bad, key=lambda t: t[1])


def cmyk_to_srgb(img, icc):
    """CMYK-снимок со встроенным CMYK-профилем -> sRGB (иначе цвета тусклые и с синим оттенком)."""
    if icc:
        try:
            src = ImageCms.ImageCmsProfile(io.BytesIO(icc))
            if src.profile.xcolor_space.strip() == "CMYK":
                return ImageCms.profileToProfile(img, src, _srgb(), renderingIntent=1, outputMode="RGB", flags=CMS_BPC)
        except Exception:
            pass
    return img.convert("RGB")


def to_rgb(img, icc=None):
    """В RGB. Для CMYK со встроенным профилем нужно передать icc: результат — уже sRGB."""
    if img.mode == "RGB":
        return img
    if img.mode == "CMYK":
        return cmyk_to_srgb(img, icc)
    if img.mode == "F":                              # вещественный TIFF: 0..1 или 0..max
        hi = img.getextrema()[1]
        k = 255.0 if hi <= 1.0 else (255.0 / hi if hi > 255 else 1.0)
        return img.point(lambda v: v * k).convert("L").convert("RGB")
    if img.mode == "PA":
        img = img.convert("RGBA")
    if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
        img = img.convert("RGBA")
        bg = Image.new("RGB", img.size, "white")
        bg.paste(img, mask=img.split()[-1])
        return bg
    if img.mode in ("I", "I;16", "I;16B", "I;16L"):
        img = img.convert("I").point(lambda v: v * (1 / 256)).convert("L")
    return img.convert("RGB")


_SIZE_CACHE = {}


def true_size(path, rotation):
    """Реальные размеры снимка с учётом EXIF-ориентации и поворота, без полной загрузки (результат кэшируется)."""
    try:
        stt = os.stat(path)
        key = (str(path), rotation, stt.st_mtime_ns, stt.st_size)
    except OSError:
        key = None
    if key is not None and key in _SIZE_CACHE:
        return _SIZE_CACHE[key]
    r = _true_size(path, rotation)
    if key is not None:
        if len(_SIZE_CACHE) > 20000:
            _SIZE_CACHE.clear()
        _SIZE_CACHE[key] = r
    return r


def _true_size(path, rotation):
    with Image.open(path) as im:
        W, H = im.size
        try:
            o = im.getexif().get(0x0112, 1)
        except Exception:
            o = 1
    if o in (5, 6, 7, 8):
        W, H = H, W
    if rotation in (90, 270):
        W, H = H, W
    return W, H


def load_preview(path, rotation):
    with Image.open(path) as im:
        im.draft("RGB", (PREVIEW_MAX, PREVIEW_MAX))  # быстрое уменьшение JPEG
        icc = im.info.get("icc_profile")
        was_cmyk = im.mode == "CMYK"
        im = ImageOps.exif_transpose(im)
        if rotation:
            im = im.rotate(-rotation, expand=True)
        im = to_rgb(im, icc)
        if was_cmyk:
            icc = None                                # после конвертации это уже sRGB
        im.thumbnail((PREVIEW_MAX, PREVIEW_MAX), RESAMPLE_FAST)
        return im, icc


# ---- цветовые профили

def _rgb_profile(icc):
    """Встроенный в фото RGB-профиль или None."""
    if icc:
        try:
            p = ImageCms.ImageCmsProfile(io.BytesIO(icc))
            if p.profile.xcolor_space.strip() == "RGB":
                return p
        except Exception:
            pass
    return None


def _srgb():
    return ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB"))


def profile_info(path):
    """(описание, цветовое пространство, список поддерживаемых способов рендеринга)."""
    prof = ImageCms.ImageCmsProfile(str(path))
    space = prof.profile.xcolor_space.strip()
    desc = (ImageCms.getProfileDescription(prof) or "").strip() or Path(path).name
    ok = [n for n, i in INTENTS.items() if ImageCms.isIntentSupported(prof, i, 1) == 1]
    return desc, space, ok


def cm_build(path, intent_name, bpc, embed):
    """Параметры цветопреобразования. ValueError с понятным текстом при ошибке."""
    path = str(path or "").strip()
    if not path or not Path(path).is_file():
        raise ValueError("Укажите файл цветового профиля принтера (.icc / .icm).")
    try:
        desc, space, ok = profile_info(path)
        data = Path(path).read_bytes()
    except Exception:
        raise ValueError("Не удалось прочитать файл профиля. Проверьте, что это ICC-профиль.")
    if space != "RGB":
        raise ValueError(f"Нужен RGB-профиль принтера (в файле: {space}).")
    if intent_name not in ok:
        raise ValueError(f"Профиль не поддерживает способ «{intent_name}».\nДоступно: " + ", ".join(ok))
    return {"profile": data, "intent": INTENTS[intent_name], "flags": CMS_BPC if bpc else 0,
            "embed": bool(embed), "name": desc}


_xform_cache = {}


def apply_printer_profile(img, src_icc, cm):
    """Преобразует цвета фото (встроенный профиль или sRGB) в пространство профиля принтера.
    Преобразование строится один раз и переиспользуется (для LUT-профилей принтера построение занимает секунды —
    при многих листах это заметно)."""
    key = (hash(cm["profile"]), hash(src_icc) if src_icc else 0, cm["intent"], cm["flags"])
    t = _xform_cache.get(key)
    if t is None:
        src = _rgb_profile(src_icc) or _srgb()
        dst = ImageCms.ImageCmsProfile(io.BytesIO(cm["profile"]))
        t = ImageCms.buildTransform(src, dst, "RGB", "RGB", renderingIntent=cm["intent"], flags=cm["flags"])
        if len(_xform_cache) > 8:
            _xform_cache.clear()
        _xform_cache[key] = t
    return ImageCms.applyTransform(img if img.mode == "RGB" else img.convert("RGB"), t)


_disp_profile = None
_proof_cache = {}


def _display_profile():
    global _disp_profile
    if _disp_profile is None:
        try:
            _disp_profile = ImageCms.get_display_profile()
        except Exception:
            _disp_profile = None
        if _disp_profile is None:
            _disp_profile = _srgb()
    return _disp_profile


def proof_preview(img, src_icc, cm):
    """Имитация печати: как фото будет выглядеть на бумаге с этим профилем (для экрана)."""
    key = (hash(cm["profile"]), hash(src_icc) if src_icc else 0, cm["intent"], cm["flags"] & CMS_BPC)
    t = _proof_cache.get(key)
    if t is None:
        prn = ImageCms.ImageCmsProfile(io.BytesIO(cm["profile"]))
        t = ImageCms.buildProofTransform(_rgb_profile(src_icc) or _srgb(), _display_profile(), prn,
                                         "RGB", "RGB", 1, cm["intent"], CMS_SOFTPROOF | (cm["flags"] & CMS_BPC))
        if len(_proof_cache) > 8:
            _proof_cache.clear()
        _proof_cache[key] = t
    return ImageCms.applyTransform(img, t)


def gamut_preview(img, src_icc, cm):
    """Имитация печати + подсветка цветов, которые принтер на этой бумаге не передаст (проверка lcms).
    Возвращает (картинка, доля пикселей вне охвата в процентах)."""
    key = ("gamut", hash(cm["profile"]), hash(src_icc) if src_icc else 0, cm["intent"], cm["flags"] & CMS_BPC)
    t = _proof_cache.get(key)
    if t is None:
        prn = ImageCms.ImageCmsProfile(io.BytesIO(cm["profile"]))
        t = ImageCms.buildProofTransform(_rgb_profile(src_icc) or _srgb(), _display_profile(), prn, "RGB", "RGB", 1, cm["intent"],
                                         CMS_SOFTPROOF | CMS_GAMUTCHECK | (cm["flags"] & CMS_BPC))
        if len(_proof_cache) > 8:
            _proof_cache.clear()
        _proof_cache[key] = t
    proof = proof_preview(img, src_icc, cm)
    chk = ImageCms.applyTransform(img, t)

    def grey127(im):                              # lcms красит «вне охвата» в серый (127,127,127)
        m = [c.point([255 if v == 127 else 0 for v in range(256)]) for c in im.split()]
        return ImageChops.multiply(ImageChops.multiply(m[0], m[1]), m[2])
    mask = ImageChops.subtract(grey127(chk), grey127(proof))   # серые пиксели самого фото не считаем
    h = mask.histogram()
    pct = h[255] / float(max(1, img.width * img.height)) * 100
    if h[255]:
        proof = Image.composite(Image.new("RGB", proof.size, (255, 0, 255)), proof, mask)
    return proof, pct


def render_frame(img, g, tw=None, th=None):
    """Вырезает рамку g (возможно повёрнутую и выходящую за фото) в картинку tw×th.
    Всё, что вне фото, заливается белым. Если tw/th не заданы — берётся натуральный размер рамки."""
    cx, cy, w, h, ang = g
    W, H = img.size
    if abs(ang) < 1e-6 and frame_inside(W, H, g):
        x0, y0 = cx - w / 2, cy - h / 2
        out = img.crop((round(x0), round(y0), round(x0 + w), round(y0 + h)))
        if tw is not None and out.size != (tw, th):
            out = out.resize((tw, th), RESAMPLE_HQ)
        return out

    if tw is None:
        tw, th = max(1, round(w)), max(1, round(h))
    f = int(w / tw)
    if f >= 2:  # сильное уменьшение: сначала усредняем, чтобы не было «лесенки»
        pts = frame_corners(cx, cy, w, h, ang)
        pad = 2 * f + 4
        bx0 = max(0, int(min(p[0] for p in pts)) - pad)
        by0 = max(0, int(min(p[1] for p in pts)) - pad)
        bx1 = min(W, int(max(p[0] for p in pts)) + pad + 1)
        by1 = min(H, int(max(p[1] for p in pts)) + pad + 1)
        if bx1 > bx0 and by1 > by0:
            img = img.crop((bx0, by0, bx1, by1)).reduce(f)
            cx, cy, w, h = (cx - bx0) / f, (cy - by0) / f, w / f, h / f
    a = math.radians(ang)
    c, s = math.cos(a), math.sin(a)
    kx, ky = w / tw, h / th
    A, B, D, E = kx * c, -ky * s, kx * s, ky * c
    C = cx - (A * tw / 2 + B * th / 2)
    F = cy - (D * tw / 2 + E * th / 2)
    return img.transform((tw, th), AFFINE, (A, B, C, D, E, F), resample=RESAMPLE_CUBIC,
                         fillcolor=(255, 255, 255))


def render(img, paper, st, mode, dpi, resize):
    """Готовое изображение для печати и его DPI."""
    W, H = img.size
    pw, ph = paper
    if mode == "fit" and not resize:                 # без пересчёта: снимок как есть на белом поле нужной формы
        r = pw / ph
        cw, ch = (W, max(H, round(W / r))) if W / H >= r else (max(W, round(H * r)), H)
        out = Image.new("RGB", (cw, ch), "white")
        out.paste(img, ((cw - W) // 2, (ch - H) // 2))
        return out, cw / (pw / 25.4)
    if mode == "fit":
        tw, th = round(pw / 25.4 * dpi), round(ph / 25.4 * dpi)
        k = min(tw / W, th / H)
        nw, nh = max(1, round(W * k)), max(1, round(H * k))
        pic = img.resize((nw, nh), RESAMPLE_HQ)
        out = Image.new("RGB", (tw, th), "white")
        out.paste(pic, ((tw - nw) // 2, (th - nh) // 2))
        return out, dpi
    g = frame_geom(W, H, paper, st)
    if resize:
        tw, th = round(pw / 25.4 * dpi), round(ph / 25.4 * dpi)
        return render_frame(img, g, tw, th), dpi
    out = render_frame(img, g)
    return out, out.width / (pw / 25.4)


ADJ_KEYS = ("bright", "contrast", "gamma", "shadows", "highlights", "sat", "vib", "temp", "tint", "r", "g", "b",
            "auto", "bw", "sepia", "denoise", "sharp", "sharp_radius", "sharp_thr")
NEUTRAL_ADJ = {"bright": 0.0, "contrast": 0.0, "gamma": 1.0, "shadows": 0.0, "highlights": 0.0,
               "sat": 0.0, "vib": 0.0, "temp": 0.0, "tint": 0.0, "r": 0.0, "g": 0.0, "b": 0.0,
               "auto": "", "bw": False, "sepia": False, "denoise": 0.0,
               "sharp": 0.0, "sharp_radius": 1.0, "sharp_thr": 2}
ADJ_LIMITS = {"bright": (-100, 100), "contrast": (-100, 100), "gamma": (0.2, 5), "shadows": (-100, 100),
              "highlights": (-100, 100), "sat": (-100, 100), "vib": (-100, 100), "temp": (-100, 100),
              "tint": (-100, 100), "r": (-100, 100), "g": (-100, 100), "b": (-100, 100), "denoise": (0, 100),
              "sharp": (0, 500), "sharp_radius": (0.1, 10), "sharp_thr": (0, 255)}
AUTO_MODES = ("", "contrast", "color", "bw")


def adj_full(a):
    """Полный набор коррекции: недостающее — нейтрально."""
    r = dict(NEUTRAL_ADJ)
    for k in NEUTRAL_ADJ:
        if a.get(k) is not None:
            r[k] = a[k]
    return r


def clean_adj(a):
    """Только отличающееся от нейтрального, значения в допустимых пределах."""
    out = {}
    for k, v in a.items():
        if k not in NEUTRAL_ADJ:
            continue
        n = NEUTRAL_ADJ[k]
        if isinstance(n, bool):
            v = bool(v)
        elif k == "auto":
            v = v if v in AUTO_MODES else ""
        else:
            v = fnum(v, n, *ADJ_LIMITS[k])
            if k == "sharp_thr":
                v = int(v)
        if v != n:
            out[k] = v
    return out


MIN_AUTO_SPAN = 190      # растяжение уровней не сильнее ~1.35 раза (линейное растяжение поднимает насыщенность)


def _auto_bounds(img, mode, clip=0.001):
    """Границы растяжения гистограммы: ([lo, lo, lo], [hi, hi, hi]) по яркости или по каждому каналу.
    Режим "bw" (авто чёрно-белое): по яркости и до конца — в ч/б растяжение не «взрывает» цвет, поэтому
    узкий диапазон тоже растягивается (с тем же отсечением 0,1 %, чтобы пыль и блики не мешали)."""
    full = mode == "bw"
    if full:
        clip = 0.002

    def edges(h):
        n = sum(h) or 1
        acc, lo = 0, 0
        for i, c in enumerate(h):
            acc += c
            if acc > n * clip:
                lo = i
                break
        acc, hi = 0, 255
        for i in range(255, -1, -1):
            acc += h[i]
            if acc > n * clip:
                hi = i
                break
        if hi - lo < 32:                              # почти плоская картинка — не растягиваем
            return 0, 255
        span = hi - lo
        if span < MIN_AUTO_SPAN and not full:                      # узкий диапазон (кожа, небо, туман): растягиваем лишь частично,
            pad = (MIN_AUTO_SPAN - span) / 2.0        # иначе цвет «взрывается»
            lo, hi = max(0, int(lo - pad)), min(255, int(hi + pad))
        return lo, hi
    if mode == "color":
        h = img.histogram()
        e = [edges(h[i * 256:(i + 1) * 256]) for i in range(3)]
        return [x[0] for x in e], [x[1] for x in e]
    lo, hi = edges(img.convert("L").histogram())
    return [lo] * 3, [hi] * 3


BW_AUTO_CURVE = [int(round(255 * min(1.0, max(0.0, (i / 255.0) - 0.2 * math.sin(2 * math.pi * i / 255.0) / (2 * math.pi)))))
                 for i in range(256)]


def _smooth(t):
    t = min(1.0, max(0.0, t))
    return t * t * (3 - 2 * t)


def build_luts(a, bounds=None):
    """Три таблицы по 256 значений: баланс каналов, температура/оттенок, яркость, контраст, гамма, тени/света."""
    a = adj_full(a)
    t, ti = a["temp"] / 100.0, a["tint"] / 100.0
    gain = [1 + 0.30 * t + 0.30 * a["r"] / 100.0,
            1 - 0.22 * ti + 0.30 * a["g"] / 100.0,
            1 - 0.30 * t + 0.30 * a["b"] / 100.0]
    bgk = 2.0 * a["bright"] / 100.0
    kc = 1 + a["contrast"] / 100.0
    inv = 1.0 / max(0.05, a["gamma"])
    sh, hl = 0.25 * a["shadows"] / 100.0, 0.25 * a["highlights"] / 100.0
    luts = []
    for c in range(3):
        lo, hi = (bounds[0][c], bounds[1][c]) if bounds else (0, 255)
        tab = []
        for i in range(256):
            x = (i - lo) / float(max(1, hi - lo))
            x = min(1.0, max(0.0, x))
            x = min(1.0, x * gain[c])
            x += bgk * x * (1 - x)                   # яркость: сдвиг средних тонов, чёрный и белый остаются на месте
            x = (x - 0.5) * kc + 0.5
            x = min(1.0, max(0.0, x))
            if inv != 1.0:
                x = x ** inv
            if sh or hl:               # чёрный и белый остаются на месте: правятся только тени и света
                x += sh * (1 - x) ** 2 * _smooth(x / 0.12) + hl * x * x * _smooth((1 - x) / 0.12)
            v = int(round(255 * min(1.0, max(0.0, x))))
            tab.append(max(v, tab[-1]) if tab else v)   # таблица не убывает (при больших значениях яркости)
        luts.append(tab)
    return luts


def hist_rgb(img):
    """Гистограмма RGB (768 значений) и процент пикселей, упёршихся в чёрное/белое."""
    h = img.convert("RGB").histogram()
    n = max(1, img.width * img.height)
    low = sum(h[c * 256] for c in range(3)) / (3.0 * n) * 100
    high = sum(h[c * 256 + 255] for c in range(3)) / (3.0 * n) * 100
    return h, low, high


def merge_adj(o, st):
    """Настройки печати + индивидуальная коррекция снимка."""
    adj = getattr(st, "adj", None)
    if not adj:
        return o
    return {**o, **NEUTRAL_ADJ, **adj}      # своя коррекция фото заменяет общую (иначе общую нельзя «обнулить» для одного фото)


def jpeg_draft(im0, st, mode, dpi, paper=None, fmt=None, orient=None):
    """Ускоряет чтение JPEG: декодер сразу уменьшает снимок в 2/4/8 раз, но не ниже, чем нужно для печати
    (с учётом размера рамки), поэтому качество результата не страдает."""
    if im0.format != "JPEG" or im0.mode not in ("RGB", "L"):
        return
    try:
        rw, rh = im0.size
        ori = im0.getexif().get(0x0112, 1)
        swap = (ori in (5, 6, 7, 8)) != (st.rotation in (90, 270))
        W, H = (rh, rw) if swap else (rw, rh)
        if paper is None:
            paper = paper_size(fmt, orient, W, H)
        tw, th = paper[0] / 25.4 * dpi, paper[1] / 25.4 * dpi
        if mode == "fit":
            k = min(tw / W, th / H)
            nw, nh = W * k, H * k
        else:
            _, _, fw, fh, _ = frame_geom(W, H, paper, st)
            nw, nh = tw * W / fw, th * H / fh
        if swap:
            nw, nh = nh, nw
        im0.draft(im0.mode, (max(1, math.ceil(nw)), max(1, math.ceil(nh))))
    except Exception:
        pass


OUT_SUBDIR = "Готовые"
OWN_OUT_DIRS = ("Печать", "Готовые")


SKIP_EXTS = {".heic", ".heif", ".cr2", ".cr3", ".nef", ".arw", ".dng", ".raf", ".orf", ".rw2", ".gif"}


def looks_like_output(stem):
    labels = "|".join(re.escape(v[2]) for v in FORMATS.values())
    return re.search(rf"_(?:{labels})(?:_x\d+)?(?:_\d+)?(?:_print)?$", stem, re.I) is not None


def is_own_output(rel_parts, name=None, stem=""):
    """Результат программы (лежит в её папке «Готовые»/«Печать» и назван как готовый файл) — при открытии папки пропускаем.
    Чужие файлы в папке с таким именем не теряются."""
    own = {x.lower() for x in OWN_OUT_DIRS} | ({name.lower()} if name else set())
    return any(p.lower() in own for p in rel_parts) and looks_like_output(stem)


def _out_roots(src, outdirs):
    """Папки вывода, лежащие ВНУТРИ src (по пути, а не по имени): всё в них — результаты, а не исходники."""
    roots = []
    try:
        base = os.path.normcase(os.path.abspath(str(src)))
    except (OSError, ValueError):
        return roots
    for d in outdirs or ():
        if not d:
            continue
        try:
            r = os.path.normcase(os.path.abspath(str(d)))
        except (OSError, ValueError):
            continue
        if r != base and r.startswith(base + os.sep):          # сама папка src не считается папкой вывода
            roots.append(r + os.sep)
    return roots


def scan_folder(src, recursive, out_name=None, outdirs=()):
    """Фото папки: (файлы, пропущено своих результатов, пропущено неподдерживаемых форматов {расширение: число}).
    outdirs — пути, куда программа сохраняет результат: файлы внутри них пропускаются при любом названии папки."""
    it = src.rglob("*") if recursive else src.iterdir()
    files, own, other = [], 0, {}
    roots = _out_roots(src, outdirs)
    for f in it:
        if not f.is_file():
            continue
        ext = f.suffix.lower()
        if ext in EXTS:
            if roots and os.path.normcase(os.path.abspath(str(f))).startswith(tuple(roots)):
                own += 1
            elif is_own_output(f.relative_to(src).parts[:-1], out_name, f.stem):
                own += 1
            else:
                files.append(f)
        elif ext in SKIP_EXTS:
            other[ext] = other.get(ext, 0) + 1
    return sorted(files, key=natural_key), own, other


def skipped_note(own, other):
    parts = []
    if own:
        parts.append(f"{own} файл(ов) — готовые результаты программы (папки «Готовые»/«Печать») пропущены")
    if other:
        parts.append("не поддерживаются и пропущены: " + ", ".join(f"{k} ×{v}" for k, v in sorted(other.items())) +
                     " (HEIC/RAW переведите в JPEG)")
    return "\n".join(parts)


def out_dirs(jobs, o):
    """Папки, куда пойдут результаты (для сообщения «Готово»)."""
    seen = []
    for f, st in jobs:
        d = plan_dest(f, o, None, st.copies).parent
        if d not in seen:
            seen.append(d)
    return seen


def plan_dest(path, o, used=None, copies=1):
    """Имя итогового файла. used — множество уже занятых имён серии: одинаковые файлы из разных папок не затирают друг друга."""
    if o.get("out_mode") == "orig":               # рядом с оригиналом, в новую подпапку
        outdir = Path(path).parent / (o.get("out_name") or OUT_SUBDIR)
    else:
        outdir = Path(o["outdir"])
    if o["subfolder"]:
        outdir = outdir / o["fmt"][2]
    tag = f"_x{copies}" if (o.get("copies_in_name") and copies > 1) else ""   # число копий — для заказа печати
    dest = outdir / f"{path.stem}_{o['fmt'][2]}{tag}{FILETYPES[o['filetype']]}"
    if dest.resolve() == path.resolve():
        dest = dest.with_name(dest.stem + "_print" + dest.suffix)
    if used is not None:
        base, n = dest, 1
        while str(dest).lower() in used:
            n += 1
            dest = base.with_name(f"{base.stem}_{n}{base.suffix}")
        used.add(str(dest).lower())
    return dest


def plan_names(jobs, o):
    """Имена результатов для заданий. Если в o['universe'] перечислены ВСЕ открытые файлы [(путь, копии)], имена считаются
    сразу для всех: одно пересохранённое фото получает то же имя, что и при пакетном сохранении, а исходные файлы
    никогда не становятся целью записи. Совпадения решаются суффиксом _2, _3…"""
    uni = [(str(p), c) for p, c in (o.get("universe") or [])]
    used = {str(Path(p)).lower() for p, _ in uni} | {str(Path(f)).lower() for f, _ in jobs}   # исходники — под защитой
    names = {}
    for p, c in uni:
        names[(p, c)] = plan_dest(Path(p), o, used, c)
    out = []
    for f, st in jobs:
        key = (str(f), st.copies)
        out.append(names[key] if key in names else plan_dest(Path(f), o, used, st.copies))
    return out


def batch_workers(jobs, o=None):
    """Сколько потоков брать для пакетной обработки: по ядрам, но меньше для очень больших снимков (память)."""
    try:
        env = int(os.environ.get("PHOTOCROP_WORKERS", "0"))
    except ValueError:
        env = 0
    if env > 0:
        return env
    w = max(1, min(os.cpu_count() or 2, 6, len(jobs)))
    big = 0                                           # самый тяжёлый снимок среди заданий (по заголовкам — быстро)
    for f, st in jobs[:300]:
        try:
            with Image.open(f) as im:
                big = max(big, im.width * im.height)
        except Exception:
            pass
    out_px = 0
    if o:
        try:
            pw, ph = o["fmt"][0], o["fmt"][1]
            out_px = (pw / 25.4 * o["dpi"]) * (ph / 25.4 * o["dpi"])
        except Exception:
            pass
    per = 14.0 * big + 16.0 * out_px                  # грубо: байт на один поток (источник, копии, результат)
    if per > 0:
        w = max(1, min(w, int(3.0e9 / per)))
    return w


def process_batch(jobs, o, progress=None, cancel=None, workers=None):
    """Параллельная обработка [(путь, CropState)]. Pillow отпускает GIL при декодировании/масштабировании,
    поэтому потоки реально ускоряют работу. Имена файлов назначаются заранее и одинаково при каждом запуске.
    progress(сделано, всего, имя); cancel.is_set() — остановка. Возвращает (список файлов в порядке заданий, ошибки)."""
    from concurrent.futures import ThreadPoolExecutor, as_completed
    n = len(jobs)
    if n == 0:
        return [], []
    dests = plan_names(jobs, o)
    saved, errors, done = [None] * n, [], 0

    def one(i):
        f, st = jobs[i]
        if cancel is not None and cancel.is_set():
            return i, None, None
        try:
            return i, str(process_file(f, st, o, dests[i])), None
        except Exception as ex:
            return i, None, f"{Path(f).name}: {ex}"

    with ThreadPoolExecutor(max_workers=workers or batch_workers(jobs, o)) as ex:
        for fu in as_completed([ex.submit(one, i) for i in range(n)]):
            i, dest, err = fu.result()
            saved[i] = dest
            if err:
                errors.append(err)
            done += 1
            if progress:
                progress(done, n, Path(jobs[i][0]).name)
    return [x for x in saved if x], errors


def _fix_exif(ex, dpi):
    """EXIF не должен противоречить готовому файлу: ориентация уже применена, размеры и разрешение другие."""
    for tag in (0x0112,):
        if tag in ex:
            ex[tag] = 1
    for tag in (0x011A, 0x011B, 0x0128, 0xA002, 0xA003):     # разрешение, единицы, PixelX/YDimension
        try:
            if tag in ex:
                del ex[tag]
        except Exception:
            pass
    try:
        sub = ex.get_ifd(0x8769)
        for tag in (0xA002, 0xA003):
            if tag in sub:
                del sub[tag]
    except Exception:
        pass
    return ex


def process_file(path, st, o, dest=None):
    with Image.open(path) as im0:
        if o["resize"]:
            jpeg_draft(im0, st, o["mode"], o["dpi"], fmt=o["fmt"], orient=(st.orient if st.orient else o["orient"]))
        icc = im0.info.get("icc_profile")
        cmyk = im0.mode == "CMYK"
        im = ImageOps.exif_transpose(im0)
    exif_bytes = None
    try:
        ex = _fix_exif(im.getexif(), o["dpi"])
        if len(ex):
            exif_bytes = ex.tobytes()
    except Exception:
        pass
    if st.rotation:
        im = im.rotate(-st.rotation, expand=True)
    im = to_rgb(im, icc)
    if cmyk:
        icc = None                                # CMYK уже переведён в sRGB
    adj = merge_adj(o, st)
    im = adjust_color(im, adj)                    # цвет по самому снимку (белые поля листа не затрагиваются)
    W, H = im.size
    orient = st.orient if st.orient else o["orient"]
    paper = paper_size(o["fmt"], orient, W, H)
    out, out_dpi = render(im, paper, st, o["mode"], o["dpi"], o["resize"])
    out = adjust_detail(out, adj, out_dpi)
    cm = o.get("cm")
    if cm:
        out = apply_printer_profile(out, icc, cm)
        icc = cm["profile"] if cm["embed"] else None
        out.info.pop("icc_profile", None)         # профиль встраиваем только если так заказано
    elif icc and not _rgb_profile(icc):
        icc = None   # серый/CMYK-профиль не подходит к RGB-файлу

    dest = dest or plan_dest(path, o, None, st.copies)
    dest.parent.mkdir(parents=True, exist_ok=True)

    d = round(out_dpi) if o["filetype"] == "JPEG" else out_dpi
    kw = {"dpi": (d, d)}
    if icc:
        kw["icc_profile"] = icc
    tmp = dest.with_name(dest.name + ".part")     # пишем во временный файл: сбой не оставит обрезанный JPEG вместо хорошего
    try:
        if o["filetype"] == "JPEG":
            kw.update(quality=o["quality"], subsampling=0 if o["quality"] >= 90 else 2)
            done = False
            if exif_bytes:
                try:
                    out.save(tmp, "JPEG", exif=exif_bytes, **kw)
                    done = True
                except Exception:
                    pass  # слишком большой/повреждённый EXIF — сохраняем без него
            if not done:
                out.save(tmp, "JPEG", **kw)
        else:
            if o["filetype"] == "TIFF":
                kw["compression"] = "tiff_lzw"
            out.save(tmp, o["filetype"], **kw)
        os.replace(tmp, dest)
    except BaseException:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise
    return dest


def natural_key(p):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", str(p))]


# ---------------------------------------------------------------- язык интерфейса (русский / English)
# Исходные тексты в программе русские; английский — словарь «русский текст → английский».
# Переводятся подписи кнопок, флажков, рамок и заголовков окон + типовые сообщения. Тексты, собираемые
# программой «на лету» (длинные пояснения с цифрами, названия в списках выбора), остаются русскими.

LANGS = {"ru": "Русский", "en": "English"}
_LANG = "ru"
try:                                         # дополнительные языки интерфейса (словари — в i18n.py)
    import i18n as _i18n
    LANGS.update(_i18n.LANG_NAMES)
except Exception:
    _i18n = None

EN = {
    "📂 Папка…": "📂 Folder…", "🖼 Фото…": "🖼 Photos…", "＋ Добавить": "＋ Add", "с подпапками": "with subfolders",
    "Формат:": "Format:", "Ориентация:": "Orientation:", "Режим:": "Mode:", "Сетка 1/3": "Rule of thirds",
    "Авто": "Auto", "Книжная": "Portrait", "Альбомная": "Landscape", "Кадрировать": "Crop", "Вписать": "Fit",
    "☑ Выбрать все": "☑ Select all", "☐ Сбросить": "☐ Clear", "Убрать неотмеченные из списка": "Remove unchecked from list",
    "＋/✓ — отметить фото   ✎ — правка   ◐ — цвет": "＋/✓ — mark photo   ✎ — edited   ◐ — colour",
    "◀ Назад": "◀ Back", " Копий этого фото ": " Copies of this photo ", "Вперёд ▶": "Next ▶",
    "⟲ Фото": "⟲ Photo", "⟳ Фото": "⟳ Photo", "⇄ Книжная/альбомная (R)": "⇄ Portrait/landscape (R)",
    "Сбросить рамку": "Reset frame", "Сбросить все": "Reset all", "🎚 Цвет": "🎚 Colour",
    "Наклон рамки:": "Frame tilt:", "Выровнять (0°)": "Straighten (0°)",
    "Откройте папку с фотографиями": "Open a folder with photos", " Сохранение ": " Saving ",
    "Куда сохранять готовые файлы:": "Where to save finished files:", "Рядом с фото, в папку:": "Next to photos, in folder:",
    "В другую папку:": "To another folder:", "Подпапка с названием формата": "Subfolder named after the format",
    "Число копий в имени файла (_x3)": "Number of copies in file name (_x3)", "Разрешение печати, DPI:": "Print resolution, DPI:",
    "Пересчитать до точного\nразмера печати (рекомендуется)": "Resample to exact\nprint size (recommended)",
    "Тип файла:": "File type:", " Цвет ": " Colour ", "🎚 Коррекция фото… (C)": "🎚 Photo adjustments… (C)",
    "🎨 Профиль принтера…": "🎨 Printer profile…", "Имитация печати на экране": "Simulate print on screen",
    "Показать цвета вне охвата (розовым)": "Show out-of-gamut colours (pink)", "🖨 Печать…": "🖨 Print…",
    "📂 Открыть проект": "📂 Open project", "💾 Сохранить проект": "💾 Save project", "💾 Сохранить текущее": "💾 Save current",
    "💾 Сохранить все": "💾 Save all", " Качество печати ": " Print quality ",
    "Нажмите «Открыть папку…» и выберите папку с фотографиями": "Click “Folder…” and choose a folder with photos",
    "Применять профиль принтера при сохранении": "Apply printer profile when saving", "Обзор…": "Browse…",
    "Способ рендеринга:": "Rendering intent:", "Компенсация точки чёрного": "Black point compensation",
    "Встроить профиль в готовый файл": "Embed profile in output file", "Закрыть": "Close", "Сохранение…": "Saving…",
    " Менять ": " Apply to ", "только это фото": "this photo only", "все фото сразу": "all photos at once",
    "Чёрно-белое": "Black & white", "Сепия": "Sepia", "Авто-уровни:": "Auto levels:",
    " Улучшение для печати на Epson ": " Enhancement for Epson printing ", "✨ Улучшения для Epson": "✨ Epson enhance",
    "✨✨ Супер улучшения": "✨✨ Super enhance",
    "Подбирается под каждый снимок; результат — обычные ползунки, их можно поправить.":
        "Tuned for each photo; the result is ordinary sliders you can adjust.",
    "Применить ко всем": "Apply to all", "Копировать": "Copy", "Вставить": "Paste", "Вставить во все": "Paste to all",
    "Авто-яркость": "Auto brightness", "Сбросить фото": "Reset photo", "👁 Показать оригинал (удерживайте)": "👁 Show original (hold)",
    "Печатать:": "Print:", "🖨 Печать": "🖨 Print", "💾 Листы в файлы…": "💾 Sheets to files…", "Отмена": "Cancel",
    "Принтер": "Printer", "Принтер:": "Printer:", "⚙ Свойства принтера (драйвер)…": "⚙ Printer properties (driver)…",
    "Пресеты (принтер + драйвер + раскладка):": "Presets (printer + driver + layout):", "Сохранить…": "Save…", "Удалить": "Delete",
    "Бумага:": "Paper:", "Своя, мм:": "Custom, mm:", "Копий листа:": "Sheet copies:", "Передача в драйвер, ppi:": "Sent to driver, ppi:",
    "Каждый лист — отдельным заданием, пауза, сек:": "Each sheet as a separate job, pause, s:",
    "Отключить управление цветом Windows (ICM)": "Turn off Windows colour management (ICM)",
    "Раскладка": "Layout", "Что печатать:": "What to print:", "Поля листа, мм:": "Sheet margins, mm:",
    "Расстояние между фото, мм:": "Gap between photos, mm:", "Выравнивание:": "Alignment:", "Копий каждого фото ×:": "Copies of each photo ×:",
    "Заполнить лист копиями каждого фото": "Fill the sheet with copies of each photo",
    "Поворачивать фото, если так помещается больше": "Rotate photos if more fit that way",
    "Печать без полей — подрезка принтером, мм:": "Borderless printing — printer overscan, mm:",
    "Одинаково со всех сторон:": "Same on all sides:", "Лево": "Left", "Верх": "Top", "Право": "Right", "Низ": "Bottom",
    "🧪 Тестовая шкала краёв → в список фото": "🧪 Edge test scale → to photo list",
    "Рамка вокруг фото, мм:": "Border around photo, mm:", "Метки реза": "Crop marks", "Подпись под фото:": "Caption under photo:",
    "Обработка": "Processing", "Применяется только к печати и сохранённым листам.": "Applies to printing and saved sheets only.",
    "Чёрно-белая печать": "Black & white printing", "Сбросить обработку": "Reset processing", "Цвет": "Colour",
    "🎨 Настроить профиль принтера…": "🎨 Set up printer profile…",
    "Предпросмотр с имитацией печати (по профилю)": "Preview with print simulation (by profile)",
    "Подготовка…": "Preparing…", "Отменено": "Cancelled", "Ошибка": "Error",
    "📂 Открыть…": "📂 Open…", "🖼 Выбрать фото…": "🖼 Choose photos…", "📁 Выбрать папку целиком…": "📁 Choose a whole folder…",
    "＋ Добавить фото к списку…": "＋ Add photos to list…",
    "Ни одно фото не отмечено.\nОтметьте «+» на превью слева — фото появится здесь.": "No photo is checked.\nCheck “+” on a thumbnail on the left — the photo will appear here.",
    "Нажмите «Открыть…» и выберите фото или папку": "Click “Open…” and choose photos or a folder",
    "Фирменная": "Brand", "Тёмная": "Dark", "Светлая": "Light", "Чёрно-серо-белая": "Black, grey & white",
    "Оформление": "Appearance", "Тема оформления:": "Theme:", "Анимация отправки листов на печать": "Animate sheets being sent to the printer",
    "Тема меняется сразу, по кнопке «Применить».": "The theme changes immediately when you click “Apply”.",
    "Отметить все фото": "Check all photos", "Снять все отметки": "Uncheck all", "Предыдущее фото (←)": "Previous photo (←)",
    "Следующее фото (→)": "Next photo (→)", "Повернуть фото влево на 90°": "Rotate photo left 90°",
    "Повернуть фото вправо на 90°": "Rotate photo right 90°", "Рамка: книжная ⇄ альбомная (R)": "Frame: portrait ⇄ landscape (R)",
    "Коррекция цвета (C)": "Colour adjustments (C)", "Отменить (Ctrl+Z)": "Undo (Ctrl+Z)", "Повторить (Ctrl+Y)": "Redo (Ctrl+Y)",
    "На уровень выше": "Up one level", "Открыть фото или папку": "Open photos or a folder", "Открыть": "Open",
    "🖥 Рабочий стол": "🖥 Desktop", "🖼 Изображения": "🖼 Pictures", "⬇ Загрузки": "⬇ Downloads", "💽 Диски": "💽 Drives",
    "Имя": "Name", "Размер": "Size", "Добавить к уже открытым фото": "Add to the photos already open",
    "Открыть всю папку с подпапками": "Open the whole folder with subfolders",
    "Ctrl/Shift — несколько фото, Ctrl+A — все, двойной щелчок — войти в папку": "Ctrl/Shift — several photos, Ctrl+A — all, double-click — enter folder",
    "⚙ Настройки": "⚙ Settings", "Настройки": "Settings", "Общие": "General", "Кадрирование": "Cropping", "О программе": "About",
    "Язык интерфейса:": "Interface language:", "Папка по умолчанию в диалогах открытия:": "Default folder in open dialogs:",
    "Рабочий стол": "Desktop", "Последняя использованная": "Last used",
    "Прилипание рамки к краям и центру фото": "Snap frame to photo edges and centre",
    "Сила прилипания, экранных пикселей:": "Snap strength, screen pixels:",
    "Ctrl при перетаскивании — временно отключает прилипание.": "Hold Ctrl while dragging to disable snapping temporarily.",
    "Применить": "Apply", "OK": "OK",
    "Язык меняется сразу. Часть динамических надписей и названия в выпадающих списках остаются на русском.":
        "The language changes immediately. Some dynamic labels and names in drop-down lists remain in Russian.",
    "Программа для кадрирования и печати фотографий.": "Photo cropping and printing program.",
    "Папка с фотографиями": "Folder with photos", "Печать": "Print", "Коррекция": "Adjustments", "Коррекция фото": "Photo adjustments",
    "Цветовой профиль печати": "Printer colour profile",
    "PhotoCrop — кадрирование для фотопечати": "PhotoCrop — cropping for photo printing",
    "Сначала откройте папку с фотографиями.": "Open a folder with photos first.",
    "Идёт сохранение. Всё равно выйти?": "Saving is in progress. Quit anyway?",
    "Нет фотографий для печати.": "No photos to print.", "Принтер не выбран или недоступен.": "No printer selected or printer unavailable.",
    "Начать печать?": "Start printing?",
    "Ни одно фото не отмечено. Отметьте нужные («+» в углу превью).": "No photo is checked. Check the ones you need (“+” in the thumbnail corner).",
    "Среди выбранных нет поддерживаемых фотографий (JPG, PNG, TIFF, BMP, WEBP).": "None of the selected files is a supported photo (JPG, PNG, TIFF, BMP, WEBP).",
    "В выбранной папке нет фотографий (JPG, PNG, TIFF, BMP, WEBP).": "No photos (JPG, PNG, TIFF, BMP, WEBP) in the selected folder.",
}
EN_FMT = {
    "Открыть выбранные фото ({n})": "Open selected photos ({n})", "Открыть папку «{name}» целиком": "Open the whole folder “{name}”",
    "Открыть всю папку ({n} фото)": "Open the whole folder ({n} photos)", "В папке фото: {n}": "Photos in folder: {n}",
    "Отмечено фото: 0": "Checked photos: 0",   # шаблоны с подстановками (str.format) — динамические надписи
    "Файлов: {m}   отмечено: {n}": "Files: {m}   checked: {n}",
    "💾 Сохранить отмеченные ({n})": "💾 Save checked ({n})",
}


def set_language(code):
    global _LANG
    _LANG = code if code in LANGS else "ru"


def get_language():
    return _LANG


def tr(text):
    """Перевод строки на текущий язык; неизвестное остаётся как есть (построчно для многострочных)."""
    if _LANG == "ru" or not isinstance(text, str) or not text:
        return text
    hit = EN.get(text)
    if hit is None and "\n" in text:
        hit = "\n".join(EN.get(l, l) for l in text.split("\n"))
    if _LANG != "en" and _i18n is not None:       # остальные языки: русский -> английский -> язык (нет перевода — английский)
        loc = _i18n.lookup(_LANG, hit if hit is not None else text)
        if loc is not None:
            return loc
    return hit if hit is not None else text


def trf(template, **kw):
    """Шаблон с подстановками: trf("Файлов: {m}", m=3)."""
    t = template if _LANG == "ru" else EN_FMT.get(template, template)
    return t.format(**kw)


def i18n_apply(widget):
    """Проходит по дереву виджетов и ставит подписи на текущем языке. Исходный русский текст
    запоминается в виджете, поэтому можно переключаться туда и обратно сколько угодно раз."""
    try:
        kids = widget.winfo_children()
    except Exception:
        return
    for w in [widget] + list(kids):
        if w is not widget:
            i18n_apply(w)
        try:
            if w.cget("textvariable"):
                continue
        except Exception:
            pass
        try:
            cur = w.cget("text")
        except Exception:
            cur = None
        if isinstance(cur, str) and cur:
            orig = getattr(w, "_i18n_orig", None)
            if orig is None or cur not in (orig, getattr(w, "_i18n_last", None)):
                orig = cur                       # текст поменяла сама программа — это новый исходник
                w._i18n_orig = orig
            new = tr(orig)
            if new != cur:
                try:
                    w.configure(text=new)
                except Exception:
                    pass
            w._i18n_last = new
    try:
        t = widget.title() if hasattr(widget, "title") and widget.winfo_toplevel() is widget else None
    except Exception:
        t = None
    if t:
        o = getattr(widget, "_i18n_title", None)
        if o is None or t not in (o, tr(o)):
            o = t
            widget._i18n_title = o
        try:
            widget.title(tr(o))
        except Exception:
            pass


class _MessageBoxTr:
    """Обёртка над tkinter.messagebox: заголовок и текст проходят через tr()."""

    def __init__(self, mb):
        self._mb = mb

    def __getattr__(self, name):
        f = getattr(self._mb, name)
        if not callable(f) or not name.startswith(("show", "ask")):
            return f

        def call(title=None, message=None, *a, **kw):
            return f(tr(title), tr(message), *a, **kw)
        return call


if _RAW_MESSAGEBOX is not None:
    messagebox = _MessageBoxTr(_RAW_MESSAGEBOX)


def load_settings():
    try:
        return json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def write_json_atomic(path, data):
    """Запись через временный файл: при сбое посреди записи старая копия остаётся целой."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    os.replace(tmp, path)


def save_settings(d):
    try:
        write_json_atomic(SETTINGS_PATH, d)
    except Exception:
        pass


AUTOSAVE_DIR = SETTINGS_PATH.parent / "autosave"
AUTOSAVE_SECONDS = 4


def autosave_path(folder):
    """Файл автосохранения рамок для папки с фото."""
    try:
        key = str(Path(folder).resolve()).lower()
    except OSError:
        key = str(folder).lower()
    return AUTOSAVE_DIR / (hashlib.md5(key.encode("utf-8")).hexdigest()[:16] + ".json")


# ---------------------------------------------------------------- печать: настройки и раскладка

CAPTION_MM = 4.5   # высота строки подписи под фото

LAYOUTS = {"Одно фото на листе": "single", "Несколько фото на листе": "multi"}
RANGES = {"Все фото": "all", "Текущее фото": "current", "Изменённые (✎)": "edited"}
PRINT_ORIENTS = {"Авто": "auto", "Книжная": "portrait", "Альбомная": "landscape"}
ALIGNS = {"По центру": "center", "Сверху слева": "topleft"}
CAPTIONS = {"Нет": "none", "Имя файла": "name", "Номер и имя файла": "name_n"}
BORDER_COLORS = {"Белая": (255, 255, 255), "Чёрная": (0, 0, 0), "Серая": (128, 128, 128)}
PAGES = {"Все листы": "all", "Только текущий лист": "current"}
EXPORT_FORMATS = ["JPEG", "TIFF", "PNG", "PDF"]
PPI_CHOICES = ["Авто", "240", "300", "360", "600"]   # выше 600 лист не помещается в память (A4 при 1440 ≈ 200 Мпикс)
MAX_PPI = 600
PAPER_DRIVER = "Как в драйвере принтера"
PAPER_CUSTOM = "Своя…"
# название -> (ширина мм, высота мм, код бумаги Windows; 0 — нестандартная)
VIRTUAL_PAPERS = {
    "A4 (210×297)": (210, 297, 9), "A5 (148×210)": (148, 210, 11), "A3 (297×420)": (297, 420, 8),
    "A6 (105×148)": (105, 148, 70), "Letter (216×279)": (215.9, 279.4, 1),
    "10×15 см": (102, 152, 0), "13×18 см": (127, 178, 0), "15×21 см": (152, 216, 0), "20×30 см": (203, 305, 0),
}

PRINT_DEFAULTS = {
    "layout": "Несколько фото на листе", "range": "Все фото", "pages": "Все листы",
    "orient": "Авто", "paper": PAPER_DRIVER, "paper_w": "210", "paper_h": "297",
    "margin_l": "5", "margin_t": "5", "margin_r": "5", "margin_b": "5",
    "gap": "3", "align": "По центру", "copies": "1", "sheet_copies": "1",
    "fill": False, "rotate_fit": True, "marks": False,
    "border": "0", "border_color": "Белая", "caption": "Нет", "bleed_on": True, "bleed": "0",
    "bleed_l": "", "bleed_t": "", "bleed_r": "", "bleed_b": "",
    "one_by_one": True, "job_pause": "2",
    "icm_off": True, "ppi": "Авто",
    "sharp": "0", "sharp_radius": "1.0", "sharp_thr": "2",
    "bright": "0", "contrast": "0", "sat": "0", "gamma": "1.0", "bw": False,
    "export_fmt": "JPEG", "proof": False,
}


def fnum(v, default=0.0, lo=None, hi=None):
    try:
        x = float(str(v).replace(",", ".").strip())
    except (ValueError, TypeError):
        x = float(default)
    if lo is not None:
        x = max(lo, x)
    if hi is not None:
        x = min(hi, x)
    return x


def parse_print_opts(r):
    """Значения из полей окна (строки/флажки) -> типизированные настройки."""
    g = lambda k: r.get(k, PRINT_DEFAULTS[k])
    f = lambda k, lo=None, hi=None: fnum(g(k), PRINT_DEFAULTS[k], lo, hi)
    return {
        "layout": LAYOUTS.get(g("layout"), "multi"), "range": RANGES.get(g("range"), "all"),
        "pages": PAGES.get(g("pages"), "all"), "orient": PRINT_ORIENTS.get(g("orient"), "auto"),
        "paper": g("paper"), "paper_w": f("paper_w", 20, 2000), "paper_h": f("paper_h", 20, 2000),
        "ml": f("margin_l", 0, 200), "mt": f("margin_t", 0, 200), "mr": f("margin_r", 0, 200), "mb": f("margin_b", 0, 200),
        "gap": f("gap", 0, 100), "align": ALIGNS.get(g("align"), "center"),
        "copies": int(f("copies", 1, 999)), "sheet_copies": int(f("sheet_copies", 1, 999)),
        "fill": bool(g("fill")), "rotate_fit": bool(g("rotate_fit")), "marks": bool(g("marks")),
        "border": f("border", 0, 50), "border_color": BORDER_COLORS.get(g("border_color"), (255, 255, 255)),
        "caption": CAPTIONS.get(g("caption"), "none"), "bleed_on": bool(g("bleed_on")), "bleed": f("bleed", -10, 10),
        **{"bleed_" + k: (None if str(g("bleed_" + k)).strip() == "" else f("bleed_" + k, -10, 10)) for k in "ltrb"},
        "one_by_one": bool(g("one_by_one")), "job_pause": f("job_pause", 0, 60),
        "icm_off": bool(g("icm_off")), "ppi": g("ppi"),
        "sharp": f("sharp", 0, 500), "sharp_radius": f("sharp_radius", 0.1, 10), "sharp_thr": int(f("sharp_thr", 0, 255)),
        "bright": f("bright", -100, 100), "contrast": f("contrast", -100, 100), "sat": f("sat", -100, 100),
        "gamma": f("gamma", 0.2, 5), "bw": bool(g("bw")),
        "export_fmt": g("export_fmt") if g("export_fmt") in EXPORT_FORMATS else "JPEG", "proof": bool(g("proof")),
    }


def mm2px(v, ppi):
    return int(round(v / 25.4 * ppi))


def pack_slots(sizes, area, gap, rotate_fit=True, align="center"):
    """Раскладка прямоугольников рядами («полками») с переносом на новый лист.
    sizes — [(w, h)] в мм, area — (x0, y0, x1, y1) в мм.
    Результат: список листов; лист — список (номер, x, y, w, h, повёрнут); w, h уже с учётом поворота."""
    x0, y0, x1, y1 = area
    AW, AH = x1 - x0, y1 - y0
    eps = 1e-6
    sheets, rows, row, used = [], [], None, 0.0

    def close_row():
        nonlocal row, used
        if row is not None:
            rows.append(row)
            used += row["h"] + gap
            row = None

    def finish_sheet():
        nonlocal rows, used
        close_row()
        if rows:
            sheets.append(rows)
        rows, used = [], 0.0

    def cands(w, h):
        c = [(w, h, False)]
        if rotate_fit and abs(w - h) > 1e-6:
            c.append((h, w, True))
        return c

    for idx, (w, h) in enumerate(sizes):
        placed = False
        if row is not None:                       # 1) в текущий ряд
            for cw, ch, r in cands(w, h):
                nw, nh = row["w"] + gap + cw, max(row["h"], ch)
                if nw <= AW + eps and used + nh <= AH + eps:
                    row["items"].append((idx, cw, ch, r))
                    row["w"], row["h"] = nw, nh
                    placed = True
                    break
        if placed:
            continue
        close_row()                               # 2) новый ряд на этом листе
        for cw, ch, r in cands(w, h):
            if cw <= AW + eps and used + ch <= AH + eps:
                row = {"w": cw, "h": ch, "items": [(idx, cw, ch, r)]}
                placed = True
                break
        if placed:
            continue
        finish_sheet()                            # 3) новый лист
        for cw, ch, r in cands(w, h):
            if cw <= AW + eps and ch <= AH + eps:
                row = {"w": cw, "h": ch, "items": [(idx, cw, ch, r)]}
                placed = True
                break
        if not placed:                            # не помещается совсем — кладём по центру, края обрежутся
            cw, ch, r = cands(w, h)[0]
            row = {"w": cw, "h": ch, "items": [(idx, cw, ch, r)]}
    finish_sheet()

    out = []
    for rws in sheets:
        total_h = sum(r["h"] for r in rws) + gap * (len(rws) - 1)
        y = y0 + ((AH - total_h) / 2 if align == "center" else 0.0)
        placed_list = []
        for r in rws:
            x = x0 + ((AW - r["w"]) / 2 if align == "center" else 0.0)
            for idx, cw, ch, rot_ in r["items"]:
                placed_list.append((idx, x, y, cw, ch, rot_))
                x += cw + gap
            y += r["h"] + gap
        out.append(placed_list)
    return out


def sheet_capacity(size, area, gap, rotate_fit):
    res = pack_slots([size] * 400, area, gap, rotate_fit)
    return max(1, len(res[0])) if res else 1


def make_edge_test(w_mm, h_mm, ppi=300):
    """Шкала краёв: чёрточки через 0,5 мм от края фото, цифры в мм. После печати без полей последняя различимая цифра
    у каждого края = сколько мм срезал принтер."""
    W, H = max(1, round(w_mm / 25.4 * ppi)), max(1, round(h_mm / 25.4 * ppi))
    im = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(im)
    px = ppi / 25.4
    f = _font(max(10, round(px * 2.2)))
    d.rectangle((0, 0, W - 1, H - 1), outline="black", width=max(1, round(px * 0.15)))
    for k in range(0, 21):                            # 0 … 10 мм через 0,5
        mm = k / 2.0
        ln = px * (3.0 if k % 2 == 0 else 1.5)
        o_ = mm * px
        wd = max(1, round(px * 0.12))
        for pos in (0.2, 0.5, 0.8):
            xs, ys = W * pos, H * pos
            d.line((xs, o_, xs, o_ + ln), fill="black", width=wd)                 # верх
            d.line((xs, H - 1 - o_, xs, H - 1 - o_ - ln), fill="black", width=wd)  # низ
            d.line((o_, ys, o_ + ln, ys), fill="black", width=wd)                 # лево
            d.line((W - 1 - o_, ys, W - 1 - o_ - ln, ys), fill="black", width=wd)  # право
        if k % 2 == 0 and k > 0:
            t = str(k // 2)
            d.text((W * 0.5 + px * 1.0, o_ + px * 0.2), t, fill="black", font=f)
            d.text((W * 0.5 + px * 1.0, H - o_ - px * 2.8), t, fill="black", font=f)
            d.text((o_ + px * 0.4, H * 0.5 - px * 4.0), t, fill="black", font=f)
            d.text((W - o_ - px * 2.2, H * 0.5 - px * 4.0), t, fill="black", font=f)
    c = (W // 2, H // 2)
    d.line((c[0] - px * 8, c[1], c[0] + px * 8, c[1]), fill="red", width=max(1, round(px * 0.15)))
    d.line((c[0], c[1] - px * 8, c[0], c[1] + px * 8), fill="red", width=max(1, round(px * 0.15)))
    d.text((c[0] - px * 18, c[1] + px * 10), "Шкала краёв: цифра = мм от края фото", fill="black", font=f)
    return im


def bleed_sides(o):
    """Вылет за край листа по сторонам (лево, верх, право, низ), мм: общий bleed, если сторона не задана отдельно.
    Положительное — снимок заходит за край (запас на обрезку принтером), отрицательное — отступ внутрь."""
    if not o.get("bleed_on", True):               # режим подрезки выключен — значения сохранены, но не применяются
        return (0.0, 0.0, 0.0, 0.0)
    b = o.get("bleed", 0.0) or 0.0
    return tuple((o.get("bleed_" + k) if o.get("bleed_" + k) is not None else b) for k in "ltrb")


def sheet_area(geom, o):
    """Область листа (мм), в которой можно размещать фото: поля пользователя ∩ печатное поле принтера."""
    W, H = geom["paper"]
    ax0, ay0, ax1, ay1 = geom["area"]
    if o["layout"] == "single" and any(abs(v) > 1e-9 for v in bleed_sides(o)):
        return 0.0, 0.0, W, H
    x0, y0 = max(o["ml"], ax0), max(o["mt"], ay0)
    x1, y1 = min(W - o["mr"], ax1), min(H - o["mb"], ay1)
    if x1 - x0 < 5 or y1 - y0 < 5:
        return ax0, ay0, ax1, ay1
    return x0, y0, x1, y1


def virtual_geometry(W, H, orient):
    """Лист без принтера (предпросмотр, экспорт): печатное поле = вся бумага."""
    short, long_ = min(W, H), max(W, H)
    pw, ph = (short, long_) if orient == "portrait" else (long_, short)
    return {"paper": (pw, ph), "area": (0.0, 0.0, pw, ph), "dpi": (300, 300), "orient": orient, "virtual": True}


def build_photos(entries, fmt, global_orient, o):
    """entries: [(путь, CropState)] -> (список фото для печати, список нечитаемых файлов)."""
    photos, skipped = [], []
    for path, st in entries:
        try:
            W, H = true_size(path, st.rotation)
        except Exception:
            skipped.append(Path(path).name)
            continue
        paper = paper_size(fmt, st.orient if st.orient else global_orient, W, H)
        photos.append({"path": path, "st": st.copy(), "paper": paper,     # снимок состояния: правки во время печати не влияют
                       "copies": max(1, st.copies) * o["copies"]})
    return photos, skipped


def _plan_for(photos, geom, o):
    area = sheet_area(geom, o)
    AW, AH = area[2] - area[0], area[3] - area[1]
    gap = o["gap"]
    if o["marks"] and o["layout"] != "single":
        gap = max(gap, 4.5)                       # место под метки реза между фото
    cap = CAPTION_MM if o["caption"] != "none" else 0.0
    bl, bt, br, bb = bleed_sides(o) if o["layout"] == "single" else (0.0, 0.0, 0.0, 0.0)
    bleed = max(bl, bt, br, bb, 0.0)

    def slot(i):
        pw, ph = photos[i]["paper"]
        iw, ih = max(1.0, pw + bl + br), max(1.0, ph + bt + bb)
        return iw, ih, (iw, ih + cap)

    groups = []                                   # каждая группа раскладывается на свои листы
    if o["layout"] == "single":
        for i, p in enumerate(photos):
            groups += [[i] for _ in range(p["copies"])]
    elif o["fill"]:
        for i in range(len(photos)):
            groups.append([i] * sheet_capacity(slot(i)[2], area, gap, o["rotate_fit"]))
    else:
        seq = []
        for i, p in enumerate(photos):
            seq += [i] * p["copies"]
        if seq:
            groups.append(seq)

    sheets, used_area = [], 0.0
    for g in groups:
        for placed in pack_slots([slot(i)[2] for i in g], area, gap, o["rotate_fit"], o["align"]):
            sheet = []
            for idx, x, y, w, h, r in placed:
                iw, ih, _ = slot(g[idx])
                if o["layout"] == "single" and not r and o["align"] == "center":   # фото по центру листа, вылет — наружу по каждой стороне отдельно
                    x += (br - bl) / 2.0
                    y += (bb - bt) / 2.0
                sheet.append({"photo": g[idx], "x": x, "y": y, "w": w, "h": h, "rot": r, "iw": iw, "ih": ih})
                used_area += min(photos[g[idx]]["paper"][0] * photos[g[idx]]["paper"][1], AW * AH)   # только видимая часть, без вылета
            sheets.append(sheet)

    warnings = []
    for i, p in enumerate(photos):
        pw, ph = p["paper"]
        fits = (pw <= AW + 0.5 and ph + cap <= AH + 0.5) or (o["rotate_fit"] and ph <= AW + 0.5 and pw + cap <= AH + 0.5)
        if not fits:
            warnings.append(f"{Path(p['path']).name}: {pw:.0f}×{ph:.0f} мм не помещается на лист "
                            f"(область печати {AW:.0f}×{AH:.0f} мм)")
    if any(abs(v) > 1e-9 for v in (bl, bt, br, bb)):
        W, H = geom["paper"]
        ax0, ay0, ax1, ay1 = geom["area"]
        over = max(ax0, ay0, W - ax1, H - ay1)
        side_txt = f"лево {bl:g}, верх {bt:g}, право {br:g}, низ {bb:g} мм"
        if not geom.get("virtual") and over > 0.5:
            warnings.append(f"Вылет/отступ ({side_txt}): принтер не печатает ближе {over:.1f} мм к краю листа. Без режима «без полей» "
                            f"в драйвере по краям останутся белые полосы, а вылет будет обрезан.")
        elif geom.get("virtual"):
            warnings.append(f"Вылет/отступ ({side_txt}): край листа условный — убедитесь, что в драйвере включена печать без полей.")
    util = used_area / (len(sheets) * AW * AH) if sheets and AW * AH > 0 else 0.0
    return {"geom": geom, "area": area, "sheets": sheets, "warnings": warnings, "util": util, "gap": gap}


def plan_layout(photos, geom_for, o):
    """Раскладка по листам. geom_for(orient) -> геометрия листа. При «Авто» выбирается ориентация,
    дающая меньше листов (затем — плотнее заполнение)."""
    orients = ["portrait", "landscape"] if o["orient"] == "auto" else [o["orient"]]
    nport = sum(1 for p in photos if p["paper"][0] < p["paper"][1])
    pref = "portrait" if nport * 2 >= len(photos) else "landscape"
    best, best_key = None, None
    for ori in orients:
        plan = _plan_for(photos, geom_for(ori), o)
        plan["orient"] = ori
        # меньше листов → плотнее заполнение → при равенстве предпочитаем ориентацию большинства фото
        key = (len(plan["sheets"]), -round(plan["util"], 3), 0 if ori == pref else 1)
        if best is None or key < best_key:
            best, best_key = plan, key
    return best


# ---------------------------------------------------------------- печать: отрисовка листов

_FONTS = {}


def _font(px):
    if px not in _FONTS:
        f = None
        for name in ("arial.ttf", "segoeui.ttf", "DejaVuSans.ttf", "LiberationSans-Regular.ttf"):
            try:
                f = ImageFont.truetype(name, px)
                break
            except Exception:
                continue
        _FONTS[px] = f or ImageFont.load_default()
    return _FONTS[px]


def adj_has_color(a):
    return any(a[k] != NEUTRAL_ADJ[k] for k in NEUTRAL_ADJ if k not in ("denoise", "sharp", "sharp_radius", "sharp_thr"))


def adjust_color(img, o, ref=None):
    """Тон и цвет (точечные операции): авто-уровни -> каналы/тон (одна таблица) -> насыщенность -> ч/б, сепия.
    ref — снимок целиком, по которому считаются авто-уровни (чтобы белые поля не влияли)."""
    a = adj_full(o)
    if not adj_has_color(a):
        return img
    if img.mode != "RGB":
        img = img.convert("RGB")
    bounds = None
    bw_auto = a["auto"] == "bw"
    if a["auto"]:
        r = ref if ref is not None else img
        if max(r.size) > 700:
            r = r.copy()
            r.thumbnail((700, 700), RESAMPLE_FAST)
        bounds = _auto_bounds(r, a["auto"])
    luts = build_luts(a, bounds)
    if bounds or any(luts[c] != list(range(256)) for c in range(3)):
        img = img.point(luts[0] + luts[1] + luts[2])
    if a["sat"]:
        img = ImageEnhance.Color(img).enhance(max(0.0, 1 + a["sat"] / 100.0))
    if a["vib"]:
        v = a["vib"] / 100.0
        s_ch = img.convert("HSV").getchannel(1)
        if v > 0:      # красочность: усиливаем в основном бледные цвета
            boosted = ImageEnhance.Color(img).enhance(1 + 1.5 * v)
            img = Image.composite(boosted, img, s_ch.point([255 - i for i in range(256)]))
        else:          # приглушаем в основном самые насыщенные
            dull = ImageEnhance.Color(img).enhance(max(0.0, 1 + 1.5 * v))
            img = Image.composite(dull, img, s_ch)
    if a["bw"] or a["sepia"] or bw_auto:
        g = img.convert("L")
        if bw_auto:                                   # авто ч/б: мягкая S-кривая — снимок «оживает», белый и чёрный на месте
            g = g.point(BW_AUTO_CURVE)
        img = ImageOps.colorize(g, (28, 16, 6), (255, 242, 222), mid=(150, 110, 70)) if a["sepia"] else g.convert("RGB")
    return img


def adjust_detail(img, o, ppi, preview=False):
    """Пространственные операции уже на размере печати: шум цвета и резкость (радиус масштабируется по ppi)."""
    a = adj_full(o)
    if not (a["denoise"] > 0 or a["sharp"] > 0):
        return img
    if img.mode != "RGB":
        img = img.convert("RGB")
    if a["denoise"] > 0 and not (a["bw"] or a["sepia"] or a["auto"] == "bw"):
        y, cb, cr = img.convert("YCbCr").split()
        r = max(0.4, a["denoise"] / 100.0 * 6.0 * (100 if preview else ppi) / 300.0)
        img = Image.merge("YCbCr", (y, cb.filter(ImageFilter.GaussianBlur(r)), cr.filter(ImageFilter.GaussianBlur(r)))).convert("RGB")
    if a["sharp"] > 0 and not preview:
        img = img.filter(ImageFilter.UnsharpMask(radius=a["sharp_radius"] * ppi / 300.0,
                                                 percent=int(a["sharp"]), threshold=int(a["sharp_thr"])))
    return img


def adjust_tile(img, o, ppi, preview=False, ref=None):
    """Вся коррекция сразу (для экрана и тестов): цвет, затем детали."""
    return adjust_detail(adjust_color(img, o, ref), o, ppi, preview)


def _extended_tile(im, paper, st, sides, ppi):
    """Плитка с вылетом: расширенная рамка (по положительным сторонам) вырезается из самого снимка.
    None — если расширенная рамка выходит за снимок (тогда вылет делается масштабированием)."""
    pl, pt, pr, pb = (max(0.0, v) for v in sides)
    W, H = im.size
    pw, ph_ = paper
    cx, cy, w, h, ang = frame_geom(W, H, paper, st)
    k = w / pw                                        # пикселей снимка на мм бумаги
    dx, dy = rot((pr - pl) / 2.0 * k, (pb - pt) / 2.0 * k, ang)
    g = (cx + dx, cy + dy, (pw + pl + pr) * k, (ph_ + pt + pb) * k, ang)
    if not frame_inside(W, H, g):
        return None
    tw, th = max(1, mm2px(pw + pl + pr, ppi)), max(1, mm2px(ph_ + pt + pb, ppi))
    return render_frame(im, g, tw, th)


def photo_sides(ph, o):
    """Вылет по сторонам СНИМКА (лево, верх, право, низ), мм. У фото может быть свой набор (ph["sides"]) —
    например, когда оно лежит на листе боком; иначе общий для листа. Только для раскладки «одно фото на лист»."""
    if o.get("layout") != "single":
        return (0.0, 0.0, 0.0, 0.0)
    s = ph.get("sides")
    return tuple(s) if s is not None else bleed_sides(o)


def _tile(ph, ppi, o, mode, fast, cache):
    st, paper = ph["st"], ph["paper"]
    o = merge_adj(o, st)
    sides = photo_sides(ph, o)
    key = (str(ph["path"]), st.cx, st.cy, st.scale, st.angle, st.rotation, paper, ppi, mode, fast, sides,
           tuple(sorted(adj_full(o).items())))
    if cache is not None and key in cache:
        return cache[key]
    tw, th = max(1, mm2px(paper[0], ppi)), max(1, mm2px(paper[1], ppi))
    with Image.open(ph["path"]) as im0:
        icc = im0.info.get("icc_profile")
        cmyk = im0.mode == "CMYK"
        jpeg_draft(im0, st, mode, ppi, paper=paper)
        im = ImageOps.exif_transpose(im0)
    if st.rotation:
        im = im.rotate(-st.rotation, expand=True)
    im = to_rgb(im, icc)
    if cmyk:
        icc = None
    im = adjust_color(im, o)                      # тон и цвет — по самому снимку, без белых полей листа
    out = None
    if mode == "crop" and any(v > 1e-9 for v in sides):
        # настоящий вылет: рамка расширяется за край кадра там, где разрешено, — снимок заходит за край листа реальным содержимым
        ext = _extended_tile(im, paper, st, sides, ppi)
        if ext is not None:
            out = ext
    if out is None:
        out, _ = render(im, paper, st, mode, ppi, True)
    src = _rgb_profile(icc)
    if src is not None:                           # листы всегда в sRGB: профиль фото -> sRGB
        try:
            if "sRGB" not in (ImageCms.getProfileDescription(src) or ""):
                out = ImageCms.profileToProfile(out, src, _srgb(), renderingIntent=1, outputMode="RGB", flags=CMS_BPC)
        except Exception:
            pass
    out = adjust_detail(out, o, ppi)
    if cache is not None:
        px = sum(t.width * t.height for t in cache.values()) + out.width * out.height
        if len(cache) > 40 or px > 60_000_000:     # не копим гигабайты плиток крупных листов
            cache.clear()
        if out.width * out.height <= 60_000_000:
            cache[key] = out
    return out


def _draw_marks(d, rect, ppi):
    X0, Y0, X1, Y1 = rect
    off, ln = mm2px(1.0, ppi), mm2px(3.0, ppi)
    w = max(1, round(ppi / 300))
    for x, sx in ((X0, -1), (X1, 1)):
        for y, sy in ((Y0, -1), (Y1, 1)):
            d.line((x + sx * off, y, x + sx * (off + ln), y), fill=(0, 0, 0), width=w)
            d.line((x, y + sy * off, x, y + sy * (off + ln)), fill=(0, 0, 0), width=w)


def compose_sheet(plan, k, photos, ppi, o, mode, fast=False, cache=None):
    """Рисует лист k (всю бумагу целиком) с разрешением ppi. Цвета — sRGB."""
    PW, PH = plan["geom"]["paper"]
    S = Image.new("RGB", (max(1, mm2px(PW, ppi)), max(1, mm2px(PH, ppi))), "white")
    d = ImageDraw.Draw(S)
    rot90 = getattr(Image, "Transpose", Image).ROTATE_90
    cap_px = mm2px(CAPTION_MM, ppi) if o["caption"] != "none" else 0
    for pl in plan["sheets"][k]:
        ph = photos[pl["photo"]]
        tile = _tile(ph, ppi, o, mode, fast, cache)
        iw, ih = max(1, mm2px(pl["iw"], ppi)), max(1, mm2px(pl["ih"], ppi))
        canvas = Image.new("RGB", (iw, ih + cap_px), "white")
        if o.get("layout") == "single" and tile.size != (iw, ih) and any(abs(v) > 1e-9 for v in photo_sides(ph, o)):
            tile = tile.resize((iw, ih), RESAMPLE_HQ)        # точное соответствие вылету по сторонам (искажение < 3%)
        b = mm2px(o["border"], ppi)
        if b > 0 and iw > 2 * b + 2 and ih > 2 * b + 2:
            canvas.paste(o["border_color"], (0, 0, iw, ih))
            canvas.paste(ImageOps.fit(tile, (iw - 2 * b, ih - 2 * b), RESAMPLE_HQ), (b, b))   # без искажения пропорций
        else:
            canvas.paste(tile if tile.size == (iw, ih) else ImageOps.fit(tile, (iw, ih), RESAMPLE_HQ), (0, 0))
        if cap_px:
            name = Path(ph["path"]).name
            text = f"{pl['photo'] + 1}. {name}" if o["caption"] == "name_n" else name
            fnt = _font(max(8, round(ppi * 2.6 / 25.4)))
            cd = ImageDraw.Draw(canvas)
            while len(text) > 4 and cd.textlength(text, font=fnt) > iw:
                text = text[:-2]
            cd.text((0, ih + max(1, cap_px // 8)), text, fill=(0, 0, 0), font=fnt)
        if pl["rot"]:
            canvas = canvas.transpose(rot90)
        X, Y = mm2px(pl["x"], ppi), mm2px(pl["y"], ppi)
        S.paste(canvas, (X, Y))
        if o["marks"]:
            rect = (X, Y, X + ih, Y + iw) if pl["rot"] else (X, Y, X + iw, Y + ih)
            _draw_marks(d, rect, ppi)
    return S


def resolve_ppi(o, geom):
    if o["ppi"] != "Авто":
        try:
            return max(72, min(MAX_PPI, int(o["ppi"])))
        except ValueError:
            pass
    dx = int(geom["dpi"][0])
    for c in (360, 300, 240):
        if dx % c == 0:
            return c
    return max(72, min(dx, 360))


# ---------------------------------------------------------------- печать: Windows (GDI / драйвер)

DM_ORIENTATION, DM_PAPERSIZE, DM_PAPERLENGTH, DM_PAPERWIDTH = 0x1, 0x2, 0x4, 0x8
DM_COPIES, DM_FORMNAME, DM_ICMMETHOD = 0x100, 0x10000, 0x800000
DM_OUT_BUFFER, DM_IN_PROMPT, DM_IN_BUFFER = 2, 4, 8
DMPAPER_USER, DMICMMETHOD_NONE = 256, 1


class DEVMODEW(ctypes.Structure):
    _fields_ = [
        ("dmDeviceName", ctypes.c_uint16 * 32), ("dmSpecVersion", ctypes.c_ushort), ("dmDriverVersion", ctypes.c_ushort),
        ("dmSize", ctypes.c_ushort), ("dmDriverExtra", ctypes.c_ushort), ("dmFields", ctypes.c_uint32),
        ("dmOrientation", ctypes.c_short), ("dmPaperSize", ctypes.c_short), ("dmPaperLength", ctypes.c_short),
        ("dmPaperWidth", ctypes.c_short), ("dmScale", ctypes.c_short), ("dmCopies", ctypes.c_short),
        ("dmDefaultSource", ctypes.c_short), ("dmPrintQuality", ctypes.c_short), ("dmColor", ctypes.c_short),
        ("dmDuplex", ctypes.c_short), ("dmYResolution", ctypes.c_short), ("dmTTOption", ctypes.c_short),
        ("dmCollate", ctypes.c_short), ("dmFormName", ctypes.c_uint16 * 32), ("dmLogPixels", ctypes.c_ushort),
        ("dmBitsPerPel", ctypes.c_uint32), ("dmPelsWidth", ctypes.c_uint32), ("dmPelsHeight", ctypes.c_uint32),
        ("dmDisplayFlags", ctypes.c_uint32), ("dmDisplayFrequency", ctypes.c_uint32), ("dmICMMethod", ctypes.c_uint32),
        ("dmICMIntent", ctypes.c_uint32), ("dmMediaType", ctypes.c_uint32), ("dmDitherType", ctypes.c_uint32),
        ("dmReserved1", ctypes.c_uint32), ("dmReserved2", ctypes.c_uint32), ("dmPanningWidth", ctypes.c_uint32),
        ("dmPanningHeight", ctypes.c_uint32),
    ]


class DOCINFOW(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_int), ("lpszDocName", ctypes.c_wchar_p), ("lpszOutput", ctypes.c_wchar_p),
                ("lpszDatatype", ctypes.c_wchar_p), ("fwType", ctypes.c_uint32)]


class PRINTER_INFO_4(ctypes.Structure):
    _fields_ = [("pPrinterName", ctypes.c_wchar_p), ("pServerName", ctypes.c_wchar_p), ("Attributes", ctypes.c_uint32)]


_WIN = None


def _win():
    """Загружает winspool/gdi32 (только Windows)."""
    global _WIN
    if _WIN is None:
        if sys.platform != "win32":
            raise OSError("Печать на принтер доступна только в Windows.")
        from ctypes import wintypes as wt
        wp = ctypes.WinDLL("winspool.drv", use_last_error=True)
        gd = ctypes.WinDLL("gdi32", use_last_error=True)
        wp.OpenPrinterW.argtypes = [wt.LPWSTR, ctypes.POINTER(wt.HANDLE), ctypes.c_void_p]
        wp.OpenPrinterW.restype = wt.BOOL
        wp.ClosePrinter.argtypes = [wt.HANDLE]
        wp.ClosePrinter.restype = wt.BOOL
        wp.DocumentPropertiesW.argtypes = [wt.HWND, wt.HANDLE, wt.LPWSTR, ctypes.c_void_p, ctypes.c_void_p, wt.DWORD]
        wp.DocumentPropertiesW.restype = ctypes.c_long
        wp.EnumPrintersW.argtypes = [wt.DWORD, wt.LPWSTR, wt.DWORD, ctypes.c_void_p, wt.DWORD,
                                     ctypes.POINTER(wt.DWORD), ctypes.POINTER(wt.DWORD)]
        wp.EnumPrintersW.restype = wt.BOOL
        wp.GetDefaultPrinterW.argtypes = [wt.LPWSTR, ctypes.POINTER(wt.DWORD)]
        wp.GetDefaultPrinterW.restype = wt.BOOL
        gd.CreateDCW.argtypes = [wt.LPCWSTR, wt.LPCWSTR, wt.LPCWSTR, ctypes.c_void_p]
        gd.CreateDCW.restype = ctypes.c_void_p
        gd.DeleteDC.argtypes = [ctypes.c_void_p]
        gd.GetDeviceCaps.argtypes = [ctypes.c_void_p, ctypes.c_int]
        gd.GetDeviceCaps.restype = ctypes.c_int
        gd.StartDocW.argtypes = [ctypes.c_void_p, ctypes.POINTER(DOCINFOW)]
        gd.StartDocW.restype = ctypes.c_int
        for fn in ("StartPage", "EndPage", "EndDoc", "AbortDoc"):
            getattr(gd, fn).argtypes = [ctypes.c_void_p]
            getattr(gd, fn).restype = ctypes.c_int
        _WIN = (wp, gd, wt)
    return _WIN


def list_printers():
    """Установленные принтеры Windows (имя по умолчанию — первым)."""
    if sys.platform != "win32":
        return []
    try:
        wp, gd, wt = _win()
        flags = 2 | 4   # PRINTER_ENUM_LOCAL | PRINTER_ENUM_CONNECTIONS
        need, ret = wt.DWORD(0), wt.DWORD(0)
        wp.EnumPrintersW(flags, None, 4, None, 0, ctypes.byref(need), ctypes.byref(ret))
        if need.value == 0:
            return []
        buf = ctypes.create_string_buffer(need.value)
        if not wp.EnumPrintersW(flags, None, 4, buf, need.value, ctypes.byref(need), ctypes.byref(ret)):
            return []
        arr = ctypes.cast(buf, ctypes.POINTER(PRINTER_INFO_4))
        names = [arr[i].pPrinterName for i in range(ret.value)]
        n = wt.DWORD(512)
        dbuf = ctypes.create_unicode_buffer(512)
        if wp.GetDefaultPrinterW(dbuf, ctypes.byref(n)) and dbuf.value in names:
            names.remove(dbuf.value)
            names.insert(0, dbuf.value)
        return names
    except Exception:
        return []


def devmode_valid(blob):
    if not blob or len(blob) < 72:
        return False
    dm_size, extra = struct.unpack_from("<HH", blob, 68)
    return dm_size >= 72 and dm_size + extra == len(blob)


def _docprops(name, blob, mode, hwnd=None):
    """DocumentPropertiesW: размер, значения по умолчанию, слияние или диалог свойств драйвера."""
    wp, gd, wt = _win()
    h = wt.HANDLE()
    if not wp.OpenPrinterW(name, ctypes.byref(h), None):
        raise OSError(f"Не удалось открыть принтер «{name}».")
    try:
        size = wp.DocumentPropertiesW(None, h, name, None, None, 0)
        if size <= 0:
            raise OSError("Драйвер принтера не вернул настройки.")
        out = ctypes.create_string_buffer(size)
        if blob is not None and (mode & DM_IN_BUFFER):
            inb = ctypes.create_string_buffer(blob, max(len(blob), size))
            res = wp.DocumentPropertiesW(hwnd, h, name, out, inb, mode)
        else:
            res = wp.DocumentPropertiesW(hwnd, h, name, out, None, mode)
        return res, out.raw[:size]
    finally:
        wp.ClosePrinter(h)


def default_devmode(name):
    res, blob = _docprops(name, None, DM_OUT_BUFFER)
    if res != 1:
        raise OSError("Не удалось получить настройки принтера по умолчанию.")
    return blob


def merge_devmode(name, blob):
    """Просит драйвер проверить и согласовать настройки."""
    res, out = _docprops(name, blob, DM_IN_BUFFER | DM_OUT_BUFFER)
    return out if res == 1 else blob


def edit_devmode_dialog(name, blob, hwnd):
    """Окно «Свойства принтера» драйвера. Возвращает новые настройки или None при отмене."""
    res, out = _docprops(name, blob, DM_IN_BUFFER | DM_OUT_BUFFER | DM_IN_PROMPT, hwnd)
    return out if res == 1 else None


def patch_devmode(blob, orientation=None, icm_off=None, paper=None, copies=1):
    """Меняет общедоступные поля DEVMODE (ориентация, ICM, бумага, копии); поля драйвера не трогает.
    paper — (ширина мм, высота мм, код Windows)."""
    ba = bytearray(blob)
    need = ctypes.sizeof(DEVMODEW)
    padded = len(ba) < need
    if padded:
        ba += bytearray(need - len(ba))
    dm = DEVMODEW.from_buffer(ba)
    if orientation:
        dm.dmOrientation = 1 if orientation == "portrait" else 2
        dm.dmFields |= DM_ORIENTATION
    if copies:
        dm.dmCopies = int(copies)
        dm.dmFields |= DM_COPIES
    if icm_off:
        dm.dmICMMethod = DMICMMETHOD_NONE
        dm.dmFields |= DM_ICMMETHOD
    if paper:
        w, h, code = paper
        dm.dmFields &= ~DM_FORMNAME
        if code:
            dm.dmPaperSize = code
            dm.dmFields = (dm.dmFields | DM_PAPERSIZE) & ~(DM_PAPERLENGTH | DM_PAPERWIDTH)
        else:
            dm.dmPaperSize = DMPAPER_USER
            dm.dmPaperWidth, dm.dmPaperLength = int(round(w * 10)), int(round(h * 10))
            dm.dmFields |= DM_PAPERSIZE | DM_PAPERLENGTH | DM_PAPERWIDTH
    return bytes(ba[:len(blob)])


def _create_dc(name, blob):
    wp, gd, wt = _win()
    buf = ctypes.create_string_buffer(blob, len(blob))
    dc = gd.CreateDCW("WINSPOOL", name, None, ctypes.cast(buf, ctypes.c_void_p))
    if not dc:
        raise OSError(f"Не удалось подключиться к принтеру «{name}».")
    return dc, buf


def printer_geometry(name, blob, orient):
    """Размер бумаги, печатное поле и разрешение для текущих настроек драйвера (мм, dpi)."""
    wp, gd, wt = _win()
    dc, _keep = _create_dc(name, blob)
    try:
        cap = lambda i: gd.GetDeviceCaps(dc, i)
        dpx, dpy = cap(88), cap(90)
        pw, ph, ox, oy = cap(110), cap(111), cap(112), cap(113)
        hr, vr = cap(8), cap(10)
        if dpx <= 0 or dpy <= 0 or pw <= 0 or ph <= 0:
            raise OSError("Драйвер вернул некорректные размеры бумаги.")
        mmx, mmy = 25.4 / dpx, 25.4 / dpy
        return {"paper": (pw * mmx, ph * mmy), "area": (ox * mmx, oy * mmy, (ox + hr) * mmx, (oy + vr) * mmy),
                "dpi": (dpx, dpy), "orient": orient, "virtual": False}
    finally:
        gd.DeleteDC(dc)


class PrinterJob:
    """Одно задание печати: открывается, принимает листы, закрывается."""

    def __init__(self, name, blob, title):
        self.name, self.blob, self.title = name, blob, title
        self.dc = None
        self.started = False

    def __enter__(self):
        wp, gd, wt = _win()
        self.dc, self._keep = _create_dc(self.name, self.blob)
        cap = lambda i: gd.GetDeviceCaps(self.dc, i)
        self.physw, self.physh, self.offx, self.offy = cap(110), cap(111), cap(112), cap(113)
        di = DOCINFOW(ctypes.sizeof(DOCINFOW), self.title, None, None, 0)
        if gd.StartDocW(self.dc, ctypes.byref(di)) <= 0:
            gd.DeleteDC(self.dc)
            self.dc = None
            raise OSError("Принтер не принял задание на печать.")
        self.started = True
        return self

    def page(self, img, band=512):
        """Печатает лист (картинка = вся бумага). Передача полосами — экономит память и надёжнее для драйверов."""
        from PIL import ImageWin
        wp, gd, wt = _win()
        gd.StartPage(self.dc)
        W, H = img.size
        x0, y0 = -self.offx, -self.offy
        for a in range(0, H, band):
            b = min(H, a + band)
            top = y0 + round(a * self.physh / H)
            bot = y0 + round(b * self.physh / H)
            ImageWin.Dib(img.crop((0, a, W, b))).draw(int(self.dc), (x0, top, x0 + self.physw, bot))
        gd.EndPage(self.dc)

    def finish(self):
        if self.dc and self.started:
            _win()[1].EndDoc(self.dc)
            self.started = False

    def abort(self):
        if self.dc and self.started:
            _win()[1].AbortDoc(self.dc)
            self.started = False

    def __exit__(self, et, ev, tb):
        if self.dc:
            if self.started:
                _win()[1].AbortDoc(self.dc)
            _win()[1].DeleteDC(self.dc)
            self.dc = None
        return False


# ---------------------------------------------------------------- печать: общая логика (окно и агент)

def paper_dims(o):
    """(ширина мм, высота мм, код бумаги Windows) выбранной бумаги."""
    if o["paper"] in VIRTUAL_PAPERS:
        return VIRTUAL_PAPERS[o["paper"]]
    return o["paper_w"], o["paper_h"], 0


def prepare_blob(printer, blob, orient, o):
    """Настройки драйвера для печати: ориентация, отключённый ICM Windows, при необходимости бумага."""
    paper = None
    if o["paper"] != PAPER_DRIVER:
        w, h, code = paper_dims(o)
        paper = (min(w, h), max(w, h), code)
    blob = patch_devmode(blob, orientation=orient, icm_off=o["icm_off"], paper=paper, copies=1)
    return merge_devmode(printer, blob)


_GEOM_CACHE = {}
GEOM_TTL = 120.0   # секунд: запросы к драйверу медленные, а результат для одних и тех же настроек не меняется


def clear_geom_cache():
    _GEOM_CACHE.clear()


def make_geom_for(printer, blob, o):
    """Функция orient -> геометрия листа (по драйверу принтера или условный лист). Результаты кэшируются по
    (принтер, настройки драйвера, бумага, ориентация) — перерисовка предпросмотра не дёргает драйвер заново."""
    bh = hashlib.md5(blob).hexdigest() if blob is not None else ""

    def geom_for(orient):
        key = (printer, bh, orient, o["paper"], o["paper_w"], o["paper_h"], o["icm_off"])
        hit = _GEOM_CACHE.get(key)
        if hit and time.time() - hit[0] < GEOM_TTL:
            return hit[1]
        g = geom_uncached(orient)
        if g.get("virtual") and printer and blob is not None:
            return g                      # драйвер не ответил — не запоминаем, попробуем снова
        if len(_GEOM_CACHE) > 64:
            _GEOM_CACHE.clear()
        _GEOM_CACHE[key] = (time.time(), g)
        return g

    def geom_uncached(orient):
        if o["paper"] == PAPER_DRIVER:
            if not printer or blob is None:
                raise RuntimeError("Принтер недоступен. Выберите принтер или размер бумаги из списка.")
            return printer_geometry(printer, prepare_blob(printer, blob, orient, o), orient)
        w, h, _ = paper_dims(o)
        g = virtual_geometry(w, h, orient)
        if printer and blob is not None:
            try:
                g2 = printer_geometry(printer, prepare_blob(printer, blob, orient, o), orient)
                if abs(g2["paper"][0] - g["paper"][0]) <= 2 and abs(g2["paper"][1] - g["paper"][1]) <= 2:
                    return g2
            except Exception:
                pass
        return g
    return geom_for


EXPORT_EXT = {"JPEG": ".jpg", "TIFF": ".tif", "PNG": ".png", "PDF": ".pdf"}


class PdfWriter:
    """Минимальный PDF: страницы дописываются в файл по одной (JPEG как есть), память не растёт с числом листов."""

    def __init__(self, path, icc=None):
        self.f = open(path, "wb")
        self.icc, self.icc_num = icc, None
        self.offs, self.kids, self.n = {}, [], 2          # объекты 1 (каталог) и 2 (страницы) — в конце
        self.f.write(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")

    def _obj(self, num, body):
        self.offs[num] = self.f.tell()
        self.f.write(b"%d 0 obj\n" % num + body + b"\nendobj\n")

    def add_jpeg(self, jpeg, w, h, ppi):
        pw, ph = w / ppi * 72.0, h / ppi * 72.0
        if self.icc and self.icc_num is None:           # профиль принтера записываем один раз на весь файл
            self.n += 1
            self.icc_num = self.n
            self._obj(self.icc_num, b"<< /N 3 /Alternate /DeviceRGB /Length %d >>\nstream\n" % len(self.icc) + self.icc + b"\nendstream")
        cs = b"[/ICCBased %d 0 R]" % self.icc_num if self.icc_num else b"/DeviceRGB"
        im, ct, pg = self.n + 1, self.n + 2, self.n + 3
        self.n += 3
        self._obj(im, (b"<< /Type /XObject /Subtype /Image /Width %d /Height %d /ColorSpace %s /BitsPerComponent 8 "
                       b"/Filter /DCTDecode /Length %d >>\nstream\n" % (w, h, cs, len(jpeg))) + jpeg + b"\nendstream")
        data = b"q %.3f 0 0 %.3f 0 0 cm /Im0 Do Q" % (pw, ph)
        self._obj(ct, b"<< /Length %d >>\nstream\n" % len(data) + data + b"\nendstream")
        self._obj(pg, b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 %.3f %.3f] /Resources << /XObject << /Im0 %d 0 R >> >> "
                      b"/Contents %d 0 R >>" % (pw, ph, im, ct))
        self.kids.append(pg)

    def close(self):
        if self.f.closed:
            return
        self._obj(1, b"<< /Type /Catalog /Pages 2 0 R >>")
        self._obj(2, b"<< /Type /Pages /Kids [" + b" ".join(b"%d 0 R" % k for k in self.kids) + b"] /Count %d >>" % len(self.kids))
        xref = self.f.tell()
        self.f.write(b"xref\n0 %d\n0000000000 65535 f \n" % (self.n + 1))
        for i in range(1, self.n + 1):
            self.f.write(b"%010d 00000 n \n" % self.offs[i])
        self.f.write(b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (self.n + 1, xref))
        self.f.close()


def shrink_sheet(img, pct):
    """Компенсация размера при печати без полей: лист уменьшается на pct % (вокруг — белое поле) или,
    при отрицательном значении, увеличивается с обрезкой краёв. Размер картинки не меняется."""
    try:
        pct = max(-10.0, min(10.0, float(pct or 0)))
    except (TypeError, ValueError):
        pct = 0.0
    if abs(pct) < 1e-6:
        return img
    w, h = img.size
    nw, nh = max(1, round(w * (1 - pct / 100.0))), max(1, round(h * (1 - pct / 100.0)))
    small = img.resize((nw, nh), RESAMPLE_HQ)
    out = Image.new("RGB", (w, h), "white")
    out.paste(small, ((w - nw) // 2, (h - nh) // 2))
    return out


def run_sheets_job(c, progress, cancel):
    """Печать (c['kind']=='print') или экспорт листов в файлы. Блокирующая функция для потока.
    progress(j, n, текст); cancel — объект с is_set().
    Результат: ("done", число листов, папка|None, [файлы]) или ("cancelled", сделано)."""
    cache, o, idxs = {}, c["o"], c["idxs"]
    n = len(idxs)

    def sheet_image(k):
        img = compose_sheet(c["plan"], k, c["photos"], c["ppi"], o, c["mode"], cache=cache)
        img = shrink_sheet(img, o.get("shrink_pct"))
        return apply_printer_profile(img, None, c["cm"]) if c["cm"] else img

    if c["kind"] == "print":
        title = c.get("title") or "PhotoCrop"
        total = n * o["sheet_copies"]
        if o.get("one_by_one", True):
            # как в Epson Photo+: каждый лист — отдельное задание, следующее уходит после паузы
            done = 0
            for j, k in enumerate(idxs):
                if cancel.is_set():
                    return ("cancelled", done)
                progress(j, n, f"Готовлю лист {j + 1} из {n}…")
                img = sheet_image(k)
                for r in range(o["sheet_copies"]):
                    if cancel.is_set():
                        return ("cancelled", done)
                    progress(j, n, f"Отправляю в печать лист {j + 1} из {n}" + (f" (копия {r + 1})" if o["sheet_copies"] > 1 else "") + "…")
                    with PrinterJob(c["printer"], c["blob"], f"{title} — {done + 1} из {total}") as job:
                        job.page(img)
                        job.finish()
                    done += 1
                    if done < total and o.get("job_pause", 0) > 0:
                        t_end = time.time() + o["job_pause"]
                        while time.time() < t_end:
                            if cancel.is_set():
                                return ("cancelled", done)
                            time.sleep(0.1)
                del img
            return ("done", done, None, [])
        with PrinterJob(c["printer"], c["blob"], title) as job:
            for j, k in enumerate(idxs):
                if cancel.is_set():
                    job.abort()
                    return ("cancelled", j)
                progress(j, n, f"Готовлю лист {j + 1} из {n}…")
                img = sheet_image(k)
                for _ in range(o["sheet_copies"]):
                    if cancel.is_set():
                        job.abort()
                        return ("cancelled", j)
                    progress(j, n, f"Печать листа {j + 1} из {n}…")
                    job.page(img)
                del img
            job.finish()
        return ("done", n * o["sheet_copies"], None, [])
    fmt = o["export_fmt"]
    ext = EXPORT_EXT[fmt]
    icc = c["cm"]["profile"] if (c["cm"] and c["cm"]["embed"]) else None
    outdir = Path(c["dir"])
    outdir.mkdir(parents=True, exist_ok=True)
    files, pdf, pdf_path = [], None, outdir / "Листы.pdf"
    old = [p for p in outdir.iterdir() if p.is_file() and (re.fullmatch(r"Лист_\d{3}\.(jpg|tif|png)", p.name, re.I) or p.name == "Листы.pdf")]
    if old:                                              # листы прошлого экспорта не должны смешаться с новыми
        arch = outdir / ("старые листы_" + time.strftime("%Y%m%d_%H%M%S"))
        arch.mkdir(exist_ok=True)
        for p in old:
            try:
                os.replace(p, arch / p.name)
            except OSError:
                pass
    try:
        for j, k in enumerate(idxs):
            if cancel.is_set():
                if pdf:
                    pdf.close()
                    pdf_path.unlink()
                    pdf = None
                return ("cancelled", j)
            progress(j, n, f"Лист {j + 1} из {n}…")
            img = sheet_image(k)
            if fmt == "PDF":                       # страница сразу дописывается в файл — листы в памяти не копятся
                pdf = pdf or PdfWriter(pdf_path, icc)                 # профиль в PDF — только если включено «встроить профиль»
                bio = io.BytesIO()
                img.save(bio, "JPEG", quality=95, subsampling=0)
                pdf.add_jpeg(bio.getvalue(), img.width, img.height, c["ppi"])
                del img, bio
                continue
            kw = {"dpi": (c["ppi"], c["ppi"])}
            if icc:
                kw["icc_profile"] = icc
            if fmt == "JPEG":
                kw.update(quality=95, subsampling=0)
            elif fmt == "TIFF":
                kw["compression"] = "tiff_lzw"
            dest = outdir / f"Лист_{k + 1:03d}{ext}"
            img.save(dest, fmt, **kw)
            files.append(str(dest))
            del img
        if pdf:
            pdf.close()
            files.append(str(pdf_path))
    finally:
        if pdf and not pdf.f.closed:
            pdf.f.close()
    return ("done", n, str(outdir), files)


# ---------------------------------------------------------------- агент: управление без окна
# Всё, что делает человек в окне (папка, рамка, коррекция, профиль, листы, принтер, очередь),
# доступно ИИ-агенту как набор команд. Результаты — всегда JSON с цифрами (размеры, dpi, листы,
# статистика изображения), так что «видеть» экран не нужно: состояние можно проверить числами,
# а при желании получить картинку (preview_photo / render_sheet с inline=true).

AGENT_DIR = SETTINGS_PATH.parent
AGENT_STATE = AGENT_DIR / "agent_state.json"
AGENT_LOG = AGENT_DIR / "agent.log"
AGENT_VERSION = "1.2"


class AgentError(Exception):
    def __init__(self, msg, code="error", **extra):
        super().__init__(msg)
        self.code, self.extra = code, extra


# ---- DEVMODE: чтение/запись общедоступных полей драйвера

DM_FIELDS = {   # имя: (флаг DM_*, поле DEVMODE)
    "orientation": (0x1, "dmOrientation"), "paper": (0x2, "dmPaperSize"), "paper_length": (0x4, "dmPaperLength"),
    "paper_width": (0x8, "dmPaperWidth"), "scale": (0x10, "dmScale"), "copies": (0x100, "dmCopies"),
    "source": (0x200, "dmDefaultSource"), "quality": (0x400, "dmPrintQuality"), "color": (0x800, "dmColor"),
    "duplex": (0x1000, "dmDuplex"), "y_resolution": (0x2000, "dmYResolution"), "tt_option": (0x4000, "dmTTOption"),
    "collate": (0x8000, "dmCollate"), "icm_method": (0x800000, "dmICMMethod"), "icm_intent": (0x1000000, "dmICMIntent"),
    "media_type": (0x2000000, "dmMediaType"), "dither": (0x4000000, "dmDitherType"),
}
DM_FORM = 0x10000
DM_ENUMS = {
    "orientation": {"portrait": 1, "landscape": 2}, "color": {"mono": 1, "color": 2},
    "duplex": {"simplex": 1, "long": 2, "short": 3},
    "quality": {"draft": -1, "low": -2, "medium": -3, "high": -4},
    "icm_method": {"none": 1, "system": 2, "driver": 3, "device": 4},
    "icm_intent": {"saturation": 1, "contrast": 2, "colorimetric": 3, "absolute": 4},
    "media_type": {"standard": 1, "transparency": 2, "glossy": 3},
    "collate": {"false": 0, "true": 1},
}


def _w2s(arr):
    return "".join(chr(c) for c in arr if c)


def _dm(blob):
    ba = bytearray(blob)
    if len(ba) < ctypes.sizeof(DEVMODEW):
        ba += bytearray(ctypes.sizeof(DEVMODEW) - len(ba))
    return DEVMODEW.from_buffer(ba), ba


def devmode_read(blob):
    """Общедоступные поля DEVMODE -> словарь. Частные (специфические для драйвера) настройки здесь не видны."""
    dm, _ = _dm(blob)
    f = dm.dmFields
    out = {"device": _w2s(dm.dmDeviceName), "driver_version": dm.dmDriverVersion, "size": dm.dmSize,
           "private_bytes": dm.dmDriverExtra, "settings": {}, "names": {}}
    for k, (flag, attr) in DM_FIELDS.items():
        if f & flag:
            v = getattr(dm, attr)
            out["settings"][k] = v
            for nm, num in DM_ENUMS.get(k, {}).items():
                if num == v:
                    out["names"][k] = nm
    if f & DM_FORM:
        out["settings"]["form"] = _w2s(dm.dmFormName)
    return out


def devmode_write(blob, changes):
    """Записывает поля в DEVMODE (значения — числа или имена из DM_ENUMS). Возвращает новый blob."""
    dm, ba = _dm(blob)
    changes = dict(changes)
    mm = changes.pop("paper_mm", None)
    if mm is not None:
        try:
            w, h = float(mm[0]), float(mm[1])
        except Exception:
            raise AgentError("paper_mm: ожидается [ширина_мм, высота_мм]", "bad_value")
        changes.update(paper=DMPAPER_USER, paper_width=round(w * 10), paper_length=round(h * 10))
    form = changes.pop("form", None)
    for k, v in changes.items():
        if k not in DM_FIELDS:
            raise AgentError(f"Неизвестное поле драйвера «{k}». Доступно: " + ", ".join(sorted(list(DM_FIELDS) + ["form", "paper_mm"])),
                             "bad_key")
        flag, attr = DM_FIELDS[k]
        if isinstance(v, bool):
            v = int(v)
        if isinstance(v, str):
            tbl = DM_ENUMS.get(k, {})
            if v.strip().lower() in tbl:
                v = tbl[v.strip().lower()]
            else:
                try:
                    v = int(float(v))
                except ValueError:
                    raise AgentError(f"{k}: значение «{v}» не распознано. Допустимо: " + (", ".join(tbl) or "число"), "bad_value")
        try:
            v = int(v)
        except (TypeError, ValueError):
            raise AgentError(f"{k}: ожидается число или одно из: " + ", ".join(DM_ENUMS.get(k, {})), "bad_value")
        if attr in ("dmICMMethod", "dmICMIntent", "dmMediaType", "dmDitherType"):
            if v < 0:
                raise AgentError(f"{k}: отрицательное значение недопустимо", "bad_value")
        elif not -32768 <= v <= 32767:
            raise AgentError(f"{k}: значение вне диапазона", "bad_value")
        setattr(dm, attr, v)
        dm.dmFields |= flag
    if form is not None:
        form = str(form)[:31]
        for i in range(32):
            dm.dmFormName[i] = ord(form[i]) if i < len(form) else 0
        dm.dmFields = (dm.dmFields | DM_FORM) & ~(DM_PAPERSIZE | DM_PAPERLENGTH | DM_PAPERWIDTH)
    elif "paper" in changes or mm is not None:
        dm.dmFields &= ~DM_FORM
    return bytes(ba[:len(blob)])


# ---- возможности принтера (DeviceCapabilitiesW)

DC = {"fields": 1, "papers": 2, "papersize": 3, "bins": 6, "duplex": 7, "binnames": 12, "resolutions": 13,
      "papernames": 16, "orientation": 17, "copies": 18, "collate": 22, "mediaready": 29, "colordevice": 32,
      "mediatypenames": 34, "mediatypes": 35}


def printer_capabilities(name):
    wp, gd, wt = _win()
    fn = wp.DeviceCapabilitiesW
    fn.argtypes = [wt.LPCWSTR, wt.LPCWSTR, wt.WORD, ctypes.c_void_p, ctypes.c_void_p]
    fn.restype = ctypes.c_int

    def items(cap, size):
        n = fn(name, None, DC[cap], None, None)
        if n <= 0:
            return []
        buf = ctypes.create_string_buffer(n * size)
        fn(name, None, DC[cap], buf, None)
        return [buf.raw[i * size:(i + 1) * size] for i in range(n)]

    def scalar(cap):
        return fn(name, None, DC[cap], None, None)

    txt = lambda b: b.decode("utf-16le", "ignore").split("\0")[0]
    codes = [struct.unpack("<H", b)[0] for b in items("papers", 2)]
    names = [txt(b) for b in items("papernames", 128)]
    sizes = [struct.unpack("<ii", b) for b in items("papersize", 8)]
    papers = []
    for i, c in enumerate(codes):
        papers.append({"code": c, "name": names[i] if i < len(names) else "",
                       "width_mm": sizes[i][0] / 10 if i < len(sizes) else None,
                       "height_mm": sizes[i][1] / 10 if i < len(sizes) else None})
    bins = [{"code": struct.unpack("<H", b)[0], "name": n} for b, n in zip(items("bins", 2), [txt(b) for b in items("binnames", 48)])]
    mt_codes = [struct.unpack("<I", b)[0] for b in items("mediatypes", 4)]
    mt_names = [txt(b) for b in items("mediatypenames", 128)]
    media = [{"code": c, "name": mt_names[i] if i < len(mt_names) else ""} for i, c in enumerate(mt_codes)]
    ready = [txt(b) for b in items("mediaready", 128)]
    res = [struct.unpack("<ii", b) for b in items("resolutions", 8)]
    return {"papers": papers, "paper_ready": ready, "bins": bins, "media_types": media,
            "resolutions_dpi": [list(r) for r in res], "color": bool(scalar("colordevice") == 1),
            "duplex": bool(scalar("duplex") == 1), "max_copies": scalar("copies"), "collate": bool(scalar("collate") == 1)}


# ---- очередь печати и состояние принтера (PowerShell, без привязки к окну)

PRINTER_STATUS = {1: "other", 2: "unknown", 3: "idle", 4: "printing", 5: "warmup", 6: "stopped", 7: "offline"}
PRINTER_ERROR = {0: "unknown", 1: "other", 2: "no_error", 3: "low_paper", 4: "no_paper", 5: "low_toner", 6: "no_toner",
                 7: "door_open", 8: "jammed", 9: "offline", 10: "service_requested", 11: "output_bin_full"}


def _ps(script, env=None, timeout=40):
    if sys.platform != "win32":
        raise AgentError("Управление очередью печати доступно только в Windows.", "windows_only")
    import subprocess
    e = dict(os.environ)
    e.update({k: str(v) for k, v in (env or {}).items()})
    pre = "[Console]::OutputEncoding=[Text.Encoding]::UTF8; $ErrorActionPreference='Stop'; "
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", pre + script],
                           capture_output=True, timeout=timeout, env=e, creationflags=0x08000000)
    except subprocess.TimeoutExpired:
        raise AgentError("PowerShell не ответил вовремя.", "timeout")
    out = r.stdout.decode("utf-8", "replace").strip()
    if r.returncode != 0:
        raise AgentError("Ошибка очереди печати: " + (r.stderr.decode("utf-8", "replace").strip() or out)[:500], "spooler_error")
    if not out:
        return None
    try:
        return json.loads(out)
    except ValueError:
        return out


def spooler_printer_status(name):
    d = _ps("$p = Get-CimInstance Win32_Printer | Where-Object Name -eq $env:PC_PRINTER; if(-not $p){'null'}else{"
            "$p | Select-Object Name,DriverName,PortName,WorkOffline,PrinterStatus,DetectedErrorState,Default | ConvertTo-Json -Compress}",
            {"PC_PRINTER": name})
    if not d:
        raise AgentError(f"Принтер «{name}» не найден в системе.", "no_printer")
    return {"name": d.get("Name"), "driver": d.get("DriverName"), "port": d.get("PortName"),
            "offline": bool(d.get("WorkOffline")), "default": bool(d.get("Default")),
            "status": PRINTER_STATUS.get(d.get("PrinterStatus"), str(d.get("PrinterStatus"))),
            "error": PRINTER_ERROR.get(d.get("DetectedErrorState"), str(d.get("DetectedErrorState")))}


def spooler_queue(name):
    d = _ps("$j = @(Get-PrintJob -PrinterName $env:PC_PRINTER | Select-Object Id,DocumentName,UserName,TotalPages,PagesPrinted,Size,"
            "@{n='Status';e={$_.JobStatus.ToString()}},@{n='Submitted';e={$_.SubmittedTime.ToString('s')}}); ConvertTo-Json -InputObject $j -Compress",
            {"PC_PRINTER": name})
    if isinstance(d, dict):
        d = [d]
    return [{"id": j.get("Id"), "document": j.get("DocumentName"), "user": j.get("UserName"), "status": j.get("Status"),
             "pages": j.get("TotalPages"), "pages_printed": j.get("PagesPrinted"), "bytes": j.get("Size"),
             "submitted": j.get("Submitted")} for j in (d or [])]


SPOOLER_ACTIONS = {"cancel": "Remove-PrintJob", "pause": "Suspend-PrintJob", "resume": "Resume-PrintJob", "restart": "Restart-PrintJob"}


def spooler_job_action(name, job_id, action):
    cmd = SPOOLER_ACTIONS[action]
    _ps(f"{cmd} -PrinterName $env:PC_PRINTER -ID ([int]$env:PC_JOB)", {"PC_PRINTER": name, "PC_JOB": int(job_id)})


def spooler_clear(name):
    _ps("Get-PrintJob -PrinterName $env:PC_PRINTER | Remove-PrintJob", {"PC_PRINTER": name})


def spooler_pause_printer(name, pause):
    m = "Pause" if pause else "Resume"
    _ps("$p = Get-CimInstance Win32_Printer | Where-Object Name -eq $env:PC_PRINTER; Invoke-CimMethod -InputObject $p -MethodName "
        + m + " | Out-Null", {"PC_PRINTER": name})


# ---- анализ изображения (числа вместо глаз)

def analyze_image(img):
    from PIL import ImageStat
    im = to_rgb(img).copy()                          # не трогаем чужую картинку (предпросмотр на экране)
    im.thumbnail((480, 480), RESAMPLE_FAST)
    L = im.convert("L")
    hist = L.histogram()
    n = float(sum(hist)) or 1.0

    def pct(p):
        acc, lim = 0, p * n
        for i, h in enumerate(hist):
            acc += h
            if acc >= lim:
                return i
        return 255

    st = ImageStat.Stat(L)
    rgb = ImageStat.Stat(im).mean
    sat = ImageStat.Stat(im.convert("HSV").getchannel(1)).mean[0] / 255.0
    edges = L.filter(ImageFilter.FIND_EDGES)
    sharp = ImageStat.Stat(edges).var[0] ** 0.5
    small = edges.resize((48, 48), RESAMPLE_FAST)
    px = list(small.tobytes())   # режим L: по байту на пиксель (getdata() устарел)
    wsum = sum(v * v for v in px) or 1.0
    fx = sum((i % 48 + 0.5) / 48 * v * v for i, v in enumerate(px)) / wsum
    fy = sum((i // 48 + 0.5) / 48 * v * v for i, v in enumerate(px)) / wsum
    return {"size": list(img.size), "mean_luma": round(st.mean[0], 1), "contrast_std": round(st.stddev[0], 1),
            "p1": pct(0.01), "p50": pct(0.5), "p99": pct(0.99),
            "shadow_clip_pct": round(sum(hist[:6]) / n * 100, 2), "highlight_clip_pct": round(sum(hist[250:]) / n * 100, 2),
            "saturation": round(sat, 3), "mean_rgb": [round(v, 1) for v in rgb], "warmth_r_minus_b": round(rgb[0] - rgb[2], 1),
            "sharpness": round(sharp, 2), "focus_point": [round(fx, 3), round(fy, 3)],
            "white_pct": round(sum(hist[252:]) / n * 100, 2)}


def suggest_adjust(an, strength=1.0):
    """Осторожная авто-коррекция по статистике: яркость к ~средне-серому и растяжение узкого диапазона."""
    mean = max(1.0, an["mean_luma"])
    bright = 0.0
    if abs(mean - 118) > 8:
        bright = max(-40.0, min(40.0, (118.0 / mean - 1.0) * 100.0 * 0.7))
    rng = max(1, an["p99"] - an["p1"])
    contrast = min(30.0, (215.0 / rng - 1.0) * 100.0 * 0.5) if rng < 190 else 0.0
    return {"bright": round(bright * strength, 1), "contrast": round(max(0.0, contrast) * strength, 1)}


ENHANCE_KEYS = ("bright", "contrast", "shadows", "highlights", "sat", "vib", "auto", "denoise", "sharp", "sharp_radius", "sharp_thr")


def enhance_adj(an, level=1):
    """Улучшение под фотопечать на струйном принтере Epson (шестицветные водные чернила, например L8050) с
    индивидуальным ICC-профилем. Профиль уже отвечает за точность цвета, поэтому здесь правятся только то, что
    профиль не исправляет: общая светлота (отпечаток темнее экрана), детали в тенях и светах, мягкая красочность
    и резкость под размер печати. level 1 — осторожно, level 2 — сильнее и подстраивается под снимок."""
    lvl = 2 if level >= 2 else 1
    mean0 = mean = max(1.0, an["mean_luma"])
    rng = max(1.0, an["p99"] - an["p1"])
    target = 126.0 if lvl == 2 else 122.0
    cap = 24.0 if lvl == 2 else 14.0
    # растягиваем уровни только у плоских снимков средней светлоты: у светлых (high-key) растяжение ставит
    # «чёрную точку» и затемняет весь кадр, у тёмных (ночь) — ломает настроение
    stretch = 120 <= rng < (200 if lvl == 1 else 225) and 80 <= mean0 <= 150
    if stretch:                                      # яркость считаем уже после растяжения уровней
        mean = max(1.0, min(254.0, (mean - an["p1"]) / rng * 255.0))
    # улучшение для печати никогда не затемняет: отпечаток и так темнее экрана
    bright = max(0.0, (target - mean) / target * 100.0 * (0.55 if lvl == 2 else 0.4))
    if mean0 < 170:
        bright += 5.0 if lvl == 2 else 3.0           # запас на то, что бумага темнее светящегося экрана
    if mean0 < 75:                                   # тёмный (night/low-key): оставляем настроение кадра
        bright = min(bright, 14.0 if lvl == 2 else 8.0)
    bright = min(cap, bright)
    shadows = (10.0 if lvl == 1 else 16.0) + min(12.0, an["shadow_clip_pct"] * 1.5)
    if mean0 > 150 or mean0 < 75:                    # светлый снимок: тени и так открыты; ночной: не высветляем черноту
        shadows *= 0.5
    clip = an["highlight_clip_pct"]                  # света приглушаем, только когда они действительно выбиты
    highlights = -min(10.0 if lvl == 1 else 14.0, max(0.0, clip - 0.5) * (1.5 if lvl == 1 else 2.0))
    out = {"bright": bright, "shadows": shadows, "highlights": highlights,
           "contrast": 5.0 if lvl == 1 else 10.0}
    if mean0 < 90:                                   # тёмный кадр: контраст вокруг середины только вдавит тени в чёрное
        out["contrast"] = 0.0
    if stretch:                                      # плоский снимок: растянуть уровни
        out["auto"] = "contrast"
        out["contrast"] = out["contrast"] * 0.5
    dull = an["saturation"] < 0.22
    out["vib"] = (8.0 if lvl == 1 else 18.0) + (6.0 if dull and lvl == 2 else 0.0)
    if lvl == 2:
        out["sat"] = 4.0 if dull else 0.0
        if mean < 80:
            out["denoise"] = 20.0
    out["sharp"] = 70.0 if lvl == 1 else 100.0 + (30.0 if an.get("sharpness", 99) < 8 else 0.0)
    out["sharp_radius"] = 0.8 if lvl == 1 else 0.9
    out["sharp_thr"] = 2
    return clean_adj({k: round(v, 1) if isinstance(v, float) else v for k, v in out.items()})


# ---- описание команд (для help, CLI и MCP)

PHOTO = ("photo", "any", "Photo: 0-based index, file name / stem / unique substring, or omitted = current photo.")
PHOTOS = ("photo", "any", "Photo ref, list of refs, or \"all\". Omitted = current photo.")
WAITP = [("wait", "boolean", "Block until the job finishes (default true)."),
         ("timeout", "number", "Seconds to wait before returning the still-running job (default 120).")]
SPEC = {
    "help": ("List commands, or describe one.", [("command", "string", "Command name.")]),
    "status": ("Full snapshot of the session: folder, photos, format/orientation/mode, save options, colour profile, printer, print options, jobs.", []),
    "reset_session": ("Forget folder, crops and settings of this agent session.", []),
    "open_folder": ("Load all photos of a folder (natural sort). Resets crops.", [("path", "string", "Folder path."), ("recursive", "boolean", "Include sub-folders (default false). Folders where results are saved are skipped by path.")]),
    "list_photos": ("List photos with size, crop summary and flags.", [("offset", "integer", ""), ("limit", "integer", "Default 200.")]),
    "select_photo": ("Make a photo current.", [PHOTO]),
    "photo_info": ("Everything about one photo: size, frame geometry (corners as fractions), effective dpi, part of the frame outside the photo, adjustments.", [PHOTO]),
    "analyze_photo": ("Numeric analysis (brightness, clipping, contrast, saturation, sharpness, focus point) of the whole photo or of the crop frame.",
                      [PHOTO, ("region", "string", "\"frame\" (default) or \"full\".")]),
    "preview_photo": ("Render the cropped result (with adjustments). Saves a PNG and returns analysis; inline=true also returns a small JPEG.",
                      [PHOTO, ("path", "string", "Where to save the PNG."), ("max_px", "integer", "Long side, default 800."), ("inline", "boolean", "")]),
    "set_crop": ("Set crop frame values (any subset). cx,cy = frame centre as fractions 0..1 of the photo; scale = frame size relative to the largest inscribed frame (0.05..3); angle = degrees clockwise; orient = portrait|landscape|auto; rotation = photo rotation 0/90/180/270; copies = print copies.",
                 [PHOTOS, ("cx", "number", ""), ("cy", "number", ""), ("scale", "number", ""), ("angle", "number", ""),
                  ("orient", "string", ""), ("rotation", "integer", ""), ("copies", "integer", "")]),
    "move_crop": ("Relative frame change: dx,dy in fractions of the photo, dscale multiplies the size, dangle adds degrees.",
                  [PHOTOS, ("dx", "number", ""), ("dy", "number", ""), ("dscale", "number", ""), ("dangle", "number", "")]),
    "auto_crop": ("Automatic frame. method: center | focus (centre on the sharpest/most detailed area) | fill (largest frame, centred) | "
                  "smart (SmartCrop: keep people and pets uncut; returns status ok|note|check|manual with reasons and alternatives per photo — look at `review`).",
                  [PHOTOS, ("method", "string", "center|focus|fill|smart"), ("scale", "number", "Frame size, default 1."),
                   ("apply", "boolean", "smart: false = only analyze, do not change frames."), ("keep_manual", "boolean", "smart: skip photos whose frame was already changed."),
                   ("priority", "any", "smart: order of importance, e.g. head,torso,pet,hands,arms,legs,feet,other"),
                   ("algo", "string", "smart: simple (default; weighted cost) | enhanced (body parts sized from the head; importance strictly in order head > torso > hands > arms > legs > feet)"),
                   ("orient_mode", "string", "smart: photo (default; a landscape photo stays landscape) | person ('Человек': the AI picks portrait/landscape per photo by how little of the people it cuts)."),
                   ("config", "object", "smart: extra SmartCrop settings.")]),
    "reset_crop": ("Reset frame (and optionally everything) of photo(s).", [PHOTOS, ("everything", "boolean", "Also copies, rotation, adjustments.")]),
    "rotate_photo": ("Rotate the photo itself by 90/180/270 degrees (resets the frame).", [PHOTOS, ("degrees", "integer", "90, -90, 180, 270")]),
    "set_copies": ("Number of copies to print per photo.", [PHOTOS, ("copies", "integer", "1..99")]),
    "set_adjust": ("Per-photo adjustments (QImage-style) for saving and printing: bright/contrast/sat/vib/temp/tint/r/g/b/shadows/highlights -100..100, gamma 0.2..5, auto contrast|color|off, bw/sepia bool, denoise 0..100, sharp 0..500 (%), sharp_radius, sharp_thr. 'photo' may be 'all'.",
                   [PHOTOS, ("bright", "number", ""), ("contrast", "number", ""), ("sat", "number", ""), ("gamma", "number", ""), ("bw", "boolean", ""),
                    ("vib", "number", "Vibrance: boosts muted colours."), ("temp", "number", "-100 cool .. +100 warm"), ("tint", "number", "-100 green .. +100 magenta"),
                    ("r", "number", "Red balance"), ("g", "number", "Green balance"), ("b", "number", "Blue balance"),
                    ("shadows", "number", "Lift shadows (+) / deepen (-)"), ("highlights", "number", "Brighten (+) / recover (-) highlights"),
                    ("auto", "string", "contrast | color | bw | off — auto levels (bw = automatic black-and-white with enhancement)"), ("sepia", "boolean", ""), ("denoise", "number", "Colour-noise reduction 0..100"),
                    ("sharp", "number", ""), ("sharp_radius", "number", ""), ("sharp_thr", "integer", ""), ("reset", "boolean", "Clear adjustments first.")]),
    "auto_adjust": ("Suggest (and by default apply) brightness/contrast from image statistics.",
                    [PHOTOS, ("strength", "number", "0..1.5, default 1"), ("apply", "boolean", "Default true.")]),
    "list_formats": ("Print formats, orientations, modes, intents, file types and print-option enums.", []),
    "set_format": ("Print format (e.g. \"10x15\", \"A5\", \"A4\", \"9x13\"…).", [("format", "string", "")]),
    "set_orientation": ("auto | portrait | landscape (clears per-photo overrides).", [("orientation", "string", "")]),
    "set_mode": ("crop (fill the sheet) | fit (whole photo, white margins).", [("mode", "string", "")]),
    "set_save_options": ("Options of save_files: dpi, resize, filetype (JPEG|PNG|TIFF), quality, outdir, subfolder.",
                         [("dpi", "number", ""), ("resize", "boolean", ""), ("filetype", "string", ""), ("quality", "integer", ""),
                          ("outdir", "string", ""), ("out_mode", "string", "orig = next to each original photo, in subfolder out_name; custom = outdir"),
                          ("out_name", "string", "Subfolder name for out_mode=orig (default 'Готовые')."), ("subfolder", "boolean", ""), ("copies_in_name", "boolean", "Append _xN to file name when copies > 1.")]),
    "set_color_profile": ("Printer ICC profile conversion for saving/printing. on, icc (path), intent, bpc, embed.",
                          [("on", "boolean", ""), ("icc", "string", ""), ("intent", "string", "relative|perceptual|saturation|absolute"),
                           ("bpc", "boolean", ""), ("embed", "boolean", "")]),
    "get_color_profile": ("Current profile settings and what the profile file supports.", []),
    "save_files": ("Crop and save photos as files (applies crop, adjustments, ICC profile). Without `photo` ALL photos of the folder are saved.",
                   [PHOTOS] + WAITP),
    "list_printers": ("Installed printers (Windows).", []),
    "select_printer": ("Choose the printer; loads its stored driver settings.", [("name", "string", "")]),
    "driver_settings": ("Decoded public driver settings (DEVMODE) of the selected printer.", []),
    "set_driver_settings": ("Change driver settings: orientation, paper (code), paper_mm [w,h], form (name), copies, quality (draft|low|medium|high|dpi), color (mono|color), "
                            "duplex, media_type (standard|glossy|code), source (tray), y_resolution, icm_method (none|system|driver|device), icm_intent, collate, scale, dither. "
                            "The driver may refuse values; the reply shows the actual result and `rejected`. Driver-private options (e.g. Epson's colour-management switch) "
                            "cannot be set here — set them once in the GUI printer properties; they are stored and reused.",
                            [("settings", "object", "Key/values; keys may also be given at top level.")]),
    "reset_driver_settings": ("Back to the driver's defaults.", []),
    "driver_capabilities": ("Papers (code, name, size), trays, media types, resolutions, colour, duplex.", []),
    "get_print_options": ("Typed print options (layout, margins, copies, ppi, adjustments…).", []),
    "set_print_options": ("Set print options. See list_formats.print_options for keys/values. Enum values accept English codes.",
                          [("options", "object", "Key/values; keys may also be given at top level.")]),
    "list_presets": ("Saved print presets (shared with the GUI).", []),
    "save_preset": ("Save printer + print options + driver settings as a preset.", [("name", "string", "")]),
    "load_preset": ("Apply a preset.", [("name", "string", "")]),
    "delete_preset": ("Delete a preset.", [("name", "string", "")]),
    "plan_print": ("Layout: sheets, positions of every photo (mm), warnings, dpi of each photo, ppi.",
                   [("photos", "array", "Restrict to these photo refs."), ("sheets", "array", "")]),
    "render_sheet": ("Render one sheet to a PNG file; returns image statistics (and a JPEG when inline=true).",
                     [("sheet", "integer", "0-based, default 0"), ("path", "string", ""), ("ppi", "integer", "Preview ppi, default 100"),
                      ("proof", "boolean", "Simulate the printer profile."), ("inline", "boolean", ""), ("photos", "array", "")]),
    "preflight": ("Checks before printing; every item has level error|warning|info and a code. ready=false when any error exists (no printer, photo does not fit the sheet, <100 dpi, …).",
                  [("photos", "array", ""), ("allow_low_res", "boolean", "Downgrade the <100 dpi error to a warning.")]),
    "print": ("Print the planned sheets to the selected printer. dry_run=true only runs the checks.",
              [("dry_run", "boolean", ""), ("photos", "array", "Restrict to these photo refs."), ("sheets", "array", "0-based sheet numbers."),
               ("max_sheets", "integer", "Safety limit, default 200."), ("strict", "boolean", "Refuse when warnings exist."), ("allow_low_res", "boolean", "Print even photos under 100 dpi."),
               ("title", "string", "Spooler document name.")] + WAITP),
    "export_sheets": ("Save sheets as JPEG/TIFF/PNG/PDF files instead of printing.",
                      [("dir", "string", ""), ("format", "string", "JPEG|TIFF|PNG|PDF"), ("photos", "array", ""), ("sheets", "array", "")] + WAITP),
    "printer_status": ("Printer state from the system: status, offline, error (no_paper, jammed…).", [("printer", "string", "Default: selected.")]),
    "queue": ("Jobs in the printer's spooler queue.", [("printer", "string", "")]),
    "job_control": ("Spooler job: cancel | pause | resume | restart.", [("job_id", "integer", ""), ("action", "string", ""), ("printer", "string", "")]),
    "clear_queue": ("Delete every job in the printer queue.", [("printer", "string", "")]),
    "pause_printer": ("Pause the printer queue.", [("printer", "string", "")]),
    "resume_printer": ("Resume the printer queue.", [("printer", "string", "")]),
    "wait_queue": ("Wait until the spooler has no job with the given document title (default: last print job).",
                   [("title", "string", ""), ("timeout", "number", "Default 300."), ("printer", "string", "")]),
    "jobs": ("Jobs started by this session (print / export / save).", []),
    "job_status": ("Progress and result of a session job.", [("job_id", "string", ""), ("wait", "boolean", ""), ("timeout", "number", "")]),
    "cancel_job": ("Cancel a running session job (stops sending further sheets).", [("job_id", "string", "")]),
    "print_configuration": ("One-shot report of everything that determines the printed result.", []),
    "save_project": ("Write crops and settings to a JSON file.", [("path", "string", "")]),
    "load_project": ("Read crops and settings from a JSON file.", [("path", "string", "")]),
    "get_log": ("Last audit-log entries of agent commands.", [("tail", "integer", "Default 30.")]),
    "undo": ("Undo the last change(s) of frames, rotation, copies, adjustments, format/orientation/mode.", [("steps", "integer", "Default 1.")]),
    "redo": ("Redo what undo reverted.", [("steps", "integer", "Default 1.")]),
    "reload": ("Rescan the open folder; frames of photos that are still there are kept, new photos are added, missing ones dropped.",
               [("recursive", "boolean", "Default: as opened.")]),
}
UNDOABLE = {"set_crop", "move_crop", "auto_crop", "reset_crop", "rotate_photo", "set_copies", "set_adjust", "auto_adjust",
            "set_format", "set_orientation", "set_mode"}
READONLY = {"help", "status", "list_photos", "photo_info", "analyze_photo", "preview_photo", "list_formats", "get_color_profile",
            "list_printers", "driver_settings", "driver_capabilities", "get_print_options", "list_presets", "plan_print",
            "render_sheet", "preflight", "printer_status", "queue", "wait_queue", "jobs", "job_status", "print_configuration", "get_log"}

ENUM_FIELDS = {"layout": LAYOUTS, "range": RANGES, "pages": PAGES, "orient": PRINT_ORIENTS, "align": ALIGNS,
               "caption": CAPTIONS, "border_color": BORDER_COLORS}
ENUM_BY_FIELD = {   # поле -> {английский код -> русская подпись}
    "layout": {"single": "Одно фото на листе", "multi": "Несколько фото на листе"},
    "range": {"all": "Все фото", "current": "Текущее фото", "edited": "Изменённые (✎)"},
    "pages": {"all": "Все листы", "current": "Только текущий лист"},
    "orient": {"auto": "Авто", "portrait": "Книжная", "landscape": "Альбомная"},
    "align": {"center": "По центру", "topleft": "Сверху слева"},
    "caption": {"none": "Нет", "name": "Имя файла", "name_n": "Номер и имя файла"},
    "border_color": {"white": "Белая", "black": "Чёрная", "gray": "Серая"},
}
INTENT_CODES = {"relative": "Относительный колориметрический", "perceptual": "Перцепционный",
                "saturation": "Насыщенность", "absolute": "Абсолютный колориметрический"}


def _truthy(v):
    if isinstance(v, str):
        return v.strip().lower() in ("1", "true", "yes", "y", "on", "да")
    return bool(v)


def _jsonable(o):
    if isinstance(o, (bytes, bytearray)):
        return base64.b64encode(bytes(o)).decode()
    if isinstance(o, Path):
        return str(o)
    if isinstance(o, set):
        return sorted(o)
    return str(o)


class AgentJob:
    def __init__(self, kind, title):
        self.id = f"{kind}-{int(time.time() * 1000) % 10 ** 9:09d}"
        self.kind, self.title, self.state = kind, title, "running"
        self.done, self.total, self.text = 0, 0, ""
        self.result, self.error = None, None
        self.cancel, self.finished = threading.Event(), threading.Event()
        self.t0, self.t1 = time.time(), None

    def info(self):
        t = time.time()
        d = {"job_id": self.id, "kind": self.kind, "state": self.state, "title": self.title,
             "progress": {"done": self.done, "total": self.total, "text": self.text},
             "seconds": round((self.t1 or t) - self.t0, 1)}
        if self.result is not None:
            d["result"] = self.result
        if self.error:
            d["error"] = self.error
        return d


class AgentSession:
    """Состояние и команды для управления программой без окна."""

    def __init__(self, persist=True, state_path=None, log_path=None):
        self.persist = persist
        self.state_path = Path(state_path) if state_path else AGENT_STATE
        self.log_path = Path(log_path) if log_path else AGENT_LOG
        self.lock = threading.RLock()
        self.jobs, self.last_title, self.active_preset = {}, None, None
        self.settings = load_settings()
        self._reset_state()

    # ---------- состояние
    def _reset_state(self):
        s = self.settings
        self.files, self.states, self.folder, self.idx, self.recursive = [], {}, None, -1, False
        self.fmt_name = s.get("format") if s.get("format") in FORMATS else "10×15 см"
        self.orient_name = s.get("orient") if s.get("orient") in ORIENTS else "Авто (по фото)"
        self.mode_name = s.get("mode") if s.get("mode") in MODES else "Кадрировать (заполнить лист)"
        self.save = {"dpi": float(s.get("dpi", 300) or 300), "resize": bool(s.get("resize", True)),
                     "filetype": s.get("filetype") if s.get("filetype") in FILETYPES else "JPEG",
                     "quality": int(s.get("quality", 95) or 95), "outdir": "", "subfolder": bool(s.get("subfolder", True)),
                     "out_mode": "custom", "out_name": OUT_SUBDIR,
                     "copies_in_name": bool(s.get("copies_in_name", True))}
        self.cm = {"on": bool(s.get("cm_on", False)), "icc": s.get("icc", ""),
                   "intent": s.get("intent") if s.get("intent") in INTENTS else "Относительный колориметрический",
                   "bpc": bool(s.get("bpc", True)), "embed": bool(s.get("embed", False))}
        self.popts = dict(PRINT_DEFAULTS)
        self.popts.update({k: v for k, v in s.get("print", {}).items() if k in PRINT_DEFAULTS})
        self._undo, self._redo = [], []                  # откат команд агента (рамки, поворот, копии, коррекция, формат)
        self.smart = {}                                  # последние решения SmartCrop: {Path: решение}
        self.out_seen = set()                            # все папки вывода этого сеанса: при повторном открытии папки пропускаются
        self.printers = []
        self.printer, self.blob = "", None
        last = s.get("print_printer")
        if last:
            self.printer = last

    def _ensure_printer(self):
        """Лениво подгружает список принтеров и настройки драйвера выбранного принтера."""
        if not self.printers:
            self.printers = list_printers()
        if self.printer and self.printer not in self.printers:
            self.printer = ""
        if not self.printer and self.printers:
            self.printer = self.printers[0]
        if self.printer and self.blob is None:
            self._load_blob()

    def _load_blob(self):
        self.blob = None
        stored = self.settings.get("print_devmodes", {}).get(self.printer)
        if stored:
            try:
                b = base64.b64decode(stored)
                if devmode_valid(b):
                    self.blob = b
            except Exception:
                pass
        if self.blob is None:
            try:
                self.blob = default_devmode(self.printer)
            except Exception:
                self.blob = None

    def _store_blob(self):
        if self.printer and self.blob:
            self.settings.setdefault("print_devmodes", {})[self.printer] = base64.b64encode(self.blob).decode()
            save_settings(self.settings)

    def to_project(self, full=True):
        d = {"version": 1, "folder": str(self.folder) if self.folder else "", "recursive": self.recursive,
             "files": [str(f) for f in self.files], "idx": self.idx,
             "format": self.fmt_name, "orient": self.orient_name, "mode": self.mode_name,
             "states": {str(f): {k: getattr(st, k) for k in CropState.__slots__} for f, st in self.states.items()}}
        if full:
            d.update(save=self.save, cm=self.cm, print_options=self.popts, printer=self.printer,
                     devmode=base64.b64encode(self.blob).decode() if self.blob else "")
        return d

    def from_project(self, d):
        files = [Path(p) for p in d.get("files", [])]
        self.files = [f for f in files if f.is_file()]
        self.folder = Path(d["folder"]) if d.get("folder") else None
        self.recursive = bool(d.get("recursive", False))
        self.states = {}
        for f in self.files:
            st = CropState()
            for k, v in (d.get("states", {}).get(str(f)) or {}).items():
                if k in CropState.__slots__:
                    setattr(st, k, dict(v) if k == "adj" else v)
            _sanitize_state(st)
            self.states[f] = st
        self.idx = min(max(int(d.get("idx", 0)), 0), len(self.files) - 1) if self.files else -1
        if d.get("format") in FORMATS:
            self.fmt_name = d["format"]
        if d.get("orient") in ORIENTS:
            self.orient_name = d["orient"]
        if d.get("mode") in MODES:
            self.mode_name = d["mode"]
        if "save" in d:
            self.save.update(d["save"])
        if "cm" in d:
            self.cm.update(d["cm"])
        if "print_options" in d:
            self.popts.update({k: v for k, v in d["print_options"].items() if k in PRINT_DEFAULTS})
        if d.get("printer"):
            self.printer = d["printer"]
        if d.get("devmode"):
            try:
                b = base64.b64decode(d["devmode"])
                if devmode_valid(b):
                    self.blob = b
            except Exception:
                pass

    def save_state(self):
        if not self.persist:
            return
        try:
            write_json_atomic(self.state_path, self.to_project())
        except Exception:
            pass

    def load_state(self):
        try:
            self.from_project(json.loads(self.state_path.read_text(encoding="utf-8")))
            return True
        except Exception:
            return False

    # ---------- вспомогательное
    def _path(self, p, what="path"):
        if not p or not str(p).strip():
            raise AgentError(f"{what}: путь не указан", "bad_value")
        pth = Path(str(p)).expanduser()
        roots = [r for r in os.environ.get("PHOTOCROP_AGENT_ROOTS", "").split(os.pathsep) if r.strip()]
        if roots:
            rp = pth.resolve()
            if not any(rp == Path(r).resolve() or Path(r).resolve() in rp.parents for r in roots):
                raise AgentError(f"{what}: путь вне разрешённых папок (PHOTOCROP_AGENT_ROOTS)", "path_not_allowed")
        return pth

    def _need_files(self):
        if not self.files:
            raise AgentError("Папка не открыта. Сначала вызовите open_folder.", "no_folder")

    def _one(self, ref):
        self._need_files()
        if ref is None:
            if self.idx < 0:
                self.idx = 0
            return self.files[self.idx]
        if isinstance(ref, bool):
            raise AgentError("photo: неверная ссылка", "bad_photo")
        if isinstance(ref, float) and ref == int(ref):
            ref = int(ref)
        if isinstance(ref, str) and re.fullmatch(r"-?\d+", ref.strip()):
            ref = int(ref)
        if isinstance(ref, int):
            if not 0 <= ref < len(self.files):
                raise AgentError(f"photo: индекс {ref} вне диапазона 0..{len(self.files) - 1}", "bad_photo")
            return self.files[ref]
        s = str(ref).strip().lower()
        for pick in (lambda f: str(f).lower() == s, lambda f: f.name.lower() == s, lambda f: f.stem.lower() == s):
            m = [f for f in self.files if pick(f)]
            if len(m) == 1:
                return m[0]
            if len(m) > 1:
                raise AgentError(f"photo «{ref}»: неоднозначно", "bad_photo", candidates=[str(f) for f in m[:10]])
        m = [f for f in self.files if s in f.name.lower()]
        if len(m) == 1:
            return m[0]
        raise AgentError(f"photo «{ref}»: " + ("не найдено" if not m else "неоднозначно"), "bad_photo",
                         candidates=[f.name for f in m[:10]])

    def _many(self, a, key="photo"):
        self._need_files()
        v = a.get(key)
        if isinstance(v, str) and v.strip().lower() == "all":
            return list(self.files)
        if isinstance(v, (list, tuple)):
            out = []
            for r in v:
                f = self._one(r)
                if f not in out:
                    out.append(f)
            return out
        return [self._one(v)]

    def _mark(self, f):
        self.states[f].edited = True

    def _paper_for(self, f, st, W, H):
        return paper_size(FORMATS[self.fmt_name], st.orient if st.orient else ORIENTS[self.orient_name], W, H)

    def _crop_info(self, f):
        st = self.states[f]
        W, H = true_size(f, st.rotation)
        paper = self._paper_for(f, st, W, H)
        g = frame_geom(W, H, paper, st)
        mode = MODES[self.mode_name]
        cs = frame_corners(*g)
        n, inside = 24, 0
        for i in range(n):
            for j in range(n):
                lx, ly = ((i + 0.5) / n - 0.5) * g[2], ((j + 0.5) / n - 0.5) * g[3]
                dx, dy = rot(lx, ly, g[4])
                x, y = g[0] + dx, g[1] + dy
                inside += 1 if (0 <= x <= W and 0 <= y <= H) else 0
        return {"photo": f.name, "index": self.files.index(f), "image_px": [W, H],
                "paper_mm": [round(paper[0], 1), round(paper[1], 1)],
                "orientation": "portrait" if paper[0] < paper[1] else "landscape",
                "crop": {"cx": round(st.cx, 4), "cy": round(st.cy, 4), "scale": round(st.scale, 4), "angle": round(st.angle, 2),
                         "orient": st.orient, "rotation": st.rotation, "copies": st.copies, "adjust": dict(st.adj), "edited": st.edited},
                "frame_px": {"center": [round(g[0], 1), round(g[1], 1)], "width": round(g[2], 1), "height": round(g[3], 1)},
                "frame_corners": [[round(x / W, 4), round(y / H, 4)] for x, y in cs],
                "frame_inside_photo": frame_inside(W, H, g),
                "outside_pct": round((1 - inside / float(n * n)) * 100, 1),
                "effective_dpi": round(effective_dpi(W, H, paper, st, mode), 1), "mode": MODES[self.mode_name]}

    def _preview_img(self, f, max_px=800, adjust=True):
        st = self.states[f]
        prev, _ = load_preview(f, st.rotation)
        W, H = prev.size
        paper = self._paper_for(f, st, W, H)
        dpi = max_px / (max(paper) / 25.4)
        out, _ = render(prev, paper, st, MODES[self.mode_name], dpi, True)
        if adjust and st.adj:
            out = adjust_tile(out, merge_adj({}, st), dpi)
        return out

    def _flag(self, a, key, default):
        return _truthy(a[key]) if key in a else default

    def _enum_print(self, k, v):
        tbl = ENUM_BY_FIELD.get(k)
        if tbl is None:
            return v
        s = str(v).strip()
        if s.lower() in tbl:
            return tbl[s.lower()]
        if s in ENUM_FIELDS[k]:
            return s
        raise AgentError(f"{k}: «{v}» не распознано. Допустимо: " + ", ".join(tbl), "bad_value")

    def _paper_name(self, v):
        s = str(v).strip()
        if s == PAPER_DRIVER or s.lower() in ("driver", "printer"):
            return PAPER_DRIVER
        if s.lower() in ("custom", "своя", PAPER_CUSTOM.lower()):
            return PAPER_CUSTOM
        for name in VIRTUAL_PAPERS:
            if s == name:
                return name
        low = s.lower().replace("x", "×").replace(" ", "")
        m = [n for n in VIRTUAL_PAPERS if n.lower().replace(" ", "").startswith(low) or n.lower().replace(" ", "").split("(")[0] == low]
        if len(m) == 1:
            return m[0]
        raise AgentError(f"paper: «{v}» не распознано. Допустимо: driver, custom, " + ", ".join(VIRTUAL_PAPERS), "bad_value")

    def _popts_typed(self):
        o = parse_print_opts(self.popts)
        o = dict(o)
        o["border_color"] = list(o["border_color"])
        return o

    def _entries_for(self, a, o):
        if a.get("photos") is not None:
            fl = self._many({"photo": a["photos"]})
        else:
            self._need_files()
            r = o["range"]
            if r == "current":
                fl = [self._one(None)]
            elif r == "edited":
                fl = [f for f in self.files if self.states[f].edited]
            else:
                fl = list(self.files)
        return [(f, self.states[f]) for f in fl]

    def _cm_dict(self):
        if not self.cm["on"]:
            return None
        return cm_build(self._path(self.cm["icc"], "icc") if self.cm["icc"] else "", self.cm["intent"], self.cm["bpc"], self.cm["embed"])

    def _ctx(self, a, need_printer=False):
        o = parse_print_opts(self.popts)
        if need_printer or o["paper"] == PAPER_DRIVER:
            self._ensure_printer()
        else:
            try:
                self._ensure_printer()
            except Exception:
                pass
        try:
            cm = self._cm_dict()
        except ValueError as ex:
            raise AgentError(str(ex), "bad_profile")
        entries = self._entries_for(a, o)
        photos, skipped = build_photos(entries, FORMATS[self.fmt_name], ORIENTS[self.orient_name], o)
        if not photos:
            raise AgentError("Нет фотографий для печати (проверьте range / photos).", "no_photos", skipped=skipped)
        try:
            plan = plan_layout(photos, make_geom_for(self.printer, self.blob, o), o)
        except (RuntimeError, OSError) as ex:
            raise AgentError(str(ex), "no_printer")
        n = len(plan["sheets"])
        sheets = a.get("sheets")
        if sheets is not None:
            if not isinstance(sheets, (list, tuple)):
                sheets = [sheets]
            idxs = []
            for k in sheets:
                k = int(k)
                if not 0 <= k < n:
                    raise AgentError(f"sheets: лист {k} вне диапазона 0..{n - 1}", "bad_value")
                idxs.append(k)
        else:
            idxs = list(range(n))
        return {"plan": plan, "photos": photos, "o": o, "mode": MODES[self.mode_name], "cm": cm,
                "ppi": resolve_ppi(o, plan["geom"]), "idxs": idxs, "skipped": skipped,
                "allow_low_res": self._flag(a, "allow_low_res", False)}

    def _plan_summary(self, c):
        plan, photos, o = c["plan"], c["photos"], c["o"]
        g = plan["geom"]
        sheets = []
        for k, sh in enumerate(plan["sheets"]):
            sheets.append({"sheet": k, "items": [
                {"photo": Path(photos[p["photo"]]["path"]).name, "x_mm": round(p["x"], 1), "y_mm": round(p["y"], 1),
                 "w_mm": round(p["w"], 1), "h_mm": round(p["h"], 1), "rotated": bool(p["rot"])} for p in sh]})
        dpis = {}
        for ph in photos:
            f = Path(ph["path"])
            if f.name in dpis:
                continue
            try:
                W, H = true_size(f, ph["st"].rotation)
                dpis[f.name] = round(effective_dpi(W, H, ph["paper"], ph["st"], c["mode"]), 0)
            except Exception:
                pass
        return {"orientation": plan["orient"], "paper_mm": [round(g["paper"][0], 1), round(g["paper"][1], 1)],
                "printable_area_mm": [round(v, 1) for v in g["area"]], "driver_dpi": list(g["dpi"]), "ppi": c["ppi"],
                "virtual_sheet": bool(g.get("virtual")), "sheet_count": len(plan["sheets"]),
                "sheets_to_print": len(c["idxs"]) * o["sheet_copies"], "sheet_copies": o["sheet_copies"],
                "fill_pct": round(plan["util"] * 100, 1), "photo_count": len(photos), "warnings": plan["warnings"],
                "skipped_unreadable": c["skipped"], "photo_dpi": dpis, "sheets": sheets}

    def _checks(self, c, printing=True):
        o, plan = c["o"], c["plan"]
        out = []
        add = lambda lvl, code, msg: out.append({"level": lvl, "code": code, "message": msg})
        if printing:
            if not self.printer:
                add("error", "no_printer", "Принтер не выбран (list_printers → select_printer).")
            elif self.blob is None:
                add("error", "no_driver_settings", "Не удалось получить настройки драйвера принтера.")
            if plan["geom"].get("virtual"):
                add("error", "virtual_sheet", "Драйвер не принял выбранный размер бумаги. Задайте paper=driver и бумагу через set_driver_settings (paper/paper_mm/form).")
        for w in plan["warnings"]:
            if "не помещается" in w:                        # фото не влезает на лист — печатать нельзя
                add("error", "does_not_fit", w)
            else:
                add("warning", "layout", w)
        if o["layout"] != "single" and any(abs(v) > 1e-9 for v in bleed_sides(o)):
            add("warning", "bleed_ignored", "Вылет (bleed, bleed_l/t/r/b) действует только при layout=single (одно фото на листе); сейчас он не применяется.")
        for nm in c["skipped"]:
            add("warning", "unreadable", f"Файл не прочитан: {nm}")
        low, crit = [], []
        for ph in c["photos"]:
            try:
                f = Path(ph["path"])
                W, H = true_size(f, ph["st"].rotation)
                d = effective_dpi(W, H, ph["paper"], ph["st"], c["mode"])
                if d < 100:
                    crit.append(f"{f.name}: {d:.0f} dpi")
                elif d < 150:
                    low.append(f"{f.name}: {d:.0f} dpi")
            except Exception:
                pass
        if crit:                                            # <100 dpi — результат заведомо плохой: блокируем, пока не разрешено явно
            add("warning" if c.get("allow_low_res") else "error", "low_resolution_critical",
                "Очень малое разрешение (<100 dpi): " + "; ".join(sorted(set(crit))[:8])
                + ("" if c.get("allow_low_res") else ". Печать остановлена; чтобы всё равно печатать — allow_low_res=true."))
        if low:
            add("warning", "low_resolution", "Малое разрешение для печати (<150 dpi): " + "; ".join(sorted(set(low))[:8]))
        if printing and not o["icm_off"]:
            add("warning", "windows_icm_on", "Включено управление цветом Windows (icm_off=false) — возможна двойная цветокоррекция.")
        pre = self.settings.get("print_presets", {}).get(self.active_preset or "", {}).get("cm")
        if pre and pre.get("on") and c["cm"] and pre.get("icc") != self.cm["icc"]:
            add("warning", "profile_differs_from_preset",
                f"Профиль изменён после загрузки пресета «{self.active_preset}»: {Path(self.cm['icc']).name} вместо {Path(pre['icc']).name}.")
        if pre and pre.get("on") and not c["cm"]:
            add("warning", "profile_off_but_preset_has_one", f"В пресете «{self.active_preset}» был профиль, а сейчас цветопреобразование выключено.")
        if c["cm"]:
            add("info", "profile_on", f"Применяется профиль принтера «{c['cm']['name']}». В драйвере должно быть отключено управление цветом "
                "(Epson: «Без цветокоррекции»/No Color Adjustment) — эта опция частная, её задают один раз в окне свойств принтера (GUI); "
                "она сохраняется и подхватывается агентом.")
        total = len(c["idxs"]) * o["sheet_copies"]
        if total > 20:
            add("info", "many_sheets", f"К печати {total} листов.")
        return out

    @staticmethod
    def _sheets_work(c):
        def work(progress, cancel):
            r = run_sheets_job(c, progress, cancel)
            if r[0] == "cancelled":
                return r
            return ("done", {"sheets": r[1], "dir": r[2], "files": r[3]} if r[2] else {"sheets_sent": r[1]})
        return work

    def _run_job(self, kind, title, work, a, default_timeout=120.0):
        job = AgentJob(kind, title)
        self.jobs[job.id] = job

        def progress(j, n, text):
            job.done, job.total, job.text = j, n, text

        def target():
            try:
                res = work(progress, job.cancel)
                if res[0] == "cancelled":
                    job.state, job.result = "cancelled", {"sheets_done": res[1]}
                else:
                    job.state = "done"
                    job.done = job.total
                    job.result = res[1] if isinstance(res[1], dict) else {"count": res[1]}
            except AgentError as ex:
                job.state, job.error = "error", {"code": ex.code, "message": str(ex)}
            except Exception as ex:
                job.state, job.error = "error", {"code": ex.__class__.__name__, "message": str(ex)}
            finally:
                job.t1 = time.time()
                job.finished.set()

        threading.Thread(target=target, daemon=True).start()
        if self._flag(a, "wait", True):
            job.finished.wait(fnum(a.get("timeout"), default_timeout, 0, 86400))
        info = job.info()
        if job.state == "error":
            raise AgentError(job.error["message"], job.error["code"], job=info)
        return info

    # ---------- выполнение
    def execute(self, req):
        """req: {"cmd": имя, ...параметры} -> {"ok": True, "result": …} | {"ok": False, "error": {...}}"""
        t0 = time.time()
        name = ""
        try:
            if not isinstance(req, dict):
                raise AgentError("Запрос должен быть JSON-объектом {\"cmd\": …}", "bad_request")
            req = dict(req)
            name = req.pop("cmd", None)
            if name is None:
                name = req.pop("command", "")
            name = str(name or "")
            if name not in SPEC:
                raise AgentError(f"Неизвестная команда «{name}». Список: help", "unknown_command")
            with self.lock:
                snap = self._snapshot() if name in UNDOABLE else None
                res = getattr(self, "cmd_" + name)(req)
                if self.save.get("outdir"):
                    self.out_seen.add(self.save["outdir"])
                if snap is not None and self._snapshot_key(snap) != self._snapshot_key(self._snapshot()):
                    self._undo.append(snap)
                    del self._undo[:-UNDO_LIMIT]
                    self._redo.clear()
                if name not in READONLY:
                    self.save_state()
            out = {"ok": True, "cmd": name, "result": res}
        except AgentError as ex:
            out = {"ok": False, "cmd": name, "error": {"code": ex.code, "message": str(ex), **ex.extra}}
        except Exception as ex:
            out = {"ok": False, "cmd": name, "error": {"code": "internal", "message": f"{ex.__class__.__name__}: {ex}"}}
            if os.environ.get("PHOTOCROP_AGENT_DEBUG"):
                import traceback
                out["error"]["trace"] = traceback.format_exc()
        self._log(req if isinstance(req, dict) else {}, name, out, time.time() - t0)
        return out

    # ---------- откат
    def _snapshot(self):
        return {"states": {f: st.copy() for f, st in self.states.items()}, "fmt": self.fmt_name, "orient": self.orient_name,
                "mode": self.mode_name, "idx": self.idx}

    @staticmethod
    def _snapshot_key(sn):
        return (sn["fmt"], sn["orient"], sn["mode"],
                tuple((str(f), tuple(getattr(st, k) for k in CropState.__slots__ if k != "adj"), tuple(sorted(st.adj.items())))
                      for f, st in sn["states"].items()))

    def _restore(self, sn):
        if set(sn["states"]) != set(self.states):
            raise AgentError("Набор фото изменился (open_folder/reload) — откат невозможен.", "undo_impossible")
        self.states = {f: st.copy() for f, st in sn["states"].items()}
        self.fmt_name, self.orient_name, self.mode_name = sn["fmt"], sn["orient"], sn["mode"]
        self.idx = sn["idx"]

    def cmd_undo(self, a):
        n = int(fnum(a.get("steps"), 1, 1, UNDO_LIMIT))
        done = 0
        while self._undo and done < n:
            sn = self._undo.pop()
            cur = self._snapshot()
            self._restore(sn)
            self._redo.append(cur)
            done += 1
        if not done:
            raise AgentError("Откатывать нечего.", "nothing_to_undo")
        return {"undone": done, "can_undo": len(self._undo), "can_redo": len(self._redo)}

    def cmd_redo(self, a):
        n = int(fnum(a.get("steps"), 1, 1, UNDO_LIMIT))
        done = 0
        while self._redo and done < n:
            sn = self._redo.pop()
            cur = self._snapshot()
            self._restore(sn)
            self._undo.append(cur)
            done += 1
        if not done:
            raise AgentError("Повторять нечего.", "nothing_to_redo")
        return {"redone": done, "can_undo": len(self._undo), "can_redo": len(self._redo)}

    def cmd_reload(self, a):
        """Заново просмотреть открытую папку: рамки оставшихся фото сохраняются, новые добавляются, пропавшие убираются."""
        self._need_files()
        if not self.folder:
            raise AgentError("Папка неизвестна (проект без папки) — используйте open_folder.", "no_folder")
        rec = self._flag(a, "recursive", self.recursive)
        files, own, other = scan_folder(Path(self.folder), rec, self.save.get("out_name"), [self.save.get("outdir"), *self.out_seen])
        if not files:
            raise AgentError("В папке не осталось фотографий.", "empty_folder")
        old = self.states
        cur = self.files[self.idx] if 0 <= self.idx < len(self.files) else None
        added = [f.name for f in files if f not in old]
        removed = [f.name for f in old if f not in set(files)]
        self.files, self.recursive = files, rec
        self.states = {f: (old[f] if f in old else CropState()) for f in files}
        self.idx = files.index(cur) if cur in self.states else 0
        self._undo.clear()
        self._redo.clear()
        return {"photo_count": len(files), "kept": len(files) - len(added), "added": added[:50], "removed": removed[:50]}

    def _log(self, req, name, out, dt):
        if not self.persist:
            return
        try:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            if self.log_path.exists() and self.log_path.stat().st_size > 2_000_000:
                self.log_path.replace(self.log_path.with_suffix(".old"))
            rec = {"t": time.strftime("%Y-%m-%dT%H:%M:%S"), "cmd": name, "args": req, "ok": out["ok"],
                   "ms": round(dt * 1000)}
            if not out["ok"]:
                rec["error"] = out["error"]
            with open(self.log_path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(rec, ensure_ascii=False, default=_jsonable) + "\n")
        except Exception:
            pass

    # ================= команды: сеанс
    def cmd_help(self, a):
        c = a.get("command")
        if c:
            if c not in SPEC:
                raise AgentError(f"Неизвестная команда «{c}»", "unknown_command")
            s, ps = SPEC[c]
            return {"command": c, "summary": s, "params": [{"name": n, "type": t, "description": d} for n, t, d in ps]}
        return {"version": AGENT_VERSION, "commands": {k: v[0] for k, v in SPEC.items()},
                "notes": ["Photo refs: 0-based index or file name. Fractions: cx,cy in 0..1.",
                          "Typical flow: open_folder → set_format → (set_crop/auto_crop/set_adjust) → set_color_profile → select_printer → "
                          "set_driver_settings → set_print_options → plan_print → render_sheet → preflight → print → wait_queue."]}

    def cmd_status(self, a):
        return {"platform": sys.platform, "windows": sys.platform == "win32", "version": AGENT_VERSION,
                "folder": str(self.folder) if self.folder else None, "photo_count": len(self.files),
                "current": self.idx, "edited": sum(1 for s in self.states.values() if s.edited),
                "format": self.fmt_name, "orientation": self.orient_name, "mode": self.mode_name,
                "save_options": self.save, "color_profile": self.cm, "printer": self.printer or None,
                "print_options": self._popts_typed(), "jobs": [j.info() for j in self.jobs.values()][-5:]}

    def cmd_reset_session(self, a):
        self.jobs.clear()
        self._reset_state()
        return {"reset": True}

    # ================= команды: фото
    def cmd_open_folder(self, a):
        src = self._path(a.get("path"), "path")
        if not src.is_dir():
            raise AgentError(f"Папка не найдена: {src}", "not_found")
        rec = self._flag(a, "recursive", False)
        files, own, other = scan_folder(src, rec, self.save.get("out_name"), [self.save.get("outdir"), *self.out_seen])
        if not files:
            raise AgentError("В папке нет фотографий (JPG, PNG, TIFF, BMP, WEBP)." + (" " + skipped_note(own, other) if (own or other) else ""), "empty_folder")
        self.folder, self.recursive, self.files = src, rec, files
        self.states = {f: CropState() for f in files}
        self.idx = 0
        self.save["outdir"] = str(src / "Печать")
        r = {"folder": str(src), "photo_count": len(files), "first": [f.name for f in files[:10]], "outdir": self.save["outdir"]}
        if own or other:
            r["skipped"] = {"own_results": own, "unsupported": other, "note": skipped_note(own, other)}
        return r

    def cmd_list_photos(self, a):
        self._need_files()
        off, lim = int(fnum(a.get("offset"), 0, 0)), int(fnum(a.get("limit"), 200, 1, 2000))
        out = []
        for i, f in enumerate(self.files[off:off + lim], off):
            st = self.states[f]
            try:
                W, H = true_size(f, st.rotation)
            except Exception:
                W = H = None
            out.append({"index": i, "name": f.name, "size_px": [W, H], "edited": st.edited, "copies": st.copies,
                        "orient": st.orient, "rotation": st.rotation, "crop": [round(st.cx, 3), round(st.cy, 3), round(st.scale, 3), round(st.angle, 1)],
                        "adjusted": bool(st.adj)})
        return {"total": len(self.files), "offset": off, "photos": out}

    def cmd_select_photo(self, a):
        f = self._one(a.get("photo"))
        self.idx = self.files.index(f)
        return self._crop_info(f)

    def cmd_photo_info(self, a):
        f = self._one(a.get("photo"))
        info = self._crop_info(f)
        info["path"] = str(f)
        try:
            with Image.open(f) as im:
                info["format"], info["mode_px"] = im.format, im.mode
                icc = im.info.get("icc_profile")
                dpi = im.info.get("dpi")
                info["file_dpi"] = list(dpi) if dpi else None
                info["icc"] = (ImageCms.getProfileDescription(_rgb_profile(icc)) or "").strip() if _rgb_profile(icc) else None
        except Exception:
            pass
        return info

    def cmd_analyze_photo(self, a):
        f = self._one(a.get("photo"))
        st = self.states[f]
        region = str(a.get("region") or "frame").lower()
        if region == "full":
            img, _ = load_preview(f, st.rotation)
        else:
            img = self._preview_img(f, 600, adjust=False)
        an = analyze_image(img)
        an.update(photo=f.name, region=region, suggested_adjust=suggest_adjust(an))
        return an

    def cmd_preview_photo(self, a):
        f = self._one(a.get("photo"))
        mx = int(fnum(a.get("max_px"), 800, 100, 4000))
        img = self._preview_img(f, mx)
        if a.get("path"):
            dest = self._path(a["path"], "path")
        else:
            dest = AGENT_DIR / "preview" / (f.stem + "_preview.png")
        dest.parent.mkdir(parents=True, exist_ok=True)
        img.save(dest, "PNG")
        res = {"photo": f.name, "file": str(dest), "size_px": list(img.size), "analysis": analyze_image(img)}
        if self._flag(a, "inline", False):
            res["_image_b64"] = self._jpeg_b64(img, 640)
        return res

    @staticmethod
    def _jpeg_b64(img, side):
        t = to_rgb(img).copy()
        t.thumbnail((side, side), RESAMPLE_HQ)
        bio = io.BytesIO()
        t.save(bio, "JPEG", quality=80)
        return base64.b64encode(bio.getvalue()).decode()

    # ================= команды: рамка и коррекция
    def cmd_set_crop(self, a):
        fl = self._many(a)
        rotation = None
        if a.get("rotation") is not None:
            rotation = int(fnum(a["rotation"], 0)) % 360
            if rotation % 90:
                raise AgentError("rotation: 0, 90, 180 или 270", "bad_value")
        orient = False
        if "orient" in a:
            o = a["orient"]
            if o in (None, "", "auto", "Авто"):
                orient = None
            elif str(o).lower() in ("portrait", "landscape"):
                orient = str(o).lower()
            else:
                raise AgentError("orient: portrait | landscape | auto", "bad_value")
        nums = {}
        for k, lo, hi in (("cx", 0, 1), ("cy", 0, 1), ("scale", MIN_SCALE, MAX_SCALE), ("angle", -3600, 3600)):
            if a.get(k) is not None:
                try:
                    nums[k] = min(hi, max(lo, float(str(a[k]).replace(",", "."))))
                except ValueError:
                    raise AgentError(f"{k}: ожидается число", "bad_value")
        copies = int(fnum(a["copies"], 1, 1, 99)) if a.get("copies") is not None else None
        for f in fl:
            st = self.states[f]
            if rotation is not None and rotation != st.rotation:
                st.rotation = rotation
                st.cx = st.cy = 0.5
                st.scale, st.angle = 1.0, 0.0
            for k, v in nums.items():
                setattr(st, k, v)
            if orient is not False:
                st.orient = orient
            if copies is not None:
                st.copies = copies
            normalize(st)
            self._mark(f)
        if len(fl) == 1:
            return self._crop_info(fl[0])
        return {"updated": len(fl)}

    def cmd_move_crop(self, a):
        fl = self._many(a)
        for f in fl:
            st = self.states[f]
            st.cx += fnum(a.get("dx"), 0)
            st.cy += fnum(a.get("dy"), 0)
            st.scale *= fnum(a.get("dscale"), 1, 0.01, 100)
            st.angle += fnum(a.get("dangle"), 0)
            normalize(st)
            self._mark(f)
        return self._crop_info(fl[0]) if len(fl) == 1 else {"updated": len(fl)}

    def cmd_auto_crop(self, a):
        fl = self._many(a)
        method = str(a.get("method") or "focus").lower()
        if method not in ("center", "focus", "fill", "smart"):
            raise AgentError("method: center | focus | fill | smart", "bad_value")
        if method == "smart":
            return self._smart_crop(fl, a)
        for f in fl:
            st = self.states[f]
            scale = fnum(a.get("scale"), 1.0, MIN_SCALE, MAX_SCALE) if method != "fill" else 1.0
            st.angle, st.scale, st.cx, st.cy = 0.0, scale, 0.5, 0.5
            if method == "focus":
                img, _ = load_preview(f, st.rotation)
                fx, fy = analyze_image(img)["focus_point"]
                W, H = true_size(f, st.rotation)
                paper = self._paper_for(f, st, W, H)
                _, _, w, h, _ = frame_geom(W, H, paper, st)
                st.cx = min(max(fx, (w / 2) / W), 1 - (w / 2) / W) if w < W else 0.5
                st.cy = min(max(fy, (h / 2) / H), 1 - (h / 2) / H) if h < H else 0.5
            self._mark(f)
        return self._crop_info(fl[0]) if len(fl) == 1 else {"updated": len(fl)}

    def _smart_crop(self, fl, a):
        """SmartCrop: рамка так, чтобы не отрезать людей и питомцев; вердикт ok|note|check|manual и причины для каждого кадра."""
        try:
            import smart_crop as sc
        except Exception as ex:
            raise AgentError(f"smart_crop недоступен ({ex.__class__.__name__}: {ex}). Нужен файл smart_crop.py рядом с photo_crop.py и "
                             "pip install numpy opencv-python onnxruntime; затем python smart_crop.py setup (модели).", "smart_unavailable")
        cfg = dict(a.get("config")) if isinstance(a.get("config"), dict) else {}
        if a.get("algo"):
            cfg["algo"] = str(a["algo"]).strip().lower()
        pr = a.get("priority")
        if pr:
            cfg["priority"] = [x.strip() for x in pr.split(",") if x.strip()] if isinstance(pr, str) else list(pr)
        rot90 = str(a.get("orient_mode") or "").lower() == "person" or self._flag(a, "rotate90", False)
        if rot90:
            cfg.setdefault("portrait_fit", True)               # «Человек»: приблизить людей, оставив немного фона
        try:
            cropper = sc.SmartCropper(cfg)
        except ValueError as ex:
            raise AgentError(str(ex), "bad_value")
        fmt, glob = FORMATS[self.fmt_name][:2], ORIENTS[self.orient_name]
        keep, apply_ = self._flag(a, "keep_manual", False), self._flag(a, "apply", True)
        out, counts = [], {"ok": 0, "note": 0, "check": 0, "manual": 0}
        for f in fl:
            st = self.states[f]
            if keep and (st.cx, st.cy, st.scale, st.angle) != (0.5, 0.5, 1.0, 0.0):
                out.append({"photo": f.name, "skipped": "frame already changed (keep_manual)"})
                continue
            try:
                if glob:
                    ori = glob
                elif rot90:
                    ori = "auto"
                else:                                   # по умолчанию ориентация фото сохраняется
                    W0, H0 = true_size(f, st.rotation)
                    ori = "portrait" if H0 >= W0 else "landscape"
                dec = cropper.analyze(f, fmt, ori, st.rotation)
            except Exception as ex:
                out.append({"photo": f.name, "error": f"{ex.__class__.__name__}: {ex}"})
                continue
            self.smart[f] = dec
            if apply_:
                W, H = true_size(f, st.rotation)
                base = glob or ("portrait" if H >= W else "landscape")
                st.cx, st.cy, st.scale, st.angle = dec["cx"], dec["cy"], dec["scale"], 0.0
                st.orient = None if dec["orient"] == base else dec["orient"]
                self._mark(f)
            counts[dec["status"]] += 1
            out.append({"photo": f.name, "status": dec["status"], "risk": dec["risk"], "persons": dec["persons"], "orient": dec["orient"],
                        "skeleton_people": sum(1 for d_ in dec.get("detections", []) if d_.get("keypoints")),
                        "crop": [dec["cx"], dec["cy"], dec["scale"]], "dpi": dec["dpi"], "reasons": [r["message"] for r in dec["reasons"]],
                        "alternatives": [{k: al[k] for k in ("name", "label", "orient", "mode", "cx", "cy", "scale")} for al in dec["alternatives"]]})
        return {"method": "smart", "algo": cropper.cfg.get("algo", "simple"), "applied": apply_, "summary": counts, "review": [x["photo"] for x in out if x.get("status") in ("check", "manual")],
                "detectors": cropper.backends() or None, "notes": cropper.problems, "photos": out[:300]}

    def cmd_reset_crop(self, a):
        fl = self._many(a)
        full = self._flag(a, "everything", False)
        for f in fl:
            st = self.states[f]
            keep = (st.copies, st.rotation, dict(st.adj))
            n = CropState()
            if not full:
                n.copies, n.rotation, n.adj = keep
            n.edited = bool(n.rotation or n.copies != 1 or n.adj)
            self.states[f] = n
        return self._crop_info(fl[0]) if len(fl) == 1 else {"reset": len(fl)}

    def cmd_rotate_photo(self, a):
        deg = int(fnum(a.get("degrees"), 90))
        if deg % 90:
            raise AgentError("degrees: кратно 90", "bad_value")
        fl = self._many(a)
        for f in fl:
            st = self.states[f]
            st.rotation = (st.rotation + deg) % 360
            st.cx = st.cy = 0.5
            st.scale, st.angle, st.orient = 1.0, 0.0, None
            self._mark(f)
        return self._crop_info(fl[0]) if len(fl) == 1 else {"rotated": len(fl)}

    def cmd_set_copies(self, a):
        n = int(fnum(a.get("copies"), 1, 1, 99))
        fl = self._many(a)
        for f in fl:
            self.states[f].copies = n
            self._mark(f)
        return {"copies": n, "photos": len(fl)}

    def cmd_set_adjust(self, a):
        fl = self._many(a)
        for f in fl:
            st = self.states[f]
            if self._flag(a, "reset", False):
                st.adj = {}
            upd = {}
            for k in ADJ_KEYS:
                if k in a and a[k] is not None:
                    v = a[k]
                    if k == "auto":
                        v = str(v).strip().lower()
                        v = "" if v in ("", "off", "none", "false", "0") else v
                        if v not in AUTO_MODES:
                            raise AgentError("auto: contrast | color | bw | off", "bad_value")
                    elif isinstance(NEUTRAL_ADJ[k], bool):
                        v = _truthy(v)
                    else:
                        try:
                            float(str(v).replace(",", "."))
                        except ValueError:
                            raise AgentError(f"{k}: нужно число, получено «{v}»", "bad_value")
                    upd[k] = v
            st.adj = clean_adj({**st.adj, **upd})
            self._mark(f)
        return {"photos": len(fl), "adjust": dict(self.states[fl[0]].adj)}

    def cmd_auto_adjust(self, a):
        fl = self._many(a)
        strength = fnum(a.get("strength"), 1.0, 0, 1.5)
        apply = self._flag(a, "apply", True)
        res = []
        for f in fl:
            st = self.states[f]
            sug = suggest_adjust(analyze_image(self._preview_img(f, 500, adjust=False)), strength)
            if apply:
                st.adj.update({k: v for k, v in sug.items() if v})
                for k, v in sug.items():
                    if not v:
                        st.adj.pop(k, None)
                self._mark(f)
            res.append({"photo": f.name, "suggested": sug, "adjust": dict(st.adj)})
        return {"applied": apply, "photos": res[:50], "count": len(res)}

    # ================= команды: формат, сохранение, цвет
    def cmd_list_formats(self, a):
        return {"formats": {k: {"short_mm": v[0], "long_mm": v[1], "label": v[2]} for k, v in FORMATS.items()},
                "orientations": ["auto", "portrait", "landscape"], "modes": ["crop", "fit"],
                "file_types": list(FILETYPES), "intents": list(INTENT_CODES),
                "papers": {k: {"w_mm": v[0], "h_mm": v[1]} for k, v in VIRTUAL_PAPERS.items()},
                "print_options": {
                    "layout": "single|multi", "range": "all|current|edited", "pages": "all|current", "orient": "auto|portrait|landscape",
                    "paper": "driver | custom | " + " | ".join(VIRTUAL_PAPERS), "paper_w/paper_h": "mm (for custom)",
                    "margin_l/t/r/b": "mm", "gap": "mm", "align": "center|topleft", "copies": "per photo", "sheet_copies": "repeat each sheet", "bleed_l/t/r/b": "mm per side (empty = use bleed; negative = inset to compensate a printer that crops borderless prints)", "one_by_one": "true: each sheet is a separate print job", "job_pause": "seconds between jobs (0-60)",
                    "fill": "bool: fill sheet with copies of each photo", "rotate_fit": "bool", "marks": "bool: crop marks",
                    "border": "mm", "border_color": "white|black|gray", "caption": "none|name|name_n", "bleed_on": "true/false: apply the bleed/inset values (false = ignore them, values are kept)", "bleed": "mm (single layout)",
                    "icm_off": "bool: switch off Windows ICM", "ppi": "auto|240|300|360|600",
                    "sharp": "0..500 %", "sharp_radius": "px@300", "sharp_thr": "0..255", "bright/contrast/sat": "-100..100",
                    "gamma": "0.2..5", "bw": "bool", "export_fmt": "JPEG|TIFF|PNG|PDF", "proof": "bool"}}

    def _pick(self, tbl, v, what):
        s = str(v).strip().lower()
        for k, val in tbl.items():
            if s in (k.lower(), str(val).lower()):
                return k
        raise AgentError(f"{what}: «{v}» не распознано. Допустимо: " + ", ".join(tbl), "bad_value")

    def cmd_set_format(self, a):
        norm = lambda t: str(t).lower().replace(" ", "").replace("×", "x").replace("х", "x").replace("см", "")
        v = norm(a.get("format", ""))
        for k, val in FORMATS.items():
            if v in (val[2].lower(), norm(k)):
                self.fmt_name = k
                return {"format": k, "size_mm": [val[0], val[1]]}
        raise AgentError(f"format: «{a.get('format')}» не найден. Допустимо: " + ", ".join(v[2] for v in FORMATS.values()), "bad_value")

    def cmd_set_orientation(self, a):
        self.orient_name = self._pick({"Авто (по фото)": "auto", "Книжная": "portrait", "Альбомная": "landscape"},
                                      a.get("orientation"), "orientation")
        for st in self.states.values():
            st.orient = None
        return {"orientation": self.orient_name}

    def cmd_set_mode(self, a):
        self.mode_name = self._pick({"Кадрировать (заполнить лист)": "crop", "Вписать целиком (белые поля)": "fit"}, a.get("mode"), "mode")
        return {"mode": self.mode_name}

    def cmd_set_save_options(self, a):
        s = self.save
        if a.get("dpi") is not None:
            s["dpi"] = fnum(a["dpi"], 300, 50, 2400)
        if a.get("resize") is not None:
            s["resize"] = _truthy(a["resize"])
        if a.get("filetype") is not None:
            s["filetype"] = self._pick({k: k for k in FILETYPES}, a["filetype"], "filetype")
        if a.get("quality") is not None:
            s["quality"] = int(fnum(a["quality"], 95, 1, 100))
        if a.get("outdir") is not None:
            s["outdir"] = str(self._path(a["outdir"], "outdir"))
        if a.get("out_mode") is not None:
            s["out_mode"] = self._pick({"orig": "orig", "custom": "custom"}, a["out_mode"], "out_mode")
        if a.get("out_name") is not None:
            s["out_name"] = re.sub(r'[\\/:*?"<>|]+', "", str(a["out_name"])).strip(" .") or OUT_SUBDIR
        if a.get("subfolder") is not None:
            s["subfolder"] = _truthy(a["subfolder"])
        if a.get("copies_in_name") is not None:
            s["copies_in_name"] = _truthy(a["copies_in_name"])
        return dict(s)

    def cmd_set_color_profile(self, a):
        c = self.cm
        if a.get("icc") is not None:
            c["icc"] = str(self._path(a["icc"], "icc")) if str(a["icc"]).strip() else ""
        if a.get("intent") is not None:
            v = str(a["intent"]).strip()
            c["intent"] = INTENT_CODES.get(v.lower()) or (v if v in INTENTS else None)
            if not c["intent"]:
                raise AgentError("intent: " + " | ".join(INTENT_CODES), "bad_value")
        for k in ("bpc", "embed", "on"):
            if a.get(k) is not None:
                c[k] = _truthy(a[k])
        if c["on"]:
            try:
                self._cm_dict()
            except ValueError as ex:
                c["on"] = False
                raise AgentError(str(ex) + " (профиль выключен)", "bad_profile")
        return self.cmd_get_color_profile({})

    def cmd_get_color_profile(self, a):
        c = dict(self.cm)
        c["intent_codes"] = {k: v for k, v in INTENT_CODES.items() if v == c["intent"]}
        if c["icc"] and Path(c["icc"]).is_file():
            try:
                desc, space, ok = profile_info(c["icc"])
                c["profile"] = {"description": desc, "space": space, "supported_intents": ok}
            except Exception as ex:
                c["profile"] = {"error": str(ex)}
        return c

    def cmd_save_files(self, a):
        self._need_files()
        fl = self._many(a) if a.get("photo") is not None else list(self.files)     # без photo — все фото папки
        s = self.save
        if s.get("out_mode") != "orig" and not s["outdir"]:
            raise AgentError("Не задана папка сохранения (set_save_options outdir).", "no_outdir")
        try:
            cm = self._cm_dict()
        except ValueError as ex:
            raise AgentError(str(ex), "bad_profile")
        o = {"fmt": FORMATS[self.fmt_name], "orient": ORIENTS[self.orient_name], "mode": MODES[self.mode_name],
             "dpi": s["dpi"], "resize": s["resize"], "filetype": s["filetype"], "quality": s["quality"],
             "outdir": s["outdir"], "subfolder": s["subfolder"], "out_mode": s.get("out_mode", "custom"),
             "out_name": s.get("out_name") or OUT_SUBDIR,
             "copies_in_name": s.get("copies_in_name", True), "cm": cm,
             "universe": [(f, self.states[f].copies) for f in self.files]}
        jobs = [(f, self.states[f].copy()) for f in fl]
        low = low_res_list(jobs, o)

        def work(progress, cancel):
            saved, errors = process_batch(jobs, o, progress, cancel)
            if cancel.is_set():
                return ("cancelled", len(saved) + len(errors))
            return ("done", {"saved": len(saved), "files": saved[:200], "errors": errors, "profile": cm["name"] if cm else None,
                             "low_res_under_150dpi": [{"photo": n, "dpi": d} for n, d in low[:50]]})

        return self._run_job("save", f"{len(fl)} файл(ов)", work, a, 600)

    # ================= команды: принтер и драйвер
    def cmd_list_printers(self, a):
        self.printers = list_printers()
        return {"printers": self.printers, "selected": self.printer or None, "default": self.printers[0] if self.printers else None,
                "windows": sys.platform == "win32"}

    def cmd_select_printer(self, a):
        self.printers = list_printers()
        want = str(a.get("name", "")).strip()
        m = [p for p in self.printers if p.lower() == want.lower()] or [p for p in self.printers if want and want.lower() in p.lower()]
        if len(m) != 1:
            raise AgentError(f"Принтер «{want}» " + ("не найден" if not m else "указан неоднозначно") + ". Установлены: " + ", ".join(self.printers),
                             "no_printer")
        self.printer = m[0]
        self.blob = None
        self._load_blob()
        self.settings["print_printer"] = self.printer
        save_settings(self.settings)
        return {"printer": self.printer, "driver_settings": devmode_read(self.blob) if self.blob else None}

    def _need_blob(self):
        self._ensure_printer()
        if not self.printer:
            raise AgentError("Принтер не выбран. list_printers → select_printer.", "no_printer")
        if self.blob is None:
            raise AgentError("Не удалось получить настройки драйвера.", "no_driver_settings")

    def cmd_driver_settings(self, a):
        self._need_blob()
        d = devmode_read(self.blob)
        d["printer"] = self.printer
        return d

    def cmd_set_driver_settings(self, a):
        self._need_blob()
        ch = dict(a.get("settings") or {})
        ch.update({k: v for k, v in a.items() if k != "settings"})
        if not ch:
            raise AgentError("Нет полей для изменения.", "bad_request")
        new = devmode_write(self.blob, ch)
        merged = merge_devmode(self.printer, new)
        after = devmode_read(merged)
        rejected = {}
        want = devmode_read(new)["settings"]
        for k, v in want.items():
            if k in ch or (k == "paper" and "paper_mm" in ch):
                if after["settings"].get(k) != v:
                    rejected[k] = {"requested": v, "actual": after["settings"].get(k)}
        self.blob = merged
        self._store_blob()
        after["printer"] = self.printer
        after["rejected"] = rejected
        return after

    def cmd_reset_driver_settings(self, a):
        self._ensure_printer()
        if not self.printer:
            raise AgentError("Принтер не выбран.", "no_printer")
        self.blob = default_devmode(self.printer)
        self._store_blob()
        return devmode_read(self.blob)

    def cmd_driver_capabilities(self, a):
        self._ensure_printer()
        if not self.printer:
            raise AgentError("Принтер не выбран.", "no_printer")
        return printer_capabilities(self.printer)

    # ================= команды: параметры печати и пресеты
    def cmd_get_print_options(self, a):
        return {"options": self._popts_typed(), "raw": dict(self.popts)}

    def cmd_set_print_options(self, a):
        ch = dict(a.get("options") or {})
        ch.update({k: v for k, v in a.items() if k != "options"})
        if not ch:
            raise AgentError("Нет параметров.", "bad_request")
        alias = {"margins": None}
        bad = [k for k in ch if k not in PRINT_DEFAULTS and k not in alias]
        if bad:
            raise AgentError("Неизвестные параметры: " + ", ".join(bad) + ". Допустимо: " + ", ".join(PRINT_DEFAULTS), "bad_key")
        if "margins" in ch:
            m = ch.pop("margins")
            for k in ("margin_l", "margin_t", "margin_r", "margin_b"):
                ch.setdefault(k, m)
        new = dict(self.popts)
        for k, v in ch.items():
            d = PRINT_DEFAULTS[k]
            if isinstance(d, bool):
                new[k] = _truthy(v)
            elif k in ENUM_BY_FIELD:
                new[k] = self._enum_print(k, v)
            elif k == "paper":
                new[k] = self._paper_name(v)
            elif k == "ppi":
                s = str(v).strip().lower()
                if s in ("auto", "авто"):
                    new[k] = "Авто"
                elif s in PPI_CHOICES:
                    new[k] = s
                else:
                    raise AgentError("ppi: auto или число (" + ", ".join(PPI_CHOICES[1:]) + ")", "bad_value")
            elif k == "export_fmt":
                if str(v).upper() not in EXPORT_FORMATS:
                    raise AgentError("export_fmt: " + "|".join(EXPORT_FORMATS), "bad_value")
                new[k] = str(v).upper()
            else:
                try:
                    float(str(v).replace(",", "."))
                except ValueError:
                    raise AgentError(f"{k}: ожидается число", "bad_value")
                new[k] = str(v)
        self.popts = new
        self.settings["print"] = dict(new)
        save_settings(self.settings)
        return self.cmd_get_print_options({})

    def cmd_list_presets(self, a):
        p = self.settings.get("print_presets", {})
        return {"presets": [{"name": n, "printer": v.get("printer")} for n, v in sorted(p.items())]}

    def cmd_save_preset(self, a):
        name = str(a.get("name", "")).strip()
        if not name:
            raise AgentError("name: пустое имя", "bad_value")
        self.settings.setdefault("print_presets", {})[name] = {
            "printer": self.printer, "opts": dict(self.popts),
            "devmode": base64.b64encode(self.blob).decode() if self.blob else "", "cm": dict(self.cm)}
        save_settings(self.settings)
        return {"saved": name, "includes_color_profile": bool(self.cm["icc"])}

    def cmd_load_preset(self, a):
        name = str(a.get("name", "")).strip()
        p = self.settings.get("print_presets", {}).get(name)
        if not p:
            raise AgentError(f"Пресет «{name}» не найден.", "not_found", available=sorted(self.settings.get("print_presets", {})))
        self.popts.update({k: v for k, v in p.get("opts", {}).items() if k in PRINT_DEFAULTS})
        self.active_preset = name
        if p.get("cm"):
            self.cm.update({k: p["cm"][k] for k in ("on", "icc", "intent", "bpc", "embed") if k in p["cm"]})
        self.printers = list_printers()
        if p.get("printer") and p["printer"] in self.printers:
            self.printer = p["printer"]
            try:
                b = base64.b64decode(p.get("devmode", ""))
                if devmode_valid(b):
                    self.blob = b
                    self._store_blob()
                else:
                    self.blob = None
            except Exception:
                self.blob = None
        self.settings["print"] = dict(self.popts)
        warn = None
        if p.get("cm") and p["cm"].get("on") and not Path(self.cm["icc"]).is_file():
            warn = f"Файл профиля из пресета не найден: {self.cm['icc']}"
        return {"loaded": name, "printer": self.printer or None, "options": self._popts_typed(),
                "color_profile": dict(self.cm), "warning": warn}

    def cmd_delete_preset(self, a):
        name = str(a.get("name", "")).strip()
        if self.settings.get("print_presets", {}).pop(name, None) is None:
            raise AgentError(f"Пресет «{name}» не найден.", "not_found")
        save_settings(self.settings)
        return {"deleted": name}

    # ================= команды: раскладка, проверка, печать
    def cmd_plan_print(self, a):
        return self._plan_summary(self._ctx(a))

    def cmd_render_sheet(self, a):
        c = self._ctx(a)
        k = int(fnum(a.get("sheet"), 0, 0))
        if k >= len(c["plan"]["sheets"]):
            raise AgentError(f"sheet: есть только листы 0..{len(c['plan']['sheets']) - 1}", "bad_value")
        ppi = int(fnum(a.get("ppi"), 100, 20, 600))
        img = compose_sheet(c["plan"], k, c["photos"], ppi, c["o"], c["mode"], fast=True)
        if c["cm"]:
            if self._flag(a, "proof", c["o"]["proof"]):
                img = proof_preview(img, None, c["cm"])
        dest = self._path(a["path"], "path") if a.get("path") else AGENT_DIR / "preview" / f"sheet_{k + 1:03d}.png"
        dest.parent.mkdir(parents=True, exist_ok=True)
        img.save(dest, "PNG", dpi=(ppi, ppi))
        res = {"sheet": k, "file": str(dest), "size_px": list(img.size), "paper_mm": [round(v, 1) for v in c["plan"]["geom"]["paper"]],
               "items": self._plan_summary(c)["sheets"][k]["items"], "analysis": analyze_image(img)}
        if self._flag(a, "inline", False):
            res["_image_b64"] = self._jpeg_b64(img, 800)
        return res

    def cmd_preflight(self, a):
        try:
            c = self._ctx(a, need_printer=True)
        except AgentError as ex:
            if ex.code in ("no_photos", "no_folder"):
                return {"ready": False, "checks": [{"level": "error", "code": ex.code, "message": str(ex)}]}
            if ex.code == "no_printer":
                return {"ready": False, "checks": [{"level": "error", "code": "no_printer", "message": str(ex)}]}
            raise
        checks = self._checks(c)
        return {"ready": not any(x["level"] == "error" for x in checks), "checks": checks,
                "sheets_to_print": len(c["idxs"]) * c["o"]["sheet_copies"], "ppi": c["ppi"], "printer": self.printer}

    def cmd_print(self, a):
        c = self._ctx(a, need_printer=True)
        checks = self._checks(c)
        errors = [x for x in checks if x["level"] == "error"]
        warns = [x for x in checks if x["level"] == "warning"]
        total = len(c["idxs"]) * c["o"]["sheet_copies"]
        base = {"printer": self.printer, "sheets_to_print": total, "ppi": c["ppi"], "checks": checks}
        if errors:
            raise AgentError(errors[0]["message"], "preflight_failed", **base)
        if self._flag(a, "strict", False) and warns:
            raise AgentError("strict: есть предупреждения — " + warns[0]["message"], "preflight_warnings", **base)
        mx = int(fnum(a.get("max_sheets"), 200, 1, 100000))
        if total > mx:
            raise AgentError(f"К печати {total} листов — больше лимита max_sheets={mx}.", "too_many_sheets", **base)
        if self._flag(a, "dry_run", False) or os.environ.get("PHOTOCROP_AGENT_DRYRUN"):
            return {"dry_run": True, **base, "plan": self._plan_summary(c)}
        c["blob"] = prepare_blob(self.printer, self.blob, c["plan"]["orient"], c["o"])
        c.update(kind="print", printer=self.printer)
        job_title = str(a.get("title") or "PhotoCrop")
        job_id_hint = time.strftime("%H%M%S")
        c["title"] = f"{job_title} {job_id_hint}"
        self.last_title = c["title"]
        res = self._run_job("print", c["title"], self._sheets_work(c), a, 120)
        res.update(base)
        res["document_title"] = c["title"]
        res["note"] = "Статус «done» = все листы переданы в очередь печати. Физическое завершение — wait_queue / queue."
        return res

    def cmd_export_sheets(self, a):
        c = self._ctx(a)
        if a.get("format"):
            f = str(a["format"]).upper()
            if f not in EXPORT_FORMATS:
                raise AgentError("format: " + "|".join(EXPORT_FORMATS), "bad_value")
            c["o"] = dict(c["o"], export_fmt=f)
        d = a.get("dir") or (str(Path(self.save["outdir"]) / "Листы") if self.save["outdir"] else None)
        c.update(kind="export", dir=self._path(d, "dir"))
        return self._run_job("export", str(c["dir"]), self._sheets_work(c), a, 300)

    # ================= команды: принтер/очередь/задания
    def _pname(self, a):
        n = a.get("printer") or self.printer
        if not n:
            self._ensure_printer()
            n = self.printer
        if not n:
            raise AgentError("Принтер не выбран.", "no_printer")
        return n

    def cmd_printer_status(self, a):
        return spooler_printer_status(self._pname(a))

    def cmd_queue(self, a):
        n = self._pname(a)
        return {"printer": n, "jobs": spooler_queue(n)}

    def cmd_job_control(self, a):
        act = str(a.get("action", "")).lower()
        if act not in SPOOLER_ACTIONS:
            raise AgentError("action: " + " | ".join(SPOOLER_ACTIONS), "bad_value")
        try:
            jid = int(a.get("job_id"))
        except (TypeError, ValueError):
            raise AgentError("job_id: целое число из команды queue", "bad_value")
        n = self._pname(a)
        spooler_job_action(n, jid, act)
        return {"printer": n, "job_id": jid, "action": act, "queue": spooler_queue(n)}

    def cmd_clear_queue(self, a):
        n = self._pname(a)
        spooler_clear(n)
        return {"printer": n, "queue": spooler_queue(n)}

    def cmd_pause_printer(self, a):
        n = self._pname(a)
        spooler_pause_printer(n, True)
        return {"printer": n, "paused": True}

    def cmd_resume_printer(self, a):
        n = self._pname(a)
        spooler_pause_printer(n, False)
        return {"printer": n, "paused": False}

    def cmd_wait_queue(self, a):
        n = self._pname(a)
        title = a.get("title") or self.last_title
        deadline = time.time() + fnum(a.get("timeout"), 300, 1, 86400)
        seen = False
        while True:
            q = spooler_queue(n)
            mine = [j for j in q if (not title or title in (j.get("document") or ""))]
            if mine:
                seen = True
            if not mine:
                return {"printer": n, "title": title, "state": "finished" if seen else "not_in_queue", "queue": q}
            st = spooler_printer_status(n)
            if st["error"] not in ("no_error", "unknown") or st["offline"]:
                return {"printer": n, "title": title, "state": "attention", "printer_status": st, "jobs": mine}
            if time.time() > deadline:
                return {"printer": n, "title": title, "state": "timeout", "jobs": mine, "printer_status": st}
            time.sleep(2.0)

    def cmd_jobs(self, a):
        return {"jobs": [j.info() for j in self.jobs.values()]}

    def _job(self, a):
        jid = a.get("job_id")
        if jid is None and self.jobs:
            jid = list(self.jobs)[-1]
        if jid not in self.jobs:
            raise AgentError(f"Задание «{jid}» не найдено.", "not_found", available=list(self.jobs))
        return self.jobs[jid]

    def cmd_job_status(self, a):
        j = self._job(a)
        if self._flag(a, "wait", False):
            j.finished.wait(fnum(a.get("timeout"), 120, 0, 86400))
        return j.info()

    def cmd_cancel_job(self, a):
        j = self._job(a)
        j.cancel.set()
        j.finished.wait(30)
        return j.info()

    def cmd_print_configuration(self, a):
        out = {"photos": len(self.files), "format": self.fmt_name, "orientation": self.orient_name, "mode": self.mode_name,
               "color_profile": self.cmd_get_color_profile({}), "printer": self.printer or None, "print_options": self._popts_typed()}
        try:
            self._ensure_printer()
            out["printer"] = self.printer or None
            if self.blob:
                out["driver_settings"] = devmode_read(self.blob)
        except Exception as ex:
            out["driver_error"] = str(ex)
        if self.files:
            try:
                out["plan"] = self._plan_summary(self._ctx({}))
                out["checks"] = self._checks(self._ctx({}))
            except AgentError as ex:
                out["plan_error"] = {"code": ex.code, "message": str(ex)}
        return out

    def cmd_save_project(self, a):
        p = self._path(a.get("path"), "path")
        write_json_atomic(p, self.to_project())
        return {"saved": str(p)}

    def cmd_load_project(self, a):
        p = self._path(a.get("path"), "path")
        try:
            self.from_project(json.loads(p.read_text(encoding="utf-8")))
        except (OSError, ValueError) as ex:
            raise AgentError(f"Не удалось прочитать проект: {ex}", "bad_project")
        return self.cmd_status({})

    def cmd_get_log(self, a):
        n = int(fnum(a.get("tail"), 30, 1, 500))
        try:
            lines = self.log_path.read_text(encoding="utf-8").splitlines()[-n:]
        except OSError:
            lines = []
        out = []
        for ln in lines:
            try:
                out.append(json.loads(ln))
            except ValueError:
                pass
        return {"entries": out}


# ---- каналы: CLI, JSON-строки (serve), MCP по stdio

REQUIRED = {   # обязательные параметры команд (для схем MCP)
    "open_folder": ["path"], "set_format": ["format"], "set_orientation": ["orientation"], "set_mode": ["mode"],
    "select_printer": ["name"], "save_preset": ["name"], "load_preset": ["name"], "delete_preset": ["name"],
    "save_project": ["path"], "load_project": ["path"], "job_control": ["job_id", "action"],
}


def _tool_schema(name):
    summary, params = SPEC[name]
    props = {}
    for pn, pt, pd in params:
        p = {"description": pd} if pd else {}
        if pt != "any":
            p["type"] = pt
        props[pn] = p
    schema = {"type": "object", "properties": props, "additionalProperties": True}
    req = [r for r in REQUIRED.get(name, []) if r in props]
    if req:
        schema["required"] = req
    # подсказки клиенту: что только читает, а что тратит бумагу или пишет на диск (клиент может не спрашивать подтверждение у безопасных)
    ann = {"readOnlyHint": name in READONLY, "openWorldHint": False}
    if name not in READONLY:
        ann["destructiveHint"] = name in ("print", "save_files", "export_sheets", "clear_queue", "cancel_job", "job_control")
    return {"name": name, "description": summary, "inputSchema": schema, "annotations": ann}


MCP_INSTRUCTIONS = (
    "PhotoCrop: crop photos for print formats, apply a printer ICC profile and print. Every command returns numbers (sizes, dpi, "
    "layout, image statistics), so you can verify work without seeing the screen; render_sheet/preview_photo with inline=true "
    "return a picture. Flow: open_folder → set_format → crop/adjust → set_color_profile → select_printer → set_driver_settings → "
    "set_print_options → plan_print → render_sheet → preflight → print(wait=false) → job_status / wait_queue / queue. "
    "Printing wastes paper: always run preflight first and check the checks list.")


MCP_VERSIONS = ("2025-06-18", "2025-03-26", "2024-11-05")


def _mcp_result(res):
    img = None
    if isinstance(res.get("result"), dict) and "_image_b64" in res["result"]:
        img = res["result"].pop("_image_b64")
    content = [{"type": "text", "text": json.dumps(res, ensure_ascii=False, default=_jsonable)}]
    if img:
        content.append({"type": "image", "data": img, "mimeType": "image/jpeg"})
    return {"content": content, "isError": not res.get("ok", False)}


def mcp_handle(session, msg):
    """Один JSON-RPC запрос MCP -> ответ (dict) или None для уведомлений."""
    mid, method, params = msg.get("id"), msg.get("method", ""), msg.get("params") or {}
    if mid is None:                       # уведомление
        return None
    ok = lambda r: {"jsonrpc": "2.0", "id": mid, "result": r}
    err = lambda c, m: {"jsonrpc": "2.0", "id": mid, "error": {"code": c, "message": m}}
    if method == "initialize":
        want = params.get("protocolVersion")
        ver = want if want in MCP_VERSIONS else MCP_VERSIONS[0]        # неизвестную версию клиента отвечаем нашей новейшей
        return ok({"protocolVersion": ver, "capabilities": {"tools": {"listChanged": False}},
                   "serverInfo": {"name": "photocrop", "version": AGENT_VERSION}, "instructions": MCP_INSTRUCTIONS})
    if method == "ping":
        return ok({})
    if method == "tools/list":
        return ok({"tools": [_tool_schema(n) for n in SPEC if n != "help"]})
    if method == "tools/call":
        name = params.get("name", "")
        if name not in SPEC:
            return err(-32602, f"Unknown tool: {name}")
        req = dict(params.get("arguments") or {})
        req["cmd"] = name
        return ok(_mcp_result(session.execute(req)))
    return err(-32601, f"Method not found: {method}")


def _stdio_utf8():
    for st in (sys.stdin, sys.stdout, sys.stderr):
        try:
            st.reconfigure(encoding="utf-8")
        except Exception:
            pass


def _parse_cli_value(v):
    try:
        return json.loads(v)
    except ValueError:
        return v


def mcp_server_entry():
    """Как Claude Desktop должен запускать сервер: exe (в сборке) или python + этот файл."""
    exe = sys.executable
    if getattr(sys, "frozen", False):
        return {"command": exe, "args": ["mcp"]}
    return {"command": exe, "args": [str(Path(__file__).resolve()), "mcp"]}


def mcp_install(args):
    """Дописывает сервер photocrop в claude_desktop_config.json (остальные серверы не трогает; рядом остаётся копия .bak).
    --path <файл>: другой файл конфигурации; --print: только показать."""
    path = None
    if "--path" in args:
        path = Path(args[args.index("--path") + 1])
    if path is None:
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        path = Path(base) / "Claude" / "claude_desktop_config.json"
    entry = mcp_server_entry()
    cfg = {}
    if path.is_file():
        try:
            cfg = json.loads(path.read_text(encoding="utf-8") or "{}")
        except ValueError:
            print(f"Файл {path} не является корректным JSON — исправьте его вручную, ничего не изменено.")
            return 2
        if not isinstance(cfg, dict):
            print(f"Файл {path}: ожидался JSON-объект — ничего не изменено.")
            return 2
    servers = cfg.setdefault("mcpServers", {})
    if not isinstance(servers, dict):
        print(f"Файл {path}: mcpServers должен быть объектом — ничего не изменено.")
        return 2
    servers["photocrop"] = entry
    text = json.dumps(cfg, ensure_ascii=False, indent=2)
    if "--print" in args:
        print(text)
        return 0
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file():
        shutil.copyfile(path, path.with_name(path.name + ".bak"))
    write_json_atomic(path, cfg)
    print(f"Готово: сервер photocrop записан в {path}\nПерезапустите Claude Desktop (закройте полностью, в т. ч. значок в трее).")
    return 0


def agent_main(argv):
    """photo_crop.py agent …  /  photo_crop.py mcp  /  photo_crop.py mcp-config"""
    import warnings
    warnings.simplefilter("ignore")      # предупреждения библиотек не должны засорять вывод агента
    _stdio_utf8()
    dump = lambda o, pretty=False: json.dumps(o, ensure_ascii=False, default=_jsonable, indent=1 if pretty else None)
    if argv and argv[0] == "mcp-config":
        print(dump({"mcpServers": {"photocrop": mcp_server_entry()}}, True))
        return 0
    if argv and argv[0] == "mcp-install":
        return mcp_install(argv[1:])
    if argv and argv[0] == "mcp":
        s = AgentSession()
        s.load_state()
        out = sys.stdout                       # протокол идёт только в настоящий stdout; случайные print() библиотек — в stderr
        sys.stdout = sys.stderr
        try:
            out.reconfigure(newline="\n")      # на Windows без «\r\n»: одна строка — одно сообщение
        except Exception:
            pass

        def send(obj):
            out.write(dump(obj) + "\n")
            out.flush()
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except ValueError:
                send({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}})
                continue
            if isinstance(msg, list):          # пакетный запрос -> один ответ-массив
                rs = [r for r in (mcp_handle(s, m) for m in msg if isinstance(m, dict)) if r is not None]
                if rs:
                    send(rs)
            elif isinstance(msg, dict):
                r = mcp_handle(s, msg)
                if r is not None:
                    send(r)
            else:
                send({"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "Invalid Request"}})
        return 0
    # agent …
    args = list(argv[1:]) if argv and argv[0] == "agent" else list(argv)
    pretty = "--pretty" in args
    args = [x for x in args if x != "--pretty"]
    fresh = "--fresh" in args
    args = [x for x in args if x != "--fresh"]
    s = AgentSession()
    if not fresh:
        s.load_state()
    if not args or args[0] in ("--list", "list", "--help", "-h"):
        print(dump({"usage": ["photo_crop.py agent <command> [key=value …]", "photo_crop.py agent '{\"cmd\":\"status\"}'",
                              "photo_crop.py agent --file commands.json", "photo_crop.py agent --serve   (JSON line in → JSON line out)",
                              "photo_crop.py mcp   |   photo_crop.py mcp-config"],
                    "commands": {k: v[0] for k, v in SPEC.items()}}, True))
        return 0
    if args[0] == "--serve":
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                req = json.loads(line)
            except ValueError:
                print(dump({"ok": False, "error": {"code": "bad_json", "message": "Некорректный JSON"}}), flush=True)
                continue
            reqs = req if isinstance(req, list) else [req]
            outs = [s.execute(r) for r in reqs]
            print(dump(outs if isinstance(req, list) else outs[0]), flush=True)
        return 0
    if args[0] == "--file":
        try:
            data = json.loads(Path(args[1]).read_text(encoding="utf-8"))
        except (IndexError, OSError, ValueError) as ex:
            print(dump({"ok": False, "error": {"code": "bad_file", "message": str(ex)}}))
            return 1
        outs = [s.execute(r) for r in (data if isinstance(data, list) else [data])]
        print(dump(outs, pretty))
        return 0 if all(o["ok"] for o in outs) else 1
    if args[0].lstrip().startswith("{"):
        try:
            req = json.loads(" ".join(args))
        except ValueError as ex:
            print(dump({"ok": False, "error": {"code": "bad_json", "message": str(ex)}}))
            return 1
    else:
        req = {"cmd": args[0]}
        for kv in args[1:]:
            if "=" not in kv:
                print(dump({"ok": False, "error": {"code": "bad_args", "message": f"Ожидается ключ=значение, получено «{kv}»"}}))
                return 1
            k, v = kv.split("=", 1)
            req[k] = _parse_cli_value(v)
    out = s.execute(req)
    if isinstance(out.get("result"), dict):
        out["result"].pop("_image_b64", None)
    print(dump(out, pretty))
    return 0 if out["ok"] else 1



# ---------------------------------------------------------------- интерфейс

THUMB = 104                      # сторона квадратной превьюшки, px
CELL_W, CELL_H = THUMB + 12, THUMB + 34


def desktop_dir():
    """Рабочий стол пользователя (Windows: реальный путь, в т.ч. перенесённый в OneDrive)."""
    if sys.platform == "win32":
        try:
            buf = ctypes.create_unicode_buffer(520)
            if ctypes.windll.shell32.SHGetFolderPathW(None, 0x10, None, 0, buf) == 0 and Path(buf.value).is_dir():
                return buf.value
        except Exception:
            pass
    home = Path.home()
    for p in (home / "Desktop", home / "OneDrive" / "Desktop", home / "Рабочий стол", home / "OneDrive" / "Рабочий стол"):
        if p.is_dir():
            return str(p)
    return str(home)


def make_thumb(path, rotation=0, size=THUMB):
    """Квадратная превьюшка (снимок целиком на тёмном фоне) — PIL-картинка size×size."""
    with Image.open(path) as im0:
        im0.draft("RGB", (size * 2, size * 2))
        icc = im0.info.get("icc_profile")
        im = ImageOps.exif_transpose(im0)
        if rotation:
            im = im.rotate(-rotation, expand=True)
        im = to_rgb(im, icc)
        im.thumbnail((size, size), RESAMPLE_FAST)
    bg = Image.new("RGB", (size, size), (32, 32, 32))
    bg.paste(im, ((size - im.width) // 2, (size - im.height) // 2))
    return bg


# ---------------------------------------------------------------- оформление: темы, подсказки, иконки, анимация

THEMES = {
    "brand": {"title": "Фирменная",
              "bg": "#14213d", "fg": "#edf0f7", "muted": "#9fb0d0", "field": "#1d2d50", "border": "#2c3f69",
              "accent": "#fca311", "accent_hi": "#ffbb4d", "accent_fg": "#14213d", "btn": "#22345c", "btn_hover": "#2c4273",
              "canvas": "#0d1526", "thumbs": "#101b33", "tile": "#1b2a4a", "tile_sel": "#3a4f80", "sel_line": "#fca311",
              "tile_fg": "#dfe6f5", "check": "#fca311", "check_fg": "#14213d", "frame": "#fca311"},
    "dark": {"title": "Тёмная",
             "bg": "#23262b", "fg": "#e6e8eb", "muted": "#9aa1ab", "field": "#2f333a", "border": "#3d424b",
             "accent": "#4c9aff", "accent_hi": "#78b4ff", "accent_fg": "#0b1220", "btn": "#343942", "btn_hover": "#414752",
             "canvas": "#17191c", "thumbs": "#1c1e22", "tile": "#2b2f36", "tile_sel": "#2f4f7a", "sel_line": "#7fb2ff",
             "tile_fg": "#dddddd", "check": "#2e9e4f", "check_fg": "#ffffff", "frame": "#ffcc00"},
    "light": {"title": "Светлая",
              "bg": "#f4f5f7", "fg": "#1f2328", "muted": "#5f6672", "field": "#ffffff", "border": "#c9ced6",
              "accent": "#2563eb", "accent_hi": "#3b82f6", "accent_fg": "#ffffff", "btn": "#e6e9ee", "btn_hover": "#d8dde5",
              "canvas": "#6b6f76", "thumbs": "#e3e6eb", "tile": "#ffffff", "tile_sel": "#cfe0ff", "sel_line": "#2563eb",
              "tile_fg": "#1f2328", "check": "#2e9e4f", "check_fg": "#ffffff", "frame": "#ffcc00"},
    "mono": {"title": "Чёрно-серо-белая",
             "bg": "#2b2b2b", "fg": "#f0f0f0", "muted": "#a8a8a8", "field": "#3a3a3a", "border": "#5a5a5a",
             "accent": "#e6e6e6", "accent_hi": "#ffffff", "accent_fg": "#111111", "btn": "#404040", "btn_hover": "#525252",
             "canvas": "#777777", "thumbs": "#1e1e1e", "tile": "#333333", "tile_sel": "#666666", "sel_line": "#ffffff",
             "tile_fg": "#e0e0e0", "check": "#f0f0f0", "check_fg": "#111111", "frame": "#ffffff"},
}
DEFAULT_THEME = "brand"
PAL = dict(THEMES[DEFAULT_THEME])          # текущая палитра; читают все, кто рисует сам (холсты, превью)
UI_FONT = ("Segoe UI", 10)
ICON_FONT = ("Segoe UI Symbol", 13)
_MUTED_SRC = {"#555", "#666", "#888", "#555555", "#666666", "#888888"}


def apply_theme(root, name):
    """Включает тему: цвета всех ttk-виджетов задаются через стили (основа — «clam», её можно красить),
    обычные tk-виджеты и холсты перекрашивает theme_walk. Ошибка оформления не должна мешать работе."""
    PAL.clear()
    PAL.update(THEMES.get(name, THEMES[DEFAULT_THEME]))
    p = PAL
    try:
        st = ttk.Style()
        try:
            st.theme_use("clam")
        except Exception:
            pass
        c = st.configure
        c(".", background=p["bg"], foreground=p["fg"], fieldbackground=p["field"], bordercolor=p["border"],
          lightcolor=p["bg"], darkcolor=p["bg"], troughcolor=p["field"], focuscolor=p["accent"],
          selectbackground=p["accent"], selectforeground=p["accent_fg"], insertcolor=p["fg"], font=UI_FONT)
        c("TFrame", background=p["bg"])
        c("TLabel", background=p["bg"], foreground=p["fg"])
        c("TSeparator", background=p["border"])
        for nm, pad in (("TButton", (10, 5)), ("Big.TButton", (12, 7)), ("Icon.TButton", (7, 3))):
            c(nm, background=p["btn"], foreground=p["fg"], bordercolor=p["border"], lightcolor=p["btn"], darkcolor=p["btn"],
              relief="flat", padding=pad)
            st.map(nm, background=[("pressed", p["border"]), ("active", p["btn_hover"])],
                   lightcolor=[("active", p["btn_hover"])], darkcolor=[("active", p["btn_hover"])],
                   foreground=[("disabled", p["muted"])])
        c("Icon.TButton", font=ICON_FONT)
        c("Accent.TButton", background=p["accent"], foreground=p["accent_fg"], bordercolor=p["accent"], lightcolor=p["accent"],
          darkcolor=p["accent"], relief="flat", padding=(12, 7), font=(UI_FONT[0], UI_FONT[1], "bold"))
        st.map("Accent.TButton", background=[("disabled", p["btn"]), ("pressed", p["accent"]), ("active", p["accent_hi"])],
               lightcolor=[("active", p["accent_hi"])], darkcolor=[("active", p["accent_hi"])],
               foreground=[("disabled", p["muted"])])
        c("Toolbutton", background=p["btn"], foreground=p["fg"], bordercolor=p["border"], relief="flat", padding=(12, 5))
        st.map("Toolbutton", background=[("selected", p["accent"]), ("active", p["btn_hover"])],
               foreground=[("selected", p["accent_fg"])])
        for nm in ("TCheckbutton", "TRadiobutton"):
            c(nm, background=p["bg"], foreground=p["fg"], indicatorbackground=p["field"], indicatorforeground=p["accent_fg"],
              upperbordercolor=p["border"], lowerbordercolor=p["border"])
            st.map(nm, background=[("active", p["bg"])], indicatorbackground=[("selected", p["accent"]), ("active", p["btn_hover"])],
                   foreground=[("disabled", p["muted"])])
        for nm in ("TEntry", "TSpinbox", "TCombobox"):
            c(nm, fieldbackground=p["field"], foreground=p["fg"], background=p["btn"], bordercolor=p["border"],
              lightcolor=p["field"], darkcolor=p["field"], arrowcolor=p["fg"], insertcolor=p["fg"], padding=3)
            st.map(nm, fieldbackground=[("readonly", p["field"]), ("disabled", p["bg"])],
                   foreground=[("disabled", p["muted"]), ("readonly", p["fg"])],
                   selectbackground=[("readonly", p["field"]), ("!focus", p["field"])],
                   selectforeground=[("readonly", p["fg"]), ("!focus", p["fg"])],
                   bordercolor=[("focus", p["accent"])], background=[("active", p["btn_hover"])])
        c("TNotebook", background=p["bg"], bordercolor=p["border"], tabmargins=(2, 4, 2, 0))
        c("TNotebook.Tab", background=p["btn"], foreground=p["muted"], bordercolor=p["border"], lightcolor=p["btn"], padding=(12, 6))
        st.map("TNotebook.Tab", background=[("selected", p["bg"]), ("active", p["btn_hover"])],
               foreground=[("selected", p["fg"])], lightcolor=[("selected", p["accent"])])
        c("TLabelframe", background=p["bg"], bordercolor=p["border"], lightcolor=p["bg"], darkcolor=p["bg"])
        c("TLabelframe.Label", background=p["bg"], foreground=p["muted"])
        c("TScale", background=p["btn_hover"], troughcolor=p["field"], bordercolor=p["border"], lightcolor=p["btn_hover"], darkcolor=p["btn_hover"])
        c("TProgressbar", background=p["accent"], troughcolor=p["field"], bordercolor=p["border"], lightcolor=p["accent"], darkcolor=p["accent"])
        c("TScrollbar", background=p["btn"], troughcolor=p["bg"], bordercolor=p["bg"], arrowcolor=p["fg"], lightcolor=p["btn"], darkcolor=p["btn"])
        st.map("TScrollbar", background=[("active", p["btn_hover"])])
        c("Treeview", background=p["field"], fieldbackground=p["field"], foreground=p["fg"], bordercolor=p["border"], rowheight=24)
        c("Treeview.Heading", background=p["btn"], foreground=p["fg"], relief="flat")
        st.map("Treeview", background=[("selected", p["accent"])], foreground=[("selected", p["accent_fg"])])
    except Exception:
        pass
    try:
        for k, v in (("*TCombobox*Listbox.background", p["field"]), ("*TCombobox*Listbox.foreground", p["fg"]),
                     ("*TCombobox*Listbox.selectBackground", p["accent"]), ("*TCombobox*Listbox.selectForeground", p["accent_fg"]),
                     ("*Menu.background", p["field"]), ("*Menu.foreground", p["fg"]),
                     ("*Menu.activeBackground", p["accent"]), ("*Menu.activeForeground", p["accent_fg"])):
            root.option_add(k, v)
    except Exception:
        pass
    theme_walk(root)


def theme_walk(w):
    """Перекрашивает обычные tk-виджеты, приглушённые подписи и холсты под текущую тему (вглубь по дереву)."""
    p = PAL
    try:
        cls = str(w.winfo_class())
    except Exception:
        return
    try:
        if cls in ("Tk", "Toplevel", "Frame"):
            w.configure(bg=p["bg"])
        elif cls == "Label":
            w.configure(bg=p["bg"])
            if not getattr(w, "_own_fg", False):
                w.configure(fg=p["fg"])
        elif cls == "TLabel":
            if getattr(w, "_muted", False) or str(w.cget("foreground")) in _MUTED_SRC:
                w._muted = True
                w.configure(foreground=p["muted"])
        elif cls == "Canvas":
            key = getattr(w, "_th_key", None)
            if key:
                w.configure(bg=p[key])
        elif cls == "TCombobox":
            try:
                pop = w.tk.eval("ttk::combobox::PopdownWindow %s" % w)
                w.tk.call(pop + ".f.l", "configure", "-background", p["field"], "-foreground", p["fg"],
                          "-selectbackground", p["accent"], "-selectforeground", p["accent_fg"])
            except Exception:
                pass
        elif cls == "Menu":
            w.configure(bg=p["field"], fg=p["fg"], activebackground=p["accent"], activeforeground=p["accent_fg"])
    except Exception:
        pass
    try:
        kids = w.winfo_children()
    except Exception:
        return
    for k in kids:
        theme_walk(k)


class Tooltip:
    """Всплывающая подсказка к кнопке-иконке (появляется через полсекунды после наведения)."""

    def __init__(self, widget, text):
        self.w, self.text, self.tip, self._id = widget, text, None, None
        try:
            widget.bind("<Enter>", self._enter, add="+")
            widget.bind("<Leave>", self._leave, add="+")
            widget.bind("<ButtonPress>", self._leave, add="+")
        except Exception:
            pass

    def _enter(self, e=None):
        self._leave()
        try:
            self._id = self.w.after(500, self._show)
        except Exception:
            pass

    def _show(self):
        self._id = None
        try:
            x = self.w.winfo_rootx() + 8
            y = self.w.winfo_rooty() + self.w.winfo_height() + 6
            t = self.tip = tk.Toplevel(self.w)
            t.wm_overrideredirect(True)
            t.wm_geometry("+%d+%d" % (x, y))
            tk.Label(t, text=tr(self.text), bg=PAL["field"], fg=PAL["fg"], bd=0, padx=8, pady=4, font=(UI_FONT[0], 9),
                     highlightthickness=1, highlightbackground=PAL["accent"]).pack()
        except Exception:
            self.tip = None

    def _leave(self, e=None):
        try:
            if self._id:
                self.w.after_cancel(self._id)
            if self.tip is not None:
                self.tip.destroy()
        except Exception:
            pass
        self._id = self.tip = None


def icon_btn(parent, glyph, tip, command, **kw):
    """Кнопка-иконка без подписи; смысл — во всплывающей подсказке."""
    b = ttk.Button(parent, text=glyph, style="Icon.TButton", width=kw.pop("width", 3), command=command, **kw)
    b._tip = Tooltip(b, tip)
    return b


class SendAnim:
    """Анимация отправки листа на печать: лист с фото «въезжает» в принтер, счётчик показывает сколько отправлено."""
    H = 72
    FRAMES = 26
    STEP_MS = 22

    def __init__(self, parent):
        self.cv = tk.Canvas(parent, height=self.H, highlightthickness=0, bg=PAL["bg"])
        self.cv._th_key = "bg"
        self.kind = "print"
        self._job = None
        self._t = 0
        self._img = None
        self._count = ""
        self._led = False
        try:
            self.cv.bind("<Configure>", lambda e: self._paint(None))
        except Exception:
            pass

    def pack(self, **kw):
        self.cv.pack(**kw)

    def reset(self, kind="print"):
        self.kind, self._count, self._led = kind, "", False
        self._stop()
        self._paint(None)

    def _stop(self):
        if self._job is not None:
            try:
                self.cv.after_cancel(self._job)
            except Exception:
                pass
            self._job = None

    def send(self, j, n, thumb=None):
        """Запускает полёт листа j из n. thumb — миниатюра PIL для листа (или None — пустой лист)."""
        self._stop()
        self._count = f"{j} / {n}"
        self._img = None
        if thumb is not None and ImageTk is not None:
            try:
                self._img = ImageTk.PhotoImage(thumb.resize((30, 30)))
            except Exception:
                self._img = None
        self._t = 0
        self._tick()

    def done(self):
        self._stop()
        self._led = False
        self._paint(None, final=True)

    def _tick(self):
        self._job = None
        self._t += 1
        f = min(1.0, self._t / self.FRAMES)
        self._led = (self._t // 4) % 2 == 0
        self._paint(f * f * (3 - 2 * f))            # плавный разгон и торможение
        if self._t < self.FRAMES:
            try:
                self._job = self.cv.after(self.STEP_MS, self._tick)
            except Exception:
                self._job = None
        else:
            self._led = False
            self._paint(None)

    def _paint(self, t, final=False):
        c, p = self.cv, PAL
        try:
            c.delete("all")
            W = max(240, int(c.winfo_width()))
        except Exception:
            return
        H = self.H
        px = W - 96                                   # левый край принтера
        c.create_line(16, H - 14, px, H - 14, fill=p["border"], dash=(2, 4))
        if t is not None:                             # лист едет слева в щель принтера
            x = 16 + (px + 18 - 16) * t
            y = H - 14 - 44
            c.create_rectangle(x, y, x + 34, y + 44, fill="white", outline=p["border"])
            if self._img is not None:
                c.create_image(x + 2, y + 7, anchor="nw", image=self._img)
            else:
                c.create_rectangle(x + 4, y + 8, x + 30, y + 34, fill=p["accent"], outline="")
        # принтер рисуется поверх листа — лист «уходит» внутрь
        c.create_rectangle(px + 14, 8, px + 66, 24, fill=p["field"], outline=p["border"])          # лоток сверху
        c.create_rectangle(px, 22, px + 80, H - 12, fill=p["btn"], outline=p["border"], width=1)   # корпус
        c.create_rectangle(px + 8, H - 26, px + 72, H - 20, fill=p["canvas"], outline="")           # щель выдачи
        c.create_oval(px + 64, 28, px + 72, 36, fill=p["accent"] if (self._led or final) else p["border"], outline="")
        c.create_text(px + 34, 38, text="✓" if final else ("💾" if self.kind == "export" else "🖨"), fill=p["fg"], font=(UI_FONT[0], 12))
        if self._count:
            c.create_text(16, 10, anchor="w", text=self._count, fill=p["muted"], font=(UI_FONT[0], 9, "bold"))


class OpenDialog:
    """Универсальное окно «Открыть»: в одном списке папки и фотографии. Можно выделить мышью несколько фото
    (Ctrl/Shift, Ctrl+A — все) и открыть только их, а можно открыть папку целиком — одной и той же кнопкой.
    Результат: self.result = ("files", [пути], добавить) | ("folder", путь, добавить) | None."""

    def __init__(self, app, start):
        self.app, self.result = app, None
        self.cwd = Path(start) if start and Path(start).is_dir() else Path(desktop_dir())
        self.items = {}                       # id строки -> (вид, путь)
        self.n_files = 0
        self._prev_img = None
        w = self.win = tk.Toplevel(app.root)
        w.title("Открыть фото или папку")
        w.geometry("860x560")
        w.minsize(700, 420)
        w.transient(app.root)
        top = ttk.Frame(w, padding=(10, 10, 10, 4))
        top.pack(fill="x")
        icon_btn(top, "⬆", "На уровень выше", self.up).pack(side="left")
        self.v_path = tk.StringVar(value=str(self.cwd))
        ent = ttk.Entry(top, textvariable=self.v_path)
        ent.pack(side="left", fill="x", expand=True, padx=6)
        ent.bind("<Return>", lambda e: self.goto(self.v_path.get()))
        places = ttk.Frame(w, padding=(10, 0, 10, 6))
        places.pack(fill="x")
        home = Path.home()
        for label, pth in (("🖥 Рабочий стол", Path(desktop_dir())), ("🖼 Изображения", home / "Pictures"),
                           ("⬇ Загрузки", home / "Downloads")):
            if pth.is_dir():
                ttk.Button(places, text=label, command=lambda q=pth: self.goto(q)).pack(side="left", padx=(0, 4))
        if sys.platform == "win32":
            ttk.Button(places, text="💽 Диски", command=lambda: self.goto(None)).pack(side="left")
        body = ttk.Frame(w, padding=(10, 0, 10, 0))
        body.pack(fill="both", expand=True)
        side = ttk.Frame(body, width=236)
        side.pack(side="right", fill="y", padx=(8, 0))
        self.prev = tk.Canvas(side, width=228, height=228, highlightthickness=0, bg=PAL["canvas"])
        self.prev._th_key = "canvas"
        self.prev.pack()
        self.v_prev = tk.StringVar(value="")
        ttk.Label(side, textvariable=self.v_prev, wraplength=226, justify="left").pack(anchor="w", pady=(6, 0))
        tv = self.tv = ttk.Treeview(body, columns=("size",), show="tree headings", selectmode="extended")
        tv.heading("#0", text=tr("Имя"), anchor="w")
        tv.heading("size", text=tr("Размер"), anchor="e")
        tv.column("#0", width=430, anchor="w")
        tv.column("size", width=90, anchor="e", stretch=False)
        sb = ttk.Scrollbar(body, orient="vertical", command=tv.yview)
        tv.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        tv.pack(side="left", fill="both", expand=True)
        tv.bind("<<TreeviewSelect>>", lambda e: self._upd())
        tv.bind("<Double-Button-1>", self._dbl)
        tv.bind("<Return>", lambda e: self.accept())
        tv.bind("<BackSpace>", lambda e: self.up())
        for k in ("<Control-a>", "<Control-A>", "<Control-Cyrillic_ef>", "<Control-Cyrillic_EF>"):
            tv.bind(k, self._select_all)
        bot = ttk.Frame(w, padding=10)
        bot.pack(fill="x")
        opts = ttk.Frame(bot)
        opts.pack(fill="x")
        ttk.Checkbutton(opts, text="с подпапками", variable=app.v_recursive, command=self._upd).pack(side="left")
        self.v_add = tk.BooleanVar(value=False)
        if app.files:
            ttk.Checkbutton(opts, text="Добавить к уже открытым фото", variable=self.v_add).pack(side="left", padx=(14, 0))
        self.v_hint = tk.StringVar(value="")
        ttk.Label(opts, textvariable=self.v_hint, foreground="#666").pack(side="right")
        btns = ttk.Frame(bot)
        btns.pack(fill="x", pady=(8, 0))
        ttk.Button(btns, text="Отмена", command=w.destroy).pack(side="right")
        self.btn = ttk.Button(btns, text="Открыть", style="Accent.TButton", command=self.accept)
        self.btn.pack(side="right", padx=(0, 8))
        w.bind("<Escape>", lambda e: w.destroy())
        self.fill()
        try:
            theme_walk(w)
            i18n_apply(w)
            tv.focus_set()
        except Exception:
            pass
        try:
            w.wait_visibility()
            w.grab_set()
        except Exception:
            pass

    # ---- содержимое папки
    @staticmethod
    def list_dir(folder):
        """(папки, фото) в папке, по порядку «как в проводнике». folder=None — список дисков (Windows)."""
        if folder is None:
            import string
            return [Path(f"{c}:\\") for c in string.ascii_uppercase if os.path.exists(f"{c}:\\")], []
        dirs, files = [], []
        try:
            for q in Path(folder).iterdir():
                if q.name.startswith(".") or q.name.startswith("$"):
                    continue
                try:
                    if q.is_dir():
                        dirs.append(q)
                    elif q.suffix.lower() in EXTS and q.is_file():
                        files.append(q)
                except OSError:
                    pass
        except OSError:
            pass
        return sorted(dirs, key=natural_key), sorted(files, key=natural_key)

    @staticmethod
    def decide(sel, cwd, n_files):
        """Что делает кнопка «Открыть» при таком выделении: ("files", [...]) | ("folder", путь) | None.
        sel — список (вид, путь). Выделены фото — открываются они; выделена одна папка — она целиком;
        ничего не выделено — вся текущая папка."""
        files = [q for k, q in sel if k == "f"]
        dirs = [q for k, q in sel if k == "d"]
        if files:
            return ("files", files)
        if len(dirs) == 1:
            return ("folder", dirs[0])
        if not dirs and cwd is not None:
            return ("folder", cwd)
        return None

    def fill(self):
        tv = self.tv
        tv.delete(*tv.get_children())
        self.items = {}
        dirs, files = self.list_dir(self.cwd)
        self.n_files = len(files)
        for q in dirs:
            iid = tv.insert("", "end", text="📁  " + (q.name or str(q)), values=("",))
            self.items[iid] = ("d", q)
        for q in files:
            try:
                sz = q.stat().st_size
                size = f"{sz / 1048576:.1f} МБ" if sz >= 1048576 else f"{max(1, sz // 1024)} КБ"
            except OSError:
                size = ""
            iid = tv.insert("", "end", text="🖼  " + q.name, values=(size,))
            self.items[iid] = ("f", q)
        self.v_path.set("" if self.cwd is None else str(self.cwd))
        self._upd()

    def goto(self, target):
        if target is None:
            self.cwd = None
        else:
            q = Path(str(target).strip().strip('"'))
            if q.is_file():
                q = q.parent
            if not q.is_dir():
                return
            self.cwd = q
        self.fill()

    def up(self):
        if self.cwd is None:
            return
        par = self.cwd.parent
        if par == self.cwd:
            if sys.platform == "win32":
                self.goto(None)
            return
        self.goto(par)

    def _sel(self):
        return [self.items[i] for i in self.tv.selection() if i in self.items]

    def _select_all(self, e=None):
        self.tv.selection_set([i for i, (k, _) in self.items.items() if k == "f"])
        return "break"

    def _dbl(self, e=None):
        sel = self._sel()
        if len(sel) == 1 and sel[0][0] == "d":
            self.goto(sel[0][1])
            return "break"
        if len(sel) == 1:
            self.accept()
            return "break"

    def _upd(self):
        sel = self._sel()
        act = self.decide(sel, self.cwd, self.n_files)
        rec = bool(self.app.v_recursive.get())
        if act is None:
            text, ok = tr("Открыть"), False
        elif act[0] == "files":
            text, ok = trf("Открыть выбранные фото ({n})", n=len(act[1])), True
        elif sel:
            text, ok = trf("Открыть папку «{name}» целиком", name=act[1].name or str(act[1])), True
        else:
            text = trf("Открыть всю папку ({n} фото)", n=self.n_files) if not rec else tr("Открыть всю папку с подпапками")
            ok = self.n_files > 0 or rec
        try:
            self.btn.config(text=text, state="normal" if ok else "disabled")
            self.v_hint.set(tr("Ctrl/Shift — несколько фото, Ctrl+A — все, двойной щелчок — войти в папку"))
        except Exception:
            pass
        self._preview(next((q for k, q in sel if k == "f"), None))

    def _preview(self, q):
        c = self.prev
        try:
            c.delete("all")
            if q is None:
                self.v_prev.set(trf("В папке фото: {n}", n=self.n_files))
                return
            im = make_thumb(str(q), 0, 228)
            self._prev_img = ImageTk.PhotoImage(im)
            c.create_image(114, 114, image=self._prev_img)
            self.v_prev.set(q.name)
        except Exception:
            self.v_prev.set(q.name if q else "")

    def accept(self):
        act = self.decide(self._sel(), self.cwd, self.n_files)
        if act is None:
            return
        self.result = (act[0], act[1], bool(self.v_add.get()))
        self.win.destroy()

    def show(self):
        try:
            self.app.root.wait_window(self.win)
        except Exception:
            pass
        return self.result


class ThumbList:
    """Колонка квадратных превью с отметками (как в QImage): + / ✓ в углу, клик по снимку открывает его в рабочем поле.
    Совместима по методам с tk.Listbox, которые использует программа. Рисуются только видимые плитки,
    миниатюры грузятся фоновым потоком."""

    def __init__(self, parent, app, width=2 * CELL_W + 22):
        self.app = app
        self.frame = ttk.Frame(parent)
        self.cv = tk.Canvas(self.frame, width=width, bg=PAL["thumbs"], highlightthickness=0)
        self.cv._th_key = "thumbs"
        self.sb = ttk.Scrollbar(self.frame, orient="vertical", command=self._scroll_cmd)
        self.cv.pack(side="left", fill="y", expand=True)
        self.sb.pack(side="left", fill="y")
        self.n, self.sel, self.top = 0, None, 0
        self._handler = None
        self.pil, self.tkimgs, self.pending = {}, {}, set()
        self._q = queue.Queue()
        self._lock = threading.Lock()
        self._done = []
        self._worker_on = False
        self.cv.bind("<Configure>", lambda e: self.draw())
        self.cv.bind("<ButtonPress-1>", self._click)
        self.cv.bind("<MouseWheel>", lambda e: self._wheel(-1 if e.delta > 0 else 1))
        self.cv.bind("<Button-4>", lambda e: self._wheel(-1))
        self.cv.bind("<Button-5>", lambda e: self._wheel(1))

    # ---- совместимость с Listbox
    def pack(self, **kw):
        self.frame.pack(**kw)

    def bind(self, event, fn):
        self._handler = fn

    def delete(self, a, b=None):
        if b == "end" or a == "end":
            self.n = 0
            self.sel = None
        else:
            self.n = max(0, self.n - 1)
        self.draw()

    def insert(self, pos, text=""):
        self.n += 1
        self.draw()

    def selection_clear(self, a=0, b=None):
        self.sel = None

    def selection_set(self, i):
        self.sel = i
        self.draw()

    def curselection(self):
        return (self.sel,) if self.sel is not None else ()

    def see(self, i):
        r = i // self._cols()
        y0, y1 = r * CELL_H, (r + 1) * CELL_H
        h = self._h()
        if y0 < self.top:
            self.top = y0
        elif y1 > self.top + h:
            self.top = y1 - h
        self.top = max(0, self.top)
        self.draw()

    def yview(self):
        tot = max(1, self._total())
        return (self.top / tot, min(1.0, (self.top + self._h()) / tot))

    def yview_moveto(self, f):
        self.top = int(f * self._total())
        self.draw()

    def configure(self, **kw):
        pass

    # ---- геометрия
    def _w(self):
        try:
            return max(CELL_W, int(self.cv.winfo_width()))
        except Exception:
            return 2 * CELL_W

    def _h(self):
        try:
            return max(50, int(self.cv.winfo_height()))
        except Exception:
            return 600

    def _cols(self):
        return max(1, self._w() // CELL_W)

    def _total(self):
        return ((self.n + self._cols() - 1) // self._cols()) * CELL_H

    def _scroll_cmd(self, *a):
        if a and a[0] == "moveto":
            self.yview_moveto(float(a[1]))
        elif a and a[0] == "scroll":
            self._wheel(int(a[1]) * (1 if a[2] == "units" else 3))

    def _wheel(self, d):
        self.top = max(0, min(max(0, self._total() - self._h()), self.top + d * CELL_H // 2))
        self.draw()

    # ---- миниатюры
    def _request(self, key):
        if key in self.pending or key in self.pil:
            return
        self.pending.add(key)
        self._q.put(key)
        if not self._worker_on:
            self._worker_on = True
            threading.Thread(target=self._loader, daemon=True).start()

    def _loader(self):
        while True:
            try:
                key = self._q.get(timeout=1.5)
            except queue.Empty:
                self._worker_on = False
                return
            try:
                im = make_thumb(key[0], key[1])
            except Exception:
                im = None
            with self._lock:
                self._done.append((key, im))

    def _pump(self):
        with self._lock:
            done, self._done = self._done, []
        if done:
            for key, im in done:
                self.pending.discard(key)
                self.pil[key] = im
            self.draw()
        if self.pending:
            try:
                self.cv.after(80, self._pump)
            except Exception:
                pass

    def forget(self, path):
        """Снимок изменился (поворот) — миниатюру нужно перерисовать."""
        for k in [k for k in list(self.pil) if k[0] == path]:
            self.pil.pop(k, None)
            self.tkimgs.pop(k, None)

    # ---- рисование и мышь
    def draw(self):
        c = self.cv
        c.delete("all")
        app = self.app
        cols = self._cols()
        h = self._h()
        self.top = max(0, min(self.top, max(0, self._total() - h)))
        r0 = self.top // CELL_H
        need = False
        for r in range(r0, r0 + h // CELL_H + 2):
            for cc in range(cols):
                i = r * cols + cc
                if i >= self.n or i >= len(app.files):
                    continue
                f = app.files[i]
                st = app.states.get(f)
                x, y = 6 + cc * CELL_W, r * CELL_H - self.top + 4
                cur = (i == self.sel)
                c.create_rectangle(x - 3, y - 3, x + THUMB + 3, y + CELL_H - 27, fill=PAL["tile_sel"] if cur else PAL["tile"],
                                   outline=PAL["sel_line"] if cur else PAL["border"], width=2 if cur else 1)
                key = (str(f), st.rotation if st else 0)
                im = self.pil.get(key)
                if im is not None:
                    ti = self.tkimgs.get(key)
                    if ti is None:
                        if len(self.tkimgs) > 700:
                            self.tkimgs.clear()
                        ti = self.tkimgs[key] = ImageTk.PhotoImage(im)
                    c.create_image(x, y, anchor="nw", image=ti)
                else:
                    c.create_rectangle(x, y, x + THUMB, y + THUMB, fill="#202020", outline="")
                    c.create_text(x + THUMB // 2, y + THUMB // 2, text="…" if key in self.pending or im is None and key not in self.pil else "?",
                                  fill="#888")
                    if key not in self.pil:
                        self._request(key)
                        need = True
                chk = f in app.checked
                c.create_oval(x + 4, y + 4, x + 26, y + 26, fill=PAL["check"] if chk else "#202020", outline="white", width=1)
                c.create_text(x + 15, y + 15, text="✓" if chk else "+", fill=PAL["check_fg"] if chk else "white", font=("Segoe UI", 11, "bold"))
                badge = ("✎" if st and st.edited else "") + ("◐" if st and st.adj else "") + (f" ×{st.copies}" if st and st.copies > 1 else "")
                if badge:
                    c.create_text(x + THUMB - 4, y + 12, text=badge, anchor="e", fill="#ffd54a", font=("Segoe UI", 10, "bold"))
                name = f.name if len(f.name) <= 17 else f.name[:8] + "…" + f.name[-8:]
                c.create_text(x + THUMB // 2, y + THUMB + 12, text=name, fill=PAL["tile_fg"], font=("Segoe UI", 8))
        tot = max(1, self._total())
        try:
            self.sb.set(self.top / tot, min(1.0, (self.top + h) / tot))
        except Exception:
            pass
        if need:
            try:
                self.cv.after(80, self._pump)
            except Exception:
                pass

    def _index_at(self, x, y):
        cols = self._cols()
        cc, r = (x - 3) // CELL_W, (y + self.top) // CELL_H
        i = r * cols + cc
        return (i if 0 <= cc < cols and 0 <= i < self.n else None), (x - 3) % CELL_W, (y + self.top) % CELL_H

    def _click(self, e):
        i, dx, dy = self._index_at(e.x, e.y)
        if i is None:
            return
        if dx < 34 and dy < 34:                       # плюс / галочка в углу
            self.app.toggle_check(i, shift=bool(getattr(e, "state", 0) & 0x1))
            self.draw()
            return
        self.sel = i
        self.draw()
        if self._handler:
            self._handler(None)


class App:
    HANDLE = 10
    ROT_OFFSET = 30   # расстояние от верхнего края рамки до ручки поворота, пикселей экрана
    CORNERS = ("nw", "ne", "se", "sw")

    def __init__(self, root):
        self.root = root
        root.title("PhotoCrop — кадрирование для фотопечати")
        root.geometry("1320x860")
        root.minsize(1000, 640)

        self.files = []
        self.states = {}
        self.idx = -1
        self.preview = None   # то, что показано на экране (с имитацией печати или без)
        self.raw = None       # предпросмотр без имитации
        self.icc = None       # встроенный профиль текущего фото
        self.cm_dialog = None
        self.size = (0, 0)
        self.tkimg = None
        self.tk_key = None
        self.geom = None
        self.drag = None
        self.q = queue.Queue()
        self.saving = False
        self.src_dir = None

        s = load_settings()
        self.settings = s
        set_language(s.get("language", "ru"))
        self.v_format = tk.StringVar(value=s.get("format") if s.get("format") in FORMATS else next(iter(FORMATS)))
        self.v_orient = tk.StringVar(value=s.get("orient") if s.get("orient") in ORIENTS else next(iter(ORIENTS)))
        self.v_mode = tk.StringVar(value=s.get("mode") if s.get("mode") in MODES else next(iter(MODES)))
        self.v_recursive = tk.BooleanVar(value=s.get("recursive", False))
        self.v_outdir = tk.StringVar(value=s.get("outdir_custom", ""))
        self.v_outmode = tk.StringVar(value=s.get("out_mode") if s.get("out_mode") in ("orig", "custom") else "orig")
        self.v_outname = tk.StringVar(value=s.get("out_name") or OUT_SUBDIR)
        self.v_subfolder = tk.BooleanVar(value=s.get("subfolder", False))
        self.v_copies_name = tk.BooleanVar(value=s.get("copies_in_name", True))
        self.v_dpi = tk.StringVar(value=str(s.get("dpi", 300)))
        self.v_resize = tk.BooleanVar(value=s.get("resize", True))
        self.v_filetype = tk.StringVar(value=s.get("filetype") if s.get("filetype") in FILETYPES else "JPEG")
        self.v_quality = tk.IntVar(value=s.get("quality", 95))
        self.v_grid = tk.BooleanVar(value=s.get("grid", True))
        self.v_cm_on = tk.BooleanVar(value=s.get("cm_on", False))
        self.v_icc = tk.StringVar(value=s.get("icc", ""))
        self.v_intent = tk.StringVar(value=s.get("intent") if s.get("intent") in INTENTS else next(iter(INTENTS)))
        self.v_bpc = tk.BooleanVar(value=s.get("bpc", True))
        self.v_embed = tk.BooleanVar(value=s.get("embed", True))
        self.v_proof = tk.BooleanVar(value=False)
        self.v_gamut = tk.BooleanVar(value=False)
        self.v_snap = tk.BooleanVar(value=s.get("snap", True))   # прилипание рамки к краям и центру
        self._snap_guides = []
        self.checked = set()          # фото, отмеченные «+» в левой колонке: сохраняются и печатаются только они
        self.v_adj_scope = tk.StringVar(value="one")      # коррекция: только это фото / все фото
        self.adj_panel = None
        self._adj_clipboard = None
        self._adj_after = None
        self._show_orig = False
        self._adj_img = None        # скорректированное (до имитации печати) — для гистограммы
        self.gamut_pct = None
        self.v_cm_text = tk.StringVar(value="")
        self.v_copies = tk.StringVar(value="1")
        self._copies_lock = False
        self.print_dialog = None
        self.v_icc_status = tk.StringVar(value="")

        self._build_ui()
        theme_walk(self.root)
        i18n_apply(self.root)
        self.root.title(tr("PhotoCrop — кадрирование для фотопечати"))
        for v in (self.v_format, self.v_mode, self.v_grid):
            v.trace_add("write", lambda *a: self._changed())
        self.v_orient.trace_add("write", lambda *a: self._orient_changed())
        for v in (self.v_cm_on, self.v_icc, self.v_intent, self.v_bpc, self.v_proof, self.v_gamut):
            v.trace_add("write", lambda *a: self._cm_changed())
        self._icc_info()
        root.protocol("WM_DELETE_WINDOW", self._on_close)
        self._auto_sig = None
        self._undo, self._redo, self._undo_key, self._undo_t = [], [], None, 0.0
        root.after(AUTOSAVE_SECONDS * 1000, self._autosave_tick)

    # ---------- построение окна
    def _build_ui(self):
        apply_theme(self.root, self.settings.get("theme", DEFAULT_THEME))

        top = ttk.Frame(self.root, padding=(8, 6))
        top.pack(side="top", fill="x")
        ttk.Button(top, text="📂 Открыть…", style="Accent.TButton", command=self.open_any).pack(side="left", padx=(0, 14))
        ttk.Label(top, text="Формат:").pack(side="left")
        ttk.Combobox(top, textvariable=self.v_format, values=list(FORMATS), state="readonly", width=16).pack(side="left", padx=(4, 12))
        ttk.Label(top, text="Ориентация:").pack(side="left")
        for label, key in (("Авто", "Авто (по фото)"), ("Книжная", "Книжная"), ("Альбомная", "Альбомная")):
            ttk.Radiobutton(top, text=label, value=key, variable=self.v_orient, style="Toolbutton").pack(side="left", padx=1)
        ttk.Label(top, text="Режим:").pack(side="left", padx=(12, 0))
        for label, key in (("Кадрировать", "Кадрировать (заполнить лист)"), ("Вписать", "Вписать целиком (белые поля)")):
            ttk.Radiobutton(top, text=label, value=key, variable=self.v_mode, style="Toolbutton").pack(side="left", padx=1)
        ttk.Checkbutton(top, text="Сетка 1/3", variable=self.v_grid).pack(side="left", padx=(12, 0))
        icon_btn(top, "⚙", "Настройки", self.open_settings).pack(side="right")

        main = ttk.Frame(self.root)
        main.pack(side="top", fill="both", expand=True)

        # колонка квадратных превью
        left = ttk.Frame(main, padding=(8, 0, 0, 0))
        left.pack(side="left", fill="y")
        self.lbl_count = ttk.Label(left, text="Файлов: 0")
        self.lbl_count.pack(anchor="w")
        lb = ttk.Frame(left)
        lb.pack(fill="x", pady=(2, 4))
        icon_btn(lb, "☑", "Отметить все фото", lambda: self.check_all(True)).pack(side="left")
        icon_btn(lb, "☐", "Снять все отметки", lambda: self.check_all(False)).pack(side="left", padx=4)
        icon_btn(lb, "🗑", "Убрать неотмеченные из списка", self.remove_unchecked).pack(side="left")
        self.listbox = ThumbList(left, self)
        self.listbox.pack(fill="y", expand=True)
        self.listbox.bind("<<ListboxSelect>>", self._on_list)
        ttk.Label(left, text="＋/✓ — отметить фото   ✎ — правка   ◐ — цвет", foreground="#666").pack(anchor="w", pady=(2, 0))

        # панель сохранения
        right = ttk.Frame(main, padding=8)
        right.pack(side="right", fill="y")
        self._build_save_panel(right)

        # центр: холст + навигация
        center = ttk.Frame(main, padding=(8, 0))
        center.pack(side="left", fill="both", expand=True)
        self.canvas = tk.Canvas(center, bg=PAL["canvas"], highlightthickness=0, cursor="arrow")
        self.canvas._th_key = "canvas"
        self.canvas.pack(fill="both", expand=True)
        c = self.canvas
        c.bind("<Configure>", lambda e: self.redraw())
        c.bind("<ButtonPress-1>", self._press)
        c.bind("<B1-Motion>", self._motion_drag)
        c.bind("<ButtonRelease-1>", self._release)
        c.bind("<Motion>", self._hover)
        c.bind("<Double-Button-1>", lambda e: self.reset_frame())
        c.bind("<MouseWheel>", self._wheel)
        c.bind("<Button-4>", lambda e: self._zoom(WHEEL_STEP))
        c.bind("<Button-5>", lambda e: self._zoom(1 / WHEEL_STEP))

        # навигация и число копий — по центру под фото
        nav = ttk.Frame(center, padding=(0, 8, 0, 2))
        nav.pack(fill="x")
        mid = ttk.Frame(nav)
        mid.pack()                      # без side — центрируется
        icon_btn(mid, "◀", "Предыдущее фото (←)", lambda: self.go(-1), width=4).pack(side="left")
        cp = ttk.LabelFrame(mid, text=" Копий этого фото ", padding=(8, 2))
        cp.pack(side="left", padx=16)
        ttk.Button(cp, text="−", width=3, command=lambda: self._copies_step(-1)).pack(side="left")
        ttk.Spinbox(cp, from_=1, to=99, width=4, justify="center", textvariable=self.v_copies,
                    command=self._copies_changed).pack(side="left", padx=4)
        ttk.Button(cp, text="+", width=3, command=lambda: self._copies_step(1)).pack(side="left")
        icon_btn(mid, "▶", "Следующее фото (→)", lambda: self.go(1), width=4).pack(side="left")
        self.v_copies.trace_add("write", lambda *a: self._copies_changed())

        nav1 = ttk.Frame(center, padding=(0, 2, 0, 2))
        nav1.pack(fill="x")
        icon_btn(nav1, "⟲", "Повернуть фото влево на 90°", lambda: self.rotate_photo(270)).pack(side="left")
        icon_btn(nav1, "⟳", "Повернуть фото вправо на 90°", lambda: self.rotate_photo(90)).pack(side="left", padx=(4, 12))
        icon_btn(nav1, "⇄", "Рамка: книжная ⇄ альбомная (R)", self.flip_frame).pack(side="left")
        ttk.Button(nav1, text="Сбросить рамку", command=self.reset_frame).pack(side="left", padx=4)
        ttk.Button(nav1, text="Сбросить все", command=self.reset_all).pack(side="left")
        icon_btn(nav1, "🎚", "Коррекция цвета (C)", self.open_adjust).pack(side="left", padx=(12, 0))
        icon_btn(nav1, "↶", "Отменить (Ctrl+Z)", self.undo).pack(side="left", padx=(12, 2))
        icon_btn(nav1, "↷", "Повторить (Ctrl+Y)", self.redo).pack(side="left")

        nav2 = ttk.Frame(center, padding=(0, 0, 0, 4))
        nav2.pack(fill="x")
        ttk.Label(nav2, text="Наклон рамки:").pack(side="left")
        ttk.Button(nav2, text="↺ 1°", width=6, command=lambda: self.tilt(-1)).pack(side="left", padx=(6, 2))
        ttk.Button(nav2, text="↻ 1°", width=6, command=lambda: self.tilt(1)).pack(side="left", padx=2)
        ttk.Button(nav2, text="↺ 0,1°", width=7, command=lambda: self.tilt(-0.1)).pack(side="left", padx=2)
        ttk.Button(nav2, text="↻ 0,1°", width=7, command=lambda: self.tilt(0.1)).pack(side="left", padx=2)
        ttk.Button(nav2, text="Выровнять (0°)", command=lambda: self.tilt(None)).pack(side="left", padx=(8, 0))

        self.lbl_info = tk.Label(center, text="Откройте папку с фотографиями", anchor="w", font=("Segoe UI", 10), bg=PAL["bg"], fg=PAL["muted"])
        self.lbl_info._own_fg = True
        self.lbl_info.pack(fill="x", pady=(0, 6))

        r = self.root
        for k in ("<Left>", "<Prior>"):
            r.bind(k, lambda e: self._key(lambda: self.go(-1)))
        for k in ("<Right>", "<Next>"):
            r.bind(k, lambda e: self._key(lambda: self.go(1)))
        for k in ("r", "R", "к", "К"):
            r.bind(k, lambda e: self._key(self.flip_frame))
        for k in ("<plus>", "<equal>", "<KP_Add>"):
            r.bind(k, lambda e: self._key(lambda: self._zoom(1.02)))
        for k in ("<minus>", "<KP_Subtract>"):
            r.bind(k, lambda e: self._key(lambda: self._zoom(1 / 1.02)))
        for k in ("<Control-o>", "<Control-O>", "<Control-Cyrillic_shcha>", "<Control-Cyrillic_SHCHA>"):
            r.bind(k, lambda e: self.open_any())
        for k in ("<Control-s>", "<Control-Cyrillic_yeru>"):
            r.bind(k, lambda e: self.save(False))          # Ctrl+S — сохранить текущее фото
        for k in ("<Control-S>", "<Control-Cyrillic_YERU>"):
            r.bind(k, lambda e: self.save(True))           # Ctrl+Shift+S — сохранить все
        for k in ("<Control-p>", "<Control-P>", "<Control-Cyrillic_ze>", "<Control-Cyrillic_ZE>"):
            r.bind(k, lambda e: self.open_print())
        for k in ("<Control-z>", "<Control-Cyrillic_ya>"):
            r.bind(k, lambda e: self._key(self.undo))
        for k in ("<Control-y>", "<Control-Y>", "<Control-Cyrillic_en>", "<Control-Cyrillic_EN>", "<Control-Z>", "<Control-Cyrillic_YA>"):
            r.bind(k, lambda e: self._key(self.redo))
        for k in ("c", "C", "<Cyrillic_es>", "<Cyrillic_ES>"):
            r.bind(k, lambda e: self._key(self.open_adjust))
        r.bind("<bracketleft>", lambda e: self._key(lambda: self.tilt(-1)))
        r.bind("<bracketright>", lambda e: self._key(lambda: self.tilt(1)))

    def _build_save_panel(self, p):
        box = ttk.LabelFrame(p, text=" Сохранение ", padding=10)
        box.pack(fill="x")
        ttk.Label(box, text="Куда сохранять готовые файлы:").pack(anchor="w")
        r1 = ttk.Frame(box)
        r1.pack(fill="x", pady=(2, 0))
        ttk.Radiobutton(r1, text="Рядом с фото, в папку:", value="orig", variable=self.v_outmode).pack(side="left")
        self.ent_outname = ttk.Entry(r1, textvariable=self.v_outname, width=12)
        self.ent_outname.pack(side="left", padx=(4, 0), fill="x", expand=True)
        r2 = ttk.Frame(box)
        r2.pack(fill="x", pady=(2, 6))
        ttk.Radiobutton(r2, text="В другую папку:", value="custom", variable=self.v_outmode).pack(side="left")
        self.ent_outdir = ttk.Entry(r2, textvariable=self.v_outdir, width=14)
        self.ent_outdir.pack(side="left", padx=(4, 0), fill="x", expand=True)
        self.btn_outdir = ttk.Button(r2, text="…", width=3, command=self.choose_outdir)
        self.btn_outdir.pack(side="left", padx=(4, 0))
        self.v_outmode.trace_add("write", lambda *a: self._outmode_changed())
        self._outmode_changed()
        ttk.Checkbutton(box, text="Подпапка с названием формата", variable=self.v_subfolder).pack(anchor="w", pady=(0, 2))
        ttk.Checkbutton(box, text="Число копий в имени файла (_x3)", variable=self.v_copies_name).pack(anchor="w", pady=(0, 8))

        ttk.Label(box, text="Разрешение печати, DPI:").pack(anchor="w")
        ttk.Combobox(box, textvariable=self.v_dpi, values=["200", "240", "254", "300", "360", "400", "600"], width=8).pack(anchor="w", pady=(2, 4))
        ttk.Checkbutton(box, text="Пересчитать до точного\nразмера печати (рекомендуется)", variable=self.v_resize).pack(anchor="w", pady=(0, 8))

        ttk.Label(box, text="Тип файла:").pack(anchor="w")
        ttk.Combobox(box, textvariable=self.v_filetype, values=list(FILETYPES), state="readonly", width=8).pack(anchor="w", pady=(2, 8))
        self.lbl_q = ttk.Label(box, text="")
        self.lbl_q.pack(anchor="w")
        ttk.Scale(box, from_=60, to=100, variable=self.v_quality, orient="horizontal",
                  command=lambda v: self._upd_quality()).pack(fill="x")
        self._upd_quality()

        cbox = ttk.LabelFrame(p, text=" Цвет ", padding=8)
        cbox.pack(fill="x", pady=(8, 0))
        ttk.Button(cbox, text="🎚 Коррекция фото… (C)", command=self.open_adjust).pack(fill="x", pady=(0, 4))
        ttk.Button(cbox, text="🎨 Профиль принтера…", command=self.open_cm_dialog).pack(fill="x")
        ttk.Checkbutton(cbox, text="Имитация печати на экране", variable=self.v_proof).pack(anchor="w", pady=(6, 0))
        ttk.Checkbutton(cbox, text="Показать цвета вне охвата (розовым)", variable=self.v_gamut).pack(anchor="w")
        ttk.Label(cbox, textvariable=self.v_cm_text, wraplength=240, foreground="#555").pack(anchor="w", pady=(4, 0))
        ttk.Button(p, text="🖨 Печать…", style="Accent.TButton", command=self.open_print).pack(fill="x", pady=(8, 0))
        prow = ttk.Frame(p)
        prow.pack(fill="x", pady=(6, 0))
        ttk.Button(prow, text="📂 Открыть проект", command=self.load_project).pack(side="left", fill="x", expand=True)
        ttk.Button(prow, text="💾 Сохранить проект", command=self.save_project).pack(side="left", fill="x", expand=True, padx=(6, 0))

        ttk.Separator(p).pack(fill="x", pady=10)
        ttk.Button(p, text="💾 Сохранить текущее", style="Big.TButton", command=lambda: self.save(False)).pack(fill="x")
        self.btn_all = ttk.Button(p, text="💾 Сохранить все", style="Accent.TButton", command=lambda: self.save(True))
        self.btn_all.pack(fill="x", pady=(6, 0))
        self.progress = ttk.Progressbar(p, mode="determinate")
        self.progress.pack(fill="x", pady=(10, 2))
        self.lbl_prog = ttk.Label(p, text="", wraplength=250)
        self.lbl_prog.pack(anchor="w")

        legend = ttk.LabelFrame(p, text=" Качество печати ", padding=8)
        legend.pack(fill="x", side="bottom")
        for col, t in (("#1a8f2e", "≥ 250 dpi — отлично"), ("#d08000", "150–250 dpi — нормально"), ("#c62828", "< 150 dpi — будет нерезко")):
            ll = tk.Label(legend, text="■ " + t, fg=col, bg=PAL["bg"], anchor="w")
            ll._own_fg = True
            ll.pack(fill="x")

    def _outmode_changed(self):
        orig = self.v_outmode.get() == "orig"
        self.ent_outname.config(state="normal" if orig else "disabled")
        self.ent_outdir.config(state="disabled" if orig else "normal")
        self.btn_outdir.config(state="disabled" if orig else "normal")

    def _upd_quality(self):
        self.lbl_q.config(text=f"Качество JPEG: {int(float(self.v_quality.get()))}")

    def _key(self, fn):
        w = self.root.focus_get()
        if isinstance(w, (tk.Entry, ttk.Entry, ttk.Combobox, tk.Spinbox)):
            return
        fn()

    # ---------- файлы
    def _start_dir(self):
        """Начальная папка диалогов: по умолчанию рабочий стол (в настройках можно выбрать «последняя использованная»)."""
        if self.settings.get("start_dir_mode") == "last" and self.settings.get("last_dir") and Path(self.settings["last_dir"]).is_dir():
            return self.settings["last_dir"]
        return desktop_dir()

    def open_any(self):
        """Единая кнопка «Открыть»: окно, где видны и папки, и фото. Выделил фото — откроются они,
        не выделил ничего — откроется вся папка."""
        try:
            res = OpenDialog(self, self._start_dir()).show()
        except Exception:                      # запасной путь: обычное окно Windows для выбора фото
            self.open_files()
            return
        if not res:
            return
        kind, val, add = res
        if kind == "files":
            self._load_files(val, add)
        else:
            self._load_folder(Path(val), add)

    def open_folder(self):
        d = filedialog.askdirectory(title="Папка с фотографиями", initialdir=self._start_dir())
        if d:
            self._load_folder(Path(d))

    def _load_folder(self, src, add=False):
        files, own, other = scan_folder(src, self.v_recursive.get(), self.v_outname.get().strip())
        if not files:
            messagebox.showinfo("PhotoCrop", "В выбранной папке нет фотографий (JPG, PNG, TIFF, BMP, WEBP)."
                                + ("\n\n" + skipped_note(own, other) if (own or other) else ""))
            return
        self.settings["last_dir"] = str(src)
        if add and self.files:
            self._load_files(files, True)
            return
        if not self.v_outdir.get().strip() or self.v_outmode.get() == "orig":
            self.v_outdir.set(str(src / OUT_SUBDIR))        # подсказка для режима «другая папка»
        states = {f: CropState() for f in files}
        idx = self._restore_autosave(src, files, states)
        self._set_files(src, files, states, idx)
        if own or other:
            messagebox.showinfo("PhotoCrop", f"Загружено фото: {len(files)}.\n\n" + skipped_note(own, other))

    def open_files_from(self, paths, add=False):
        """Загрузка заданных файлов (без диалога)."""
        self._load_files(paths, add, quiet=True)

    def open_files(self, add=False):
        """Обычное окно Windows для выбора отдельных фото (можно выделить несколько: Ctrl/Shift)."""
        types_ = [("Фотографии", " ".join("*" + e for e in sorted(EXTS))), ("Все файлы", "*.*")]
        init = str(self.src_dir) if (add and self.src_dir) else self._start_dir()
        sel = filedialog.askopenfilenames(title="Выберите фото (можно несколько)", initialdir=init, filetypes=types_)
        if sel:
            self._load_files(sel, add)

    def _load_files(self, paths, add=False, quiet=False):
        """Открывает перечисленные фото. add=True — дописывает к списку. Одно фото сразу попадает в рабочее поле."""
        new = []
        for p in paths:
            f = Path(p)
            if f.suffix.lower() in EXTS and f.is_file() and f not in new:
                new.append(f)
        if not new:
            if not quiet:
                messagebox.showinfo("PhotoCrop", "Среди выбранных нет поддерживаемых фотографий (JPG, PNG, TIFF, BMP, WEBP).")
            return
        self.settings["last_dir"] = str(new[0].parent)
        if add and self.files:
            have = set(self.files)
            fresh = [f for f in new if f not in have]
            if not fresh:
                return
            idx = len(self.files)
            for f in fresh:
                self.states[f] = CropState()
                self.checked.add(f)
            self.files = self.files + fresh
            self._rebuild_list()
            self._upd_counts()
            self.show(idx)
            return
        try:
            src = Path(os.path.commonpath([str(f.parent) for f in new]))
        except ValueError:
            src = new[0].parent
        files = sorted(new, key=natural_key)
        if self.v_outmode.get() == "orig" or not self.v_outdir.get().strip():
            self.v_outdir.set(str(src / OUT_SUBDIR))
        self._set_files(src, files, {f: CropState() for f in files}, 0)

    # ---------- отметки в левой колонке
    def _upd_counts(self):
        n, m = len([f for f in self.files if f in self.checked]), len(self.files)
        self.lbl_count.config(text=trf("Файлов: {m}   отмечено: {n}", m=m, n=n))
        self.btn_all.config(text=trf("💾 Сохранить отмеченные ({n})", n=n))

    def toggle_check(self, i, shift=False):
        if not (0 <= i < len(self.files)):
            return
        f = self.files[i]
        if shift and getattr(self, "_last_check", None) is not None:       # Shift: отметить диапазон
            a, b = sorted((self._last_check, i))
            on = f not in self.checked
            for g in self.files[a:b + 1]:
                (self.checked.add if on else self.checked.discard)(g)
        elif f in self.checked:
            self.checked.discard(f)
            on = False
        else:
            self.checked.add(f)
            on = True
        self._last_check = i
        self._upd_counts()
        self.listbox.draw()
        self._sync_work(f if (on and not shift) else None)

    def check_all(self, on):
        self.checked = set(self.files) if on else set()
        self._upd_counts()
        self.listbox.draw()
        self._sync_work()

    def _sync_work(self, newly=None):
        """Рабочее поле показывает только отмеченные фото: снял отметку — фото исчезло из работы,
        поставил — появилось. Если отмечено новое фото — оно сразу открывается."""
        if not self.files:
            return
        chk = [i for i, f in enumerate(self.files) if f in self.checked]
        if not chk:
            self.idx = -1
            self.raw = self.preview = None
            self.size = (0, 0)
            self.tk_key = None
            self.listbox.selection_clear(0, "end")
            self.redraw()
            self.lbl_info.config(text=trf("Отмечено фото: 0"), fg="#666")
            if self.adj_panel is not None:
                self.adj_panel.sync()
            return
        if newly is not None and newly in self.checked:
            self.show(self.files.index(newly))
            return
        if self.idx >= 0 and self.files[self.idx] in self.checked and self.preview is not None:
            self.redraw()                       # текущее фото осталось в работе; обновить номер «k/n»
            return
        nxt = next((i for i in chk if i > self.idx), chk[-1])
        self.show(nxt)

    def _checked_files(self):
        return [f for f in self.files if f in self.checked]

    def remove_unchecked(self):
        if not self.files:
            return
        keep = self._checked_files()
        if not keep:
            messagebox.showinfo("PhotoCrop", "Ни одно фото не отмечено. Отметьте нужные («+» в углу превью).")
            return
        if len(keep) == len(self.files):
            return
        if not messagebox.askyesno("PhotoCrop", f"Убрать из списка {len(self.files) - len(keep)} неотмеченных фото?\n"
                                   "Файлы на диске не удаляются."):
            return
        cur = self.files[self.idx] if self.idx >= 0 else None
        self._push_undo(keep)
        self.files = keep
        self.states = {f: self.states[f] for f in keep}
        self.idx = keep.index(cur) if cur in keep else 0
        self._rebuild_list()
        self._upd_counts()
        self.show(self.idx)

    # ---------- автосохранение рамок (страховка от сбоя)
    def _autosave_sig(self):
        return tuple((str(f), tuple(getattr(st, k) for k in CropState.__slots__ if k != "adj"), tuple(sorted(st.adj.items())))
                     for f, st in self.states.items())

    def _autosave_now(self):
        if not self.files or self.src_dir is None:
            return
        sig = self._autosave_sig()
        if sig == self._auto_sig:
            return
        if not any(st.edited for st in self.states.values()):
            self._auto_sig = sig
            try:                                   # всё сброшено: старую копию не предлагаем «восстановить»
                autosave_path(self.src_dir).unlink()
            except OSError:
                pass
            return
        write_json_atomic(autosave_path(self.src_dir), self._project_session().to_project(full=False))
        self._auto_sig = sig

    def _autosave_tick(self):
        try:
            self._autosave_now()
        except Exception:
            pass
        try:
            self.root.after(AUTOSAVE_SECONDS * 1000, self._autosave_tick)
        except Exception:
            pass

    def _restore_autosave(self, src, files, states):
        """Предлагает вернуть рамки из автосохранения этой папки. Возвращает номер текущего снимка."""
        self._auto_sig = None
        p = autosave_path(src)
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
            saved = d.get("states", {})
            n = sum(1 for f in files if (saved.get(str(f)) or {}).get("edited"))
        except Exception:
            return 0
        if not n or not messagebox.askyesno("PhotoCrop", f"Найдены сохранённые рамки для этой папки (изменённых снимков: {n}).\n\nВосстановить?"):
            return 0
        for f in files:
            for k, v in (saved.get(str(f)) or {}).items():
                if k in CropState.__slots__:
                    setattr(states[f], k, dict(v) if k == "adj" else v)
            _sanitize_state(states[f])
        return min(max(int(d.get("idx", 0)), 0), len(files) - 1)

    def _set_files(self, src, files, states, idx):
        self.src_dir = src
        self.files = files
        self.states = states
        self._undo, self._redo, self._undo_key = [], [], None
        self.checked = set(files)                     # после загрузки отмечены все; «Сбросить» снимает отметки
        self._last_check = None
        self.listbox.delete(0, "end")
        for f in files:
            self.listbox.insert("end", self._list_name(f))
        self._upd_counts()
        self.idx = -1
        self.show(max(0, min(idx, len(files) - 1)))

    def _project_session(self):
        s = AgentSession(persist=False)
        s.files, s.states, s.idx = list(self.files), dict(self.states), self.idx
        s.folder, s.recursive = self.src_dir, self.v_recursive.get()
        s.fmt_name, s.orient_name, s.mode_name = self.v_format.get(), self.v_orient.get(), self.v_mode.get()
        return s

    def save_project(self):
        if not self.files:
            messagebox.showinfo("PhotoCrop", "Сначала откройте папку с фотографиями.")
            return
        p = filedialog.asksaveasfilename(title="Сохранить проект (рамки и настройки)", defaultextension=".json",
                                         filetypes=[("Проект PhotoCrop", "*.json")], initialfile="photocrop_project.json")
        if p:
            try:
                write_json_atomic(p, self._project_session().to_project(full=False))
            except OSError as ex:
                messagebox.showerror("PhotoCrop", f"Не удалось сохранить проект:\n{ex}")

    def load_project(self):
        AGENT_DIR.mkdir(parents=True, exist_ok=True)
        p = filedialog.askopenfilename(title="Открыть проект (в том числе состояние агента)", initialdir=str(AGENT_DIR),
                                       filetypes=[("Проект PhotoCrop", "*.json"), ("Все файлы", "*.*")])
        if p:
            self.load_project_file(p)

    def load_project_file(self, p):
        try:
            s = AgentSession(persist=False)
            s.from_project(json.loads(Path(p).read_text(encoding="utf-8")))
        except (OSError, ValueError) as ex:
            messagebox.showerror("PhotoCrop", f"Не удалось прочитать проект:\n{ex}")
            return
        if not s.files:
            messagebox.showinfo("PhotoCrop", "В проекте нет доступных файлов фотографий.")
            return
        if s.fmt_name in FORMATS:
            self.v_format.set(s.fmt_name)
        if s.orient_name in ORIENTS:
            self.v_orient.set(s.orient_name)
        if s.mode_name in MODES:
            self.v_mode.set(s.mode_name)
        self._set_files(s.folder, s.files, s.states, s.idx)

    def _list_name(self, f):
        try:
            name = str(f.relative_to(self.src_dir)) if self.src_dir else f.name
        except ValueError:
            name = f.name
        st = self.states[f]
        return ("✎" if st.edited else " ") + ("◐" if st.adj else " ") + " " + name + (f"   ×{st.copies}" if st.copies > 1 else "")

    def _mark(self, f):
        st = self.states[f]
        if st.edited:
            return
        st.edited = True
        i = self.files.index(f)
        self.listbox.delete(i)
        self.listbox.insert(i, self._list_name(f))
        self.listbox.selection_set(i)

    def choose_outdir(self):
        d = filedialog.askdirectory(title="Куда сохранять", initialdir=self.v_outdir.get() or None)
        if d:
            self.v_outdir.set(d)
            self.v_outmode.set("custom")

    def _on_list(self, e):
        sel = self.listbox.curselection()
        if sel and sel[0] != self.idx:
            f = self.files[sel[0]]
            if f not in self.checked:          # выбрал неотмеченное фото щелчком — оно включается в работу
                self.checked.add(f)
                self._upd_counts()
                self.listbox.draw()
            self.show(sel[0])

    def go(self, d):
        chk = [i for i, f in enumerate(self.files) if f in self.checked]
        if not chk:
            return
        if self.idx in chk:
            p = max(0, min(len(chk) - 1, chk.index(self.idx) + d))
        else:
            p = 0 if d >= 0 else len(chk) - 1
        self.show(chk[p])

    def show(self, i):
        if not self.files:
            return
        self.idx = i
        f = self.files[i]
        self.listbox.selection_clear(0, "end")
        self.listbox.selection_set(i)
        self.listbox.see(i)
        self._copies_lock = True
        self.v_copies.set(str(self.states[f].copies))
        self._copies_lock = False
        try:
            st = self.states[f]
            self.size = true_size(f, st.rotation)
            self.raw, self.icc = load_preview(f, st.rotation)
            self._refresh_proof()
        except Exception as ex:
            self.raw = self.preview = None
            self.size = (0, 0)
            self.lbl_info.config(text=f"{f.name}: не удалось открыть ({ex})", fg="#c62828")
        self.tk_key = None
        self.redraw()
        if self.adj_panel is not None:
            self.adj_panel.sync()

    # ---------- отмена / повтор (Ctrl+Z / Ctrl+Y)
    @staticmethod
    def _st_tuple(st):
        return tuple(getattr(st, k) for k in CropState.__slots__ if k != "adj") + (tuple(sorted(st.adj.items())),)

    def _push_undo(self, files, key=None, merge=0.0):
        """Запоминает состояние рамок перед правкой. Одинаковые подряд правки (колесо, наклон) с одним key
        в пределах merge секунд сливаются в один шаг."""
        now = time.time()
        if key is not None and key == self._undo_key and now - self._undo_t < merge:
            self._undo_t = now
            return
        self._undo.append({f: self.states[f].copy() for f in files})
        del self._undo[:-UNDO_LIMIT]
        self._redo.clear()
        self._undo_key, self._undo_t = key, now

    def _undo_trim(self, f):
        """Клик без изменений не должен занимать шаг отмены."""
        if self._undo and list(self._undo[-1]) == [f] and self._st_tuple(self._undo[-1][f]) == self._st_tuple(self.states[f]):
            self._undo.pop()

    def _refresh_row(self, f):
        i = self.files.index(f)
        self.listbox.delete(i)
        self.listbox.insert(i, self._list_name(f))
        if i == self.idx:
            self.listbox.selection_set(i)

    def _apply_snapshot(self, snap):
        rot_changed = False
        for f, st in snap.items():
            if f not in self.states:
                continue
            if self.idx >= 0 and f == self.files[self.idx] and self.states[f].rotation != st.rotation:
                rot_changed = True
            self.states[f] = st.copy()
            self._refresh_row(f)
        first = next((f for f in snap if f in self.states), None)
        if first is None:
            return
        i = self.files.index(first)
        self._undo_key = None
        if i != self.idx or rot_changed:
            self.show(i)
        else:
            self._copies_lock = True
            self.v_copies.set(str(self.states[first].copies))
            self._copies_lock = False
            self._refresh_proof()
            self.tk_key = None
            self.redraw()
            if self.adj_panel is not None:
                self.adj_panel.sync()

    def undo(self):
        if not self._undo:
            return
        snap = self._undo.pop()
        self._redo.append({f: self.states[f].copy() for f in snap if f in self.states})
        self._apply_snapshot(snap)

    def redo(self):
        if not self._redo:
            return
        snap = self._redo.pop()
        self._undo.append({f: self.states[f].copy() for f in snap if f in self.states})
        self._apply_snapshot(snap)

    # ---------- геометрия текущего снимка
    def _cur(self):
        if self.preview is None or self.idx < 0 or self.files[self.idx] not in self.checked:
            return None
        f = self.files[self.idx]
        st = self.states[f]
        W, H = self.size
        orient = st.orient if st.orient else ORIENTS[self.v_orient.get()]
        paper = paper_size(FORMATS[self.v_format.get()], orient, W, H)
        return f, st, W, H, paper

    def _changed(self):
        self.redraw()

    def _bleed_mm(self):
        """Подрезка принтером по сторонам (лево, верх, право, низ), мм — по настройкам окна печати (живым, если оно открыто)."""
        vals = dict(PRINT_DEFAULTS)
        vals.update({k: v for k, v in self.settings.get("print", {}).items() if k in PRINT_DEFAULTS})
        pd = self.print_dialog
        try:
            if pd is not None and pd.win.winfo_exists():
                vals.update({k: v.get() for k, v in pd.v.items()})
        except Exception:
            pass
        try:
            return bleed_sides(parse_print_opts(vals))
        except Exception:
            return (0.0, 0.0, 0.0, 0.0)

    def _draw_bleed_scale(self, P, paper_w_mm):
        """Серая «шкала подрезки» вокруг рамки кадра: полоса снаружи — запас, который печатается за краем листа
        (положительное значение), полоса внутри рамки — отступ (отрицательное). Видна всегда, пока значения заданы."""
        sides = self._bleed_mm()
        if not any(abs(v) > 1e-9 for v in sides):
            return
        c = self.canvas
        ux, uy = P[1][0] - P[0][0], P[1][1] - P[0][1]
        L = math.hypot(ux, uy) or 1.0
        ux, uy = ux / L, uy / L                    # вдоль верхнего края
        vx, vy = P[3][0] - P[0][0], P[3][1] - P[0][1]
        Hh = math.hypot(vx, vy) or 1.0
        vx, vy = vx / Hh, vy / Hh                  # вдоль левого края
        mm = L / max(1e-6, paper_w_mm)             # экранных пикселей в миллиметре
        # (угол A, угол B, нормаль наружу)
        edges = ((P[3], P[0], (-ux, -uy)), (P[0], P[1], (-vx, -vy)), (P[1], P[2], (ux, uy)), (P[2], P[3], (vx, vy)))
        names = ("Л", "В", "П", "Н")
        for (a, b, n), v, nm in zip(edges, sides, names):
            if abs(v) < 1e-9:
                continue
            d = max(2.0, abs(v) * mm)
            sgn = 1 if v > 0 else -1               # + наружу, − внутрь
            a2 = (a[0] + n[0] * d * sgn, a[1] + n[1] * d * sgn)
            b2 = (b[0] + n[0] * d * sgn, b[1] + n[1] * d * sgn)
            c.create_polygon(*a, *b, *b2, *a2, fill="#9a9a9a", outline="#c8c8c8", stipple="" if v > 0 else "gray50")
            mid = ((a[0] + b[0] + a2[0] + b2[0]) / 4, (a[1] + b[1] + a2[1] + b2[1]) / 4)
            c.create_text(mid[0], mid[1], text=f"{nm} {v:+g}", fill="white", font=("Segoe UI", 8, "bold"))

    def redraw(self):
        c = self.canvas
        c.delete("all")
        cw, ch = max(c.winfo_width(), 50), max(c.winfo_height(), 50)
        cur = self._cur()
        if not cur:
            c.create_text(cw / 2, ch / 2, fill="#bbb", font=("Segoe UI", 14), justify="center",
                          text=tr("Ни одно фото не отмечено.\nОтметьте «+» на превью слева — фото появится здесь.")
                          if self.files else tr("Нажмите «Открыть…» и выберите фото или папку"))
            self.geom = None
            return
        f, st, W, H, paper = cur
        mode = MODES[self.v_mode.get()]

        if mode == "fit":
            pad = 24
            k = min((cw - 2 * pad) / paper[0], (ch - 2 * pad) / paper[1])
            PW, PH = paper[0] * k, paper[1] * k
            px, py = (cw - PW) / 2, (ch - PH) / 2
            c.create_rectangle(px + 4, py + 4, px + PW + 4, py + PH + 4, fill="#222", outline="")
            c.create_rectangle(px, py, px + PW, py + PH, fill="white", outline="#999")
            kk = min(PW / W, PH / H)
            dw, dh = max(1, int(W * kk)), max(1, int(H * kk))
            self._set_tk(dw, dh)
            c.create_image(px + (PW - dw) / 2, py + (PH - dh) / 2, anchor="nw", image=self.tkimg)
            self._draw_bleed_scale([(px, py), (px + PW, py), (px + PW, py + PH), (px, py + PH)], paper[0])
            self.geom = None
        else:
            pad = max(50, int(0.1 * min(cw, ch)))   # запас вокруг фото, чтобы рамку можно было вынести за край
            k = min((cw - 2 * pad) / W, (ch - 2 * pad) / H)
            dw, dh = max(1, int(W * k)), max(1, int(H * k))
            ox, oy = (cw - dw) // 2, (ch - dh) // 2
            g = frame_geom(W, H, paper, st)
            P = [(ox + x * k, oy + y * k) for x, y in frame_corners(*g)]
            flat = [v for p in P for v in p]

            c.create_polygon(flat, fill="white", outline="")            # «бумага» под фото: видна за краем снимка
            self._set_tk(dw, dh)
            c.create_image(ox, oy, anchor="nw", image=self.tkimg)
            # затемнение всего, что вне рамки (внешний прямоугольник с «вырезом» по рамке)
            c.create_polygon(0, 0, cw, 0, cw, ch, 0, ch, 0, 0, *flat, P[0][0], P[0][1], 0, 0,
                             fill="black", stipple="gray50", outline="")
            if self.v_grid.get():
                for t in (1 / 3, 2 / 3):
                    a1 = self._lerp(P[0], P[1], t)
                    b1 = self._lerp(P[3], P[2], t)
                    a2 = self._lerp(P[0], P[3], t)
                    b2 = self._lerp(P[1], P[2], t)
                    c.create_line(*a1, *b1, fill="white", dash=(3, 4))
                    c.create_line(*a2, *b2, fill="white", dash=(3, 4))
            self._draw_bleed_scale(P, paper[0])
            c.create_polygon(flat, outline=PAL["frame"], fill="", width=2)
            for gk, gv in self._snap_guides:                            # голубые линии прилипания
                if gk == "v":
                    c.create_line(ox + gv * k, oy, ox + gv * k, oy + dh, fill="#40d0ff", dash=(4, 3))
                else:
                    c.create_line(ox, oy + gv * k, ox + dw, oy + gv * k, fill="#40d0ff", dash=(4, 3))
            hs = self.HANDLE / 2
            for hx, hy in P:
                c.create_rectangle(hx - hs, hy - hs, hx + hs, hy + hs, fill="white", outline="black")
            for hx, hy in self._edge_pts(P).values():
                c.create_rectangle(hx - 4, hy - 4, hx + 4, hy + 4, fill=PAL["frame"], outline="black")
            # ручка поворота над верхним краем
            top = self._lerp(P[0], P[1], 0.5)
            a = math.radians(st.angle)
            rh = (top[0] + self.ROT_OFFSET * math.sin(a), top[1] - self.ROT_OFFSET * math.cos(a))
            c.create_line(*top, *rh, fill=PAL["frame"], width=2)
            c.create_oval(rh[0] - 7, rh[1] - 7, rh[0] + 7, rh[1] + 7, fill=PAL["frame"], outline="black")
            self.geom = (ox, oy, k, P, rh)
        self._update_info()

    @staticmethod
    def _lerp(p, q, t):
        return p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t

    def _set_tk(self, dw, dh):
        key = (id(self.preview), dw, dh)
        if key != self.tk_key:
            self.tkimg = ImageTk.PhotoImage(self.preview.resize((dw, dh), RESAMPLE_FAST))
            self.tk_key = key

    def _update_info(self):
        cur = self._cur()
        if not cur:
            return
        f, st, W, H, paper = cur
        mode = MODES[self.v_mode.get()]
        dpi = effective_dpi(W, H, paper, st, mode)
        if mode == "crop":
            g = frame_geom(W, H, paper, st)
            part = f"кадр {round(g[2])}×{round(g[3])} px"
            if abs(st.angle) >= 0.05:
                part += f", наклон {st.angle:.1f}°"
            if not frame_inside(W, H, g):
                part += ", есть белые поля"
        else:
            part = "без обрезки"
        orient = "книжная" if paper[0] < paper[1] else "альбомная"
        col = "#1a8f2e" if dpi >= 250 else "#d08000" if dpi >= 150 else "#c62828"
        self.lbl_info.config(
            fg=col,
            text=f"[{sum(1 for g in self.files[:self.idx + 1] if g in self.checked)}/{len(self.checked & set(self.files))}]  {f.name}   •   {W}×{H} px   •   "
                 f"{self.v_format.get()}, {orient}   •   {part}   •   печать ≈ {dpi:.0f} dpi")

    # ---------- мышь
    def _to_img(self, ex, ey):
        ox, oy, k, _, _ = self.geom
        return (ex - ox) / k, (ey - oy) / k

    def _corner_at(self, ex, ey):
        for name, (hx, hy) in zip(self.CORNERS, self.geom[3]):
            if abs(ex - hx) <= self.HANDLE and abs(ey - hy) <= self.HANDLE:
                return name
        return None

    @staticmethod
    def _edge_pts(P):
        return {"n": App._lerp(P[0], P[1], .5), "e": App._lerp(P[1], P[2], .5),
                "s": App._lerp(P[2], P[3], .5), "w": App._lerp(P[3], P[0], .5)}

    def _edge_at(self, ex, ey):
        for name, (hx, hy) in self._edge_pts(self.geom[3]).items():
            if abs(ex - hx) <= self.HANDLE and abs(ey - hy) <= self.HANDLE:
                return name
        return None

    def _rot_at(self, ex, ey):
        rx, ry = self.geom[4]
        return (ex - rx) ** 2 + (ey - ry) ** 2 <= 11 ** 2

    def _cursor(self, *names):
        for n in names:
            try:
                self.canvas.config(cursor=n)
                return
            except tk.TclError:
                continue

    def _hover(self, e):
        if not self.geom or self.drag:
            return
        cur = self._cur()
        if not cur:
            return
        corner = self._corner_at(e.x, e.y)
        if self._rot_at(e.x, e.y):
            self._cursor("exchange", "crosshair")
        elif corner:
            self._cursor("size_nw_se" if corner in ("nw", "se") else "size_ne_sw", "crosshair")
        elif self._edge_at(e.x, e.y):
            self._cursor("size_we" if self._edge_at(e.x, e.y) in ("e", "w") else "size_ns", "crosshair")
        else:
            f, st, W, H, paper = cur
            ix, iy = self._to_img(e.x, e.y)
            inside = point_in_frame(frame_geom(W, H, paper, st), ix, iy)
            self._cursor("fleur" if inside else "crosshair")

    def _press(self, e):
        self.canvas.focus_set()
        cur = self._cur()
        if not cur or not self.geom:
            return
        f, st, W, H, paper = cur
        self._push_undo([f])
        g = frame_geom(W, H, paper, st)
        ix, iy = self._to_img(e.x, e.y)
        corner = self._corner_at(e.x, e.y)
        if self._rot_at(e.x, e.y):
            self.drag = ("rotate",)
        elif corner:
            self.drag = ("corner",)     # за угол — масштаб вокруг центра, рамка остаётся по центру
        elif self._edge_at(e.x, e.y):
            edge = self._edge_at(e.x, e.y)
            cx, cy, w, h, ang = g
            ex, ey = {"n": (0, -1), "e": (1, 0), "s": (0, 1), "w": (-1, 0)}[edge]
            dx, dy = rot(-ex * w / 2 if ex else 0, -ey * h / 2 if ey else 0, ang)   # середина противоположной стороны
            self.drag = ("edge", edge, cx + dx, cy + dy)
        else:
            if not point_in_frame(g, ix, iy):
                st.cx, st.cy = ix / W, iy / H  # клик мимо рамки — перенести её сюда
                normalize(st)
            self.drag = ("move", ix - st.cx * W, iy - st.cy * H)
        self._mark(f)
        self.redraw()

    def _motion_drag(self, e):
        cur = self._cur()
        if not cur or not self.drag or not self.geom:
            return
        f, st, W, H, paper = cur
        ix, iy = self._to_img(e.x, e.y)
        kind = self.drag[0]
        self._snap_guides = []
        snap_on = self.v_snap.get() and not (e.state & 0x0004)          # Ctrl — временно без прилипания
        thr = float(self.settings.get("snap_px", 10)) / max(1e-6, self.geom[2])
        if kind == "move":
            _, dx, dy = self.drag
            st.cx, st.cy = (ix - dx) / W, (iy - dy) / H
            if snap_on:
                sx, sy, self._snap_guides = snap_move(W, H, frame_geom(W, H, paper, st), thr)
                st.cx += sx / W
                st.cy += sy / H
        elif kind == "rotate":
            step = 15 if (e.state & 0x0001) else None
            st.angle = angle_from_mouse(st.cx * W, st.cy * H, ix, iy, step)
        elif kind == "corner":
            r = paper[0] / paper[1]
            st.scale = frame_resize_center((st.cx * W, st.cy * H), (ix, iy), st.angle, r, min(W, H * r))
            if snap_on and abs(st.scale - 1.0) * min(W, H * r) <= thr:      # «ровно на весь кадр»
                st.scale = 1.0
        else:
            _, edge, ax, ay = self.drag
            r = paper[0] / paper[1]
            cx, cy, sc = frame_resize_edge((ax, ay), edge, (ix, iy), st.angle, r, min(W, H * r))
            st.cx, st.cy, st.scale = cx / W, cy / H, sc
        normalize(st)
        self.redraw()

    def _release(self, e):
        if self._snap_guides:
            self._snap_guides = []
            self.redraw()
        if self.drag and self.idx >= 0:
            self._undo_trim(self.files[self.idx])
        self.drag = None

    def _wheel(self, e):
        up = e.delta > 0
        if e.state & 0x0001:       # Shift + колесо — наклон рамки
            self.tilt(1 if up else -1)
        else:
            self._zoom(WHEEL_STEP ** max(-5.0, min(5.0, e.delta / 120.0)))

    def _zoom(self, factor):
        cur = self._cur()
        if not cur or MODES[self.v_mode.get()] != "crop":
            return
        f, st, W, H, paper = cur
        self._push_undo([f], ("zoom", f), 0.8)
        st.scale *= factor
        normalize(st)
        self._mark(f)
        self.redraw()

    # ---------- действия
    def tilt(self, delta):
        """Наклон рамки на delta градусов; None — выровнять."""
        cur = self._cur()
        if not cur or MODES[self.v_mode.get()] != "crop":
            return
        f, st, W, H, paper = cur
        self._push_undo([f], ("tilt", f) if delta is not None else None, 0.8)
        st.angle = 0.0 if delta is None else round(st.angle + delta, 3)
        normalize(st)
        self._mark(f)
        self.redraw()

    def flip_frame(self):
        cur = self._cur()
        if not cur:
            return
        f, st, W, H, paper = cur
        self._push_undo([f])
        st.orient = "landscape" if paper[0] < paper[1] else "portrait"
        _, _, W, H, paper = self._cur()
        normalize(st)
        self._mark(f)
        self.redraw()

    def rotate_photo(self, deg):
        if self.idx < 0:
            return
        f = self.files[self.idx]
        st = self.states[f]
        self._push_undo([f])
        st.rotation = (st.rotation + deg) % 360
        st.cx = st.cy = 0.5
        st.scale = 1.0
        st.angle = 0.0
        st.orient = None
        self._mark(f)
        self.show(self.idx)

    def reset_frame(self):
        if self.idx < 0:
            return
        f = self.files[self.idx]
        st = self.states[f]
        self._push_undo([f])
        st.cx = st.cy = 0.5
        st.scale = 1.0
        st.angle = 0.0
        st.orient = None
        st.edited = bool(st.rotation or st.copies != 1 or st.adj)
        self.listbox.delete(self.idx)
        self.listbox.insert(self.idx, self._list_name(f))
        self.listbox.selection_set(self.idx)
        self.redraw()

    def reset_all(self):
        if not self.files or not messagebox.askyesno("PhotoCrop", "Сбросить рамки, повороты, число копий и цветокоррекцию у всех фотографий?"):
            return
        self._push_undo(self.files)
        self.states = {f: CropState() for f in self.files}
        self.listbox.delete(0, "end")
        for f in self.files:
            self.listbox.insert("end", self._list_name(f))
        self.show(max(self.idx, 0))

    # ---------- цвет
    def _orient_changed(self):
        changed = [f for f, st in self.states.items() if st.orient is not None]
        if changed:
            self._push_undo(changed)
        for st in self.states.values():   # общая ориентация отменяет индивидуальные переключения «R»
            st.orient = None
        self.redraw()

    def _cm_changed(self):
        self._icc_info()
        self._refresh_proof()
        self.tk_key = None
        self.redraw()

    def _icc_info(self):
        p = self.v_icc.get().strip()
        if not p:
            self.v_icc_status.set("Профиль не выбран")
        else:
            try:
                desc, space, ok = profile_info(p)
                txt = f"{desc}  •  {space}"
                if space != "RGB":
                    txt += "  — нужен RGB-профиль!"
                elif self.v_intent.get() not in ok:
                    txt += "  — этот способ рендеринга профилем не поддерживается"
                self.v_icc_status.set(txt)
            except Exception:
                self.v_icc_status.set("Не удалось прочитать файл профиля")
        self.v_cm_text.set(("Профиль: " + Path(p).name) if (self.v_cm_on.get() and p) else "Профиль: выключен")

    def _cm_build(self):
        """Параметры цветопреобразования из настроек. ValueError с понятным текстом при ошибке."""
        return cm_build(self.v_icc.get(), self.v_intent.get(), self.v_bpc.get(), self.v_embed.get())

    def _refresh_proof(self):
        """Экранная картинка: снимок -> цветокоррекция -> (по желанию) имитация печати и подсветка вне охвата."""
        base = self.raw
        self._adj_img = None
        self.gamut_pct = None
        if base is not None and self.idx >= 0 and not self._show_orig:
            st = self.states[self.files[self.idx]]
            if st.adj:
                try:
                    base = adjust_tile(self.raw, merge_adj({}, st), 100, preview=True)
                except Exception:
                    base = self.raw
        self._adj_img = base
        self.preview = base
        if base is None or self._show_orig or not (self.v_proof.get() and self.v_cm_on.get()):
            return
        try:
            cm = self._cm_build()
            if self.v_gamut.get():
                self.preview, self.gamut_pct = gamut_preview(base, self.icc, cm)
            else:
                self.preview = proof_preview(base, self.icc, cm)
        except Exception:
            self.preview = base

    # ---------- цветокоррекция (как в QImage: по фото или сразу для всех)
    def open_adjust(self):
        if not self.files:
            messagebox.showinfo("PhotoCrop", "Сначала откройте папку с фотографиями.")
            return
        if self.adj_panel is not None and self.adj_panel.win.winfo_exists():
            self.adj_panel.win.lift()
            return
        self.adj_panel = AdjustPanel(self)

    def _adj_files(self):
        if self.idx < 0:
            return []
        return self._checked_files() if self.v_adj_scope.get() == "all" else [self.files[self.idx]]

    def _rebuild_list(self):
        yv = self.listbox.yview()
        self.listbox.delete(0, "end")
        for f in self.files:
            self.listbox.insert("end", self._list_name(f))
        if self.idx >= 0:
            self.listbox.selection_set(self.idx)
        self.listbox.yview_moveto(yv[0])

    def adj_set(self, upd, files=None, key=None):
        """Меняет параметры коррекции у файлов (по умолчанию — по выбранной области: это фото / все)."""
        files = files if files is not None else self._adj_files()
        if not files:
            return
        self._push_undo(files, ("adj", files[0] if len(files) == 1 else len(files), key or tuple(sorted(upd))), 1.0)
        flipped = False
        for f in files:
            st = self.states[f]
            had = bool(st.adj)
            st.adj = clean_adj({**st.adj, **upd})
            if not st.edited or had != bool(st.adj):
                flipped = flipped or had != bool(st.adj) or not st.edited
                if st.adj:
                    st.edited = True
        self._after_adj(flipped, len(files) > 1)

    def adj_replace(self, adj, files):
        """Заменяет коррекцию целиком (вставка, сброс, «применить ко всем»)."""
        if not files:
            return
        self._push_undo(files)
        new = clean_adj(adj)
        for f in files:
            st = self.states[f]
            st.adj = dict(new)
            if new:
                st.edited = True
        self._after_adj(True, len(files) > 1)

    def adj_apply_each(self, mapping, drop_keys=()):
        """Для каждого файла своя коррекция: ключи drop_keys заменяются, остальные настройки фото сохраняются."""
        files = list(mapping)
        if not files:
            return
        self._push_undo(files)
        for f in files:
            st = self.states[f]
            keep = {k: v for k, v in st.adj.items() if k not in drop_keys}
            st.adj = clean_adj({**keep, **mapping[f]})
            if st.adj:
                st.edited = True
        self._after_adj(True, len(files) > 1)

    def _after_adj(self, rows, many):
        if rows:
            if many:
                self._rebuild_list()
            else:
                self._refresh_row(self.files[self.idx])
        if self._adj_after is None:                       # не чаще раза в ~40 мс при перетаскивании ползунка
            self._adj_after = self.root.after(40, self._adj_redraw)

    def _adj_redraw(self):
        self._adj_after = None
        if self.idx < 0:
            return
        self._refresh_proof()
        self.tk_key = None
        self.redraw()
        if self.adj_panel is not None:
            self.adj_panel.update_hist()

    def adj_show_original(self, on):
        if self._show_orig != on:
            self._show_orig = on
            self._adj_redraw()

    def choose_icc(self):
        p = filedialog.askopenfilename(title="Цветовой профиль принтера",
                                       initialdir=self.settings.get("icc_dir") or None,
                                       filetypes=[("ICC-профили", "*.icc *.icm"), ("Все файлы", "*.*")])
        if p:
            self.settings["icc_dir"] = str(Path(p).parent)
            self.v_icc.set(p)
            self.v_cm_on.set(True)

    def open_cm_dialog(self):
        if self.cm_dialog is not None and self.cm_dialog.winfo_exists():
            self.cm_dialog.lift()
            return
        d = self.cm_dialog = tk.Toplevel(self.root)
        d.title("Цветовой профиль печати")
        d.after(0, lambda: (theme_walk(d), i18n_apply(d)))
        d.transient(self.root)
        d.resizable(False, False)
        f = ttk.Frame(d, padding=14)
        f.pack(fill="both", expand=True)
        ttk.Checkbutton(f, text="Применять профиль принтера при сохранении", variable=self.v_cm_on).pack(anchor="w")
        row = ttk.Frame(f)
        row.pack(fill="x", pady=(10, 2))
        ttk.Entry(row, textvariable=self.v_icc, width=56).pack(side="left", fill="x", expand=True)
        ttk.Button(row, text="Обзор…", command=self.choose_icc).pack(side="left", padx=(6, 0))
        ttk.Label(f, textvariable=self.v_icc_status, wraplength=480, foreground="#555").pack(anchor="w", pady=(0, 10))
        ttk.Label(f, text="Способ рендеринга:").pack(anchor="w")
        ttk.Combobox(f, textvariable=self.v_intent, values=list(INTENTS), state="readonly", width=34).pack(anchor="w", pady=(2, 6))
        ttk.Checkbutton(f, text="Компенсация точки чёрного", variable=self.v_bpc).pack(anchor="w")
        ttk.Checkbutton(f, text="Встроить профиль в готовый файл", variable=self.v_embed).pack(anchor="w", pady=(2, 0))
        ttk.Separator(f).pack(fill="x", pady=10)
        ttk.Label(f, wraplength=480, justify="left", foreground="#555",
                  text="Фото переводится из своего профиля (если его нет — sRGB) в пространство принтера. "
                       "Печатайте готовые файлы через драйвер Epson с отключённым управлением цветом "
                       "(«Без цветокоррекции» / No Color Adjustment), с теми же типом бумаги и качеством печати, "
                       "что были при печати тестовой мишени для профиля. "
                       "Проверить результат на экране можно галочкой «Имитация печати» в главном окне."
                  ).pack(anchor="w")
        ttk.Button(f, text="Закрыть", command=d.destroy).pack(anchor="e", pady=(10, 0))

    def _copies_step(self, d):
        if self.idx < 0:
            return
        try:
            n = int(float(self.v_copies.get()))
        except ValueError:
            n = self.states[self.files[self.idx]].copies
        self.v_copies.set(str(max(1, min(99, n + d))))

    def _copies_changed(self):
        if self._copies_lock or self.idx < 0:
            return
        try:
            n = max(1, min(99, int(float(self.v_copies.get()))))
        except ValueError:
            return
        f = self.files[self.idx]
        st = self.states[f]
        if st.copies != n:
            self._push_undo([f], ("copies", f), 1.0)
            st.copies = n
            st.edited = True
            self.listbox.delete(self.idx)
            self.listbox.insert(self.idx, self._list_name(f))
            self.listbox.selection_set(self.idx)

    def open_print(self):
        if not self.files:
            messagebox.showinfo("PhotoCrop", "Сначала откройте папку с фотографиями.")
            return
        if self.print_dialog is not None and self.print_dialog.win.winfo_exists():
            self.print_dialog.win.lift()
            return
        self.print_dialog = PrintDialog(self)

    # ---------- сохранение
    def _options(self):
        try:
            dpi = float(self.v_dpi.get().replace(",", "."))
            if not 50 <= dpi <= 2400:
                raise ValueError
        except ValueError:
            messagebox.showerror("PhotoCrop", "Укажите DPI числом от 50 до 2400.")
            return None
        outdir = self.v_outdir.get().strip()
        out_mode = self.v_outmode.get()
        out_name = re.sub(r'[\\/:*?"<>|]+', "", self.v_outname.get()).strip(" .") or OUT_SUBDIR
        if out_mode == "custom" and not outdir:
            messagebox.showerror("PhotoCrop", "Укажите папку для сохранения или выберите «Рядом с фото».")
            return None
        cm = None
        if self.v_cm_on.get():
            try:
                cm = self._cm_build()
            except ValueError as ex:
                messagebox.showerror("PhotoCrop", str(ex))
                return None
        return {
            "fmt": FORMATS[self.v_format.get()],
            "orient": ORIENTS[self.v_orient.get()],
            "mode": MODES[self.v_mode.get()],
            "dpi": dpi,
            "resize": self.v_resize.get(),
            "filetype": self.v_filetype.get(),
            "quality": int(float(self.v_quality.get())),
            "outdir": outdir, "out_mode": out_mode, "out_name": out_name,
            "subfolder": self.v_subfolder.get(),
            "copies_in_name": self.v_copies_name.get(),
            "universe": [(f, self.states[f].copies) for f in self.files],
            "cm": cm,
        }

    def save(self, all_files):
        if self.saving or not self.files:
            return
        o = self._options()
        if not o:
            return
        files = self._checked_files() if all_files else ([self.files[self.idx]] if self.idx >= 0 else [])
        if not files:
            messagebox.showinfo("PhotoCrop", "Ни одно фото не отмечено. Нажмите «Выбрать все» или «+» на превью нужных фото.")
            return
        jobs = [(f, self.states[f].copy()) for f in files]
        low = low_res_list(jobs, o)
        if low:
            lst = "\n".join(f"{n} — {d} dpi" for n, d in low[:10]) + (f"\n… и ещё {len(low) - 10}" if len(low) > 10 else "")
            if not messagebox.askyesno("PhotoCrop", f"Малое разрешение для печати (меньше 150 dpi), фото: {len(low)}\n\n{lst}\n\n"
                                       "Печать будет нерезкой. Всё равно сохранить?"):
                return
        self.saving = True
        self.progress.config(maximum=len(jobs), value=0)
        self.lbl_prog.config(text="Сохранение…")
        threading.Thread(target=self._worker, args=(jobs, o), daemon=True).start()
        self.root.after(100, self._poll)

    def _worker(self, jobs, o):
        try:
            saved, errors = process_batch(jobs, o, lambda i, n, name: self.q.put(("progress", i, n, name)))
        except Exception as ex:
            saved, errors = [], [f"{ex.__class__.__name__}: {ex}"]
        try:
            dirs = out_dirs(jobs, o)
        except Exception:
            dirs = []
        self.q.put(("done", len(saved), errors, o, dirs))

    def _poll(self):
        try:
            while True:
                msg = self.q.get_nowait()
                if msg[0] == "progress":
                    _, i, n, name = msg
                    self.progress.config(value=i)
                    self.lbl_prog.config(text=f"{i} из {n}: {name}")
                else:
                    _, ok, errors, o, dirs = msg
                    self.saving = False
                    out = dirs[0] if dirs else Path(o["outdir"])
                    self.lbl_prog.config(text=f"Готово: {ok} файл(ов)")
                    text = f"Сохранено файлов: {ok}\nПапка: {out}" + (f"  (и ещё {len(dirs) - 1})" if len(dirs) > 1 else "")
                    if o.get("cm"):
                        text += f"\nПрофиль принтера: {o['cm']['name']}"
                    if errors:
                        text += f"\n\nОшибки ({len(errors)}):\n" + "\n".join(errors[:15])
                        messagebox.showwarning("PhotoCrop", text)
                    elif messagebox.askyesno("PhotoCrop", text + "\n\nОткрыть папку?") and hasattr(os, "startfile"):
                        os.startfile(out)
                    return
        except queue.Empty:
            pass
        self.root.after(100, self._poll)

    def open_settings(self):
        """Окно настроек: язык, папка по умолчанию, прилипание рамки, о программе. Разделы добавляются по мере роста."""
        if getattr(self, "settings_win", None) is not None and self.settings_win.winfo_exists():
            self.settings_win.lift()
            return
        d = self.settings_win = tk.Toplevel(self.root)
        d.title("Настройки")
        d.transient(self.root)
        d.resizable(False, False)
        nb = ttk.Notebook(d)
        nb.pack(fill="both", expand=True, padx=10, pady=10)
        g = ttk.Frame(nb, padding=12)
        nb.add(g, text="Общие")
        ttk.Label(g, text="Язык интерфейса:").grid(row=0, column=0, sticky="w")
        v_lang = tk.StringVar(value=LANGS[get_language()])
        ttk.Combobox(g, textvariable=v_lang, values=list(LANGS.values()), state="readonly", width=14).grid(row=0, column=1, sticky="w", padx=8)
        ttk.Label(g, text="Папка по умолчанию в диалогах открытия:").grid(row=1, column=0, sticky="w", pady=(10, 0))
        dirs = {"desktop": "Рабочий стол", "last": "Последняя использованная"}
        v_dir = tk.StringVar(value=tr(dirs.get(self.settings.get("start_dir_mode"), dirs["desktop"])))
        cb = ttk.Combobox(g, textvariable=v_dir, values=[tr(x) for x in dirs.values()], state="readonly", width=24)
        cb.grid(row=1, column=1, sticky="w", padx=8, pady=(10, 0))
        ttk.Label(g, text="Язык меняется сразу. Часть динамических надписей и названия в выпадающих списках остаются на русском.",
                  wraplength=430, foreground="#666", justify="left").grid(row=2, column=0, columnspan=2, sticky="w", pady=(14, 0))
        ap = ttk.Frame(nb, padding=12)
        nb.add(ap, text="Оформление")
        ttk.Label(ap, text="Тема оформления:").grid(row=0, column=0, sticky="w")
        cur_theme = self.settings.get("theme", DEFAULT_THEME)
        v_theme = tk.StringVar(value=tr(THEMES.get(cur_theme, THEMES[DEFAULT_THEME])["title"]))
        ttk.Combobox(ap, textvariable=v_theme, values=[tr(t["title"]) for t in THEMES.values()], state="readonly",
                     width=22).grid(row=0, column=1, sticky="w", padx=8)
        v_anim = tk.BooleanVar(value=bool(self.settings.get("anim", True)))
        ttk.Checkbutton(ap, text="Анимация отправки листов на печать", variable=v_anim).grid(row=1, column=0, columnspan=2, sticky="w", pady=(12, 0))
        ttk.Label(ap, text="Тема меняется сразу, по кнопке «Применить».", foreground="#666").grid(row=2, column=0, columnspan=2, sticky="w", pady=(12, 0))
        c = ttk.Frame(nb, padding=12)
        nb.add(c, text="Кадрирование")
        ttk.Checkbutton(c, text="Прилипание рамки к краям и центру фото", variable=self.v_snap).grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Label(c, text="Сила прилипания, экранных пикселей:").grid(row=1, column=0, sticky="w", pady=(10, 0))
        v_px = tk.StringVar(value=str(int(self.settings.get("snap_px", 10))))
        ttk.Spinbox(c, from_=2, to=40, increment=1, textvariable=v_px, width=5).grid(row=1, column=1, sticky="w", padx=8, pady=(10, 0))
        ttk.Label(c, text="Ctrl при перетаскивании — временно отключает прилипание.", foreground="#666").grid(row=2, column=0, columnspan=2, sticky="w", pady=(10, 0))
        a = ttk.Frame(nb, padding=12)
        nb.add(a, text="О программе")
        ttk.Label(a, text="PhotoCrop").pack(anchor="w")
        ttk.Label(a, text="Программа для кадрирования и печати фотографий.", foreground="#666").pack(anchor="w")
        ttk.Label(a, text=str(SETTINGS_PATH), foreground="#888").pack(anchor="w", pady=(8, 0))

        def apply(close=False):
            code = next((k for k, v in LANGS.items() if v == v_lang.get()), "ru")
            self.settings["language"] = code
            inv = {tr(v): k for k, v in dirs.items()}
            self.settings["start_dir_mode"] = inv.get(v_dir.get(), "desktop")
            try:
                self.settings["snap_px"] = max(2, min(40, int(float(v_px.get()))))
            except ValueError:
                pass
            self.settings["anim"] = bool(v_anim.get())
            new_theme = next((k for k, t in THEMES.items() if tr(t["title"]) == v_theme.get()), cur_theme)
            if new_theme != self.settings.get("theme", DEFAULT_THEME):
                self.settings["theme"] = new_theme
                self.apply_theme()
            set_language(code)
            self.apply_language()
            if close:
                d.destroy()
        bt = ttk.Frame(d)
        bt.pack(fill="x", padx=10, pady=(0, 10))
        ttk.Button(bt, text="OK", command=lambda: apply(True)).pack(side="right")
        ttk.Button(bt, text="Применить", command=apply).pack(side="right", padx=6)
        theme_walk(d)
        i18n_apply(d)

    def apply_theme(self):
        """Перекрашивает все открытые окна под выбранную тему."""
        apply_theme(self.root, self.settings.get("theme", DEFAULT_THEME))
        try:
            self.listbox.draw()
            self.redraw()
            if not self.files:
                self.lbl_info.config(fg=PAL["muted"])
            pd = self.print_dialog
            if pd is not None and pd.win.winfo_exists():
                pd._draw()
                pd.anim._paint(None)
        except Exception:
            pass

    def apply_language(self):
        i18n_apply(self.root)
        self.root.title(tr("PhotoCrop — кадрирование для фотопечати"))
        try:
            self._upd_counts()
        except Exception:
            pass

    def _on_close(self):
        if self.saving and not messagebox.askyesno("PhotoCrop", "Идёт сохранение. Всё равно выйти?"):
            return
        pd0 = self.print_dialog
        try:
            printing = pd0 is not None and pd0.win.winfo_exists() and pd0.busy
        except Exception:
            printing = False
        if printing and not messagebox.askyesno("PhotoCrop", "Идёт печать или экспорт листов. Прервать и выйти?\n"
                                                "Задание в очереди принтера может остаться неполным."):
            return
        try:
            self._autosave_now()
        except Exception:
            pass
        pd = self.print_dialog
        if pd is not None:
            try:
                if pd.win.winfo_exists():
                    pd.cancel.set()
                    pd.save_state()
            except Exception:
                pass
        self.settings.update(
            format=self.v_format.get(), orient=self.v_orient.get(), mode=self.v_mode.get(),
            recursive=self.v_recursive.get(), subfolder=self.v_subfolder.get(), copies_in_name=self.v_copies_name.get(),
            resize=self.v_resize.get(), filetype=self.v_filetype.get(),
            quality=int(float(self.v_quality.get())), grid=self.v_grid.get(),
            out_mode=self.v_outmode.get(), out_name=self.v_outname.get().strip() or OUT_SUBDIR,
            outdir_custom=self.v_outdir.get().strip() if self.v_outmode.get() == "custom" else self.settings.get("outdir_custom", ""),
            cm_on=self.v_cm_on.get(), icc=self.v_icc.get().strip(), intent=self.v_intent.get(),
            bpc=self.v_bpc.get(), embed=self.v_embed.get(), snap=self.v_snap.get(), language=get_language(),
            theme=self.settings.get("theme", DEFAULT_THEME), anim=bool(self.settings.get("anim", True)))
        try:
            self.settings["dpi"] = float(self.v_dpi.get().replace(",", "."))
        except ValueError:
            pass
        save_settings(self.settings)
        self.root.destroy()


class AdjustPanel:
    """Окно «Коррекция фото» (как в QImage): ползунки с живым просмотром в главном окне, гистограмма,
    область действия — это фото или сразу все, копирование/вставка настроек, сравнение с оригиналом."""
    TABS = (
        ("Основное", (("Яркость", "bright", -100, 100, 1), ("Контраст", "contrast", -100, 100, 1),
                      ("Гамма (средние тона)", "gamma", 0.4, 2.5, 0.01), ("Тени (осветлить +)", "shadows", -100, 100, 1),
                      ("Света (вернуть −)", "highlights", -100, 100, 1), ("Насыщенность", "sat", -100, 100, 1),
                      ("Красочность (бледные цвета)", "vib", -100, 100, 1))),
        ("Цвет", (("Температура (холоднее ← → теплее)", "temp", -100, 100, 1), ("Оттенок (зелёный ← → пурпурный)", "tint", -100, 100, 1),
                  ("Красный", "r", -100, 100, 1), ("Зелёный", "g", -100, 100, 1), ("Синий", "b", -100, 100, 1))),
        ("Детали", (("Шум цвета", "denoise", 0, 100, 1), ("Резкость при печати, %", "sharp", 0, 300, 1),
                    ("Радиус резкости (при 300 ppi)", "sharp_radius", 0.1, 5, 0.1), ("Порог резкости", "sharp_thr", 0, 50, 1))),
    )

    def __init__(self, app):
        self.app = app
        self.lock = True            # пока строится окно, события ползунков игнорируются (снимается в sync)
        w = self.win = tk.Toplevel(app.root)
        w.title("Коррекция фото")
        w.after(50, lambda: (theme_walk(w), i18n_apply(w)))
        w.transient(app.root)
        w.resizable(False, False)
        try:
            w.geometry(f"+{int(app.root.winfo_rootx()) + 60}+{int(app.root.winfo_rooty()) + 70}")
        except Exception:
            pass
        w.protocol("WM_DELETE_WINDOW", self.close)
        f = ttk.Frame(w, padding=10)
        f.pack(fill="both", expand=True)

        head = ttk.Frame(f)
        head.pack(fill="x")
        ttk.Button(head, text="◀", width=3, command=lambda: app.go(-1)).pack(side="left")
        self.lbl_name = ttk.Label(head, text="", width=34, anchor="center")
        self.lbl_name.pack(side="left", padx=6, fill="x", expand=True)
        ttk.Button(head, text="▶", width=3, command=lambda: app.go(1)).pack(side="left")

        sc = ttk.LabelFrame(f, text=" Менять ", padding=(8, 2))
        sc.pack(fill="x", pady=(8, 6))
        ttk.Radiobutton(sc, text="только это фото", value="one", variable=app.v_adj_scope).pack(side="left")
        ttk.Radiobutton(sc, text="все фото сразу", value="all", variable=app.v_adj_scope).pack(side="left", padx=14)

        self.hist = tk.Canvas(f, width=256, height=72, bg="#202020", highlightthickness=1, highlightbackground="#666")
        self.hist.pack(pady=(0, 2))
        self.lbl_hist = ttk.Label(f, text="", foreground="#555")
        self.lbl_hist.pack(anchor="w")

        nb = ttk.Notebook(f)
        nb.pack(fill="x", pady=(6, 4))
        self.vars, self.vals, self.scales = {}, {}, {}
        for title, rows in self.TABS:
            tab = ttk.Frame(nb, padding=8)
            nb.add(tab, text=title)
            for label, key, lo, hi, step in rows:
                self._slider(tab, label, key, lo, hi, step)
            if title == "Цвет":
                self.v_bw = tk.BooleanVar(value=False)
                self.v_sepia = tk.BooleanVar(value=False)
                row = ttk.Frame(tab)
                row.pack(fill="x", pady=(6, 0))
                ttk.Checkbutton(row, text="Чёрно-белое", variable=self.v_bw, command=lambda: self._flag("bw", self.v_bw)).pack(side="left")
                ttk.Checkbutton(row, text="Сепия", variable=self.v_sepia, command=lambda: self._flag("sepia", self.v_sepia)).pack(side="left", padx=12)
            if title == "Основное":
                self.v_auto = tk.StringVar(value="")
                row = ttk.Frame(tab)
                row.pack(fill="x", pady=(8, 0))
                ttk.Label(row, text="Авто-уровни:").pack(side="left")
                for lab, val in (("нет", ""), ("контраст", "contrast"), ("цвет", "color"), ("Ч/Б", "bw")):
                    ttk.Radiobutton(row, text=lab, value=val, variable=self.v_auto, command=self._auto_changed).pack(side="left", padx=6)
        ttk.Label(f, foreground="#666", wraplength=330, justify="left",
                  text="Двойной щелчок по ползунку — сбросить его. Авто-уровни считаются для каждого фото отдельно "
                       "(удобно включить вместе с «все фото сразу»).").pack(anchor="w")

        eb = ttk.LabelFrame(f, text=" Улучшение для печати на Epson ", padding=6)
        eb.pack(fill="x", pady=(8, 2))
        r_ = ttk.Frame(eb)
        r_.pack(fill="x")
        ttk.Button(r_, text="✨ Улучшения для Epson", command=lambda: self.enhance(1)).pack(side="left", fill="x", expand=True)
        ttk.Button(r_, text="✨✨ Супер улучшения", command=lambda: self.enhance(2)).pack(side="left", fill="x", expand=True, padx=(4, 0))
        self.lbl_enh = ttk.Label(eb, text="Подбирается под каждый снимок; результат — обычные ползунки, их можно поправить.",
                                 foreground="#555", wraplength=330, justify="left")
        self.lbl_enh.pack(anchor="w", pady=(4, 0))
        b1 = ttk.Frame(f)
        b1.pack(fill="x", pady=(8, 2))
        ttk.Button(b1, text="Применить ко всем", command=self.apply_all).pack(side="left", fill="x", expand=True)
        ttk.Button(b1, text="Копировать", command=self.copy).pack(side="left", padx=3)
        ttk.Button(b1, text="Вставить", command=lambda: self.paste(False)).pack(side="left")
        ttk.Button(b1, text="Вставить во все", command=lambda: self.paste(True)).pack(side="left", padx=3)
        b2 = ttk.Frame(f)
        b2.pack(fill="x", pady=2)
        ttk.Button(b2, text="Авто-яркость", command=self.auto_bright).pack(side="left", fill="x", expand=True)
        ttk.Button(b2, text="Сбросить фото", command=lambda: self.reset(False)).pack(side="left", padx=3)
        ttk.Button(b2, text="Сбросить все", command=lambda: self.reset(True)).pack(side="left")
        self.btn_orig = ttk.Button(f, text="👁 Показать оригинал (удерживайте)")
        self.btn_orig.pack(fill="x", pady=(6, 0))
        self.btn_orig.bind("<ButtonPress-1>", lambda e: app.adj_show_original(True))
        self.btn_orig.bind("<ButtonRelease-1>", lambda e: app.adj_show_original(False))
        ttk.Button(f, text="Закрыть", command=self.close).pack(anchor="e", pady=(8, 0))
        self.sync()

    # ---- построение
    def _slider(self, parent, label, key, lo, hi, step):
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=1)
        ttk.Label(row, text=label, width=34, anchor="w").pack(side="top", anchor="w")
        line = ttk.Frame(row)
        line.pack(fill="x")
        var = tk.DoubleVar(value=NEUTRAL_ADJ[key])
        txt = tk.StringVar(value="")
        sc = ttk.Scale(line, from_=lo, to=hi, orient="horizontal", length=260, variable=var,
                       command=lambda v, k=key, st=step: self._moved(k, v, st))
        sc.pack(side="left", fill="x", expand=True)
        sc.bind("<Double-Button-1>", lambda e, k=key: self._reset_one(k))
        ttk.Label(line, textvariable=txt, width=6, anchor="e").pack(side="left", padx=(6, 0))
        self.vars[key], self.vals[key], self.scales[key] = var, txt, sc

    @staticmethod
    def _fmt(key, v):
        return f"{v:.2f}" if key == "gamma" else (f"{v:.1f}" if key == "sharp_radius" else f"{v:+.0f}" if key in ("bright", "contrast", "shadows", "highlights", "sat", "vib", "temp", "tint", "r", "g", "b") else f"{v:.0f}")

    def _moved(self, key, raw, step):
        v = round(float(raw) / step) * step
        v = round(v, 2)
        self.vals[key].set(self._fmt(key, v))
        if self.lock:
            return
        cur = self.cur_adj().get(key, NEUTRAL_ADJ[key])
        if abs(cur - v) < 1e-9:
            return
        self.app.adj_set({key: v}, key=("slider", key))

    def _reset_one(self, key):
        self.lock = True
        self.vars[key].set(NEUTRAL_ADJ[key])
        self.vals[key].set(self._fmt(key, NEUTRAL_ADJ[key]))
        self.lock = False
        self.app.adj_set({key: NEUTRAL_ADJ[key]})

    def _flag(self, key, var):
        self.app.adj_set({key: bool(var.get())})

    def _auto_changed(self):
        self.app.adj_set({"auto": self.v_auto.get()})

    # ---- состояние
    def cur_adj(self):
        a = self.app
        if a.idx < 0:
            return {}
        return a.states[a.files[a.idx]].adj

    def sync(self):
        a = self.app
        if a.idx < 0:
            return
        self.lock = True
        try:
            full = adj_full(self.cur_adj())
            for k, var in self.vars.items():
                var.set(full[k])
                self.vals[k].set(self._fmt(k, full[k]))
            self.v_bw.set(full["bw"])
            self.v_sepia.set(full["sepia"])
            self.v_auto.set(full["auto"])
            self.lbl_name.config(text=f"[{a.idx + 1}/{len(a.files)}]  {a.files[a.idx].name}")
        finally:
            self.lock = False
        self.update_hist()

    def update_hist(self):
        a = self.app
        img = a._adj_img if a._adj_img is not None else a.raw
        c = self.hist
        c.delete("all")
        if img is None:
            return
        try:
            h, low, high = hist_rgb(img)
        except Exception:
            return
        cap = sorted(h[i * 256 + j] for i in range(3) for j in range(2, 254))[-12] or 1   # без «шпилек» на краях
        for ch, col in ((0, "#ff5555"), (1, "#55dd55"), (2, "#6688ff")):
            pts = []
            for j in range(256):
                pts += [j + 1, 71 - min(1.0, h[ch * 256 + j] / cap) * 68]
            c.create_line(*pts, fill=col)
        warn = low > 1 or high > 1
        t = f"В чёрном: {low:.1f}%   В белом: {high:.1f}%"
        if a.gamut_pct is not None:
            t += f"   Вне охвата принтера: {a.gamut_pct:.1f}%"
        self.lbl_hist.config(text=t, foreground="#c62828" if warn else "#555")

    # ---- действия
    @staticmethod
    def _small(f):
        with Image.open(f) as im:
            im.draft("RGB", (600, 600))
            im = to_rgb(ImageOps.exif_transpose(im))
            im.thumbnail((500, 500), RESAMPLE_FAST)
            return im

    def enhance(self, level):
        a = self.app
        files = a._adj_files()
        if not files or getattr(self, "_enh_busy", False):
            return
        self._enh_busy = True
        try:
            self._enhance(level, a, files)
        finally:
            self._enh_busy = False

    def _enhance(self, level, a, files):
        if len(files) > 1 and not messagebox.askyesno(
                "Улучшение", f"Применить «{'Супер улучшения' if level >= 2 else 'Улучшения для Epson'}» к {len(files)} фото?\n"
                "Для каждого фото параметры подберутся отдельно. Заменятся яркость, контраст, тени, света, насыщенность, красочность, авто-уровни, шум и резкость; температура, оттенок, баланс, гамма, ч/б и сепия сохранятся. "
                "Отменить можно Ctrl+Z.", parent=self.win):
            return
        mapping, bad = {}, 0
        self.win.config(cursor="watch")
        try:
            for n, f in enumerate(files):
                try:
                    mapping[f] = enhance_adj(analyze_image(self._small(f)), level)
                except Exception:
                    bad += 1
                if n % 3 == 2:
                    self.lbl_enh.config(text=f"Анализ: {n + 1} из {len(files)}…")
                    self.win.update()               # окно не «зависает» на больших PNG/TIFF
        finally:
            self.win.config(cursor="")
        notes = []
        cur = a.files[a.idx]
        if cur in mapping and a.raw is not None and a.v_cm_on.get():       # цвета не должны уходить за охват принтера
            try:
                cm = a._cm_build()
                for _ in range(2):
                    test = adjust_tile(a.raw, merge_adj({}, type("S", (), {"adj": {**{k: v for k, v in a.states[cur].adj.items() if k not in ENHANCE_KEYS}, **mapping[cur]}})()), 100, preview=True)
                    pct = gamut_preview(test, a.icc, cm)[1]
                    if pct <= 3.0 or not (mapping[cur].get("vib") or mapping[cur].get("sat")):
                        break
                    mapping[cur] = clean_adj({**mapping[cur], "vib": mapping[cur].get("vib", 0) / 2, "sat": 0})
                    notes.append(f"красочность уменьшена: {pct:.0f}% цветов не передаёт принтер")
            except Exception:
                pass
        a.adj_apply_each(mapping, ENHANCE_KEYS)
        if level and str(a.v_dpi.get()).replace(",", ".").strip() not in ("360", "720"):
            a.v_dpi.set("360")                                              # родное разрешение печати Epson (5760 = 16 × 360)
            notes.append("разрешение сохранения 360 dpi")
        if a.v_cm_on.get() and not a.v_bpc.get():
            a.v_bpc.set(True)
            notes.append("включена компенсация точки чёрного")
        self.sync()
        msg = f"Готово: {len(mapping)} фото" + (f", не удалось {bad}" if bad else "")
        self.lbl_enh.config(text=msg + (". " + "; ".join(notes) if notes else "") + ".", foreground="#1a8f2e")

    def apply_all(self):
        a = self.app
        if a.idx < 0:
            return
        if len(a.files) > 1 and not messagebox.askyesno("Коррекция", "Применить настройки этого фото ко всем фотографиям?\n"
                                                        "Их собственная коррекция будет заменена. Отменить можно Ctrl+Z.", parent=self.win):
            return
        a.adj_replace(self.cur_adj(), list(a.files))

    def copy(self):
        self.app._adj_clipboard = dict(self.cur_adj())
        self.lbl_hist.config(text="Настройки скопированы — перейдите к другому фото и нажмите «Вставить»", foreground="#555")

    def paste(self, to_all):
        a = self.app
        if a._adj_clipboard is None:
            messagebox.showinfo("Коррекция", "Сначала нажмите «Копировать» на фото с нужными настройками.", parent=self.win)
            return
        a.adj_replace(a._adj_clipboard, list(a.files) if to_all else [a.files[a.idx]])
        self.sync()

    def reset(self, all_files):
        a = self.app
        if all_files and not messagebox.askyesno("Коррекция", "Сбросить цветокоррекцию у всех фотографий?", parent=self.win):
            return
        a.adj_replace({}, list(a.files) if all_files else [a.files[a.idx]])
        self.sync()

    def auto_bright(self):
        a = self.app
        if a.idx < 0 or a.raw is None:
            return
        if a.v_adj_scope.get() == "all":
            messagebox.showinfo("Коррекция", "Авто-яркость считается по каждому фото отдельно. Для всех сразу используйте «Авто-уровни».",
                                parent=self.win)
            return
        sug = suggest_adjust(analyze_image(a.raw))
        a.adj_set({"bright": sug.get("bright", 0.0), "contrast": sug.get("contrast", 0.0)}, files=[a.files[a.idx]])
        self.sync()

    def close(self):
        self.app.adj_panel = None
        self.app.adj_show_original(False)
        self.win.destroy()



class PrintDialog:
    """Окно печати: предпросмотр листов + все настройки раскладки, обработки и принтера."""
    PREVIEW_DELAY = 300

    def __init__(self, app):
        self.app = app
        self.saved = dict(app.settings.get("print", {}))
        self.printers = list_printers()
        self.photos, self.plan, self.page = [], None, 0
        self.o, self.mode, self.cm, self.cm_err = parse_print_opts({}), "crop", None, None
        self.cache = {}
        self.tkprev = None
        self._after = None
        self._err = None
        self.busy = False
        self.cancel = threading.Event()
        self.q = queue.Queue()
        self.blob = None

        w = self.win = tk.Toplevel(app.root)
        w.title("Печать")
        w.after(50, lambda: (theme_walk(w), i18n_apply(w)))
        w.geometry("1300x860")
        w.minsize(1080, 700)
        if not getattr(app, "print_only", False):       # окно печати, вызванное из нового интерфейса, живёт само по себе
            w.transient(app.root)
        w.protocol("WM_DELETE_WINDOW", self.close)

        self.v = {}
        for k, d in PRINT_DEFAULTS.items():
            val = self.saved.get(k, d)
            self.v[k] = tk.BooleanVar(value=bool(val)) if isinstance(d, bool) else tk.StringVar(value=str(val))
        last = app.settings.get("print_printer")
        self.v_printer = tk.StringVar(value=last if last in self.printers else (self.printers[0] if self.printers else ""))
        if not self.printers and self.v["paper"].get() == PAPER_DRIVER:
            self.v["paper"].set("A4 (210×297)")
        self.v_preset = tk.StringVar(value="")
        self.v_geom = tk.StringVar(value="")
        self.v_drv = tk.StringVar(value="")
        self.v_cm = tk.StringVar(value="")
        self.v_info = tk.StringVar(value="")
        self.v_page = tk.StringVar(value="")
        self._load_blob()
        self._build()
        for v in self.v.values():
            v.trace_add("write", lambda *a: self._schedule())
        self.v_printer.trace_add("write", lambda *a: self._printer_changed())
        self._update_drv_text()
        self._schedule(50)
        self.win.after(100, self._poll)

    # ---------- построение окна
    def _build(self):
        w = self.win
        right = ttk.Frame(w, padding=(0, 8, 8, 8))
        right.pack(side="right", fill="y")
        left = ttk.Frame(w, padding=(8, 8, 8, 8))
        left.pack(side="left", fill="both", expand=True)

        self.canvas = tk.Canvas(left, bg=PAL["canvas"], highlightthickness=0)
        self.canvas._th_key = "canvas"
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", lambda e: self._schedule(120))
        nav = ttk.Frame(left, padding=(0, 6, 0, 0))
        nav.pack(fill="x")
        ttk.Button(nav, text="◀", width=4, command=lambda: self._nav(-1)).pack(side="left")
        ttk.Label(nav, textvariable=self.v_page, width=18, anchor="center").pack(side="left", padx=4)
        ttk.Button(nav, text="▶", width=4, command=lambda: self._nav(1)).pack(side="left")
        ttk.Label(left, textvariable=self.v_info, wraplength=760, justify="left").pack(fill="x", pady=(6, 0))
        w.bind("<Prior>", lambda e: self._nav(-1))
        w.bind("<Next>", lambda e: self._nav(1))

        nb = ttk.Notebook(right, width=470)
        nb.pack(fill="both", expand=True)
        self._tab_printer(nb)
        self._tab_layout(nb)
        self._tab_process(nb)
        self._tab_color(nb)

        bot = ttk.Frame(right, padding=(0, 8, 0, 0))
        bot.pack(fill="x")
        row = ttk.Frame(bot)
        row.pack(fill="x")
        ttk.Label(row, text="Печатать:").pack(side="left")
        ttk.Combobox(row, textvariable=self.v["pages"], values=list(PAGES), state="readonly", width=20).pack(side="left", padx=6)
        self.progress = ttk.Progressbar(bot, mode="determinate")
        self.progress.pack(fill="x", pady=(8, 2))
        self.lbl_prog = ttk.Label(bot, text="", wraplength=450)
        self.lbl_prog.pack(anchor="w")
        self.anim = SendAnim(bot)
        if self.app.settings.get("anim", True):
            self.anim.pack(fill="x", pady=(4, 0))
        btns = ttk.Frame(bot)
        btns.pack(fill="x", pady=(6, 0))
        self.btn_print = ttk.Button(btns, text="🖨 Печать", style="Accent.TButton", command=self._print)
        self.btn_print.pack(side="left", fill="x", expand=True)
        self.btn_export = ttk.Button(btns, text="💾 Листы в файлы…", style="Big.TButton", command=self._export)
        self.btn_export.pack(side="left", fill="x", expand=True, padx=6)
        self.btn_cancel = ttk.Button(btns, text="Отмена", command=self.cancel.set, state="disabled")
        self.btn_cancel.pack(side="left")
        ttk.Button(bot, text="Закрыть", command=self.close).pack(anchor="e", pady=(6, 0))

    def _combo(self, parent, key, values, width=22):
        return ttk.Combobox(parent, textvariable=self.v[key], values=list(values), state="readonly", width=width)

    def add_edge_test(self):
        """Создаёт картинку-шкалу размера текущего формата и добавляет её в список фото: распечатайте её теми же настройками —
        последняя видимая цифра на каждой стороне показывает, сколько миллиметров срезал принтер."""
        app = self.app
        fmt = FORMATS[app.v_format.get()]
        orient = ORIENTS[app.v_orient.get()]
        w, h = (min(fmt[0], fmt[1]), max(fmt[0], fmt[1]))
        if orient == "landscape":
            w, h = h, w
        d = Path(tempfile.gettempdir()) / "PhotoCrop"
        d.mkdir(parents=True, exist_ok=True)
        p = d / f"Шкала_краёв_{fmt[2]}.png"
        make_edge_test(w, h, 300).save(p, dpi=(300, 300))
        app.open_files_from([p], add=True)

    def _spin(self, parent, key, lo, hi, step, width=7):
        return ttk.Spinbox(parent, from_=lo, to=hi, increment=step, textvariable=self.v[key], width=width)

    def _tab_printer(self, nb):
        t = ttk.Frame(nb, padding=10)
        nb.add(t, text="Принтер")
        t.columnconfigure(0, weight=1)
        ttk.Label(t, text="Принтер:").grid(row=0, column=0, sticky="w")
        self.cb_printer = ttk.Combobox(t, textvariable=self.v_printer, values=self.printers, state="readonly")
        self.cb_printer.grid(row=1, column=0, sticky="we")
        ttk.Button(t, text="↻", width=3, command=self._reload_printers).grid(row=1, column=1, padx=(4, 0))
        ttk.Button(t, text="⚙ Свойства принтера (драйвер)…", command=self._props).grid(row=2, column=0, columnspan=2, sticky="we", pady=(6, 2))
        ttk.Label(t, textvariable=self.v_drv, wraplength=430, foreground="#555", justify="left").grid(row=3, column=0, columnspan=2, sticky="w")

        ttk.Separator(t).grid(row=4, column=0, columnspan=2, sticky="we", pady=8)
        ttk.Label(t, text="Пресеты (принтер + драйвер + раскладка):").grid(row=5, column=0, columnspan=2, sticky="w")
        pr = ttk.Frame(t)
        pr.grid(row=6, column=0, columnspan=2, sticky="we", pady=(2, 0))
        self.cb_preset = ttk.Combobox(pr, textvariable=self.v_preset, values=self._preset_names(), state="readonly", width=24)
        self.cb_preset.pack(side="left", fill="x", expand=True)
        self.cb_preset.bind("<<ComboboxSelected>>", lambda e: self._preset_load())
        ttk.Button(pr, text="Сохранить…", command=self._preset_save).pack(side="left", padx=4)
        ttk.Button(pr, text="Удалить", command=self._preset_delete).pack(side="left")

        ttk.Separator(t).grid(row=7, column=0, columnspan=2, sticky="we", pady=8)
        g = ttk.Frame(t)
        g.grid(row=8, column=0, columnspan=2, sticky="we")
        ttk.Label(g, text="Бумага:").grid(row=0, column=0, sticky="w")
        self._combo(g, "paper", [PAPER_DRIVER] + list(VIRTUAL_PAPERS) + [PAPER_CUSTOM], 26).grid(row=0, column=1, sticky="w", padx=6)
        ttk.Label(g, text="Своя, мм:").grid(row=1, column=0, sticky="w", pady=(4, 0))
        cf = ttk.Frame(g)
        cf.grid(row=1, column=1, sticky="w", padx=6, pady=(4, 0))
        self._spin(cf, "paper_w", 20, 2000, 1).pack(side="left")
        ttk.Label(cf, text=" × ").pack(side="left")
        self._spin(cf, "paper_h", 20, 2000, 1).pack(side="left")
        ttk.Label(g, text="Ориентация:").grid(row=2, column=0, sticky="w", pady=(6, 0))
        of = ttk.Frame(g)
        of.grid(row=2, column=1, sticky="w", padx=6, pady=(6, 0))
        for label in PRINT_ORIENTS:
            ttk.Radiobutton(of, text=label, value=label, variable=self.v["orient"], style="Toolbutton").pack(side="left", padx=1)
        ttk.Label(g, text="Копий листа:").grid(row=3, column=0, sticky="w", pady=(6, 0))
        self._spin(g, "sheet_copies", 1, 999, 1, 6).grid(row=3, column=1, sticky="w", padx=6, pady=(6, 0))
        ttk.Label(g, text="Передача в драйвер, ppi:").grid(row=4, column=0, sticky="w", pady=(6, 0))
        self._combo(g, "ppi", PPI_CHOICES, 8).grid(row=4, column=1, sticky="w", padx=6, pady=(6, 0))
        ob = ttk.Frame(g)
        ob.grid(row=5, column=0, columnspan=2, sticky="w", pady=(6, 0))
        ttk.Checkbutton(ob, text="Каждый лист — отдельным заданием, пауза, сек:", variable=self.v["one_by_one"]).pack(side="left")
        self._spin(ob, "job_pause", 0, 60, 1, 4).pack(side="left", padx=4)
        ttk.Checkbutton(t, text="Отключить управление цветом Windows (ICM)", variable=self.v["icm_off"]).grid(row=9, column=0, columnspan=2, sticky="w", pady=(8, 0))
        ttk.Label(t, textvariable=self.v_geom, wraplength=430, foreground="#555", justify="left").grid(row=10, column=0, columnspan=2, sticky="w", pady=(8, 0))

    def _tab_layout(self, nb):
        t = ttk.Frame(nb, padding=10)
        nb.add(t, text="Раскладка")
        r = 0
        ttk.Label(t, text="Что печатать:").grid(row=r, column=0, sticky="w")
        self._combo(t, "range", RANGES, 20).grid(row=r, column=1, columnspan=3, sticky="w", padx=6)
        r += 1
        ttk.Label(t, text="Режим:").grid(row=r, column=0, sticky="w", pady=(8, 0))
        lf = ttk.Frame(t)
        lf.grid(row=r, column=1, columnspan=3, sticky="w", padx=6, pady=(8, 0))
        for label in LAYOUTS:
            ttk.Radiobutton(lf, text=label, value=label, variable=self.v["layout"], style="Toolbutton").pack(side="left", padx=1)
        r += 1
        ttk.Label(t, text="Поля листа, мм:").grid(row=r, column=0, sticky="w", pady=(8, 0))
        mf = ttk.Frame(t)
        mf.grid(row=r, column=1, columnspan=3, sticky="w", padx=6, pady=(8, 0))
        for lab, key in (("слева", "margin_l"), ("сверху", "margin_t"), ("справа", "margin_r"), ("снизу", "margin_b")):
            sub = ttk.Frame(mf)
            sub.pack(side="left", padx=(0, 6))
            ttk.Label(sub, text=lab, foreground="#666").pack()
            self._spin(sub, key, 0, 200, 1, 5).pack()
        r += 1
        ttk.Label(t, text="Расстояние между фото, мм:").grid(row=r, column=0, sticky="w", pady=(8, 0))
        self._spin(t, "gap", 0, 100, 0.5, 6).grid(row=r, column=1, sticky="w", padx=6, pady=(8, 0))
        r += 1
        ttk.Label(t, text="Выравнивание:").grid(row=r, column=0, sticky="w", pady=(6, 0))
        self._combo(t, "align", ALIGNS, 16).grid(row=r, column=1, columnspan=3, sticky="w", padx=6, pady=(6, 0))
        r += 1
        ttk.Label(t, text="Копий каждого фото ×:").grid(row=r, column=0, sticky="w", pady=(8, 0))
        self._spin(t, "copies", 1, 999, 1, 6).grid(row=r, column=1, sticky="w", padx=6, pady=(8, 0))
        r += 1
        ttk.Checkbutton(t, text="Заполнить лист копиями каждого фото", variable=self.v["fill"]).grid(row=r, column=0, columnspan=4, sticky="w", pady=(6, 0))
        r += 1
        ttk.Checkbutton(t, text="Поворачивать фото, если так помещается больше", variable=self.v["rotate_fit"]).grid(row=r, column=0, columnspan=4, sticky="w")
        r += 1
        ttk.Separator(t).grid(row=r, column=0, columnspan=4, sticky="we", pady=8)
        r += 1
        ttk.Checkbutton(t, text="Печать без полей — учитывать подрезку принтером, мм:", variable=self.v["bleed_on"]).grid(row=r, column=0, columnspan=4, sticky="w")
        r += 1
        ttk.Label(t, text="Одинаково со всех сторон:").grid(row=r, column=0, sticky="w")
        self._spin(t, "bleed", -10, 10, 0.1, 6).grid(row=r, column=1, sticky="w", padx=6)
        r += 1
        side = ttk.Frame(t)
        side.grid(row=r, column=0, columnspan=4, sticky="w", pady=(2, 0))
        for lab, key in (("Лево", "bleed_l"), ("Верх", "bleed_t"), ("Право", "bleed_r"), ("Низ", "bleed_b")):
            ttk.Label(side, text=lab).pack(side="left", padx=(0, 2))
            self._spin(side, key, -10, 10, 0.1, 6).pack(side="left", padx=(0, 10))
        r += 1
        ttk.Label(t, text="Если принтер срезает края при печати без полей — введите отрицательные значения (отступ): фото уменьшится "
                          "на эту величину со стороны, а принтер дорастит его до края. Положительные — снимок заходит за край листа "
                          "реальным содержимым. Пустое поле = «одинаково». Точное значение подбирайте по тестовой шкале.",
                  foreground="#666", wraplength=430, justify="left").grid(row=r, column=0, columnspan=4, sticky="w")
        r += 1
        ttk.Button(t, text="🧪 Тестовая шкала краёв → в список фото", command=self.add_edge_test).grid(row=r, column=0, columnspan=4, sticky="w", pady=(4, 0))
        r += 1
        ttk.Label(t, text="Рамка вокруг фото, мм:").grid(row=r, column=0, sticky="w", pady=(8, 0))
        self._spin(t, "border", 0, 50, 0.5, 5).grid(row=r, column=1, sticky="w", padx=6, pady=(8, 0))
        self._combo(t, "border_color", BORDER_COLORS, 8).grid(row=r, column=2, sticky="w", pady=(8, 0))
        r += 1
        ttk.Checkbutton(t, text="Метки реза", variable=self.v["marks"]).grid(row=r, column=0, columnspan=4, sticky="w", pady=(6, 0))
        r += 1
        ttk.Label(t, text="Подпись под фото:").grid(row=r, column=0, sticky="w", pady=(6, 0))
        self._combo(t, "caption", CAPTIONS, 20).grid(row=r, column=1, columnspan=3, sticky="w", padx=6, pady=(6, 0))

    def _tab_process(self, nb):
        t = ttk.Frame(nb, padding=10)
        nb.add(t, text="Обработка")
        ttk.Label(t, text="Применяется только к печати и сохранённым листам.", foreground="#666").grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 8))
        rows = (("Резкость, %", "sharp", 0, 500, 5), ("Радиус резкости, px (при 300 ppi)", "sharp_radius", 0.1, 10, 0.1),
                ("Порог резкости", "sharp_thr", 0, 255, 1), ("Яркость, −100…100", "bright", -100, 100, 1),
                ("Контраст, −100…100", "contrast", -100, 100, 1), ("Насыщенность, −100…100", "sat", -100, 100, 1),
                ("Гамма (средние тона)", "gamma", 0.2, 5, 0.05))
        for i, (lab, key, lo, hi, st) in enumerate(rows, start=1):
            ttk.Label(t, text=lab).grid(row=i, column=0, sticky="w", pady=3)
            self._spin(t, key, lo, hi, st, 7).grid(row=i, column=1, sticky="w", padx=8)
        ttk.Checkbutton(t, text="Чёрно-белая печать", variable=self.v["bw"]).grid(row=9, column=0, columnspan=3, sticky="w", pady=(8, 0))
        ttk.Button(t, text="Сбросить обработку", command=self._reset_process).grid(row=10, column=0, sticky="w", pady=(12, 0))

    def _tab_color(self, nb):
        t = ttk.Frame(nb, padding=10)
        nb.add(t, text="Цвет")
        ttk.Label(t, textvariable=self.v_cm, wraplength=430, justify="left").pack(anchor="w")
        ttk.Button(t, text="🎨 Настроить профиль принтера…", command=self.app.open_cm_dialog).pack(anchor="w", pady=8)
        ttk.Checkbutton(t, text="Предпросмотр с имитацией печати (по профилю)", variable=self.v["proof"]).pack(anchor="w")
        ttk.Separator(t).pack(fill="x", pady=10)
        ttk.Label(t, wraplength=430, justify="left", foreground="#555",
                  text="Если включён профиль принтера, фото переводятся в цвета принтера перед отправкой. "
                       "В свойствах драйвера тогда должно быть отключено управление цветом "
                       "(Epson: «Без цветокоррекции» / No Color Adjustment), а тип бумаги и качество — "
                       "такие же, как при печати мишени для профиля.\n\n"
                       "Если профиль не используется, цвета фото (sRGB) передаются драйверу как есть, "
                       "и цветом управляет сам драйвер."
                  ).pack(anchor="w")

    def _reset_process(self):
        for k in ("sharp", "sharp_radius", "sharp_thr", "bright", "contrast", "sat", "gamma", "bw"):
            self.v[k].set(PRINT_DEFAULTS[k])

    # ---------- принтер, драйвер, пресеты
    @property
    def printer(self):
        return self.v_printer.get().strip()

    def _load_blob(self):
        self.blob = None
        name = self.printer
        if not name:
            return
        stored = self.app.settings.get("print_devmodes", {}).get(name)
        if stored:
            try:
                b = base64.b64decode(stored)
                if devmode_valid(b):
                    self.blob = b
            except Exception:
                pass
        if self.blob is None:
            try:
                self.blob = default_devmode(name)
            except Exception:
                self.blob = None

    def _save_blob(self):
        if self.printer and self.blob:
            self.app.settings.setdefault("print_devmodes", {})[self.printer] = base64.b64encode(self.blob).decode()

    def _update_drv_text(self):
        if not self.printers:
            self.v_drv.set("Принтеры не найдены (или программа запущена не в Windows). "
                           "Доступны предпросмотр и сохранение готовых листов в файлы.")
        elif self.blob is None:
            self.v_drv.set("Не удалось получить настройки драйвера этого принтера.")
        else:
            self.v_drv.set("Откройте «Свойства принтера» и задайте тип бумаги, качество и цвет. "
                           "Настройки запоминаются для этого принтера.")

    def _reload_printers(self):
        self.printers = list_printers()
        self.cb_printer.config(values=self.printers)
        if self.printer not in self.printers:
            self.v_printer.set(self.printers[0] if self.printers else "")
        self._update_drv_text()

    def _printer_changed(self):
        self._load_blob()
        self.app.settings["print_printer"] = self.printer
        self._update_drv_text()
        self._schedule(0)

    def _props(self):
        if not self.printer or self.blob is None:
            messagebox.showinfo("Печать", "Принтер не выбран или недоступен.", parent=self.win)
            return
        try:
            new = edit_devmode_dialog(self.printer, self.blob, int(self.win.winfo_id()))
        except Exception as ex:
            messagebox.showerror("Печать", f"Не удалось открыть свойства принтера:\n{ex}", parent=self.win)
            return
        if new:
            self.blob = new
            self._save_blob()
            self._schedule(0)

    def _preset_names(self):
        return sorted(self.app.settings.get("print_presets", {}))

    def _preset_save(self):
        name = simpledialog.askstring("Пресет печати", "Название пресета:", parent=self.win)
        if not name or not name.strip():
            return
        name = name.strip()
        self.app.settings.setdefault("print_presets", {})[name] = {
            "printer": self.printer, "opts": {k: v.get() for k, v in self.v.items()},
            "devmode": base64.b64encode(self.blob).decode() if self.blob else "",
            "cm": {"on": self.app.v_cm_on.get(), "icc": self.app.v_icc.get().strip(), "intent": self.app.v_intent.get(),
                   "bpc": self.app.v_bpc.get(), "embed": self.app.v_embed.get()}}
        self.cb_preset.config(values=self._preset_names())
        self.v_preset.set(name)
        save_settings(self.app.settings)

    def _preset_load(self):
        p = self.app.settings.get("print_presets", {}).get(self.v_preset.get())
        if not p:
            return
        for k, val in p.get("opts", {}).items():
            if k in self.v:
                self.v[k].set(val)
        cm = p.get("cm")
        if cm:
            self.app.v_cm_on.set(bool(cm.get("on")))
            self.app.v_icc.set(cm.get("icc", ""))
            if cm.get("intent") in INTENTS:
                self.app.v_intent.set(cm["intent"])
            self.app.v_bpc.set(bool(cm.get("bpc", True)))
            self.app.v_embed.set(bool(cm.get("embed", False)))
        if p.get("printer") in self.printers:
            self.v_printer.set(p["printer"])
            try:
                b = base64.b64decode(p.get("devmode", ""))
                if devmode_valid(b):
                    self.blob = b
                    self._save_blob()
            except Exception:
                pass
        self._schedule(0)

    def _preset_delete(self):
        name = self.v_preset.get()
        presets = self.app.settings.get("print_presets", {})
        if name in presets and messagebox.askyesno("Печать", f"Удалить пресет «{name}»?", parent=self.win):
            del presets[name]
            self.cb_preset.config(values=self._preset_names())
            self.v_preset.set("")
            save_settings(self.app.settings)

    # ---------- раскладка и предпросмотр
    def _opts(self):
        return parse_print_opts({k: v.get() for k, v in self.v.items()})

    def _paper_dims(self, o):
        return paper_dims(o)

    def _prepare_blob(self, orient, o):
        return prepare_blob(self.printer, self.blob, orient, o)

    def _geom_for(self, orient):
        return make_geom_for(self.printer, self.blob, self.o)(orient)

    def _entries(self):
        app = self.app
        if not app.files:
            return []
        r = self.o["range"]
        if r == "current":
            fl = [app.files[app.idx]] if app.idx >= 0 else []
        elif r == "edited":
            fl = [f for f in app.files if app.states[f].edited]
        else:
            fl = [f for f in app.files if f in app.checked]        # печатаются отмеченные фото
        return [(f, app.states[f]) for f in fl]

    def _replan(self):
        app = self.app
        self.o = self._opts()
        self.mode = MODES[app.v_mode.get()]
        self.cm, self.cm_err = None, None
        if app.v_cm_on.get():
            try:
                self.cm = app._cm_build()
            except ValueError as ex:
                self.cm_err = str(ex)
        self.photos, self.skipped = build_photos(self._entries(), FORMATS[app.v_format.get()],
                                                 ORIENTS[app.v_orient.get()], self.o)
        self.plan = None
        if self.photos:
            self.plan = plan_layout(self.photos, self._geom_for, self.o)
            self.page = max(0, min(self.page, len(self.plan["sheets"]) - 1))

    def _schedule(self, delay=None):
        if self._after is not None:
            try:
                self.win.after_cancel(self._after)
            except Exception:
                pass
        self._after = self.win.after(self.PREVIEW_DELAY if delay is None else delay, self._refresh)

    def _refresh(self):
        self._after = None
        self._err = None
        try:
            self._replan()
        except Exception as ex:
            self.plan = None
            self._err = str(ex) or ex.__class__.__name__
        self._update_texts()
        try:
            self.app.redraw()
        except Exception:
            pass
        try:
            self._draw()
        except Exception as ex:
            self._err = f"Не удалось построить предпросмотр: {ex}"
            self.canvas.delete("all")
            self.canvas.create_text(30, 30, anchor="nw", fill="#ffb4a8", width=700, text=self._err)

    def _update_texts(self):
        o, plan = self.o, self.plan
        c = self.app
        if not c.v_cm_on.get():
            self.v_cm.set("Профиль принтера: выключен.")
        elif self.cm_err:
            self.v_cm.set("Профиль принтера: " + self.cm_err)
        else:
            self.v_cm.set("Профиль принтера включён: " + self.cm["name"])
        if not plan or not plan["sheets"]:
            self.v_page.set("")
            self.v_geom.set("")
            msg = self._err or ("Нет фотографий для печати. Откройте папку с фото или измените «Что печатать»."
                                if not self.photos else "Нет листов.")
            self.v_info.set(msg)
            return
        g = plan["geom"]
        n = len(plan["sheets"])
        ppi = resolve_ppi(o, g)
        ax0, ay0, ax1, ay1 = g["area"]
        self.v_page.set(f"Лист {self.page + 1} из {n}")
        self.v_geom.set(f"Бумага {g['paper'][0]:.0f}×{g['paper'][1]:.0f} мм, печатное поле {ax1 - ax0:.0f}×{ay1 - ay0:.0f} мм, "
                        f"драйвер {g['dpi'][0]}×{g['dpi'][1]} dpi, передача {ppi} ppi" + (" (условный лист)" if g.get("virtual") else ""))
        total = n * o["sheet_copies"]
        parts = [f"Фото: {len(self.photos)}", f"листов: {n}" + (f" × {o['sheet_copies']} = {total}" if o["sheet_copies"] > 1 else ""),
                 "ориентация: " + ("книжная" if plan["orient"] == "portrait" else "альбомная"),
                 f"заполнение листа: {plan['util'] * 100:.0f}%"]
        text = "  •  ".join(parts)
        if self.skipped:
            text += "\nНе удалось прочитать: " + ", ".join(self.skipped[:5])
        if plan["warnings"]:
            text += "\n⚠ " + "\n⚠ ".join(plan["warnings"][:4])
        self.v_info.set(text)

    def _nav(self, d):
        if self.plan and self.plan["sheets"]:
            self.page = max(0, min(len(self.plan["sheets"]) - 1, self.page + d))
            self._update_texts()
            self._draw()

    def _draw(self):
        c = self.canvas
        c.delete("all")
        cw, ch = max(c.winfo_width(), 100), max(c.winfo_height(), 100)
        if not self.plan or not self.plan["sheets"]:
            c.create_text(cw / 2, ch / 2, fill="#ffb4a8" if self._err else "#bbb", width=cw - 60, font=("Segoe UI", 12),
                          text=self._err or "Нет фотографий для печати")
            return
        plan = self.plan
        W, H = plan["geom"]["paper"]
        pad = 28
        pxmm = min((cw - 2 * pad) / W, (ch - 2 * pad) / H)
        ppi = max(20, min(160, pxmm * 25.4))
        sheet = compose_sheet(plan, self.page, self.photos, ppi, self.o, self.mode, fast=True, cache=self.cache)
        if self.o["proof"] and self.cm:
            try:
                sheet = proof_preview(sheet, None, self.cm)
            except Exception:
                pass
        self.tkprev = ImageTk.PhotoImage(sheet)
        ox, oy = (cw - sheet.width) // 2, (ch - sheet.height) // 2
        c.create_rectangle(ox + 4, oy + 4, ox + sheet.width + 4, oy + sheet.height + 4, fill="#222", outline="")
        c.create_image(ox, oy, anchor="nw", image=self.tkprev)
        s = sheet.width / W
        ax0, ay0, ax1, ay1 = plan["geom"]["area"]
        c.create_rectangle(ox + ax0 * s, oy + ay0 * s, ox + ax1 * s, oy + ay1 * s, outline="#2e86de", dash=(4, 3))

    # ---------- печать и экспорт
    def _animate(self, j, n, kind):
        """Лист j (с нуля) из n ушёл на печать/в файл — показать полёт листа в принтер."""
        if not self.app.settings.get("anim", True):
            return
        thumb = None
        try:
            files = self.app._checked_files()
            if files:
                f = files[j % len(files)]
                thumb = self.app.listbox.pil.get((str(f), self.app.states[f].rotation))
            self.anim.kind = kind
            self.anim.send(j + 1, n, thumb)
        except Exception:
            pass

    def _set_busy(self, busy):
        if busy:
            try:
                self.anim.reset()
            except Exception:
                pass
        self.busy = busy
        st = "disabled" if busy else "normal"
        self.btn_print.config(state=st)
        self.btn_export.config(state=st)
        self.btn_cancel.config(state="normal" if busy else "disabled")

    def _common_ctx(self):
        """Актуальная раскладка и параметры задания; None — если печатать нечего (сообщение уже показано)."""
        try:
            self._replan()
        except Exception as ex:
            messagebox.showerror("Печать", str(ex), parent=self.win)
            return None
        if not self.plan or not self.plan["sheets"]:
            messagebox.showinfo("Печать", "Нет фотографий для печати.", parent=self.win)
            return None
        if self.cm_err:
            messagebox.showerror("Печать", self.cm_err, parent=self.win)
            return None
        o, plan = self.o, self.plan
        idxs = [self.page] if o["pages"] == "current" else list(range(len(plan["sheets"])))
        return {"plan": plan, "photos": self.photos, "o": o, "mode": self.mode, "cm": self.cm,
                "ppi": resolve_ppi(o, plan["geom"]), "idxs": idxs}

    def _print(self):
        if self.busy:
            return
        ctx = self._common_ctx()
        if not ctx:
            return
        plan, o = ctx["plan"], ctx["o"]
        if not self.printer or self.blob is None:
            messagebox.showerror("Печать", "Принтер не выбран или недоступен.", parent=self.win)
            return
        if plan["geom"].get("virtual"):
            messagebox.showerror("Печать", "Драйвер не принял выбранный размер бумаги.\nВыберите «Как в драйвере принтера» "
                                 "и задайте бумагу в свойствах принтера.", parent=self.win)
            return
        total = len(ctx["idxs"]) * o["sheet_copies"]
        g = plan["geom"]
        text = (f"Принтер: {self.printer}\nБумага: {g['paper'][0]:.0f}×{g['paper'][1]:.0f} мм, "
                f"{'книжная' if plan['orient'] == 'portrait' else 'альбомная'}\nЛистов к печати: {total}\n"
                f"Фото: {len(self.photos)}\n")
        if ctx["cm"]:
            text += f"Профиль: {ctx['cm']['name']}\n"
        if plan["warnings"]:
            text += "\n⚠ " + "\n⚠ ".join(plan["warnings"][:3]) + "\n"
        if not messagebox.askyesno("Печать", text + "\nНачать печать?", parent=self.win):
            return
        try:
            ctx["blob"] = self._prepare_blob(plan["orient"], o)
        except Exception as ex:
            messagebox.showerror("Печать", f"Не удалось подготовить настройки принтера:\n{ex}", parent=self.win)
            return
        ctx.update(kind="print", printer=self.printer)
        self._start(ctx)

    def _export(self):
        if self.busy:
            return
        ctx = self._common_ctx()
        if not ctx:
            return
        app = self.app
        init = (str(app.src_dir / (app.v_outname.get().strip() or OUT_SUBDIR)) if app.v_outmode.get() == "orig" and app.src_dir
                else app.v_outdir.get().strip()) or None
        if init and not Path(init).is_dir():
            init = str(Path(init).parent) if Path(init).parent.is_dir() else None
        d = filedialog.askdirectory(title="Куда сохранить листы", initialdir=init, parent=self.win)
        if not d:
            return
        ctx.update(kind="export", dir=Path(d))
        self._start(ctx)

    def _start(self, ctx):
        self.cancel.clear()
        self._set_busy(True)
        self.progress.config(maximum=max(1, len(ctx["idxs"])), value=0)
        self.lbl_prog.config(text="Подготовка…")
        threading.Thread(target=self._worker, args=(ctx,), daemon=True).start()

    def _worker(self, c):
        try:
            res = run_sheets_job(c, lambda j, n, t: self.q.put(("progress", j, n, t)), self.cancel)
            self.q.put(("cancelled", res[1]) if res[0] == "cancelled" else ("done", res[1], res[2]))
        except Exception as ex:
            self.q.put(("error", f"{ex.__class__.__name__}: {ex}"))

    def _poll(self):
        try:
            while True:
                msg = self.q.get_nowait()
                kind = msg[0]
                if kind == "progress":
                    self.progress.config(value=msg[1])
                    self.lbl_prog.config(text=msg[3])
                    if not str(msg[3]).startswith("Готовлю"):
                        self._animate(msg[1], msg[2], "export" if str(msg[3]).startswith("Лист") else "print")
                    continue
                self._set_busy(False)
                if kind == "done":
                    self.anim.done()
                    self.progress.config(value=self.progress["maximum"])
                    if msg[2]:
                        self.lbl_prog.config(text=f"Готово: сохранено листов — {msg[1]}")
                        if messagebox.askyesno("Печать", f"Сохранено листов: {msg[1]}\nПапка: {msg[2]}\n\nОткрыть папку?", parent=self.win) \
                                and hasattr(os, "startfile"):
                            os.startfile(msg[2])
                    else:
                        self.lbl_prog.config(text=f"Отправлено на печать листов: {msg[1]}")
                        messagebox.showinfo("Печать", f"Отправлено на печать листов: {msg[1]}.\nСледите за очередью принтера.", parent=self.win)
                elif kind == "cancelled":
                    self.lbl_prog.config(text="Отменено")
                else:
                    self.lbl_prog.config(text="Ошибка")
                    messagebox.showerror("Печать", msg[1], parent=self.win)
        except queue.Empty:
            pass
        try:
            if self.win.winfo_exists():
                self.win.after(100, self._poll)
        except Exception:
            pass

    def close(self):
        if self.busy:
            if not messagebox.askyesno("Печать", "Идёт печать или сохранение. Отменить и закрыть окно?", parent=self.win):
                return
            self.cancel.set()
        self.save_state()
        self.win.destroy()
        if getattr(self.app, "print_only", False):
            try:
                self.app.root.destroy()
            except Exception:
                pass

    def save_state(self):
        self.app.settings["print"] = {k: v.get() for k, v in self.v.items()}
        self.app.settings["print_printer"] = self.printer
        self._save_blob()
        save_settings(self.app.settings)


def main():
    if len(sys.argv) > 1 and sys.argv[1] in ("agent", "mcp", "mcp-config", "mcp-install"):
        sys.exit(agent_main(sys.argv[1:]))
    if tk is None:
        sys.stderr.write("PhotoCrop: нет tkinter. Окно недоступно; режим агента: photo_crop.py agent --list\n")
        sys.exit(1)
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)  # чёткий интерфейс на 4K/масштабе 125–150 %
        except Exception:
            pass
    root = tk.Tk()
    if len(sys.argv) > 2 and sys.argv[1] == "--print-project":      # вызов из нового (Qt) интерфейса: только окно печати
        root.withdraw()
        app = App(root)
        app.print_only = True
        app.load_project_file(sys.argv[2])
        if not app.files:
            root.destroy()
            return
        app.open_print()
        try:
            app.print_dialog.win.protocol("WM_DELETE_WINDOW", app.print_dialog.close)
        except Exception:
            pass
        root.mainloop()
        return
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
