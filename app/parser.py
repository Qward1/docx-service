from __future__ import annotations

import re

from .models import (
    DEFAULT_EXECUTOR_DEPARTMENT,
    DEFAULT_EXECUTOR_NAME,
    DEFAULT_EXECUTOR_PHONE,
    DEFAULT_REFERENCE_LINE,
    DEFAULT_SIGNER_NAME,
    DEFAULT_SOURCE_LINE_1,
    DEFAULT_SOURCE_LINE_2,
    DEFAULT_SUBJECT_TITLE,
    LetterData,
    LetterOverrides,
)


REFERENCE_RE = re.compile(
    r"(от\s+\d{1,2}\s+[А-Яа-яЁё]+\s+\d{4}\s*г?\.?\s*№+\s*[-A-Za-zА-Яа-яЁё0-9/]+)",
    re.IGNORECASE,
)
FULL_NAME_RE = re.compile(
    r"\b([А-ЯЁ][а-яё]+(?:-[А-ЯЁ][а-яё]+)?\s+[А-ЯЁ][а-яё]+(?:\s+[А-ЯЁ][а-яё]+)?)\b"
)
SHORT_NAME_RE = re.compile(r"\b([А-ЯЁ][а-яё]+(?:-[А-ЯЁ][а-яё]+)?\s+[А-ЯЁ]\.[А-ЯЁ]\.)\b")
LABELLED_NAME_RE = [
    re.compile(r"(?:заявитель|фио|ф\.и\.о\.)\s*[:\-]\s*(.+)$", re.IGNORECASE),
    re.compile(r"^от\s+(.+)$", re.IGNORECASE),
]
ORG_STOPWORDS = {
    "правительства",
    "российской",
    "федерации",
    "департамент",
    "министерство",
    "минэкономразвития",
    "аппарат",
    "россии",
}
META_LINE_PATTERNS = (
    "тел.",
    "телефон",
    "e-mail",
    "email",
    "исп.",
    "доб.",
)


def parse_letter_data(text: str, overrides: LetterOverrides) -> LetterData:
    normalized = normalize_text(text)
    lines = [line for line in normalized.splitlines() if line]

    applicant_display = normalize_applicant_name(overrides.applicant_name) or extract_applicant_name(lines)
    subject_title = overrides.subject_title or DEFAULT_SUBJECT_TITLE
    reference_line = overrides.reference_line or extract_reference_line(normalized, lines) or DEFAULT_REFERENCE_LINE

    source_line1, source_line2 = resolve_source_lines(lines, overrides, reference_line)
    topic = extract_topic(lines)
    body_paragraphs = resolve_body_paragraphs(normalized, lines, overrides, topic)

    executor_department = overrides.executor_department or DEFAULT_EXECUTOR_DEPARTMENT
    dept_line1, dept_line2 = split_text_to_two_lines(executor_department, max_line_length=38)

    return LetterData(
        applicant_display=applicant_display or "заявителя",
        subject_title=subject_title,
        source_line1=source_line1,
        source_line2=source_line2,
        reference_line=reference_line,
        body_paragraphs=body_paragraphs,
        signer_name=overrides.signer_name or DEFAULT_SIGNER_NAME,
        executor_name=overrides.executor_name or DEFAULT_EXECUTOR_NAME,
        executor_phone=overrides.executor_phone or DEFAULT_EXECUTOR_PHONE,
        executor_department_line1=dept_line1,
        executor_department_line2=dept_line2,
        extracted_text=normalized,
        topic=topic,
    )


def normalize_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\xa0", " ")
    cleaned_lines = [" ".join(line.split()) for line in text.splitlines()]
    return "\n".join(line for line in cleaned_lines if line).strip()


def normalize_applicant_name(name: str | None) -> str | None:
    if not name:
        return None
    return to_brief_name(" ".join(name.split()))


def extract_reference_line(text: str, lines: list[str]) -> str | None:
    for line in lines:
        match = REFERENCE_RE.search(line)
        if match:
            return cleanup_reference_line(match.group(1))

    match = REFERENCE_RE.search(text)
    if match:
        return cleanup_reference_line(match.group(1))
    return None


def cleanup_reference_line(value: str) -> str:
    normalized = " ".join(value.replace("№ №", "№").replace("№№", "№").split())
    return normalized.strip(" .")


def resolve_source_lines(
    lines: list[str],
    overrides: LetterOverrides,
    reference_line: str,
) -> tuple[str, str]:
    if overrides.source_line1 or overrides.source_line2:
        return (
            overrides.source_line1 or DEFAULT_SOURCE_LINE_1,
            overrides.source_line2 or DEFAULT_SOURCE_LINE_2,
        )

    source_title = overrides.source_title or extract_source_title(lines, reference_line)
    if not source_title:
        return DEFAULT_SOURCE_LINE_1, DEFAULT_SOURCE_LINE_2

    line1, line2 = split_text_to_two_lines(source_title, max_line_length=31)
    if not line2:
        line2 = DEFAULT_SOURCE_LINE_2
    return line1, line2


def extract_source_title(lines: list[str], reference_line: str) -> str | None:
    for index, line in enumerate(lines):
        lower = line.lower()
        if reference_line in line:
            prefix = line.split(reference_line, 1)[0].strip(" ,.;")
            if prefix:
                return prefix
            if index > 0:
                previous = lines[index - 1].strip(" ,.;")
                if previous:
                    return previous

        if lower.startswith(("письмо", "обращение", "запрос", "заявление")):
            if "от " in lower and "№" in line:
                return line.split("от", 1)[0].strip(" ,.;")
            if len(line) <= 90:
                return line.strip(" ,.;")
    return None


