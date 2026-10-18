# -*- coding: utf-8 -*-
"""
SmartCrop — «умное» кадрирование домашних фотографий: не отрезать людей.

Самостоятельный модуль; подключён к photo_crop.py (auto_crop method=smart) и к окну photo_crop_qt.py (вкладка «Умная рамка»). Результат работы — «решение» (словарь) в тех же
величинах, что и рамка в photo_crop (cx, cy — центр рамки в долях фото, scale — размер относительно максимально
вписанной рамки, angle, orient), плюс статус проверки и причины, по которым кадр надо посмотреть глазами.

Как работает
  1. Детекторы находят лица и людей (и питомцев). Нужны только onnxruntime + opencv + numpy; модели —
     маленькие, с открытыми лицензиями (YuNet — MIT, YOLOX — Apache-2.0): `python smart_crop.py setup`.
  2. Каждый человек разбирается на части: голова, тело, кисти, руки, ноги, стопы (простой метод — по пропорциям,
     улучшенный — по размеру головы и по скелету нейросети позы MediaPipe).
  3. По вашему порядку важности (config["priority"]) подбирается положение рамки и ориентация листа, при которых
     «цена» обрезанного минимальна. Голова защищена сильнее всего (запас вокруг неё), мелкие части режутся первыми.
  4. Для каждого кадра выносится вердикт: ok / note / check / manual и список причин. Всё, что сомнительно,
     попадает в очередь на ручную проверку; есть контактный лист с затемнением обрезанных мест.

Запуск:   python smart_crop.py --help
"""
import hashlib
import json
import math
import os
import sys
import threading
import time
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

__version__ = "0.1"

APPDATA = Path(os.environ.get("APPDATA", str(Path.home())))
MODELS_DIR = APPDATA / "PhotoCrop" / "models"
CACHE_DIR = APPDATA / "PhotoCrop" / "smartcrop_cache"

_ZOO = "https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models"
MODEL_FILES = {   # ключ: (имя файла, url, примерный размер МБ)
    "yunet": ("face_detection_yunet_2023mar.onnx", _ZOO + "/face_detection_yunet/face_detection_yunet_2023mar.onnx", 0.23),
    "yolox_s": ("yolox_s.onnx", "https://github.com/Megvii-BaseDetection/YOLOX/releases/download/0.1.1rc0/yolox_s.onnx", 36),
    # поза (скелет) для улучшенного метода: MediaPipe BlazePose, Apache-2.0, 33 точки тела на человека
    "mp_pose": ("pose_estimation_mediapipe_2023mar.onnx", _ZOO + "/pose_estimation_mediapipe/pose_estimation_mediapipe_2023mar.onnx", 5.5),
    "yolox_tiny": ("yolox_tiny.onnx", "https://github.com/Megvii-BaseDetection/YOLOX/releases/download/0.1.1rc0/yolox_tiny.onnx", 20),
}

# ------------------------------------------------------------------ настройки

TIER_LABELS = {"head": "голова", "torso": "тело", "hands": "кисти рук", "arms": "руки", "legs": "ноги",
               "feet": "стопы", "pet": "питомец", "other": "прочее"}

ALGOS = {"simple": "простой", "enhanced": "улучшенный"}

DEFAULT_CONFIG = {
    # метод: simple — части по пропорциям рамки человека, цены суммируются с весами ступеней;
    # enhanced — части считаются от размера головы (антропометрия), ступени сравниваются строго по очереди:
    # сначала голова, затем тело, кисти, руки, ноги, стопы — низшая ступень никогда не вытесняет высшую
    "algo": "simple",
    "tier_eps": 0.02,                  # улучшенный: разница ступени меньше этого — считается ничьёй (решает следующая ступень)
    # порядок важности: от самого важного к наименее важному; вложенный список — части равной важности
    "priority": ["head", "torso", "pet", "hands", "arms", "legs", "feet", "other"],
    "tier_base": 5.0,                  # во сколько раз каждая следующая ступень важнее
    "head_margin": 0.12,               # запас вокруг головы (доля размера головы)
    "body_margin": 0.02,               # запас вокруг остальных частей
    "head_exponent": 0.5,              # <1: даже маленький срез головы стоит дорого
    # сколько можно срезать, оставаясь «ок» (доля площади части)
    "accept_cut": {"head": 0.02, "torso": 0.10, "pet": 0.10, "hands": 0.25, "arms": 0.35,
                   "legs": 0.50, "feet": 0.60, "other": 1.0},
    # какой уровень проблемы даёт срез сверх допустимого: note / check / manual
    "severity": {"head": "manual", "torso": "check", "pet": "check", "hands": "check", "arms": "note",
                 "legs": "note", "feet": "note", "other": "note"},
    "escalate_cut": {"torso": 0.40, "pet": 0.40, "hands": 0.80},   # срез ≥ этого — сразу «manual»
    "background_ratio": 0.12,          # человек с площадью < 12 % от самого крупного (с лицом) — «фон» (дальний план)
    "background_factor": 0.15,         # если фоновых не игнорируем: во сколько раз они менее важны
    "ignore_background": True,         # мелких людей на заднем плане вообще не учитывать
    "portrait_fit": False,             # режим «Человек»: срезать лишнее и приблизить людей, оставив немного фона
    "portrait_margin": 0.15,           # запас фона вокруг людей (доля их размера с каждой стороны)
    "portrait_min_scale": 0.35,        # сильнее этого (доля максимальной рамки) не приближать
    "faceless_lowest": True,           # люди без видимого лица (спиной, одна часть тела): самый низкий приоритет
    "min_person_conf": 0.35, "min_face_conf": 0.60, "low_conf": 0.55,
    "many_persons": 8,                 # групповое фото — всегда посмотреть
    "max_removed_area": 0.45,          # доля фото, отрезанная рамкой, после которой кадр стоит проверить
    "min_dpi": 150,
    "max_extend": 0.30,                # для варианта «с белыми полями»: насколько рамка может выйти за фото
    "joint_weight": 0.8, "joint_band": 0.025,   # не резать «по суставам»
    "center_weight": 0.3,              # лёгкое тяготение к центру группы
}


def make_config(user=None):
    cfg = json.loads(json.dumps(DEFAULT_CONFIG))
    for k, v in (user or {}).items():
        if isinstance(v, dict) and isinstance(cfg.get(k), dict):
            cfg[k].update(v)
        else:
            cfg[k] = v
    _tier_weights(cfg)   # проверка priority
    if cfg.get("algo") not in ALGOS:
        raise ValueError(f"algo: «{cfg.get('algo')}». Допустимо: {', '.join(ALGOS)}")
    return cfg


def _tier_ranks(cfg):
    """priority -> {ступень: номер по порядку важности (0 — самая важная)}; равные ступени (вложенный список) делят номер."""
    ranks, r = {}, 0
    for item in cfg["priority"]:
        for t in (item if isinstance(item, (list, tuple)) else [item]):
            ranks[t] = r
        r += 1
    for t in TIER_LABELS:
        ranks.setdefault(t, r)
    return ranks


def _tier_weights(cfg):
    """priority -> {ступень: вес}. Неуказанные ступени считаются наименее важными."""
    ranks, r = {}, 0
    for item in cfg["priority"]:
        for t in (item if isinstance(item, (list, tuple)) else [item]):
            if t not in TIER_LABELS:
                raise ValueError(f"priority: неизвестная ступень «{t}». Допустимо: {', '.join(TIER_LABELS)}")
            ranks[t] = r
        r += 1
    for t in TIER_LABELS:
        ranks.setdefault(t, r)
    n = max(ranks.values()) + 1
    return {t: cfg["tier_base"] ** (n - 1 - k) for t, k in ranks.items()}


FORMATS_MM = {"10x15": (102, 152), "9x13": (89, 127), "13x18": (127, 178), "15x21": (152, 216),
              "20x30": (203, 305), "A5": (148, 210), "A4": (210, 297), "A3": (297, 420)}
LEVELS = {"ok": 0, "note": 1, "check": 2, "manual": 3}
LEVEL_NAMES = ("ok", "note", "check", "manual")

# ------------------------------------------------------------------ геометрия

def _area(b):
    return max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])


def _inter(a, b):
    return max(0.0, min(a[2], b[2]) - max(a[0], b[0])) * max(0.0, min(a[3], b[3]) - max(a[1], b[1]))


def _clip(b, W, H):
    return (max(0.0, b[0]), max(0.0, b[1]), min(float(W), b[2]), min(float(H), b[3]))


def _inflate(b, mx, my):
    return (b[0] - mx, b[1] - my, b[2] + mx, b[3] + my)


def _cut_frac(part, frame):
    a = _area(part)
    return 0.0 if a <= 0 else 1.0 - _inter(part, frame) / a


def paper_mm(fmt, orient):
    """fmt: ключ из FORMATS_MM, (короткая, длинная) или «10x15». Возвращает (ширина, высота) в мм."""
    if isinstance(fmt, (tuple, list)):
        s, l = min(fmt[:2]), max(fmt[:2])
    else:
        key = str(fmt).replace("×", "x").replace("х", "x").replace(" ", "")
        low = {k.lower(): v for k, v in FORMATS_MM.items()}
        if key.lower() not in low:
            raise ValueError(f"Неизвестный формат «{fmt}». Допустимо: {', '.join(FORMATS_MM)}")
        s, l = low[key.lower()]
    return (s, l) if orient == "portrait" else (l, s)


def frame_for(W, H, r, scale=1.0):
    """Размер рамки (w, h) в пикселях: как frame_geom в photo_crop — максимальная вписанная рамка × scale."""
    maxw = min(W, H * r)
    w = maxw * scale
    return w, w / r


# ------------------------------------------------------------------ модели данных

class Person:
    __slots__ = ("box", "conf", "face", "face_conf", "synthetic", "head_estimated", "kind", "keypoints",
                 "prominence", "background", "ignored", "low")

    def __init__(self, box, conf=1.0, kind="person"):
        self.box, self.conf, self.kind = tuple(float(v) for v in box), float(conf), kind
        self.face = None            # (x1,y1,x2,y2) лица
        self.face_conf = 0.0
        self.synthetic = False      # тело достроено по лицу
        self.head_estimated = False # голова оценена по рамке человека (лицо не найдено)
        self.keypoints = None       # [(x, y, conf)] ×17 (COCO), если есть поза
        self.prominence = 1.0
        self.background = False
        self.ignored = False        # мелкий дальний план: рамка его не учитывает
        self.low = False            # без видимого лица: части тела важнее только пустого места

    def to_dict(self):
        return {"box": [round(v, 1) for v in self.box], "conf": round(self.conf, 3), "kind": self.kind,
                "face": [round(v, 1) for v in self.face] if self.face else None, "face_conf": round(self.face_conf, 3),
                "synthetic": self.synthetic, "head_estimated": self.head_estimated,
                "keypoints": self.keypoints}

    @staticmethod
    def from_dict(d):
        p = Person(d["box"], d.get("conf", 1.0), d.get("kind", "person"))
        p.face = tuple(d["face"]) if d.get("face") else None
        p.face_conf = d.get("face_conf", 0.0)
        p.synthetic, p.head_estimated = d.get("synthetic", False), d.get("head_estimated", False)
        p.keypoints = d.get("keypoints")
        return p


class Detection:
    """Всё найденное на фото (координаты — пиксели фото с учётом EXIF-ориентации и поворота)."""

    def __init__(self, size, persons, backends, notes=None):
        self.size, self.persons, self.backends, self.notes = tuple(size), persons, list(backends), list(notes or [])

    def to_dict(self):
        return {"size": list(self.size), "backends": self.backends, "notes": self.notes,
                "persons": [p.to_dict() for p in self.persons]}

    @staticmethod
    def from_dict(d):
        return Detection(d["size"], [Person.from_dict(p) for p in d["persons"]], d["backends"], d.get("notes"))


