import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import doc_tools as d


class DocTools(unittest.TestCase):
    def test_range(self):
        self.assertEqual(d.parse_range("", 4), [0, 1, 2, 3])
        self.assertEqual(d.parse_range("1-2, 4", 5), [0, 1, 3])
        self.assertEqual(d.parse_range("3-", 5), [2, 3, 4])
        self.assertEqual(d.parse_range("2,2,1", 5), [1, 0])
        for bad in ("0", "6", "3-2", "a", "1-9"):
            with self.assertRaises(ValueError):
                d.parse_range(bad, 5)

    def test_place(self):
        x, y, w, h, rot = d.place_page(210, 297, 210, 297)
        self.assertEqual((round(x), round(y), round(w), round(h), rot), (0, 0, 210, 297, False))
        x, y, w, h, rot = d.place_page(105, 148.5, 210, 297, "fit")          # увеличить вдвое
        self.assertEqual((round(w), round(h)), (210, 297))
        x, y, w, h, rot = d.place_page(105, 148.5, 210, 297, "shrink")       # не увеличивать
        self.assertEqual((round(w), round(h)), (105, 148))
        x, y, w, h, rot = d.place_page(297, 210, 210, 297)                    # альбомная страница на книжном листе
        self.assertTrue(rot)
        self.assertEqual((round(w), round(h)), (210, 297))
        x, y, w, h, rot = d.place_page(210, 297, 210, 297, "fit", 10)
        self.assertEqual((round(x), round(w)), (10, 190))

    def test_cmd(self):
        self.assertEqual(d.edit_command("C.exe", "a.pdf", True, "o.pdf"), ["C.exe", "--edit", "a.pdf", "--ocr", "--out", "o.pdf"])
        import tempfile
        from pathlib import Path
        exe = Path(tempfile.mkdtemp()) / "Converter.exe"
        exe.write_bytes(b"")
        self.assertEqual(d.find_converter(str(exe)), str(exe))      # свой путь из настроек проверяется первым
        self.assertEqual(str(d.converter_candidates(str(exe))[0]), str(exe))


if __name__ == "__main__":
    unittest.main()
