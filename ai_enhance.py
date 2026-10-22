"""ИИ-улучшатели фото: реестр моделей, скачивание с проверкой SHA-256, тайловый запуск ONNX.

Первая модель: realesr-general-x4v3 (Real-ESRGAN, BSD-3-Clause), увеличение в 4 раза.
Модули PIL/numpy нужны всегда; onnxruntime подгружается только при запуске модели.
При любой ошибке (нет модели, нехватка памяти, onnxruntime) enhance() откатывается на Lanczos.
"""
import hashlib
import json
import os
import threading
import urllib.request
from pathlib import Path

import numpy as np
from PIL import Image

APPDATA = Path(os.environ.get("APPDATA", str(Path.home())))
MODELS_DIR = APPDATA / "PhotoCrop" / "models"
CACHE_DIR = APPDATA / "PhotoCrop" / "enhance_cache"

# Манифесты моделей. ONNX сконвертирован из .pth (source_weights_sha256); файл надо загрузить в релиз models-v1.
REGISTRY = {
    "realesr-general-x4v3": {
        "title": "Real-ESRGAN general x4v3",
        "kind": "upscale",
        "scale": 4,
        "file": "realesr-general-x4v3.onnx",
        "url": "https://github.com/ildargiv/KopiTehnik-Print/releases/download/models-v1/realesr-general-x4v3.onnx",
        "sha256": "afca20f00823f46845fb34cc55d22861f000e19d13afdc7bd654789a3cda04c7",
        "size_mb": 4.9,
        "speed": "fast",
        "gpu": True,
        "license": "BSD-3-Clause",
        "license_url": "https://github.com/xinntao/Real-ESRGAN/blob/master/LICENSE",
        "source_weights_sha256": "8dc7edb9ac80ccdc30c3a5dca6616509367f05fbc184ad95b731f05bece96292",
    },
}
DEFAULT_MODEL = "realesr-general-x4v3"


class Cancelled(Exception):
    pass


def model_path(key, models_dir=None):
    return Path(models_dir or MODELS_DIR) / REGISTRY[key]["file"]


def is_installed(key, models_dir=None):
    return model_path(key, models_dir).is_file()


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def download_model(key, models_dir=None, log=print, accept_license=False):
    """Скачивает модель; без accept_license=True не качает (лицензию показывает интерфейс).
    Файл проверяется по SHA-256 из манифеста, при несовпадении удаляется."""
    m = REGISTRY[key]
    if not m["url"] or not m["sha256"]:
        raise RuntimeError(f"Модель {key}: адрес или контрольная сумма не заданы в манифесте")
    if not accept_license:
        raise PermissionError(f"Нужно принять лицензию {m['license']}: {m['license_url']}")
    dest = model_path(key, models_dir)
    if dest.is_file() and sha256_file(dest) == m["sha256"]:
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".part")
    log(f"скачиваю {m['file']} (~{m['size_mb']} МБ) …")
    urllib.request.urlretrieve(m["url"], tmp)
    got = sha256_file(tmp)
    if got != m["sha256"]:
        tmp.unlink(missing_ok=True)
        raise ValueError(f"Контрольная сумма {m['file']} не совпала: {got}")
    os.replace(tmp, dest)
    return dest


def _providers(use_gpu=True):
    import onnxruntime as ort
    av = ort.get_available_providers()
    if use_gpu and os.environ.get("PHOTOCROP_ENHANCE_GPU", "1") != "0":
        for p in ("DmlExecutionProvider", "CUDAExecutionProvider"):
            if p in av:
                return [p, "CPUExecutionProvider"]
    return ["CPUExecutionProvider"]


_sessions = {}
_lock = threading.Lock()


def _session(key, models_dir=None, use_gpu=True):
    path = model_path(key, models_dir)
    ck = (str(path), use_gpu)
    with _lock:
        if ck not in _sessions:
            import onnxruntime as ort
            so = ort.SessionOptions()
            so.log_severity_level = 3
            _sessions[ck] = ort.InferenceSession(str(path), so, providers=_providers(use_gpu))
        return _sessions[ck]


def run_tiled(infer, arr, scale, tile=128, pad=10, progress=None, cancel=None):
    """arr: float32 HxWx3 (0..1). infer(NCHW float32) -> NCHW float32 в scale раз больше.
    Плитки с перекрытием pad, края отрезаются, поэтому швов нет. Возвращает float32 (H*scale)x(W*scale)x3."""
    h, w = arr.shape[:2]
    out = np.zeros((h * scale, w * scale, 3), np.float32)
    ys, xs = list(range(0, h, tile)), list(range(0, w, tile))
    total, done = len(ys) * len(xs), 0
    for y in ys:
        for x in xs:
            if cancel is not None and cancel():
                raise Cancelled()
            y0, x0 = max(y - pad, 0), max(x - pad, 0)
            y1, x1 = min(y + tile + pad, h), min(x + tile + pad, w)
            t = np.ascontiguousarray(arr[y0:y1, x0:x1].transpose(2, 0, 1)[None])
            o = np.asarray(infer(t))[0].transpose(1, 2, 0)
            oy, ox = (y - y0) * scale, (x - x0) * scale
            hh, ww = min(tile, h - y) * scale, min(tile, w - x) * scale
            out[y * scale:y * scale + hh, x * scale:x * scale + ww] = o[oy:oy + hh, ox:ox + ww]
            done += 1
            if progress:
                progress(done / total)
    return out


def _lanczos(img, factor):
    from PIL import Image as _I
    rs = getattr(_I, "Resampling", _I).LANCZOS
    return img.resize((round(img.width * factor), round(img.height * factor)), rs)


def enhance(img, key=DEFAULT_MODEL, target_size=None, models_dir=None, use_gpu=True,
            tile=128, progress=None, cancel=None, log=None):
    """Увеличивает img моделью key. Возвращает (картинка, использована_ли_модель).
    target_size=(w, h): если задан, результат подгоняется Lanczos до этого размера (модель даёт ×scale).
    Ошибки модели не пробрасываются: откат на Lanczos. Cancelled пробрасывается."""
    m = REGISTRY[key]
    scale = m["scale"]
    img = img.convert("RGB")
    used = False
    try:
        if not is_installed(key, models_dir):
            raise FileNotFoundError(f"модель {key} не установлена")
        sess = _session(key, models_dir, use_gpu)
        name = sess.get_inputs()[0].name

        def infer(t):
            return sess.run(None, {name: t})[0]

        arr = np.asarray(img, np.float32) / 255.0
        out = run_tiled(infer, arr, scale, tile=tile, progress=progress, cancel=cancel)
        res = Image.fromarray((np.clip(out, 0, 1) * 255.0 + 0.5).astype(np.uint8))
        used = True
    except Cancelled:
        raise
    except Exception as e:                       # в т.ч. MemoryError и сбой onnxruntime
        if log:
            log(f"ИИ-увеличение недоступно ({e}); использую Lanczos")
        res = _lanczos(img, scale)
    if target_size and res.size != tuple(target_size):
        from PIL import Image as _I
        res = res.resize(tuple(target_size), getattr(_I, "Resampling", _I).LANCZOS)
    return res, used


def needed_factor(img_size, target_px):
    """Во сколько раз надо увеличить, чтобы покрыть target_px=(w,h) в пикселях печати."""
    return max(target_px[0] / img_size[0], target_px[1] / img_size[1])


def cache_key(path, key, target_size=None):
    st = os.stat(path)
    s = json.dumps([str(path), st.st_size, int(st.st_mtime), key, list(target_size or [])])
    return hashlib.sha1(s.encode()).hexdigest()