class Part:
    __slots__ = ("kind", "box", "person", "weight", "exp", "inflated", "pf", "low", "lw")

    def __init__(self, kind, box, person):
        self.kind, self.box, self.person = kind, box, person
        self.weight, self.exp, self.inflated = 0.0, 1.0, box
        self.pf, self.low, self.lw = 1.0, False, 0.0


# ------------------------------------------------------------------ детекторы

def _np():
    import numpy as np
    return np


class YuNetFaces:
    """Лица: OpenCV FaceDetectorYN (YuNet, MIT, ~230 КБ)."""
    name = "yunet"

    def __init__(self, model, score=0.6, nms=0.3, max_side=1600):
        import cv2
        self.cv2, self.max_side, self.lock = cv2, max_side, threading.Lock()
        self.det = cv2.FaceDetectorYN.create(str(model), "", (320, 320), score, nms, 5000)

    def detect(self, img):
        np, W, H = _np(), img.width, img.height
        k = min(1.0, self.max_side / max(W, H))
        im = img.resize((max(1, round(W * k)), max(1, round(H * k))), Image.BILINEAR) if k < 1 else img
        bgr = np.ascontiguousarray(np.asarray(im.convert("RGB"))[:, :, ::-1])
        with self.lock:
            self.det.setInputSize((im.width, im.height))
            _, faces = self.det.detect(bgr)
        out = []
        for f in (faces if faces is not None else []):
            x, y, w, h = [float(v) / k for v in f[:4]]
            out.append({"box": (x, y, x + w, y + h), "conf": float(f[14])})
        return out


class HaarFaces:
    """Запасной вариант без моделей: каскады Хаара из opencv (хуже качеством)."""
    name = "haar"

    def __init__(self, max_side=1200):
        import cv2
        self.cv2, self.max_side, self.lock = cv2, max_side, threading.Lock()
        base = cv2.data.haarcascades
        self.cas = [cv2.CascadeClassifier(base + "haarcascade_frontalface_default.xml"),
                    cv2.CascadeClassifier(base + "haarcascade_profileface.xml")]

    def detect(self, img):
        np, cv2 = _np(), self.cv2
        k = min(1.0, self.max_side / max(img.width, img.height))
        im = img.resize((max(1, round(img.width * k)), max(1, round(img.height * k)))) if k < 1 else img
        gray = cv2.cvtColor(np.asarray(im.convert("RGB")), cv2.COLOR_RGB2GRAY)
        out = []
        with self.lock:
            for c in self.cas:
                for (x, y, w, h) in c.detectMultiScale(gray, 1.1, 6, minSize=(24, 24)):
                    out.append({"box": (x / k, y / k, (x + w) / k, (y + h) / k), "conf": 0.6})
        return _nms(out, 0.4)


USE_GPU = True      # RTX 3080: нужен пакет onnxruntime-gpu (pip install onnxruntime-gpu); иначе тихо работает CPU


def _providers():
    """CUDA, если доступна и разрешена; иначе CPU. Переменная PHOTOCROP_SMART_GPU=0 отключает GPU."""
    import os
    import onnxruntime as ort
    av = ort.get_available_providers()
    if USE_GPU and os.environ.get("PHOTOCROP_SMART_GPU", "1") != "0" and "CUDAExecutionProvider" in av:
        return ["CUDAExecutionProvider", "CPUExecutionProvider"]
    return ["CPUExecutionProvider"]


class YoloXDetector:
    """Люди и питомцы: YOLOX (Apache-2.0), COCO-классы person / cat / dog."""
    name = "yolox"
    CLASSES = {0: "person", 15: "pet", 16: "pet"}

    def __init__(self, model, score=0.30, nms=0.45):
        import onnxruntime as ort
        so = ort.SessionOptions()
        so.log_severity_level = 3
        self.sess = ort.InferenceSession(str(model), so, providers=_providers())
        inp = self.sess.get_inputs()[0]
        self.input_name = inp.name
        h, w = inp.shape[2], inp.shape[3]
        self.size = (h if isinstance(h, int) else 640, w if isinstance(w, int) else 640)
        self.score, self.nms = score, nms

    def detect(self, img):
        np, cv2 = _np(), None
        import cv2
        H, W = img.height, img.width
        th, tw = self.size
        r = min(th / H, tw / W)
        nw, nh = max(1, int(W * r)), max(1, int(H * r))
        canvas = np.full((th, tw, 3), 114, dtype=np.float32)
        rs = np.asarray(img.convert("RGB").resize((nw, nh), Image.BILINEAR), dtype=np.float32)[:, :, ::-1]   # BGR
        canvas[:nh, :nw] = rs
        out = self.sess.run(None, {self.input_name: canvas.transpose(2, 0, 1)[None].copy()})[0][0]
        grids, strides = [], []
        for s in (8, 16, 32):
            gh, gw = th // s, tw // s
            xv, yv = np.meshgrid(np.arange(gw), np.arange(gh))
            grids.append(np.stack((xv, yv), 2).reshape(-1, 2))
            strides.append(np.full((gh * gw, 1), s))
        grids, strides = np.concatenate(grids), np.concatenate(strides)
        out = out.copy()
        out[:, :2] = (out[:, :2] + grids) * strides
        out[:, 2:4] = np.exp(out[:, 2:4]) * strides
        cls = out[:, 5:]
        res = []
        for cid, kind in self.CLASSES.items():
            sc = out[:, 4] * cls[:, cid]
            idx = np.where(sc >= self.score)[0]
            if len(idx) == 0:
                continue
            bx = []
            for i in idx:
                cx, cy, w, h = out[i, :4]
                bx.append([float(cx - w / 2), float(cy - h / 2), float(w), float(h)])
            keep = cv2.dnn.NMSBoxes(bx, [float(sc[i]) for i in idx], self.score, self.nms)
            for k in np.array(keep).reshape(-1):
                x, y, w, h = bx[int(k)]
                box = _clip((x / r, y / r, (x + w) / r, (y + h) / r), W, H)
                if _area(box) > 4:
                    res.append({"box": box, "conf": float(sc[idx[int(k)]]), "kind": kind})
        return res


# BlazePose-33 -> COCO-17 (первые 17 точек) + дополнительные: пальцы кистей и пятки/носки стоп
_BP_TO_COCO = (0, 2, 5, 7, 8, 11, 12, 13, 14, 15, 16, 23, 24, 25, 26, 27, 28)
_BP_EXTRA = (17, 18, 19, 20, 21, 22, 29, 30, 31, 32)     # мизинцы L/R, указательные L/R, большие L/R, пятки L/R, носки L/R
KP_FINGERS = (17, 18, 19, 20, 21, 22)                      # индексы в итоговом списке из 27 точек
KP_FEET = (23, 24, 25, 26)


class MediaPipePose:
    """Нейросеть позы (сверху вниз): по рамке человека от YOLOX находит 33 точки тела — плечи, локти, запястья, пальцы,
    бёдра, колени, лодыжки, пятки, носки. Из них собираются настоящие рамки рук, кистей, ног и стоп.
    Модель: MediaPipe BlazePose (full), ONNX из opencv_zoo, Apache-2.0, около 5,5 МБ. Возвращает 27 точек (x, y, видимость):
    первые 17 — COCO, дальше пальцы (6) и пятки/носки (4)."""
    name = "mp-pose"

    def __init__(self, model, min_presence=0.35):
        import onnxruntime as ort
        self.sess = ort.InferenceSession(str(model), providers=_providers())
        self.input_name = self.sess.get_inputs()[0].name
        self.min_presence = min_presence
        self.lock = threading.Lock()

    @staticmethod
    def _sig(v):
        np = _np()
        return 1.0 / (1.0 + np.exp(-v))

    def estimate(self, img, box):
        """img — PIL RGB, box — (x1,y1,x2,y2) в пикселях img. -> [(x, y, видимость)] ×27 или None."""
        np = _np()
        import cv2
        x1, y1, x2, y2 = box
        w, h = x2 - x1, y2 - y1
        if w < 8 or h < 8:
            return None
        side = max(w, h) * 1.25
        cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
        s = 256.0 / side
        M = np.array([[s, 0, 128 - s * cx], [0, s, 128 - s * cy]], dtype=np.float32)
        crop = cv2.warpAffine(np.asarray(img.convert("RGB")), M, (256, 256), flags=cv2.INTER_LINEAR, borderValue=(0, 0, 0))
        blob = (crop.astype(np.float32) / 255.0)[None]
        with self.lock:
            out = self.sess.run(None, {self.input_name: blob})
        lm = np.asarray(out[0]).reshape(-1, 5)[:33]
        flag = float(np.asarray(out[1]).reshape(-1)[0])
        if flag > 1.0 or flag < 0.0:
            flag = float(self._sig(flag))
        if flag < self.min_presence:
            return None
        # «видимость» сети — логит; сдвиг на 1,5 делает порог честнее: у выдуманных (за кадром) суставов логит около 0–0,6
        vis = self._sig(lm[:, 3] - 1.5)
        xs = (lm[:, 0] - 128.0) / s + cx
        ys = (lm[:, 1] - 128.0) / s + cy
        order = _BP_TO_COCO + _BP_EXTRA
        return [(float(xs[i]), float(ys[i]), float(vis[i])) for i in order]


class YoloPoseDetector:
    """НЕОБЯЗАТЕЛЬНО (пока без проверки на реальной модели): YOLO-pose в формате Ultralytics ONNX [1, 56, N]
    даёт 17 ключевых точек — части тела определяются точнее, чем по пропорциям. Лицензия моделей Ultralytics — AGPL."""
    name = "yolo-pose"

    def __init__(self, model, score=0.3, nms=0.45):
        import onnxruntime as ort
        self.sess = ort.InferenceSession(str(model), providers=_providers())
        inp = self.sess.get_inputs()[0]
        self.input_name = inp.name
        h, w = inp.shape[2], inp.shape[3]
        self.size = (h if isinstance(h, int) else 640, w if isinstance(w, int) else 640)
        self.score, self.nms = score, nms

    def detect(self, img):
        np = _np()
        import cv2
        H, W = img.height, img.width
        th, tw = self.size
        r = min(th / H, tw / W)
        nw, nh = max(1, int(W * r)), max(1, int(H * r))
        canvas = np.full((th, tw, 3), 114, dtype=np.float32)
        canvas[:nh, :nw] = np.asarray(img.convert("RGB").resize((nw, nh), Image.BILINEAR), dtype=np.float32)
        out = self.sess.run(None, {self.input_name: (canvas / 255.0).transpose(2, 0, 1)[None].astype(np.float32)})[0]
        return decode_yolo_pose(out, r, W, H, self.score, self.nms)


def decode_yolo_pose(out, r, W, H, score=0.3, nms=0.45):
    """out: массив [1, 56, N] или [1, N, 56]; r — масштаб letterbox."""
    np = _np()
    import cv2
    o = np.asarray(out)[0]
    if o.shape[0] == 56 and o.shape[1] != 56:
        o = o.T                                   # -> [N, 56]
    sel = o[o[:, 4] >= score]
    if len(sel) == 0:
        return []
    bx = [[float(a[0] - a[2] / 2), float(a[1] - a[3] / 2), float(a[2]), float(a[3])] for a in sel]
    keep = cv2.dnn.NMSBoxes(bx, [float(a[4]) for a in sel], score, nms)
    res = []
    for k in np.array(keep).reshape(-1):
        a = sel[int(k)]
        x, y, w, h = bx[int(k)]
        kp = [(float(a[5 + 3 * i] / r), float(a[6 + 3 * i] / r), float(a[7 + 3 * i])) for i in range(17)]
        res.append({"box": _clip((x / r, y / r, (x + w) / r, (y + h) / r), W, H), "conf": float(a[4]),
                    "kind": "person", "keypoints": kp})
    return res


def _nms(items, thr):
    items = sorted(items, key=lambda d: -d["conf"])
    keep = []
    for d in items:
        if all(_inter(d["box"], k["box"]) / max(1e-6, min(_area(d["box"]), _area(k["box"]))) < thr for k in keep):
            keep.append(d)
    return keep


# ------------------------------------------------------------------ сборка людей из находок

