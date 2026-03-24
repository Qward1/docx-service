from __future__ import annotations

import copy
import io
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from .models import LetterData


W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
XML_NS = "http://www.w3.org/XML/1998/namespace"
NS = {"w": W_NS}

ET.register_namespace("w", W_NS)
ET.register_namespace("xml", XML_NS)

DOCUMENT_XML_PATH = "word/document.xml"
BODY_PLACEHOLDER_START = "{{BODY_START}}"
BODY_PLACEHOLDER_END = "{{BODY_END}}"


def render_docx(template_path: Path, data: LetterData) -> bytes:
    with zipfile.ZipFile(template_path, "r") as source:
        archive_map = {name: source.read(name) for name in source.namelist()}

    root = ET.fromstring(archive_map[DOCUMENT_XML_PATH])

    replace_paragraph_texts(
        root,
        {
            "{{RECIPIENT_BLOCK}}": data.recipient_block,
            "{{SUBJECT_TITLE}}": data.subject_title,
            "{{REFERENCE_CAPTION}}": data.reference_caption,
            "{{SALUTATION}}": data.salutation,
            "Т.С. Митюков": data.signer_name,
            "Исп. Шишкин Е.Н.": f"Исп. {data.executor_name}",
            "8 (495) 870-29-21 доб. 18569": data.executor_phone,
        },
    )
    replace_signature_department(root, data)
    replace_body_paragraphs(root, data.body_paragraphs)
    turn_red_text_black(root)

    archive_map[DOCUMENT_XML_PATH] = ET.tostring(root, encoding="utf-8", xml_declaration=True)

    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as destination:
        for name, payload in archive_map.items():
            destination.writestr(name, payload)
    return output.getvalue()


def replace_paragraph_texts(root: ET.Element, replacements: dict[str, str]) -> None:
    for paragraph in root.findall(".//w:p", NS):
        current = paragraph_text(paragraph)
        if current in replacements:
            rewrite_paragraph(paragraph, replacements[current])


def replace_body_paragraphs(root: ET.Element, paragraphs: list[str]) -> None:
    body = root.find(".//w:body", NS)
    if body is None:
        raise ValueError("В шаблоне не найден body")

    body_children = list(body)
    start_index = None
    end_index = None
    template_start = None
    template_end = None

    for index, child in enumerate(body_children):
        if child.tag != w_tag("p"):
            continue
        text = paragraph_text(child)
        if start_index is None and text.startswith(BODY_PLACEHOLDER_START):
            start_index = index
            template_start = child
            continue
        if start_index is not None and text.startswith(BODY_PLACEHOLDER_END):
            end_index = index
            template_end = child
            break

    if start_index is None or end_index is None or template_start is None or template_end is None:
        raise ValueError("В шаблоне не найдены абзацы для тела письма")

    for index in range(end_index, start_index - 1, -1):
        body.remove(body_children[index])

    insert_index = start_index
    for position, paragraph in enumerate(paragraphs):
        template = template_start if position == 0 else template_end
        body.insert(insert_index + position, build_paragraph(template, paragraph))


def build_paragraph(template: ET.Element, text: str) -> ET.Element:
    paragraph = copy.deepcopy(template)
    rewrite_paragraph(paragraph, text)
    return paragraph


def rewrite_paragraph(paragraph: ET.Element, text: str) -> None:
    first_run = paragraph.find("w:r", NS)
    run_props = None
    if first_run is not None:
        original_rpr = first_run.find("w:rPr", NS)
        if original_rpr is not None:
            run_props = copy.deepcopy(original_rpr)

    preserved_children = []
    for child in paragraph:
        if child.tag == w_tag("pPr"):
            continue
        if child.find(".//w:drawing", NS) is not None:
            preserved_children.append(copy.deepcopy(child))

    for child in list(paragraph):
        if child.tag != w_tag("pPr"):
            paragraph.remove(child)

    for child in preserved_children:
        paragraph.append(child)

    wrote_content = False
    for line_index, line in enumerate(text.split("\n")):
        if line_index > 0:
            paragraph.append(build_control_run(run_props, "br"))
            wrote_content = True

        segments = line.split("\t")
        for segment_index, segment in enumerate(segments):
            if segment:
                paragraph.append(build_text_run(run_props, segment))
                wrote_content = True
            if segment_index < len(segments) - 1:
                paragraph.append(build_control_run(run_props, "tab"))
                wrote_content = True

    if not wrote_content:
        paragraph.append(build_text_run(run_props, ""))


def replace_signature_department(root: ET.Element, data: LetterData) -> None:
    paragraphs = root.findall(".//w:p", NS)
    for index, paragraph in enumerate(paragraphs):
        text = paragraph_text(paragraph)
        if text == "Директор Департамента бюджетного планирования, государственных программ":
            rewrite_paragraph(paragraph, f"Директор {data.executor_department_line1}")
            if index + 1 < len(paragraphs):
                next_paragraph = paragraphs[index + 1]
                next_text = paragraph_text(next_paragraph)
                if next_text == "и национальных проектовТ.С. Митюков":
                    rewrite_paragraph(next_paragraph, f"{data.executor_department_line2}\t{data.signer_name}")


def turn_red_text_black(root: ET.Element) -> None:
    for node in root.findall(".//w:color", NS):
        value = node.get(w_tag("val"))
        if value == "FF0000":
            node.set(w_tag("val"), "000000")


def paragraph_text(paragraph: ET.Element) -> str:
    return "".join(node.text or "" for node in paragraph.findall(".//w:t", NS)).strip()


def needs_preserve_space(text: str) -> bool:
    return text.startswith(" ") or text.endswith(" ") or "  " in text


def build_text_run(run_props: ET.Element | None, text: str) -> ET.Element:
    run = ET.Element(w_tag("r"))
    if run_props is not None:
        run.append(copy.deepcopy(run_props))
    text_node = ET.SubElement(run, w_tag("t"))
    if needs_preserve_space(text):
        text_node.set(f"{{{XML_NS}}}space", "preserve")
    text_node.text = text
    return run


def build_control_run(run_props: ET.Element | None, control: str) -> ET.Element:
    run = ET.Element(w_tag("r"))
    if run_props is not None:
        run.append(copy.deepcopy(run_props))
    ET.SubElement(run, w_tag(control))
    return run


def w_tag(local_name: str) -> str:
    return f"{{{W_NS}}}{local_name}"
