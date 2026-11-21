"""Build an editable Chinese user manual from a UTF-8 JSON outline."""

import argparse
import json
import os
from io import BytesIO
from pathlib import Path
from tempfile import NamedTemporaryFile

from PIL import Image, ImageDraw, ImageFont, ImageOps
from docx import Document
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor


def validate(spec):
    for key in ("title", "intro"):
        if not isinstance(spec.get(key), str) or not spec[key].strip():
            raise ValueError(f"请填写 {key}")
    for name in ("setup", "workflow", "skills"):
        items = spec.get(name, []) if name == "setup" else spec.get(name)
        if not isinstance(items, list) or (name != "setup" and not items):
            raise ValueError(f"{name} 应为列表，workflow 和 skills 至少各有一项")
        for i, item in enumerate(items, 1):
            keys = ("name", "goal", "output") if name == "skills" else ("title", "text")
            for key in keys:
                if not isinstance(item.get(key), str) or not item[key].strip():
                    raise ValueError(f"请填写 {name}[{i}] 的 {key}")
            if name != "skills":
                continue
            if not isinstance(item.get("inputs"), list) or not all(isinstance(s,str) and s.strip() for s in item["inputs"]):
                raise ValueError(f"{item['name']} 的 inputs 应为文件名或链接名称列表")
            if not any(item.get(k) for k in ("turns","actions","image")):
                raise ValueError(f"{item['name']} 需提供操作步骤、示范对话或操作截图")
            if item.get("turns") and item.get("actions"):
                raise ValueError(f"{item['name']} 请择一使用 turns 或 actions，可另配截图")
            for t in item.get("turns", []):
                if t.get("who") not in ("user","assistant") or not t.get("text"):
                    raise ValueError(f"{item['name']} 的每条对话需含 who 和 text")
                if any(not f.get("name") for f in t.get("files", [])):
                    raise ValueError(f"{item['name']} 的附件缺少名称")


def font_for_chat(given):
    candidates = ([Path(given)] if given else [
        Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / "msyh.ttc",
        Path("/System/Library/Fonts/PingFang.ttc"),
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
        Path("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"),
    ])
    for path in candidates:
        if path.is_file():
            return str(path)
    if given:
        raise ValueError(f"找不到字体文件 {given}")
    return None


def load_picture(base, value):
    with Image.open(base / value) as original:
        im = ImageOps.exif_transpose(original).convert("RGBA")
        background = Image.new("RGB", im.size, "white")
        background.paste(im, mask=im.getchannel("A"))
        return background


def wrap(text, font, width):
    lines = []
    for paragraph in text.split("\n"):
        line = ""
        for ch in paragraph:
            if line and font.getlength(line + ch) > width:
                lines.append(line.rstrip())
                line = ""
            line += ch
        lines.append(line)
    return lines


def picture(paragraph, image, label, max_cm, width_cm=16.2):
    stream = BytesIO()
    image.save(stream, format="PNG")
    stream.seek(0)
    placed = min(width_cm, max_cm * image.width / image.height)
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    paragraph.paragraph_format.space_after = Pt(4)
    shape = paragraph.add_run().add_picture(stream, width=Cm(placed))
    shape._inline.docPr.set("descr", label)


def attachment_label(file):
    return (file["type"] + "　" if file.get("type") else "") + file["name"]