def assemble(faces, people, W, H, cfg):
    """Лица + рамки людей (+ питомцы) -> список Person. Лицо без тела порождает «синтетического» человека."""
    persons = []
    for d in people:
        if d["conf"] < cfg["min_person_conf"] and d.get("kind", "person") == "person":
            continue
        p = Person(d["box"], d["conf"], d.get("kind", "person"))
        p.keypoints = d.get("keypoints")
        persons.append(p)
    humans = [p for p in persons if p.kind == "person"]
    for f in sorted(faces, key=lambda d: -_area(d["box"])):
        if f["conf"] < cfg["min_face_conf"]:
            continue
        fx, fy = (f["box"][0] + f["box"][2]) / 2, (f["box"][1] + f["box"][3]) / 2
        cand = [p for p in humans if p.box[0] <= fx <= p.box[2] and p.box[1] <= fy <= p.box[1] + 0.6 * (p.box[3] - p.box[1])
                and p.face is None]
        if cand:
            p = min(cand, key=lambda q: _area(q.box))
            p.face, p.face_conf = f["box"], f["conf"]
            continue
        fw, fh = f["box"][2] - f["box"][0], f["box"][3] - f["box"][1]
        head_top = f["box"][1] - 0.6 * fh
        box = _clip((fx - 1.6 * fw, head_top, fx + 1.6 * fw, head_top + 7.0 * (fh * 1.6)), W, H)
        p = Person(box, f["conf"] * 0.8)
        p.face, p.face_conf, p.synthetic = f["box"], f["conf"], True
        humans.append(p)
        persons.append(p)
    for p in humans:
        if p.face is None:
            p.head_estimated = True
    classify_people(persons, cfg)
    return persons


def classify_people(persons, cfg):
    """Значимость людей. Эталон размера — самый крупный человек С ЛИЦОМ (если лиц нет — самый крупный вообще).
    Мелкие (дальний план) помечаются background и, если включено, ignored (в расчёт не берутся).
    Люди без лица (спиной, в кадр попала лишь часть тела) получают low — наинизший приоритет,
    но только когда в кадре есть хоть один человек с лицом. Вызывается при каждом решении, поэтому
    изменение настроек действует без повторного поиска людей."""
    humans = [p for p in persons if p.kind == "person"]
    faced = [p for p in humans if p.face is not None]
    ref = max([_area(p.box) for p in (faced or humans)] or [1.0]) or 1.0
    for p in humans:
        a = _area(p.box) / ref
        p.prominence = max(0.1, min(1.0, math.sqrt(a)))
        p.background = a < cfg["background_ratio"] and p is not max(faced or humans, key=lambda q: _area(q.box))
        p.ignored = bool(cfg.get("ignore_background", True) and p.background)
        p.low = bool(cfg.get("faceless_lowest", True) and faced and p.face is None and not p.ignored)
    for p in persons:
        if p.kind != "person":
            p.prominence, p.background, p.ignored, p.low = 0.8, False, False, False
    return persons


# ------------------------------------------------------------------ части тела

def _head_box(p):
    if p.face:
        x1, y1, x2, y2 = p.face
        fw, fh = x2 - x1, y2 - y1
        return (x1 - 0.25 * fw, y1 - 0.6 * fh, x2 + 0.25 * fw, y2 + 0.2 * fh)
    x1, y1, x2, y2 = p.box
    pw, ph = x2 - x1, y2 - y1
    hh = max(ph * 0.12, min(ph * 0.30, pw * 0.55))
    hw = hh * 0.85
    cx = (x1 + x2) / 2
    return (cx - hw / 2, y1, cx + hw / 2, y1 + hh)


def person_parts(p, algo="simple"):
    """Части человека по рамке и лицу (антропометрические пропорции) или по ключевым точкам, если они есть.
    algo=enhanced: при найденном лице части считаются от размера головы (см. person_parts_enh)."""
    if p.kind != "person":
        return [Part("pet", p.box, p)]
    if p.keypoints and algo == "enhanced":
        parts = parts_from_keypoints(p.keypoints, p)
        if parts:
            return parts
    if algo == "enhanced" and p.face:
        parts = person_parts_enh(p)
        if parts:
            return parts
    x1, y1, x2, y2 = p.box
    pw, ph = x2 - x1, y2 - y1
    head = _head_box(p)
    hh = head[3] - head[1]
    neck = head[3] - 0.15 * hh
    standing = ph / max(pw, 1e-6) > 1.9
    parts = [Part("head", head, p)]
    torso_y2 = y1 + (0.55 if standing else 1.0) * ph
    parts.append(Part("torso", (x1 + 0.18 * pw, neck, x2 - 0.18 * pw, torso_y2), p))
    hand_y1, hand_y2 = (y1 + 0.42 * ph, y1 + 0.58 * ph) if standing else (y1 + 0.62 * ph, y2)
    for sx1, sx2 in ((x1, x1 + 0.22 * pw), (x2 - 0.22 * pw, x2)):
        parts.append(Part("arms", (sx1, neck + 0.05 * ph, sx2, hand_y1), p))
        parts.append(Part("hands", (sx1, hand_y1, sx2, hand_y2), p))
    if standing:
        parts.append(Part("legs", (x1 + 0.15 * pw, y1 + 0.5 * ph, x2 - 0.15 * pw, y2 - 0.07 * ph), p))
        parts.append(Part("feet", (x1 + 0.1 * pw, y2 - 0.07 * ph, x2 - 0.1 * pw, y2), p))
    return [q for q in parts if _area(q.box) > 1]


def _enh_geometry(p):
    """Опорные величины улучшенного метода: u — высота головы; t(k) -> y на k «головах» ниже макушки; центр тела cx."""
    x1, y1, x2, y2 = p.box
    head = _head_box(p)
    fh = p.face[3] - p.face[1]
    u = 1.35 * fh                               # высота головы по высоте лица (рамка головы для защиты шире — с волосами и запасом)
    if u < 4:
        return None
    top = p.face[1] - 0.4 * fh                  # макушка
    ph = y2 - top
    full = ph >= 5.2 * u                        # человек виден почти целиком: подгоняем рост (дети — крупная голова)
    k = min(1.0, max(0.72, ph / (7.5 * u))) if full else 1.0
    cx = 0.65 * (head[0] + head[2]) / 2 + 0.35 * (x1 + x2) / 2
    return {"head": head, "u": u, "k": k, "top": top, "cx": cx, "y2": y2, "box": p.box,
            "Y": (lambda t: min(y2, top + k * t * u))}


def sanity_pose(kp, p):
    """Сеть позы «достраивает» тело, которого нет в кадре (портрет по пояс: бёдра и колени ставятся на живот).
    Если лицо найдено, нижние суставы, оказавшиеся выше, чем возможно по росту (в «головах» от макушки), считаются невидимыми.
    Возвращает новый список точек и признак «нижняя часть тела обрезана кадром»."""
    if not p.face or not kp:
        return kp, False
    fh = p.face[3] - p.face[1]
    u, top = 1.35 * fh, p.face[1] - 0.4 * fh
    if u < 4:
        return kp, False
    # минимальная глубина сустава ниже макушки, в высотах головы (у взрослого пах ≈ 3,8, колено ≈ 5,4, лодыжка ≈ 6,9; с запасом на детей и позу)
    need = {11: 2.3, 12: 2.3, 13: 3.6, 14: 3.6, 15: 4.8, 16: 4.8, 23: 4.8, 24: 4.8, 25: 4.8, 26: 4.8}
    # плечи должны быть найдены уверенно и иметь разумную ширину относительно головы; иначе (крупный план лица, закрытое тело) скелету не верим
    if len(kp) > 6:
        if min(kp[5][2], kp[6][2]) < 0.5:
            return None, False
        span = math.hypot(kp[5][0] - kp[6][0], kp[5][1] - kp[6][1])
        if not (0.6 * u <= span <= 3.6 * u):
            return None, False
    out, cut = list(kp), False
    for i, t in need.items():
        if i < len(out) and out[i][2] > 0 and (out[i][1] - top) < t * u:
            out[i] = (out[i][0], out[i][1], 0.0)
            cut = cut or i in (11, 12)
    return out, cut


def person_parts_enh(p):
    """Улучшенные части: размеры тела выводятся из размера головы (рост ≈ 7,5 голов), рамка человека ограничивает их
    сверху/по бокам (поднятые и раскинутые руки) и снизу (сидит, обрезан по пояс)."""
    g = _enh_geometry(p)
    if g is None:
        return None
    head, u, cx, Y, y2 = g["head"], g["u"], g["cx"], g["Y"], g["y2"]
    x1, y1, x2, y2b = p.box
    top = g["top"]
    parts = [Part("head", head, p)]
    neck = top + 0.85 * u
    parts.append(Part("torso", (cx - 0.85 * u, neck, cx + 0.85 * u, Y(3.8)), p))
    raised = y1 < top - 0.3 * u
    for sgn in (-1, 1):
        inner = cx + sgn * 0.85 * u
        outer_default = cx + sgn * 1.35 * u
        edge = x1 if sgn < 0 else x2
        extra = ((cx - 1.35 * u) - x1) if sgn < 0 else (x2 - (cx + 1.35 * u))      # насколько рамка человека шире обычных рук
        outer = edge if extra > 0.3 * u else outer_default
        lo, hi = min(inner, outer), max(inner, outer)
        if extra > 0.3 * u and raised:                       # рука поднята: рука — от плеча вверх, кисть — наверху рамки
            parts.append(Part("arms", (lo, y1, hi, Y(1.3)), p))
            hx = (edge, y1, edge + sgn * 1.0 * u, y1 + 1.0 * u)
            parts.append(Part("hands", (min(hx[0], hx[2]), hx[1], max(hx[0], hx[2]), hx[3]), p))
        elif extra > 1.0 * u:                                # раскинута в сторону
            parts.append(Part("arms", (lo, Y(1.1), hi, Y(2.6)), p))
            hx = (edge, Y(1.2), edge + sgn * 1.0 * u, Y(2.4))
            parts.append(Part("hands", (min(hx[0], hx[2]), hx[1], max(hx[0], hx[2]), hx[3]), p))
        else:                                                # руки вдоль тела
            parts.append(Part("arms", (lo, Y(1.2), hi, Y(3.0)), p))
            parts.append(Part("hands", (lo - 0.1 * u, Y(3.0), hi + 0.1 * u, Y(4.0)), p))
    if y2b >= Y(3.8) + 1.0 * u:                              # ноги видны
        parts.append(Part("legs", (cx - 0.65 * u, Y(3.8), cx + 0.65 * u, Y(6.9)), p))
        parts.append(Part("feet", (cx - 0.75 * u, Y(6.9), cx + 0.75 * u, Y(7.5)), p))
    out = []
    for q in parts:
        b = (q.box[0], q.box[1], q.box[2], min(q.box[3], y2b))
        if _area(b) > 1:
            q.box = b
            out.append(q)
    return out