def extract_applicant_name(lines: list[str]) -> str | None:
    for line in lines:
        for pattern in LABELLED_NAME_RE:
            match = pattern.search(line)
            if not match:
                continue
            candidate = cleanup_name_candidate(match.group(1))
            if candidate:
                return candidate

    for line in reversed(lines):
        short_match = SHORT_NAME_RE.search(line)
        if short_match:
            candidate = cleanup_name_candidate(short_match.group(1))
            if candidate:
                return candidate

        full_match = FULL_NAME_RE.search(line)
        if full_match:
            candidate = cleanup_name_candidate(full_match.group(1))
            if candidate:
                return candidate
    return None


def cleanup_name_candidate(value: str) -> str | None:
    candidate = " ".join(value.replace(",", " ").split()).strip()
    if not candidate:
        return None

    tokens = [token.strip(".").lower() for token in candidate.split()]
    if any(token in ORG_STOPWORDS for token in tokens):
        return None
    return to_brief_name(candidate)


def to_brief_name(name: str) -> str:
    if SHORT_NAME_RE.fullmatch(name):
        return name

    parts = name.split()
    if len(parts) >= 3:
        initials = "".join(f"{part[0]}." for part in parts[1:3])
        return f"{parts[0]} {initials}"
    if len(parts) == 2:
        return f"{parts[0]} {parts[1][0]}."
    return name


def extract_topic(lines: list[str]) -> str | None:
    for line in lines:
        lower = line.lower()
        if lower.startswith("тема:"):
            topic = line.split(":", 1)[1].strip(" .")
            if topic:
                return topic

    for line in lines:
        if line.startswith(("О ", "Об ", "Обо ")) and 6 <= len(line) <= 120:
            return line.strip(" .")

    for line in lines:
        if looks_like_content_line(line):
            sentence = first_sentence(line)
            if sentence:
                return sentence.strip(" .")
    return None


def resolve_body_paragraphs(
    text: str,
    lines: list[str],
    overrides: LetterOverrides,
    topic: str | None,
) -> list[str]:
    if overrides.body_text:
        paragraphs = split_into_paragraphs(overrides.body_text)
        if paragraphs:
            return paragraphs

    excerpt = build_excerpt(text, lines)

    first = "Минэкономразвития России рассмотрело поступившее обращение."
    if topic:
        first = f'Минэкономразвития России рассмотрело поступившее обращение по теме "{topic.strip(" .")}".'

    second = (
        "Сообщаем, что изложенные в обращении доводы и предложения приняты к сведению "
        "и будут рассмотрены в пределах компетенции Министерства."
    )

    paragraphs = [first, second]
    if excerpt:
        paragraphs.append(f"В обращении, в частности, затронуты следующие вопросы: {excerpt}.")
    return paragraphs


def split_into_paragraphs(text: str) -> list[str]:
    blocks = [normalize_paragraph(block) for block in re.split(r"\n\s*\n", text)]
    return [block for block in blocks if block]


def normalize_paragraph(text: str) -> str:
    return " ".join(text.replace("\n", " ").split()).strip()


def build_excerpt(text: str, lines: list[str]) -> str | None:
    sentences = [normalize_paragraph(chunk) for chunk in re.split(r"(?<=[.!?])\s+", text)]
    candidates = [sentence for sentence in sentences if sentence and looks_like_content_line(sentence)]
    if not candidates:
        candidates = [line for line in lines if looks_like_content_line(line)]
    if not candidates:
        return None

    excerpt = candidates[0]
    if len(excerpt) > 220:
        excerpt = excerpt[:217].rsplit(" ", 1)[0] + "..."
    return excerpt.rstrip(".")


def looks_like_content_line(line: str) -> bool:
    lower = line.lower()
    if len(line) < 20:
        return False
    if any(pattern in lower for pattern in META_LINE_PATTERNS):
        return False
    if lower.startswith(("письмо", "обращение", "запрос", "заявление", "тема:", "заявитель:")):
        return False
    if REFERENCE_RE.search(line):
        return False
    if SHORT_NAME_RE.fullmatch(line):
        return False
    if FULL_NAME_RE.fullmatch(line):
        return False
    return True


def first_sentence(text: str) -> str | None:
    parts = re.split(r"(?<=[.!?])\s+", text, maxsplit=1)
    sentence = parts[0].strip()
    return sentence if sentence else None


def split_text_to_two_lines(text: str, max_line_length: int) -> tuple[str, str]:
    clean = " ".join(text.split())
    if len(clean) <= max_line_length:
        return clean, ""

    middle = len(clean) // 2
    candidate_indexes = [index for index, char in enumerate(clean) if char == " "]
    if not candidate_indexes:
        return clean, ""

    best_index = min(candidate_indexes, key=lambda idx: abs(idx - middle))
    line1 = clean[:best_index].strip()
    line2 = clean[best_index + 1 :].strip()

    if len(line1) > max_line_length:
        overflow_indexes = [idx for idx in candidate_indexes if idx < max_line_length]
        if overflow_indexes:
            best_index = overflow_indexes[-1]
            line1 = clean[:best_index].strip()
            line2 = clean[best_index + 1 :].strip()

    return line1 or clean, line2