def draw_chat(turns, partner, fontpath, result, caption):
    """Render a composed exchange and preserve the file format displayed by its source."""
    width, bubble = 1100, 860
    label = ImageFont.truetype(fontpath, 23)
    normal = ImageFont.truetype(fontpath, 30)
    card = ImageFont.truetype(fontpath, 26)
    blocks = []
    current_y = 64
    for idx, turn in enumerate(turns):
        user = turn["who"] == "user"
        lines = wrap(turn["text"], normal, bubble - 40)
        labels = [wrap(attachment_label(f), card, bubble - 64) for f in turn.get("files", [])]
        height = 24 + len(lines) * 43 + sum(22 + len(ls) * 36 for ls in labels)
        inner = max([normal.getlength(s) + 40 for s in lines] +
                    [card.getlength(s) + 64 for ls in labels for s in ls])
        show_result = idx == len(turns) - 1 and not user and result is not None
        caplines = []
        if show_result:
            result = result.copy()
            result.thumbnail((bubble - 40, 515), Image.Resampling.LANCZOS)
            caplines = wrap(caption, label, bubble - 40) if caption else []
            height += result.height + 12 + 31 * len(caplines)
            inner = max([inner, result.width+40] + [label.getlength(s)+40 for s in caplines])
        box_w = min(bubble, max(150, round(inner)))
        x = width - 32 - box_w if user else 32
        blocks.append((turn, user, lines, labels, show_result, caplines, x, current_y, box_w, height))
        current_y += 35 + height + 20
    img = Image.new("RGB", (width, current_y + 5), "#F5F6F8")
    d = ImageDraw.Draw(img)
    d.rectangle((0, 0, width, 51), fill="#FFFFFF")
    d.text((30, 13), "示范对话", font=label, fill="#404D59", anchor="lt")
    for turn, user, lines, labels, show_result, caplines, x, y, box_w, height in blocks:
        d.text((x + box_w if user else x, y), "用户" if user else partner,
               fill="#526372", font=label, anchor="rt" if user else "lt")
        y += 35
        d.rounded_rectangle((x, y, x + box_w, y + height), radius=11,
                            fill="#E2EDFA" if user else "#FFFFFF", outline="#CFD8E1")
        top = y + 12
        for line in lines:
            d.text((x+20, top+2), line, font=normal, fill="#17242D", anchor="lt")
            top += 43
        for file_lines in labels:
            bottom = top + 12 + 36 * len(file_lines)
            d.rounded_rectangle((x+12,top,x+box_w-12,bottom),radius=6,fill="white",outline="#AABACB",width=2)
            for i, line in enumerate(file_lines):
                d.text((x+24,top+8+i*36),line,font=card,fill="#22394B",anchor="lt")
            top = bottom+10
        if show_result:
            for line in caplines:
                d.text((x+20,top+3),line,font=label,fill="#435D70",anchor="lt")
                top += 31
            img.paste(result,(x+20,top+5))
    return img


def set_styles(doc):
    page = doc.sections[0]
    page.page_width, page.page_height = Cm(21), Cm(29.7)
    page.left_margin = page.right_margin = Cm(2.4)
    page.top_margin = page.bottom_margin = Cm(2.25)
    for name, size in [("Normal",11),("Title",25),("Heading 1",17),("Heading 2",13),("Caption",9)]:
        style=doc.styles[name]
        style.font.name="Arial"
        style.font.size=Pt(size)
        style.font.bold=name in ("Title","Heading 1","Heading 2")
        style.font.italic=False
        style.font.color.rgb=RGBColor.from_string("171717" if name!="Caption" else "505050")
        fonts=style.element.get_or_add_rPr().rFonts
        for key in ("asciiTheme","hAnsiTheme","eastAsiaTheme","cstheme"):
            fonts.attrib.pop(qn("w:"+key), None)
        fonts.set(qn("w:eastAsia"),"Microsoft YaHei")
        pf=style.paragraph_format
        pf.space_before=Pt(8 if name.startswith("Heading") else 0)
        pf.space_after=Pt(5)
        pf.line_spacing=1.22
        if name=="Title":
            border=style.element.xpath("./w:pPr/w:pBdr")
            for b in border:
                b.getparent().remove(b)


def add_figure(doc, base, path, caption, max_cm=12):
    p=doc.add_paragraph()
    p.paragraph_format.keep_with_next=bool(caption)
    picture(p, load_picture(base, path), caption or Path(path).stem, max_cm)
    if caption:
        doc.add_paragraph(caption, "Caption")


def draw_map(doc, skills):
    table=doc.add_table(rows=1,cols=4)
    table.autofit=False
    widths=(2.6,3.6,5.4,4.6)
    for col, sz in zip(table.columns,widths):
        col.width=Cm(sz)
    prop=table._tbl.tblPr
    borders=OxmlElement("w:tblBorders")
    for edge in ("top","left","bottom","right","insideH","insideV"):
        b=OxmlElement("w:"+edge)
        for attr,val in [("val","single"),("sz","5"),("color","D9D9D9")]:
            b.set(qn("w:"+attr),val)
        borders.append(b)
    prop.append(borders)
    data=[("功能","想做什么","要提供的材料","能得到什么")]
    data.extend((s["name"],s["goal"],"\n".join(s["inputs"]) or "无需文件",s["output"]) for s in skills)
    for i, values in enumerate(data):
        row=table.rows[0] if i==0 else table.add_row()
        trpr=row._tr.get_or_add_trPr()
        trpr.append(OxmlElement("w:cantSplit"))
        if i==0:
            trpr.append(OxmlElement("w:tblHeader"))
        for cell, val, sz in zip(row.cells,values,widths):
            cell.width=Cm(sz)
            cell.vertical_alignment=WD_CELL_VERTICAL_ALIGNMENT.CENTER
            p=cell.paragraphs[0]
            p.paragraph_format.space_before=Pt(3)
            p.paragraph_format.space_after=Pt(3)
            run=p.add_run(val)
            run.bold=i==0
            run.font.size=Pt(10)
            if i==0:
                shade=OxmlElement("w:shd")
                shade.set(qn("w:fill"),"EDEFF1")
                cell._tc.get_or_add_tcPr().append(shade)