def parts_from_keypoints(kp, p, thr=0.3):
    """COCO-17: 0 нос, 1-2 глаза, 3-4 уши, 5-6 плечи, 7-8 локти, 9-10 запястья, 11-12 бёдра, 13-14 колени, 15-16 лодыжки."""
    ok = lambda i: kp[i][2] >= thr
    pt = lambda i: (kp[i][0], kp[i][1])
    parts = []

    def seg_box(a, b, thick, ext=0.0):
        (ax, ay), (bx, by) = pt(a), pt(b)
        L = math.hypot(bx - ax, by - ay)
        if L < 1:
            return None
        dx, dy = (bx - ax) / L, (by - ay) / L
        bx, by = bx + dx * ext * L, by + dy * ext * L
        t = max(thick * L, 4)
        return (min(ax, bx) - t / 2, min(ay, by) - t / 2, max(ax, bx) + t / 2, max(ay, by) + t / 2)

    face_pts = [i for i in range(5) if ok(i)]
    if face_pts or p.face:
        head = _head_box(p) if p.face else None
        if head is None:
            xs, ys = [kp[i][0] for i in face_pts], [kp[i][1] for i in face_pts]
            w = max(max(xs) - min(xs), 1) * 1.9 if len(face_pts) > 1 else 40
            h = w * 1.3
            cx, cy = sum(xs) / len(xs), sum(ys) / len(ys)
            head = (cx - w / 2, cy - h * 0.55, cx + w / 2, cy + h * 0.45)
        parts.append(Part("head", head, p))
    tpts = [pt(i) for i in (5, 6, 11, 12) if ok(i)]
    if len(tpts) >= 2:
        xs, ys = [q[0] for q in tpts], [q[1] for q in tpts]
        y_bot = max(ys) if len(tpts) > 2 else max(ys) + 0.6 * (max(xs) - min(xs))
        if not (ok(11) or ok(12)) and p.face:                    # бёдер в кадре нет: тело тянется вниз до края рамки человека (не дальше роста)
            fh = p.face[3] - p.face[1]
            y_bot = max(y_bot, min(p.box[3], p.face[1] - 0.4 * fh + 3.8 * 1.35 * fh))
        parts.append(Part("torso", (min(xs), min(ys), max(xs), y_bot), p))
    n = len(kp)
    ext = lambda i: i < n and kp[i][2] >= thr                  # дополнительные точки: пальцы (17–22), пятки/носки (23–26)
    ph_ = max(p.box[3] - p.box[1], 1.0)

    def bbox(idx, pad, min_side):
        xs, ys = [kp[i][0] for i in idx], [kp[i][1] for i in idx]
        w, h = max(xs) - min(xs), max(ys) - min(ys)
        side = max(w, h, min_side)
        cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
        return (cx - side / 2 - pad, cy - side / 2 - pad, cx + side / 2 + pad, cy + side / 2 + pad)

    for sh, el, wr, fing in ((5, 7, 9, (17, 19, 21)), (6, 8, 10, (18, 20, 22))):
        if ok(sh) and ok(el):
            b = seg_box(sh, el, 0.35)
            if b:
                parts.append(Part("arms", b, p))
        fore = math.hypot(kp[wr][0] - kp[el][0], kp[wr][1] - kp[el][1]) if (ok(el) and ok(wr)) else 0.0
        if ok(el) and ok(wr):
            b = seg_box(el, wr, 0.3)
            if b:
                parts.append(Part("arms", b, p))
        if ok(wr):                                              # кисть: по пальцам, если они найдены, иначе по длине предплечья
            idx = [wr] + [i for i in fing if ext(i)]
            min_side = max(0.45 * fore, 0.035 * ph_, 6.0)
            parts.append(Part("hands", bbox(idx, 0.12 * min_side, min_side), p))
    for hp, kn, an, heel, toe in ((11, 13, 15, 23, 25), (12, 14, 16, 24, 26)):
        if ok(hp) and ok(kn):
            b = seg_box(hp, kn, 0.3)
            if b:
                parts.append(Part("legs", b, p))
        shin = math.hypot(kp[an][0] - kp[kn][0], kp[an][1] - kp[kn][1]) if (ok(kn) and ok(an)) else 0.0
        if ok(kn) and ok(an):
            b = seg_box(kn, an, 0.3)
            if b:
                parts.append(Part("legs", b, p))
        if ok(an):                                              # стопа: лодыжка + пятка + носок
            idx = [an] + [i for i in (heel, toe) if ext(i)]
            if len(idx) > 1:
                parts.append(Part("feet", bbox(idx, 0.06 * ph_, max(0.04 * ph_, 6.0)), p))
            else:
                ax, ay = pt(an)
                sz = max(0.5 * shin, 0.05 * ph_, 6.0)
                parts.append(Part("feet", (ax - sz / 2, ay - sz * 0.25, ax + sz / 2, ay + sz * 0.75), p))
    return [q for q in parts if _area(q.box) > 1]


def joint_lines(p, algo="simple"):
    """Горизонтальные «суставные» линии (y), по которым не стоит резать, и их x-диапазон."""
    x1, y1, x2, y2 = p.box
    ph, pw = y2 - y1, x2 - x1
    if p.kind != "person":
        return []
    if algo == "enhanced" and p.keypoints:
        kp = p.keypoints
        ys = []
        ok = lambda i: kp[i][2] >= 0.3
        if ok(5) and ok(6):
            ys.append((kp[5][1] + kp[6][1]) / 2)                                 # плечи/шея
        for ia, ib in ((11, 12), (13, 14), (15, 16)):                            # бёдра, колени, лодыжки
            v = [kp[i][1] for i in (ia, ib) if ok(i)]
            if v:
                ys.append(sum(v) / len(v))
        if ys:
            return [(y, x1, x2) for y in ys if y1 < y < y2 - 2]
    if algo == "enhanced" and p.face and not p.keypoints:
        g = _enh_geometry(p)
        if g:
            Y, u, cx = g["Y"], g["u"], g["cx"]
            lines = [Y(0.9), Y(3.8), Y(5.4), Y(6.9)]          # шея, пах, колени, лодыжки
            return [(y, cx - 1.4 * u, cx + 1.4 * u) for y in lines if y < y2 - 2]
    head = _head_box(p)
    lines = [head[3]]                                     # шея
    if ph / max(pw, 1e-6) > 1.9:
        lines += [y1 + 0.5 * ph, y1 + 0.74 * ph, y2 - 0.06 * ph]   # талия/бёдра, колени, лодыжки
    return [(y, x1, x2) for y in lines]


# ------------------------------------------------------------------ подбор рамки

def _prepare_parts(persons, W, H, cfg):
    tw = _tier_weights(cfg)
    twmax = max(tw.values()) or 1.0
    parts = []
    for p in persons:
        if p.ignored:                       # мелкий дальний план — не учитываем совсем
            continue
        for part in person_parts(p, cfg.get("algo", "simple")):
            part.box = _clip(part.box, W, H)
            if _area(part.box) <= 1:
                continue
            f = p.prominence * (cfg["background_factor"] if p.background else 1.0)
            part.pf = f
            part.low = p.low
            part.weight = tw[part.kind] * f
            part.lw = tw[part.kind] / twmax * f          # вес внутри «нижней» ступени (улучшенный метод)
            part.exp = cfg["head_exponent"] if part.kind == "head" else 1.0
            m = cfg["head_margin"] if part.kind == "head" else cfg["body_margin"]
            bw, bh = part.box[2] - part.box[0], part.box[3] - part.box[1]
            part.inflated = _inflate(part.box, m * bw, m * bh)
            parts.append(part)
    normal = [q.weight for q in parts if not q.low]
    if normal:                              # простой метод: любая часть безлицего дешевле самой дешёвой части остальных
        wmin = min(normal)
        for q in parts:
            if q.low:
                q.weight = 0.5 * wmin * q.lw
    return parts


def _subject_box(parts):
    """Объединённая рамка защищаемых частей (без людей «наинизшего приоритета»)."""
    main = [q for q in parts if not q.low] or parts
    if not main:
        return None
    return (min(q.inflated[0] for q in main), min(q.inflated[1] for q in main),
            max(q.inflated[2] for q in main), max(q.inflated[3] for q in main))


def _portrait_scale(subject, W, H, r, paper, cfg):
    """Режим «Человек»: масштаб рамки (доля от максимальной вписанной), при котором люди с запасом фона занимают кадр.
    Не меньше portrait_min_scale и не ниже min_dpi; если люди не помещаются — 1 (весь кадр)."""
    maxw = min(W, H * r)
    m = max(0.0, cfg.get("portrait_margin", 0.15))
    sw, sh = (subject[2] - subject[0]) * (1 + 2 * m), (subject[3] - subject[1]) * (1 + 2 * m)
    need = max(sw, sh * r) / maxw
    s_dpi = (paper[0] / 25.4 * cfg["min_dpi"]) / maxw
    return max(0.05, min(1.0, max(need, cfg.get("portrait_min_scale", 0.35), s_dpi)))


def _frame_cost(F, parts, joints, W, H, cfg, centroid, fw, fh):
    cost = 0.0
    for part in parts:
        a = _area(part.inflated)
        if a <= 0:
            continue
        cut = 1.0 - _inter(part.inflated, F) / a
        if cut > 1e-6:
            cost += part.weight * (cut ** part.exp)
    band = cfg["joint_band"] * fh
    for (y, x1, x2, w) in joints:
        if F[2] < x1 or F[0] > x2:
            continue
        for e in (F[1], F[3]):
            if 0.5 < e < H - 0.5 and abs(e - y) < band:
                cost += cfg["joint_weight"] * w
    if centroid is not None:
        cost += cfg["center_weight"] * (math.hypot((F[0] + F[2]) / 2 - centroid[0], (F[1] + F[3]) / 2 - centroid[1]) / max(fw, fh))
    return cost


def _frame_key(F, parts, joints, W, H, cfg, centroid, fw, fh, ranks, n):
    """Улучшенный метод: кортеж для лексикографического сравнения — сначала срез самой важной ступени (с допуском
    tier_eps), затем следующей и т. д.; последним идёт мелкий довесок (суставы, тяготение к центру группы)."""
    tiers = [0.0] * (n + 1)                 # последняя ступень — люди без видимого лица (наинизший приоритет)
    for part in parts:
        a = _area(part.inflated)
        if a <= 0:
            continue
        cut = 1.0 - _inter(part.inflated, F) / a
        if cut > 1e-6:
            if part.low:
                tiers[n] += part.lw * (cut ** part.exp)
            else:
                tiers[ranks[part.kind]] += part.pf * (cut ** part.exp)
    eps = max(1e-4, cfg.get("tier_eps", 0.02))
    extra = 0.0
    band = cfg["joint_band"] * fh
    for (y, x1, x2, w) in joints:
        if F[2] < x1 or F[0] > x2:
            continue
        for e in (F[1], F[3]):
            if 0.5 < e < H - 0.5 and abs(e - y) < band:
                extra += cfg["joint_weight"] * w
    if centroid is not None:
        extra += cfg["center_weight"] * (math.hypot((F[0] + F[2]) / 2 - centroid[0], (F[1] + F[3]) / 2 - centroid[1]) / max(fw, fh))
    return tuple(int(v / eps + 0.5) for v in tiers) + (extra,)


