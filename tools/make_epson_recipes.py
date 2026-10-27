# -*- coding: utf-8 -*-
"""Строит epson_recipes.py из снимков DEVMODE (папка dmsnaps с manifest.csv).
Запуск: python tools/make_epson_recipes.py <папка_dmsnaps> > epson_recipes.py
Для каждой модели: байты, которые отличаются между режимами качества, и между «с полями» / «без полей»."""
import csv
import os
import pprint
import sys

PUB = 220
QUALITY_SNAPS = {0: ("draft",), 1: ("base",), 2: ("bestphoto", "high")}
# источник подачи и носитель (публичный @196 и его зеркало в приватной зоне) обрабатываются отдельно
MEDIA_MIRROR = {796: 116, 3704: 144}       # смещение зеркала dmMediaType в приватной зоне по размеру приватной зоны
SKIP_BORDER = {88, 89, 196, 197}


def rd(d, rows, model, opts):
    for o in opts:
        for r in rows:
            if r["model"] == model and r["option"] == o and r["status"].startswith("ok"):
                return open(os.path.join(d, r["file"]), "rb").read()
    return None


def diff(a, b):
    return {i for i in range(min(len(a), len(b))) if a[i] != b[i]}


def pack(blob, offs):
    pub = {i: blob[i] for i in sorted(offs) if i < PUB}
    priv = {i - PUB: blob[i] for i in sorted(offs) if i >= PUB}
    return {"pub": pub, "priv": priv}


def main(d):
    rows = list(csv.DictReader(open(os.path.join(d, "manifest.csv"), encoding="utf-8")))
    out = {}
    for model in sorted({r["model"] for r in rows}):
        base = rd(d, rows, model, ("base",))
        q = {lvl: rd(d, rows, model, names) for lvl, names in QUALITY_SNAPS.items()}
        q = {k: v for k, v in q.items() if v is not None}
        qoffs = set()
        for v in q.values():
            qoffs |= diff(base, v)
        entry = {"quality": {k: pack(v, qoffs) for k, v in q.items()}}
        bl = rd(d, rows, model, ("borderless_glossy", "borderless"))
        if bl is not None:
            mirror = MEDIA_MIRROR.get(len(base) - PUB)
            skip = SKIP_BORDER | ({PUB + mirror, PUB + mirror + 1} if mirror else set())
            boffs = diff(base, bl) - qoffs - skip
            on, off = pack(bl, boffs), pack(base, boffs)
            src = lambda b: b[88] | b[89] << 8
            media = bl[196] | bl[197] << 8
            if media == 1 and mirror:           # драйвер держит носитель в зеркале, а публичное поле откатывает
                media = bl[PUB + mirror] | bl[PUB + mirror + 1] << 8
            entry["border"] = {"on": on, "off": off, "src_on": src(bl), "src_off": src(base),
                               "media": media if media != 1 else 0}
        entry["media_mirror"] = MEDIA_MIRROR.get(len(base) - PUB)
        out[model.upper()] = entry
    print("# -*- coding: utf-8 -*-")
    print('"""Рецепты DEVMODE моделей Epson (создан tools/make_epson_recipes.py из снимков драйвера). Не править вручную."""')
    print("RECIPES = " + pprint.pformat(out, width=140, compact=True))


if __name__ == "__main__":
    main(sys.argv[1])
