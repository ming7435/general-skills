"""Index slide text and source media in presentation order. Python standard library."""
import argparse
import json
import posixpath
import re
import shutil
import tempfile
import xml.etree.ElementTree as ET
from functools import lru_cache
from pathlib import Path
from urllib.parse import unquote
from zipfile import ZipFile


def local(tag):
    return tag.rsplit("}", 1)[-1]


def extract(source, output):
    output = output.resolve()
    if output.exists():
        raise ValueError(f"Output exists: {output}. Choose a new directory.")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=output.parent) as tmp, ZipFile(source) as deck:
        stage = Path(tmp) / "index"
        assets = stage / "assets"
        assets.mkdir(parents=True)
        names = set(deck.namelist())

        @lru_cache(maxsize=None)
        def relations(part):
            folder = posixpath.dirname(part)
            path = posixpath.join(folder, "_rels", posixpath.basename(part) + ".rels")
            if path not in names:
                return {}
            result = {}
            for item in ET.fromstring(deck.read(path)):
                if item.get("TargetMode") == "External":
                    continue
                target = unquote(item.attrib["Target"]).split("#", 1)[0]
                target = posixpath.normpath(posixpath.join(folder, target)).lstrip("/")
                result[item.attrib["Id"]] = (item.attrib["Type"].rsplit("/", 1)[-1], target)
            return result

        parts = [p for p in sorted(names) if not p.endswith("/") and
                 (p.startswith("ppt/media/") or re.fullmatch(r"ppt/charts/[^/]+\.xml", p))]
        files = {}
        for i, member in enumerate(parts, 1):
            # Generated local names avoid collisions, reserved Windows names and path traversal.
            ext = Path(posixpath.basename(member)).suffix.lower()
            if not re.fullmatch(r"\.[a-z0-9]{1,12}", ext):
                ext = ".bin"
            target = assets / f"asset-{i:04d}{ext}"
            with deck.open(member) as src, target.open("wb") as dst:
                shutil.copyfileobj(src, dst)
            files[member] = "assets/" + target.name

        @lru_cache(maxsize=None)
        def page_content(part):
            root = ET.fromstring(deck.read(part))
            xml_rels = relations(part)
            media = []
            paragraphs = []
            for node in root.iter():
                if local(node.tag) == "p":
                    words = "".join(e.text or "" for e in node.iter() if local(e.tag) == "t")
                    if words.strip():
                        paragraphs.append(words)
                for attr, rid in node.attrib.items():
                    if not attr.startswith("{") or not attr.split("}")[0].endswith("/relationships"):
                        continue
                    target = xml_rels.get(rid, ("", ""))[1]
                    if target in files and target not in media:
                        media.append(target)
            return paragraphs, media, root.get("show") in ("0", "false")

        def parents(part, kind):
            return [target for rel, target in relations(part).values() if rel == kind and target in names]

        presentation = "ppt/presentation.xml"
        document = ET.fromstring(deck.read(presentation))
        slide_order = next(e for e in document if local(e.tag) == "sldIdLst")
        pages = []
        for page, node in enumerate(slide_order, 1):
            rid = next(v for k, v in node.attrib.items() if k.endswith("/relationships}id"))
            slide = relations(presentation)[rid][1]
            paragraphs, direct, hidden = page_content(slide)
            inherited = {}
            for layout in parents(slide, "slideLayout"):
                for part in [layout, *parents(layout, "slideMaster")]:
                    refs = page_content(part)[1]
                    if refs:
                        inherited[part] = refs
            pages.append(dict(page=page, part=slide, hidden=hidden, text=paragraphs,
                              direct=direct, layout_and_master_candidates=inherited))
        manifest = dict(source=source.name, assets=files, pages=pages)
        (stage / "index.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        stage.rename(output)
    print(f"{len(pages)} slides, {len(files)} source parts: {output}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pptx", type=Path)
    parser.add_argument("out", type=Path, help="New directory for index.json and extracted source files.")
    args = parser.parse_args()
    extract(args.pptx, args.out)