def _saliency_center(img):
    """Запасной вариант без людей: центр масс контрастных деталей (доли)."""
    from PIL import ImageFilter
    g = img.convert("L")
    g.thumbnail((200, 200))
    e = g.filter(ImageFilter.FIND_EDGES).resize((32, 32))
    px = list(e.tobytes())
    ws = sum(v * v for v in px) or 1.0
    return (sum((i % 32 + 0.5) / 32 * v * v for i, v in enumerate(px)) / ws,
            sum((i // 32 + 0.5) / 32 * v * v for i, v in enumerate(px)) / ws)


def _search(parts, joints, W, H, r, cfg, scale=1.0, centroid=None, focus=None):
    """Лучшая рамка заданного масштаба: перебор вдоль свободной оси (+ точки выравнивания по краям частей)."""
    fw, fh = frame_for(W, H, r, scale)
    xr = (fw / 2, W - fw / 2) if fw <= W else (W / 2, W / 2)
    yr = (fh / 2, H - fh / 2) if fh <= H else (H / 2, H / 2)
    if scale > 1.0:                                   # с выходом за фото: центр свободен по обеим осям
        xr, yr = (min(W / 2, fw / 2 - 0.0), W / 2), (H / 2, H / 2)
    xs = _axis_candidates(xr, fw, [(p.inflated[0], p.inflated[2]) for p in parts])
    ys = _axis_candidates(yr, fh, [(p.inflated[1], p.inflated[3]) for p in parts])
    wj = [(y, x1, x2, cfg_w) for (y, x1, x2, cfg_w) in joints]
    enhanced = cfg.get("algo") == "enhanced"
    if enhanced:
        ranks = _tier_ranks(cfg)
        nt = max(ranks.values()) + 1
    best = None
    for cx in xs:
        for cy in ys:
            F = (cx - fw / 2, cy - fh / 2, cx + fw / 2, cy + fh / 2)
            if enhanced:
                c = _frame_key(F, parts, wj, W, H, cfg, centroid, fw, fh, ranks, nt)
                if focus is not None:
                    c = c[:-1] + (c[-1] + 0.01 * math.hypot(cx - focus[0], cy - focus[1]) / max(fw, fh),)
                if best is None or c[:-1] < best[0][:-1] or (c[:-1] == best[0][:-1] and c[-1] < best[0][-1] - 1e-9):
                    best = (c, F)
                continue
            c = _frame_cost(F, parts, wj, W, H, cfg, centroid, fw, fh)
            if focus is not None:
                c += 0.01 * math.hypot(cx - focus[0], cy - focus[1]) / max(fw, fh)
            if best is None or c < best[0] - 1e-9:
                best = (c, F)
    return best


def _axis_candidates(rng, size, edges):
    lo, hi = rng
    if hi - lo < 1e-6:
        return [lo]
    c = {lo, hi, (lo + hi) / 2}
    n = 80
    for i in range(n + 1):
        c.add(lo + (hi - lo) * i / n)
    for a, b in edges:
        for e in (a, b):
            for v in (e + size / 2, e - size / 2):
                if lo <= v <= hi:
                    c.add(v)
    return sorted(c)


def _exact_cuts(persons, frame, W, H, algo="simple", low=False):
    """Срезы по точным (без запаса) рамкам частей: [(person_index, kind, cut)]; несколько частей одного вида — максимум.
    Игнорируемые (мелкие) люди не входят никогда; люди без лица (low) — только при low=True."""
    best = {}
    for i, p in enumerate(persons):
        if p.ignored or (p.low and not low):
            continue
        for part in person_parts(p, algo):
            b = _clip(part.box, W, H)
            if _area(b) <= 1:
                continue
            key = (i, part.kind)
            c = _cut_frac(b, frame)
            if key not in best or c > best[key]:
                best[key] = c
    return [(i, k, c) for (i, k), c in best.items()]


def _downgrade(level):
    return LEVEL_NAMES[max(0, LEVELS[level] - 1)]


def decide(det, fmt, cfg=None, orient="natural", mode="crop", image=None, rotation=0):
    """Главная функция: Detection -> решение о рамке со статусом и причинами.
    orient: natural — ориентация листа как у фото (горизонтальное остаётся горизонтальным; по умолчанию);
    portrait/landscape — зафиксировать; auto — выбрать книжную/альбомную по минимальной цене (поворот на 90°).
    Для режима без людей можно передать image — рамка потянется к деталям."""
    cfg = make_config(cfg) if not isinstance(cfg, dict) or "tier_base" not in cfg else cfg
    W, H = det.size
    persons = det.persons
    classify_people(persons, cfg)
    humans = [p for p in persons if p.kind == "person" and not p.ignored]
    parts = _prepare_parts(persons, W, H, cfg)
    tw = _tier_weights(cfg)
    joints = []
    for p in humans:
        if p.low:                                   # безлицых «суставы» не интересуют
            continue
        f = p.prominence * (cfg["background_factor"] if p.background else 1.0)
        for (y, x1, x2) in joint_lines(p, cfg.get("algo", "simple")):
            joints.append((y, x1, x2, tw["torso"] * 0.0 + f * tw["hands"]))
    main = [q for q in parts if not q.low] or parts
    heads = [q for q in main if q.kind == "head"]
    centroid = None
    if parts:
        sw = sum(q.weight for q in heads) or sum(q.weight for q in main)
        src = heads if heads else main
        centroid = (sum((q.box[0] + q.box[2]) / 2 * q.weight for q in src) / sw,
                    sum((q.box[1] + q.box[3]) / 2 * q.weight for q in src) / sw)
    focus = None
    if not parts and image is not None:
        fx, fy = _saliency_center(image)
        focus = (fx * W, fy * H)
    natural = "portrait" if H >= W else "landscape"
    if orient == "natural":
        orient = natural
    orients = ["portrait", "landscape"] if orient == "auto" else [orient]
    cands = []
    subject = _subject_box(parts) if cfg.get("portrait_fit") else None
    pcentroid = ((subject[0] + subject[2]) / 2, (subject[1] + subject[3]) / 2) if subject else centroid
    for ori in orients:
        pw, ph = paper_mm(fmt, ori)
        r = pw / ph
        if subject:                               # «Человек»: приблизить людей, оставив немного фона
            sc_ = _portrait_scale(subject, W, H, r, (pw, ph), cfg)
            c, F = _search(parts, joints, W, H, r, cfg, sc_, pcentroid, focus)
            fw_, fh_ = F[2] - F[0], F[3] - F[1]
            cut_ = _frame_cost(F, parts, joints, W, H, cfg, None, fw_, fh_)
            cands.append(((round(cut_, 2), round(fw_ * fh_ / float(W * H), 3)), 0 if ori == natural else 1, ori, F, (pw, ph)))
        else:
            c, F = _search(parts, joints, W, H, r, cfg, 1.0, centroid, focus)
            cands.append((c, 0 if ori == natural else 1, ori, F, (pw, ph)))
    if subject:
        cands.sort(key=lambda t: (t[0], t[1]))
    else:
        cands.sort(key=lambda t: ((t[0][:-1], round(t[0][-1], 6)) if isinstance(t[0], tuple) else (round(t[0], 6),), t[1]))
    _, _, ori, F, paper = cands[0]
    r = paper[0] / paper[1]
    fw, fh = F[2] - F[0], F[3] - F[1]
    maxw = min(W, H * r)
    cost = _frame_cost(F, parts, joints, W, H, cfg, pcentroid, fw, fh)     # сводная цена для отчёта (одна шкала для обоих методов)
    dec = {"orient": ori, "mode": mode, "cx": round((F[0] + F[2]) / 2 / W, 5), "cy": round((F[1] + F[3]) / 2 / H, 5),
           "scale": round(fw / maxw, 5), "angle": 0.0, "paper_mm": [paper[0], paper[1]], "cost": round(cost, 3),
           "algo": cfg.get("algo", "simple")}
    reasons = _judge(det, persons, humans, F, W, H, paper, cfg)
    cuts = [(i, k, c) for (i, k, c) in _exact_cuts(persons, F, W, H, cfg.get("algo", "simple"), low=True) if c > 0.01]
    dec["cuts"] = [{"person": i, "part": k, "label": TIER_LABELS[k], "cut_pct": round(c * 100, 1),
                    **({"faceless": True} if persons[i].low else {})}
                   for (i, k, c) in sorted(cuts, key=lambda t: (persons[t[0]].low, -tw[t[1]], -t[2]))]
    dec["ignored"] = sum(1 for p in persons if p.ignored)
    dec["faceless"] = sum(1 for p in persons if p.low)
    dec["reasons"] = reasons
    status = max((x["level"] for x in reasons), key=lambda l: LEVELS[l], default="ok")
    dec["status"] = status
    dec["risk"] = round(min(1.0, [0.0, 0.2, 0.5, 0.75][LEVELS[status]] + 0.04 * len(reasons)), 2)
    dec["persons"] = len(humans)
    dec["frame_px"] = [round(v, 1) for v in F]
    dec["dpi"] = round(fw / (paper[0] / 25.4), 0)
    if mode == "fit":
        dec.update(cx=0.5, cy=0.5, scale=1.0)
    # --- варианты на выбор (для ручной доработки)
    alts = []
    if status in ("check", "manual") or any(x["code"] in ("big_crop",) for x in reasons):
        alts = _alternatives(det, persons, parts, joints, centroid, W, H, fmt, cfg, orient, ori, cands, tw)
    if subject and dec["scale"] < 0.99 and mode != "fit":          # «Человек»: можно вернуть кадр шире, без приближения
        _, Fw = _search(parts, joints, W, H, r, cfg, 1.0, centroid, None)
        alts.append({"name": "wide", "label": "Шире, без приближения", "orient": ori, "mode": "crop",
                     "cx": round((Fw[0] + Fw[2]) / 2 / W, 5), "cy": round((Fw[1] + Fw[3]) / 2 / H, 5), "scale": 1.0, "problems": 0})
    dec["alternatives"] = alts
    dec["detector"] = "+".join(det.backends) or "нет"
    return dec


def _judge(det, persons, humans, F, W, H, paper, cfg):
    reasons = []

    def add(code, level, msg, person=None, **extra):
        d = {"code": code, "level": level, "message": msg}
        if person is not None:
            d["person"] = person
        d.update(extra)
        reasons.append(d)

    if not det.backends:
        add("no_detector", "check", "Детекторы не установлены — автокадрирование НЕ защищает людей. Выполните: python smart_crop.py setup")
    grouped = {}
    for (i, kind, cut) in sorted(_exact_cuts(persons, F, W, H, cfg.get("algo", "simple")), key=lambda t: -t[2]):
        p = persons[i]
        if cut <= cfg["accept_cut"][kind]:
            continue
        lvl = cfg["severity"][kind]
        if cut >= cfg["escalate_cut"].get(kind, 2.0):
            lvl = "manual"
        if p.background or (p.kind == "person" and p.prominence < 0.25):
            lvl = _downgrade(lvl)
        g = grouped.setdefault((kind, lvl), [])
        g.append((i, cut))
    for (kind, lvl), lst in grouped.items():
        lst.sort(key=lambda t: -t[1])
        i0, c0 = lst[0]
        if kind == "pet":
            msg = f"Режется питомец: {c0 * 100:.0f}%"
        elif len(lst) == 1:
            msg = f"Режется «{TIER_LABELS[kind]}» у человека №{i0 + 1}: {c0 * 100:.0f}%"
        else:
            msg = (f"Режется «{TIER_LABELS[kind]}» у {len(lst)} чел. (сильнее всего №{i0 + 1}: {c0 * 100:.0f}%; "
                   f"№" + ", №".join(str(i + 1) for i, _ in lst[:6]) + (" …" if len(lst) > 6 else "") + ")")
        add(f"{kind}_cut", lvl, msg, person=i0, cut=round(c0, 3), persons=[i for i, _ in lst], count=len(lst))
    # неуверенность детекторов
    shaky = [i for i, p in enumerate(persons) if p.kind == "person" and not p.background and not p.ignored and not p.low
             and (p.conf < cfg["low_conf"] or p.synthetic)]
    if shaky:
        add("low_confidence", "check", "Детектор не уверен (человек №" + ", №".join(str(i + 1) for i in shaky[:6]) + ") — проверьте, что никого не потеряно")
    if len(humans) >= cfg["many_persons"]:
        add("many_persons", "check", f"Групповое фото ({len(humans)} чел.) — проверьте рамку")
    if not persons and det.backends:
        add("no_subjects", "note", "Люди и питомцы не найдены — рамка по центру/деталям (пейзаж, предмет или пропуск детектора)")
    inside = _inter((0, 0, W, H), F)
    removed = 1.0 - inside / _area(F) if False else 1.0 - inside / float(W * H)
    if removed > cfg["max_removed_area"] and not cfg.get("portrait_fit"):
        lvl = "check" if (not persons or any(p.conf < cfg["low_conf"] for p in persons)) else "note"
        add("big_crop", lvl, f"Рамка отрезает {removed * 100:.0f}% фото")
    dpi = (F[2] - F[0]) / (paper[0] / 25.4)
    if dpi < cfg["min_dpi"]:
        add("low_res", "check", f"Малое разрешение для печати: {dpi:.0f} dpi")
    return reasons


def _alternatives(det, persons, parts, joints, centroid, W, H, fmt, cfg, orient, chosen, cands, tw):
    alts = []
    # 1) другая ориентация листа
    for c, _, ori, F, paper in cands[1:]:
        cuts = [(i, k, cu) for (i, k, cu) in _exact_cuts(persons, F, W, H, cfg.get("algo", "simple")) if cu > cfg["accept_cut"][k]]
        alts.append({"name": "other_orientation", "label": "Другая ориентация листа", "orient": ori, "mode": "crop",
                     "cx": round((F[0] + F[2]) / 2 / W, 5), "cy": round((F[1] + F[3]) / 2 / H, 5),
                     "scale": round((F[2] - F[0]) / min(W, H * paper[0] / paper[1]), 5),
                     "problems": len(cuts), "worst_cut_pct": round(max([cu for _, _, cu in cuts], default=0) * 100, 1)})
    if orient != "auto":                              # зафиксированную ориентацию всё равно можно сменить для одного фото
        other = "landscape" if chosen == "portrait" else "portrait"
        if not any(a["name"] == "other_orientation" for a in alts):
            pw, ph = paper_mm(fmt, other)
            r = pw / ph
            c, F = _search(parts, joints, W, H, r, cfg, 1.0, centroid, None)
            cuts = [(i, k, cu) for (i, k, cu) in _exact_cuts(persons, F, W, H, cfg.get("algo", "simple")) if cu > cfg["accept_cut"][k]]
            alts.append({"name": "other_orientation", "label": "Другая ориентация листа", "orient": other, "mode": "crop",
                         "cx": round((F[0] + F[2]) / 2 / W, 5), "cy": round((F[1] + F[3]) / 2 / H, 5),
                         "scale": round((F[2] - F[0]) / min(W, H * r), 5), "problems": len(cuts),
                         "worst_cut_pct": round(max([cu for _, _, cu in cuts], default=0) * 100, 1)})
    # 2) вписать целиком (ничего не режется, белые поля)
    pw, ph = paper_mm(fmt, chosen)
    r = pw / ph
    scale_fit = min(W / (pw), H / (ph))
    white = 1.0 - (min(W / (pw / ph * H), 1.0) if W / H < r else min(H / (W / r), 1.0))
    alts.append({"name": "fit", "label": "Вписать целиком (белые поля)", "orient": chosen, "mode": "fit",
                 "cx": 0.5, "cy": 0.5, "scale": 1.0, "problems": 0, "white_pct": round(white * 100, 1)})
    # 3) рамка чуть больше фото: небольшие белые поля, но ничего не режется
    best = None
    for k in range(1, 8):
        s = 1.0 + cfg["max_extend"] * k / 7
        fw, fh = frame_for(W, H, r, s)
        for fx in (0.0, 0.25, 0.5, 0.75, 1.0):
            for fy in (0.0, 0.25, 0.5, 0.75, 1.0):
                cx = W / 2 + (fx - 0.5) * (fw - W) if fw > W else W / 2
                cy = H / 2 + (fy - 0.5) * (fh - H) if fh > H else H / 2
                F = (cx - fw / 2, cy - fh / 2, cx + fw / 2, cy + fh / 2)
                cuts = [(i, kk, cu) for (i, kk, cu) in _exact_cuts(persons, F, W, H, cfg.get("algo", "simple")) if cu > cfg["accept_cut"][kk]]
                if not cuts:
                    out = 1.0 - _inter((0, 0, W, H), F) / _area(F)
                    if best is None or out < best[0]:
                        best = (out, s, F)
        if best:
            break
    if best:
        out, s, F = best
        alts.append({"name": "extend", "label": "Рамка с небольшими белыми полями", "orient": chosen, "mode": "crop",
                     "cx": round((F[0] + F[2]) / 2 / W, 5), "cy": round((F[1] + F[3]) / 2 / H, 5), "scale": round(s, 4),
                     "problems": 0, "white_pct": round(out * 100, 1)})
    return alts


# ------------------------------------------------------------------ загрузка изображения

def load_for_detection(path, rotation=0, max_side=1600):
    """Уменьшенная копия снимка (с учётом EXIF и поворота) и истинные размеры (W, H) в пикселях."""
    with Image.open(path) as im0:
        W0, H0 = im0.size
        try:
            ori = im0.getexif().get(0x0112, 1)
        except Exception:
            ori = 1
        if im0.format == "JPEG":
            im0.draft("RGB", (max_side, max_side))
        im = ImageOps.exif_transpose(im0)
        im.load()
    if ori in (5, 6, 7, 8):
        W0, H0 = H0, W0
    if rotation:
        im = im.rotate(-rotation, expand=True)
        if rotation in (90, 270):
            W0, H0 = H0, W0
    if im.mode != "RGB":
        im = im.convert("RGB")
    return im, (W0, H0)


# ------------------------------------------------------------------ главный класс

class SmartCropper:
    def __init__(self, config=None, models_dir=None, use=("yunet", "yolox"), use_cache=True, pose_model=None):
        self.cfg = make_config(config)
        self.models_dir = Path(models_dir) if models_dir else MODELS_DIR
        self.faces, self.people, self.pose, self.problems = None, None, None, []
        self.cache = use_cache
        want = set(use)
        if self.cfg.get("algo") == "enhanced":              # улучшенный метод опирается на скелет (нейросеть позы)
            want.add("mp_pose")
        try:
            if "yunet" in want and (self.models_dir / MODEL_FILES["yunet"][0]).is_file():
                self.faces = YuNetFaces(self.models_dir / MODEL_FILES["yunet"][0])
            elif "haar" in want or "yunet" in want:
                self.faces = HaarFaces()
                if "yunet" in want:
                    self.problems.append("Модель YuNet не найдена — используются каскады Хаара (менее точно). python smart_crop.py setup")
        except Exception as ex:
            self.problems.append(f"Детектор лиц недоступен: {ex}")
        try:
            for key in ("yolox_s", "yolox_tiny"):
                if (key in want or "yolox" in want) and (self.models_dir / MODEL_FILES[key][0]).is_file():
                    self.people = YoloXDetector(self.models_dir / MODEL_FILES[key][0])
                    break
            else:
                if "yolox" in want or "yolox_s" in want:
                    self.problems.append("Модель YOLOX не найдена. python smart_crop.py setup")
        except Exception as ex:
            self.problems.append(f"Детектор людей недоступен: {ex}")
        if pose_model:
            try:
                self.pose = YoloPoseDetector(pose_model)
            except Exception as ex:
                self.problems.append(f"Модель позы недоступна: {ex}")
        self.mp_pose = None                      # скелет для улучшенного метода (рамка человека от YOLOX -> 33 точки)
        if "mp_pose" in want or "pose" in want:
            f_ = self.models_dir / MODEL_FILES["mp_pose"][0]
            if f_.is_file():
                try:
                    self.mp_pose = MediaPipePose(f_)
                except Exception as ex:
                    self.problems.append(f"Модель позы недоступна: {ex}")
            else:
                self.problems.append("Модель позы (скелет) не найдена — части тела оцениваются по размеру головы. python smart_crop.py setup")

    def backends(self):
        return [b.name for b in (self.faces, self.people, self.pose, self.mp_pose) if b is not None]

    # ---- детекция (с кэшем на диске: смена приоритетов не требует повторного распознавания)
    def _cache_file(self, path, rotation):
        p = Path(path)
        try:
            st = p.stat()
            key = f"{p.resolve()}|{st.st_mtime_ns}|{st.st_size}|{rotation}|{'+'.join(self.backends())}|{self.cfg['min_person_conf']}|{self.cfg['min_face_conf']}"
        except OSError:
            return None
        return CACHE_DIR / (hashlib.sha1(key.encode("utf-8")).hexdigest()[:20] + ".json")

    def detect(self, path, rotation=0):
        cf = self._cache_file(path, rotation) if self.cache else None
        if cf is not None and cf.is_file():
            try:
                return Detection.from_dict(json.loads(cf.read_text(encoding="utf-8")))
            except Exception:
                pass
        img, size = load_for_detection(path, rotation)
        k = img.width / float(size[0])
        faces, people = [], []
        if self.faces:
            faces = self.faces.detect(img)
        if self.pose:
            people += self.pose.detect(img)
        if self.people:
            raw = self.people.detect(img)
            if self.pose:                                    # позы уже дают людей; из YOLOX берём только питомцев
                raw = [d for d in raw if d.get("kind") != "person"]
            people += raw
        scale = lambda b: tuple(v / k for v in b)
        faces = [{"box": scale(f["box"]), "conf": f["conf"]} for f in faces]
        for d in people:
            d["box"] = scale(d["box"])
            if d.get("keypoints"):
                d["keypoints"] = [(x / k, y / k, c) for (x, y, c) in d["keypoints"]]
        persons = assemble(faces, people, size[0], size[1], self.cfg)
        if self.mp_pose:                                     # скелет по рамке каждого заметного человека (до 12 крупнейших)
            big = sorted((q for q in persons if q.kind == "person" and not q.synthetic and not q.keypoints), key=lambda q: -_area(q.box))[:12]
            for q in big:
                bb = tuple(v * k for v in q.box)
                if bb[3] - bb[1] < 48 or bb[2] - bb[0] < 24:
                    continue
                try:
                    kp = self.mp_pose.estimate(img, bb)
                except Exception as ex:
                    self.problems.append(f"Поза: {ex.__class__.__name__}: {ex}")
                    break
                if kp:
                    kp = [(x / k, y / k, c) for (x, y, c) in kp]
                    q.keypoints, _ = sanity_pose(kp, q)             # None — скелету не верим, части оцениваются по голове
        det = Detection(size, persons, self.backends(), self.problems)
        if cf is not None:
            try:
                CACHE_DIR.mkdir(parents=True, exist_ok=True)
                cf.write_text(json.dumps(det.to_dict()), encoding="utf-8")
            except OSError:
                pass
        return det

    def analyze(self, path, fmt="10x15", orient="natural", rotation=0, mode="crop"):
        det = self.detect(path, rotation)
        img = None
        if not det.persons:
            img, _ = load_for_detection(path, rotation, 400)
        dec = decide(det, fmt, self.cfg, orient, mode, img)
        dec["file"] = str(path)
        dec["size"] = list(det.size)
        dec["detections"] = [dict(p.to_dict(), ignored=p.ignored, low=p.low, box=[round(v / s, 4) for v, s in zip(p.box, (det.size[0], det.size[1]) * 2)],
                                  face=([round(v / s, 4) for v, s in zip(p.face, (det.size[0], det.size[1]) * 2)] if p.face else None),
                                  keypoints=([[round(x / det.size[0], 4), round(y / det.size[1], 4), round(c, 2)] for (x, y, c) in p.keypoints]
                                             if p.keypoints else None)) for p in det.persons]
        return dec

    def analyze_many(self, paths, fmt="10x15", orient="natural", progress=None, workers=2, rotations=None):
        from concurrent.futures import ThreadPoolExecutor, as_completed
        paths = [Path(p) for p in paths]
        out = [None] * len(paths)

        def one(i):
            try:
                return i, self.analyze(paths[i], fmt, orient, (rotations or {}).get(str(paths[i]), 0)), None
            except Exception as ex:
                return i, None, f"{ex.__class__.__name__}: {ex}"

        done = 0
        with ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
            for fu in as_completed([ex.submit(one, i) for i in range(len(paths))]):
                i, dec, err = fu.result()
                out[i] = dec or {"file": str(paths[i]), "status": "manual", "risk": 1.0,
                                 "reasons": [{"code": "read_error", "level": "manual", "message": f"Не удалось обработать файл: {err}"}],
                                 "alternatives": [], "cuts": []}
                done += 1
                if progress:
                    progress(done, len(paths), paths[i].name)
        return out


def apply_decision(dec, state):
    """Переносит решение в CropState из photo_crop (или любой объект с этими полями)."""
    state.cx, state.cy, state.scale, state.angle = dec["cx"], dec["cy"], dec["scale"], 0.0
    state.orient = dec["orient"]
    state.edited = False        # автоматическая рамка — не «ручная правка»
    return state


# ------------------------------------------------------------------ проверка человеком: контактный лист и наложение

STATUS_COLORS = {"ok": (46, 160, 67), "note": (140, 140, 140), "check": (230, 160, 20), "manual": (220, 50, 47)}
STATUS_LABELS = {"ok": "ОК", "note": "заметка", "check": "проверить", "manual": "ВРУЧНУЮ"}
TIER_COLORS = {"head": (255, 60, 60), "torso": (255, 150, 30), "hands": (60, 200, 255), "arms": (80, 160, 255),
               "legs": (160, 90, 255), "feet": (200, 90, 200), "pet": (80, 220, 120), "other": (200, 200, 200)}


def _font(px):
    for n in ("arial.ttf", "segoeui.ttf", "DejaVuSans.ttf", "LiberationSans-Regular.ttf"):
        try:
            return ImageFont.truetype(n, px)
        except Exception:
            continue
    return ImageFont.load_default()


def draw_overlay(img, dec, boxes=True, dim=True):
    """Картинка с рамкой (обрезаемое затемнено) и найденными частями людей."""
    W0, H0 = dec["size"]
    k = img.width / float(W0)
    im = img.convert("RGB").copy()
    F = [v * k for v in dec["frame_px"]]
    if dim:
        shade = Image.new("RGB", im.size, (0, 0, 0))
        mask = Image.new("L", im.size, 150)
        ImageDraw.Draw(mask).rectangle((F[0], F[1], F[2], F[3]), fill=0)
        im = Image.composite(shade, im, mask)
    d = ImageDraw.Draw(im)
    col = STATUS_COLORS[dec["status"]]
    d.rectangle(F, outline=col, width=max(2, im.width // 250))
    if boxes:
        for det in dec.get("_persons", []):
            if det.ignored:                                   # мелкий дальний план: только серая рамка человека
                d.rectangle([v * k for v in det.box], outline=(130, 130, 130), width=1)
                continue
            for part in person_parts(det, dec.get("algo", "simple")):
                b = [v * k for v in part.box]
                col_ = TIER_COLORS[part.kind]
                if det.low:
                    col_ = tuple((c + 90) // 2 for c in col_)
                d.rectangle(b, outline=col_, width=max(1, im.width // 500))
            if det.keypoints and dec.get("algo") == "enhanced":              # скелет нейросети позы
                kp = det.keypoints
                lw = max(2, im.width // 300)
                for i, j in ((5, 7), (7, 9), (6, 8), (8, 10), (5, 6), (5, 11), (6, 12), (11, 12), (11, 13), (13, 15), (12, 14), (14, 16)):
                    if kp[i][2] >= 0.3 and kp[j][2] >= 0.3:
                        d.line((kp[i][0] * k, kp[i][1] * k, kp[j][0] * k, kp[j][1] * k), fill=(255, 255, 255), width=lw)
                for x, y, c in kp[5:]:
                    if c >= 0.3:
                        r_ = lw * 1.4
                        d.ellipse((x * k - r_, y * k - r_, x * k + r_, y * k + r_), fill=(60, 230, 120) if c >= 0.6 else (255, 190, 40))
    return im


def contact_sheet(decisions, out_path, cols=4, thumb=320, only_flagged=True, sample_ok=0.0, seed=1, show_parts=True):
    """Контактный лист для быстрой проверки: худшие кадры первыми, обрезаемое затемнено, цвет рамки = статус.
    sample_ok — доля «ок»-кадров, добавляемых для выборочной проверки (ловит тихие ошибки детектора)."""
    import random
    rnd = random.Random(seed)
    items = [d for d in decisions if d["status"] in ("check", "manual")]
    if not only_flagged:
        items = list(decisions)
    elif sample_ok > 0:
        oks = [d for d in decisions if d["status"] in ("ok", "note")]
        items += rnd.sample(oks, min(len(oks), max(1, round(len(oks) * sample_ok)))) if oks else []
    items.sort(key=lambda d: -d.get("risk", 0))
    if not items:
        return None
    cap_h = 46
    rows = (len(items) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * (thumb + 10) + 10, rows * (thumb + cap_h + 10) + 10), (32, 32, 32))
    sd = ImageDraw.Draw(sheet)
    f1 = _font(14)
    for n, dec in enumerate(items):
        x = 10 + (n % cols) * (thumb + 10)
        y = 10 + (n // cols) * (thumb + cap_h + 10)
        try:
            img, size = load_for_detection(dec["file"], 0, thumb * 2)
            dd = dict(dec)
            if show_parts and dec.get("detections"):
                from types import SimpleNamespace
                dd["_persons"] = [_person_from_fraction(p, size) for p in dec["detections"]]
            ov = draw_overlay(img, dd, boxes=show_parts)
            ov.thumbnail((thumb, thumb))
        except Exception:
            ov = Image.new("RGB", (thumb, thumb), (60, 60, 60))
        col = STATUS_COLORS[dec["status"]]
        sd.rectangle((x - 3, y - 3, x + thumb + 3, y + thumb + cap_h), fill=col)
        sheet.paste(ov, (x + (thumb - ov.width) // 2, y + (thumb - ov.height) // 2))
        label = f"{STATUS_LABELS[dec['status']]}  {Path(dec['file']).name}"
        sd.text((x + 4, y + thumb + 3), label[:46], fill=(0, 0, 0) if dec["status"] == "check" else (255, 255, 255), font=f1)
        why = ", ".join(r["code"] for r in dec["reasons"][:3])
        sd.text((x + 4, y + thumb + 23), why[:50], fill=(0, 0, 0) if dec["status"] == "check" else (255, 255, 255), font=f1)
    sheet.save(out_path, quality=88)
    return out_path


def _person_from_fraction(d, size):
    W, H = size
    p = Person([d["box"][0] * W, d["box"][1] * H, d["box"][2] * W, d["box"][3] * H], d.get("conf", 1), d.get("kind", "person"))
    if d.get("face"):
        p.face = (d["face"][0] * W, d["face"][1] * H, d["face"][2] * W, d["face"][3] * H)
    if d.get("keypoints"):
        p.keypoints = [(k[0] * W, k[1] * H, k[2]) for k in d["keypoints"]]
    p.ignored, p.low = bool(d.get("ignored")), bool(d.get("low"))
    return p


# ------------------------------------------------------------------ установка моделей и командная строка

def download_models(keys=("yunet", "yolox_s", "mp_pose"), dest=None, log=print):
    import urllib.request
    dest = Path(dest) if dest else MODELS_DIR
    dest.mkdir(parents=True, exist_ok=True)
    for k in keys:
        name, url, mb = MODEL_FILES[k]
        f = dest / name
        if f.is_file() and f.stat().st_size > 100000:
            log(f"уже есть: {f}")
            continue
        log(f"скачиваю {name} (~{mb} МБ) …")
        tmp = f.with_suffix(".part")
        urllib.request.urlretrieve(url, tmp)
        os.replace(tmp, f)
        log(f"готово: {f}")


def _expand_paths(items):
    out = []
    for it in items:
        p = Path(it)
        if p.is_dir():
            out += sorted((f for f in p.iterdir() if f.suffix.lower() in (".jpg", ".jpeg", ".png", ".tif", ".tiff", ".webp", ".bmp")),
                          key=lambda f: [int(t) if t.isdigit() else t.lower() for t in __import__("re").split(r"(\d+)", f.name)])
        else:
            out.append(p)
    return out


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description="SmartCrop — автокадрирование без потери людей (самостоятельный модуль)")
    sub = ap.add_subparsers(dest="cmd")
    sub.add_parser("setup", help="скачать модели детекторов (~42 МБ)")
    sub.add_parser("selftest", help="проверка логики на синтетических сценах")
    a = sub.add_parser("analyze", help="проанализировать папку/файлы")
    a.add_argument("paths", nargs="+")
    a.add_argument("--format", default="10x15")
    a.add_argument("--orient", default="natural", choices=["natural", "auto", "portrait", "landscape"], help="natural: как у фото (по умолчанию); auto: ИИ может повернуть лист на 90°")
    a.add_argument("--portrait", action="store_true", help="режим «Человек»: срезать лишнее, людей — крупно, с небольшим запасом фона")
    a.add_argument("--priority", help="порядок важности через запятую, напр. head,torso,hands,legs,feet")
    a.add_argument("--algo", choices=list(ALGOS), help="метод: simple (простой) или enhanced (улучшенный: голова → тело → кисти → руки → ноги → стопы строго по очереди)")
    a.add_argument("--config", help="JSON-файл с настройками")
    a.add_argument("--out", help="куда записать JSON с решениями")
    a.add_argument("--sheet", help="контактный лист проблемных кадров (jpg)")
    a.add_argument("--sample-ok", type=float, default=0.03, help="доля «ок»-кадров для выборочной проверки на листе")
    a.add_argument("--workers", type=int, default=2)
    args = ap.parse_args(argv)
    if args.cmd == "setup":
        download_models()
        return 0
    if args.cmd == "selftest":
        return selftest()
    if args.cmd == "analyze":
        cfg = {}
        if args.config:
            cfg = json.loads(Path(args.config).read_text(encoding="utf-8"))
        if args.priority:
            cfg["priority"] = [s.strip() for s in args.priority.split(",") if s.strip()]
        if args.algo:
            cfg["algo"] = args.algo
        if args.portrait:
            cfg["portrait_fit"] = True
        sc = SmartCropper(cfg)
        for pr in sc.problems:
            print("⚠", pr, file=sys.stderr)
        paths = _expand_paths(args.paths)
        t0 = time.time()
        decs = sc.analyze_many(paths, args.format, args.orient, lambda i, n, name: print(f"\r{i}/{n} {name[:40]:40}", end="", file=sys.stderr),
                               args.workers)
        print(file=sys.stderr)
        for d in decs:
            d.pop("detections", None) if not args.out else None
        summary = {s: sum(1 for d in decs if d["status"] == s) for s in LEVEL_NAMES}
        print(json.dumps({"summary": summary, "seconds": round(time.time() - t0, 1), "backends": sc.backends()}, ensure_ascii=False))
        if args.out:
            Path(args.out).write_text(json.dumps(decs, ensure_ascii=False, indent=1), encoding="utf-8")
        if args.sheet:
            r = contact_sheet(decs, args.sheet, sample_ok=args.sample_ok)
            print("контактный лист:", r or "проблемных кадров нет")
        return 0
    ap.print_help()
    return 1


# ------------------------------------------------------------------ самопроверка логики (без моделей)

def _mk(W, H, people, faces=None, pets=None, cfg=None):
    cfg = make_config(cfg)
    pe = [{"box": b, "conf": 0.9} for b in people] + [{"box": b, "conf": 0.9, "kind": "pet"} for b in (pets or [])]
    fa = [{"box": b, "conf": 0.9} for b in (faces or [])]
    return Detection((W, H), assemble(fa, pe, W, H, cfg), ["synthetic"]), cfg


def selftest():
    bad = []

    def check(name, cond, info=""):
        print(("ok  " if cond else "FAIL"), name, info)
        if not cond:
            bad.append(name)

    # 1) человек у левого края альбомного фото, лист 10x15 альбомный: рамка должна уйти к человеку
    det, cfg = _mk(3000, 2000, [(150, 300, 650, 1900)], [(300, 350, 480, 560)])
    d = decide(det, "10x15", cfg, "portrait")     # книжная рамка из альбомного фото — узкая полоса
    check("рамка следует за человеком", d["cx"] < 0.35, f"cx={d['cx']}")
    check("голова не обрезана", not any(c["part"] == "head" for c in d["cuts"]), str(d["cuts"][:2]))
    # 2) широкая группа в книжный лист: неизбежно режем -> manual + предложения
    faces = [(200 + i * 500, 400, 330 + i * 500, 560) for i in range(5)]
    people = [(150 + i * 500, 350, 400 + i * 500, 1500) for i in range(5)]
    det, cfg = _mk(3000, 2000, people, faces)
    d = decide(det, "10x15", cfg, "portrait")
    check("группа не влезает -> manual", d["status"] == "manual", d["status"])
    check("есть варианты fit/extend", {a["name"] for a in d["alternatives"]} >= {"fit"}, str([a["name"] for a in d["alternatives"]]))
    d2 = decide(det, "10x15", cfg, "auto")
    check("auto-ориентация выбирает альбомную для широкой группы", d2["orient"] == "landscape" and d2["status"] in ("ok", "note", "check"), f"{d2['orient']} {d2['status']}")
    # 3) приоритеты: приходится жертвовать ногами или головой — выбираются ноги
    det, cfg = _mk(2000, 3000, [(500, 200, 1500, 2900)], [(850, 230, 1150, 600)])
    d = decide(det, "A4", cfg, "landscape")
    check("лишнее режется снизу (ноги), а не голова", not any(c["part"] == "head" for c in d["cuts"]) and d["cy"] < 0.5, f"cy={d['cy']} cuts={[c['part'] for c in d['cuts']]}")
    # 4) смена приоритета: руки важнее ног — результат зависит от порядка (проверяем, что вес меняется)
    w1 = _tier_weights(make_config({"priority": ["head", "torso", "hands", "legs"]}))
    w2 = _tier_weights(make_config({"priority": ["head", "torso", "legs", "hands"]}))
    check("порядок важности меняет веса", w1["hands"] > w1["legs"] and w2["legs"] > w2["hands"])
    # 5) нет людей
    det, cfg = _mk(3000, 2000, [])
    d = decide(det, "10x15", cfg, "auto")
    check("нет людей -> note", d["status"] == "note" and d["reasons"][0]["code"] == "no_subjects", d["status"])
    # 6) нет детекторов
    det = Detection((3000, 2000), [], [])
    d = decide(det, "10x15", make_config(), "auto")
    check("нет детекторов -> check", d["status"] == "check" and d["reasons"][0]["code"] == "no_detector")
    # 7) фоновый прохожий не вызывает «вручную»
    det, cfg = _mk(3000, 2000, [(1000, 300, 1800, 1900), (2850, 1500, 3000, 1900)], [(1300, 350, 1500, 580)])
    d = decide(det, "10x15", cfg, "portrait")
    check("фоновый человек на краю не ломает вердикт", d["status"] != "manual", d["status"])
    # 8) голова у верхнего края — рамка сдвигается вверх (при вертикальной свободе)
    det, cfg = _mk(2000, 3000, [(600, 60, 1400, 2400)], [(850, 90, 1150, 420)])
    d = decide(det, "A4", cfg, "landscape")
    check("голова у верха сохраняется", not any(c["part"] == "head" for c in d["cuts"]) and d["cy"] < 0.3, f"cy={d['cy']}")
    # 9) питомец защищается как тело
    det, cfg = _mk(3000, 2000, [], pets=[(2200, 900, 2800, 1700)])
    d = decide(det, "10x15", cfg, "portrait")
    check("питомец в кадре", not any(c["part"] == "pet" and c["cut_pct"] > 10 for c in d["cuts"]), str(d["cuts"]))
    # 10) ключевые точки -> части
    kp = [(500, 300, .9), (480, 290, .9), (520, 290, .9), (460, 300, .9), (540, 300, .9), (440, 400, .9), (560, 400, .9),
          (420, 520, .9), (580, 520, .9), (410, 640, .9), (590, 640, .9), (460, 650, .9), (540, 650, .9), (455, 850, .9),
          (545, 850, .9), (450, 1050, .9), (550, 1050, .9)]
    p = Person((380, 240, 620, 1100), 0.9)
    p.keypoints = kp
    kinds = {q.kind for q in person_parts(p, "enhanced")}
    check("части из ключевых точек (улучшенный)", {"head", "torso", "arms", "hands", "legs", "feet"} <= kinds, str(sorted(kinds)))
    # 11) декодер YOLO-pose на синтетическом тензоре
    np = _np()
    t = np.zeros((1, 56, 3), dtype=np.float32)
    t[0, :5, 0] = [320, 320, 100, 300, 0.9]
    t[0, 5:, 0] = 100.0
    res = decode_yolo_pose(t, 1.0, 640, 640, 0.3, 0.45)
    check("decode_yolo_pose", len(res) == 1 and len(res[0]["keypoints"]) == 17, str(len(res)))
    # 12) геометрия совместима с photo_crop: scale=1 -> рамка = максимально вписанная
    w, h = frame_for(3000, 2000, 102 / 152, 1.0)
    check("геометрия рамки как в photo_crop", abs(h - 2000) < 1e-6 and abs(w - 2000 * 102 / 152) < 1e-6)
    # 13) улучшенный метод: части от размера головы, ступени сравниваются строго по очереди
    det, cfg = _mk(2000, 3000, [(500, 200, 1500, 2900)], [(850, 230, 1150, 600)], cfg={"algo": "enhanced"})
    kinds = {q.kind for q in person_parts(det.persons[0], "enhanced")}
    check("улучшенный: части тела от головы", {"head", "torso", "arms", "hands", "legs", "feet"} <= kinds, str(sorted(kinds)))
    d = decide(det, "A4", cfg, "landscape")
    check("улучшенный: режется низ, голова цела", not any(c["part"] == "head" for c in d["cuts"]) and d["cy"] < 0.5 and d["algo"] == "enhanced", f"cy={d['cy']}")
    # строгий порядок: даже при одинаковых весах ступеней голова не меняется на ноги
    det2, cfg2 = _mk(2000, 3000, [(500, 100, 1500, 2900)], [(850, 130, 1150, 480)], cfg={"algo": "enhanced", "tier_base": 1.0})
    d2 = decide(det2, "A4", cfg2, "landscape")
    check("улучшенный: голова цела даже при равных весах", not any(c["part"] == "head" and c["cut_pct"] > 2 for c in d2["cuts"]) and d2["cy"] < 0.4, f"cy={d2['cy']} {d2['cuts'][:2]}")
    # раскинутая рука расширяет зону рук/кистей
    pw = Person((300, 300, 1500, 1800), 0.9)
    pw.face = (800, 330, 940, 500)
    wide = {q.kind for q in person_parts(pw, "enhanced")}
    check("улучшенный: поднятая рука даёт кисть вверху", "hands" in wide)
    # нейросеть позы достраивает тело, которого нет в кадре: бёдра «на животе» отбрасываются, торс тянется вниз
    half = Person((10, 18, 374, 506), 0.9)
    half.face = (178, 63, 268, 176)
    kp27 = [(224, 129, 1.0)] * 5 + [(272, 197, 1.0), (147, 178, 1.0), (280, 250, .9), (120, 260, .9), (279, 319, .8), (98, 270, .8),
                                   (229, 314, 1.0), (170, 314, 1.0), (245, 353, .6), (190, 353, .6), (221, 419, .6), (200, 419, .6)] + [(0, 0, 0.0)] * 10
    kp_ok, _ = sanity_pose(kp27, half)
    check("поза: выдуманные бёдра и колени отброшены", kp_ok is not None and kp_ok[11][2] == 0.0 and kp_ok[13][2] == 0.0 and kp_ok[5][2] > 0.5)
    half.keypoints = kp_ok
    pk = {q.kind: q for q in person_parts(half, "enhanced")}
    check("поза: торс тянется вниз, ног нет", "legs" not in pk and pk["torso"].box[3] > 450, str(pk["torso"].box))
    faceclose = Person((0, 0, 500, 600), 0.9)
    faceclose.face = (180, 120, 350, 330)
    kp_bad = [(250, 240, 1.0)] * 5 + [(227, 371, .1), (277, 372, .1)] + [(250, 400, .2)] * 20
    check("поза: крупный план лица — скелету не верим", sanity_pose(kp_bad, faceclose)[0] is None)
    try:
        make_config({"algo": "bogus"})
        check("неизвестный метод отвергается", False)
    except ValueError:
        check("неизвестный метод отвергается", True)
    # 8) мелкие люди вдали не учитываются совсем, люди без лица — наинизший приоритет (оба метода)
    for algo in ALGOS:
        det, cfg = _mk(3000, 2000, [(900, 300, 1700, 1900), (2900, 1500, 2990, 1700)], [(1200, 350, 1400, 600)], cfg={"algo": algo})
        d = decide(det, "10x15", cfg, "portrait")
        check(f"[{algo}] мелкий человек игнорируется", d["ignored"] == 1 and d["persons"] == 1
              and not any(c["person"] == 1 for c in d["cuts"]), f"ignored={d['ignored']} persons={d['persons']}")
        det, cfg = _mk(3000, 2000, [(900, 300, 1700, 1900), (2900, 1500, 2990, 1700)], [(1200, 350, 1400, 600)],
                       cfg={"algo": algo, "ignore_background": False})
        d = decide(det, "10x15", cfg, "portrait")
        check(f"[{algo}] без игнорирования мелкий остаётся в расчёте", d["ignored"] == 0 and d["persons"] == 2)
        faced = (200, 300, 700, 1900)
        less = (1100, 300, 1800, 1900)            # крупнее человека с лицом, но лица нет (спиной)
        det, cfg = _mk(3000, 2000, [faced, less], [(350, 350, 530, 560)], cfg={"algo": algo})
        d = decide(det, "10x15", cfg, "portrait")
        mine = [c for c in d["cuts"] if c["person"] == 0]
        check(f"[{algo}] у человека с лицом ничего не режется", not mine and d["faceless"] == 1, str(d["cuts"][:3]))
        check(f"[{algo}] безлицый режется без претензий", any(c.get("faceless") for c in d["cuts"])
              and not any(r.get("person") == 1 for r in d["reasons"]), str(d["reasons"]))
        det, cfg = _mk(3000, 2000, [faced, less], [(350, 350, 530, 560)], cfg={"algo": algo, "faceless_lowest": False})
        d2 = decide(det, "10x15", cfg, "portrait")
        check(f"[{algo}] без приоритета для безлицых кадр иной", d2["faceless"] == 0 and d2["cx"] != d["cx"], f"{d2['cx']} vs {d['cx']}")
        det, cfg = _mk(3000, 2000, [less], [], cfg={"algo": algo})                 # лиц нет вообще: все равны
        d3 = decide(det, "10x15", cfg, "portrait")
        check(f"[{algo}] если лиц нет — безлицый обычный", d3["faceless"] == 0 and not any(c["part"] == "head" for c in d3["cuts"]))
    # 9) режим «Человек»: срезать лишнее, людей крупно, но с запасом фона; без него — кадр целиком
    for algo in ALGOS:
        det, cfg = _mk(4000, 3000, [(1700, 1000, 2200, 2500)], [(1860, 1050, 2020, 1250)], cfg={"algo": algo, "portrait_fit": True})
        d = decide(det, "10x15", cfg, "auto")
        x1, y1, x2, y2 = d["frame_px"]
        check(f"[{algo}] «Человек»: кадр приближен", d["scale"] < 0.85 and d["orient"] == "portrait", f"scale={d['scale']} {d['orient']}")
        check(f"[{algo}] «Человек»: человек цел и есть запас фона", not d["cuts"] and x1 < 1700 - 60 and x2 > 2200 + 60 and y1 < 1000 - 60 and y2 > 2500 + 60, str(d["frame_px"]))
        check(f"[{algo}] «Человек»: есть вариант «шире»", any(a["name"] == "wide" and a["scale"] == 1.0 for a in d["alternatives"]))
        check(f"[{algo}] «Человек»: dpi не ниже порога", d["dpi"] >= cfg["min_dpi"] - 1, str(d["dpi"]))
        det, cfg = _mk(4000, 3000, [(1700, 1000, 2200, 2500)], [(1860, 1050, 2020, 1250)], cfg={"algo": algo})
        d0 = decide(det, "10x15", cfg, "natural")
        check(f"[{algo}] без «Человек» кадр не приближается", d0["scale"] == 1.0 and d0["orient"] == "landscape")
        det, cfg = _mk(3000, 2000, [(150, 300, 650, 1900), (2300, 300, 2800, 1900)], [(300, 350, 480, 560), (2450, 350, 2630, 560)],
                       cfg={"algo": algo, "portrait_fit": True})
        d = decide(det, "10x15", cfg, "landscape")
        check(f"[{algo}] «Человек»: широкая группа — масштаб 1", d["scale"] > 0.95, str(d["scale"]))
    print("ИТОГО:", "все проверки пройдены" if not bad else "ошибки: " + ", ".join(bad))
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
