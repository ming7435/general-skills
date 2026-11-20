import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "assets" / "system"
BROWSER = os.environ.get("POSTER_BROWSER_PATH")


class PosterTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.work = Path(tmp.name)
        self.layout = shutil.copytree(TEMPLATE, self.work / "system") / "layout.html"
        self.output = self.work / "poster.png"

    def export(self, *options):
        command = [sys.executable, str(ROOT / "scripts" / "export_poster.py"), str(self.layout), str(self.output)]
        if BROWSER:
            command.extend(["--browser-path", BROWSER])
        return subprocess.run(command + list(options), capture_output=True, text=True)

    def test_card_and_flag_export(self):
        for mode, scale in (("cards", 1), ("flags", 2)):
            with self.subTest(mode=mode):
                html = self.layout.read_text(encoding="utf-8").replace('data-flow="cards"', f'data-flow="{mode}"')
                self.layout.write_text(html, encoding="utf-8")
                result = self.export("--scale", str(scale), "--overwrite")
                self.assertEqual(result.returncode, 0, result.stderr)
                png = self.output.read_bytes()
                self.assertEqual(png[:8], b"\x89PNG\r\n\x1a\n")
                self.assertEqual(struct.unpack(">II", png[16:24]), (941 * scale, 1672 * scale))

    def test_missing_background_prevents_delivery(self):
        (self.layout.parent / "background.png").unlink()
        result = self.export()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("background.png", result.stderr)
        self.assertFalse(self.output.exists())

    def test_existing_output_is_preserved(self):
        self.output.write_bytes(b"previous")
        self.assertNotEqual(self.export().returncode, 0)
        self.assertEqual(self.output.read_bytes(), b"previous")

    def test_nodes_and_section_spacing(self):
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(executable_path=BROWSER)
            page = browser.new_page()
            page.goto(self.layout.as_uri())
            for mode in ("cards", "flags"):
                with self.subTest(mode=mode):
                    page.locator(".gate-group").evaluate("(el, mode) => el.dataset.flow = mode", mode)
                    nodes = page.locator(".gates li").evaluate_all(
                        "items => items.map(el => [el.querySelector('b').textContent, "
                        "Array.from(el.querySelectorAll('span'), s => s.textContent).join(''), "
                        "el.getBoundingClientRect().top])"
                    )
                    expected = [("QG1", "样机试制决策"), ("QG2", "小批试产决策"), ("QG3", "定型上市决策")]
                    self.assertEqual([(code, name) for code, name, y in nodes], expected)
                    heights = [y for code, name, y in nodes]
                    if mode == "flags":
                        self.assertGreater(heights[0], heights[1])
                        self.assertGreater(heights[1], heights[2])
                    else:
                        self.assertEqual(len(set(heights)), 1)
                    self.assertEqual(page.locator(".steps").is_visible(), mode == "flags")
                    self.assertEqual(page.locator(".rail").is_visible(), mode == "cards")
                    page.locator("#poster").evaluate(
                        "el => {el.style.setProperty('--gate-offset', '30px'); el.style.setProperty('--lower-offset', '30px')}"
                    )
                    sections = [page.locator(s).bounding_box() for s in (".identity", ".gate-group", ".upgrades", ".schedule")]
                    for upper, lower in zip(sections, sections[1:]):
                        self.assertLess(upper["y"] + upper["height"], lower["y"])
                    self.assertLess(sections[-1]["y"] + sections[-1]["height"], 1672)


if __name__ == "__main__":
    unittest.main()
