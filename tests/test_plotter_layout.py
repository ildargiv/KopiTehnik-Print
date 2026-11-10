import plotter_layout as pl


def lay():
    L = pl.Layout(roll_w=610, edge=5, gap=10)
    return L


def test_length_and_units():
    L = lay()
    L.add(pl.Item("a.jpg", 300, 200, x=0, y=0))
    L.add(pl.Item("b.jpg", 300, 400, x=0, y=210))
    assert L.length() == 610 + 5
    assert pl.to_mm(2, "cm") == 20 and abs(pl.from_mm(25.4, "in") - 1) < 1e-9


def test_rotate_keeps_center_and_dims():
    i = pl.Item("a", 200, 100, x=50, y=50)
    i.rotate()
    assert (i.ow, i.oh) == (100, 200)
    assert (i.x + i.ow / 2, i.y + i.oh / 2) == (150, 100)


def test_ratio_and_dpi():
    i = pl.Item("a", 100, 50, px_w=1000, px_h=500)
    i.set_width(200)
    assert i.h == 100
    assert round(i.dpi()) == 127
    i.set_size_for_dpi(300)
    assert round(i.w, 2) == round(1000 / 300 * 25.4, 2)


def test_problems():
    L = lay()
    L.add(pl.Item("a", 200, 200, x=0, y=0))
    L.add(pl.Item("b", 200, 200, x=205, y=0))     # зазор 5 < 10
    L.add(pl.Item("c", 200, 200, x=100, y=100))   # перекрытие
    L.add(pl.Item("d", 700, 50, x=0, y=500))      # за полем
    kinds = {k for _, k in L.problems()}
    assert {"gap", "overlap", "out"} <= kinds


def test_autopack_shorter_and_valid():
    L = lay()
    for k in range(6):
        L.add(pl.Item("f%d" % k, 250, 400, y=k * 410))
    before, after = L.autopack()
    assert after < before
    assert not [p for p in L.problems() if p[1] in ("overlap", "gap", "out")]


def test_autopack_rotates_to_fit():
    L = lay()
    L.add(pl.Item("wide", 900, 300))              # шире рулона: поворот обязателен
    L.autopack()
    assert L.items[0].rot == 90 and L.items[0].right <= L.printable_w + 0.1


def test_json_and_undo():
    L = lay()
    h = pl.History(L)
    h.push()
    L.add(pl.Item("a", 100, 100))
    L2 = pl.Layout.from_json(L.to_json())
    assert len(L2.items) == 1
    assert h.undo() and not L.items
    assert h.redo() and len(L.items) == 1


def test_too_long_and_snap():
    L = lay()
    i = L.add(pl.Item("a", 100, 4000))
    assert L.too_long()
    j = L.add(pl.Item("b", 100, 100, x=103, y=0))
    L.items.remove(i)
    k = L.add(pl.Item("c", 100, 100, x=2, y=3))
    L.snap(k)
    assert (k.x, k.y) == (0, 0)


def test_standard_paper_snap_and_no_rescale_on_roll_change():
    assert pl.standard_paper(296, 421)[0] == "A3"
    n, w, h = pl.standard_paper(420.5, 296.5)
    assert (n, w, h) == ("A3", 420, 297)                     # альбомная ориентация сохраняется
    assert pl.standard_paper(100, 100) is None
    assert pl.standard_paper(10, 10, 3508, 4961)[0] == "A3"  # по пикселям: A3 при 300 dpi
    L = pl.Layout(roll_w=610)
    it = L.add(pl.Item("a3", 297, 420, x=0, y=0))
    L.roll_w = 914
    L.roll_w = 432
    assert (it.w, it.h) == (297, 420)


def test_marks_proof_and_json():
    L = pl.Layout(roll_w=610, edge=5, gap=10)
    L.marks = True
    L.add(pl.Item("a", 200, 100, x=0, y=0))
    L.add(pl.Item("b", 200, 100, x=210, y=0))
    segs = L.mark_segments()
    assert len(segs) == 2 * 4 * 2                               # 2 файла × 4 угла × 2 штриха
    L.gap = 3
    assert "marks" in {k for _, k in L.problems()}
    L.gap = 10
    P = L.proof_layout()
    assert P.paper_size_mm() == (210.0, 297.0)
    assert P.items[0].w < L.items[0].w and abs(P.items[0].w / P.items[0].h - 2.0) < 1e-9
    assert pl.Layout.from_json(L.to_json()).marks is True