def labeled(doc, name, content):
    p=doc.add_paragraph()
    p.add_run(name+"　").bold=True
    p.add_run(content)


def build(spec, base, out, fontpath):
    doc=Document()
    set_styles(doc)
    doc.core_properties.title=spec["title"]
    doc.add_paragraph(spec["title"], "Title")
    doc.add_paragraph(spec["intro"])
    for title, items in (("第一次使用",spec.get("setup",[])),("操作流程",spec["workflow"])):
        if not items:
            continue
        doc.add_heading(title,1)
        for idx,step in enumerate(items,1):
            doc.add_heading(f"{idx}　{step['title']}",2)
            doc.add_paragraph(step["text"])
            if step.get("image"):
                add_figure(doc,base,step["image"],step.get("caption",""))
    illustrated = any(any(s.get(k) for k in ("image", "result_image", "turns")) for s in spec["skills"])
    doc.add_heading("能力地图",1).paragraph_format.page_break_before=illustrated
    draw_map(doc,spec["skills"])
    for i,s in enumerate(spec["skills"],1):
        if i==1:
            doc.add_heading("单项功能示例",1).paragraph_format.page_break_before=illustrated
        heading=doc.add_heading(f"{i}　{s['name']}",2)
        heading.paragraph_format.page_break_before=i>1 and any(s.get(k) for k in ("image","result_image","turns"))
        if s.get("prepare"):
            labeled(doc,"准备资料",s["prepare"])
        if s.get("image"):
            add_figure(doc,base,s["image"],s.get("caption",""))
        for n,action in enumerate(s.get("actions",[]),1):
            doc.add_paragraph(f"{n}. {action}")
        turns=s.get("turns",[])
        result=s.get("result_image")
        if turns:
            partner=spec.get("assistant_name","助手")
            embedded=bool(fontpath and turns[-1]["who"]=="assistant" and result)
            if fontpath:
                chat=draw_chat(turns,partner,fontpath,load_picture(base,result) if embedded else None,
                               s.get("result_caption",""))
                transcript=[]
                for t in turns:
                    who="用户" if t["who"]=="user" else partner
                    transcript.append(who+"　"+t["text"])
                    transcript.extend(attachment_label(f) for f in t.get("files", []))
                picture(doc.add_paragraph(),chat,"示范对话\n"+"\n".join(transcript),15)
            else:
                doc.add_paragraph("示范对话","Caption")
                for t in turns:
                    labeled(doc,"用户" if t["who"]=="user" else partner,t["text"])
                    for f in t.get("files",[]):
                        labeled(doc,"文件或链接",attachment_label(f))
            if embedded:
                result=None
        if result:
            add_figure(doc,base,result,s.get("result_caption",""))
        labeled(doc,"结果",s.get("use") or s["output"])
    out.parent.mkdir(parents=True,exist_ok=True)
    with NamedTemporaryFile(dir=out.parent,suffix=".docx",delete=False) as temp:
        temp_path=Path(temp.name)
    try:
        doc.save(temp_path)
        os.replace(temp_path,out)
    finally:
        temp_path.unlink(missing_ok=True)


def main():
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument("outline",type=Path,help="UTF-8 JSON input")
    cli.add_argument("output",type=Path,help="Output .docx path")
    cli.add_argument("--font",help="CJK .ttf, .ttc or .otf font for dialogue examples")
    args=cli.parse_args()
    if args.output.suffix.lower()!=".docx":
        cli.error("输出文件应使用 .docx 扩展名")
    try:
        data=json.loads(args.outline.read_text(encoding="utf-8-sig"))
        validate(data)
        build(data,args.outline.resolve().parent,args.output,font_for_chat(args.font))
    except (ValueError, OSError, KeyError) as exc:
        cli.exit(1,f"生成失败：{exc}\n")


if __name__=="__main__":
    main()
