# Dify Workflow Для 2 PDF -> Knowledge -> LLM -> DOCX

Актуальная схема рассчитана на два входных PDF:

- `forwarding_pdf` — сопроводительное или пересылочное письмо;
- `appeal_pdf` — само обращение гражданина.

Итоговый `docx` теперь собирается по реальному образцу ответа Минэкономразвития России. В `Dify` нужно готовить содержательные поля для этого шаблона, а не старую условную "шапку".

## Схема Узлов

1. `Start`
2. `HTTP Request` -> `extract_forwarding`
3. `Code` -> `parse_forwarding_json`
4. `HTTP Request` -> `extract_appeal`
5. `Code` -> `parse_appeal_json`
6. `Code` -> `merge_inputs`
7. `Knowledge Retrieval` -> `retrieve_context`
8. `LLM` -> `draft_response`
9. `Code` -> `normalize_json`
10. `HTTP Request` -> `render_docx`
11. `Answer`

## Что Загрузить В Knowledge Base

Загрузите:

- [response-style-reference.md](/mnt/c/Users/Admin/Desktop/Опять работа/docx-service/docx-service/docs/dify-kb/response-style-reference.md)
- [ukaz-309-economic-priorities.md](/mnt/c/Users/Admin/Desktop/Опять работа/docx-service/docx-service/docs/dify-kb/ukaz-309-economic-priorities.md)

## 1. Start

Добавьте входные переменные:

- `forwarding_pdf` -> `Single File`
- `appeal_pdf` -> `Single File`
- `instructions` -> `Paragraph` -> optional

## 2. HTTP Request -> extract_forwarding

- `Method`: `POST`
- `URL`: `http://docx-service:8000/extract`
- если сервис доступен через host:
  `http://host.docker.internal:8119/extract`
- `Body`: `Binary`
- `Binary variable`: `forwarding_pdf`
- `Headers`:
  - `Content-Type: application/pdf`
  - `X-Filename: forwarding.pdf`

## 3. Code -> parse_forwarding_json

Входы:

- `body` = `extract_forwarding.body`
- `status_code` = `extract_forwarding.status_code`

Код:

```python
def main(body: str, status_code: int) -> dict:
    import json

    if status_code != 200:
        raise Exception(f"extract_forwarding failed: {status_code}, body={body}")

    data = json.loads(body)
    return {
        "text": data.get("text", ""),
        "parsed": data.get("parsed", {}) or {},
    }
```

Выходы:

- `text` -> `String`
- `parsed` -> `Object`

## 4. HTTP Request -> extract_appeal

Настройки такие же, но:

- `Binary variable`: `appeal_pdf`
- `X-Filename: appeal.pdf`

## 5. Code -> parse_appeal_json

Входы:

- `body` = `extract_appeal.body`
- `status_code` = `extract_appeal.status_code`

Код:

```python
def main(body: str, status_code: int) -> dict:
    import json

    if status_code != 200:
        raise Exception(f"extract_appeal failed: {status_code}, body={body}")

    data = json.loads(body)
    return {
        "text": data.get("text", ""),
        "parsed": data.get("parsed", {}) or {},
    }
```

Выходы:

- `text` -> `String`
- `parsed` -> `Object`

## 6. Code -> merge_inputs

Этот узел собирает черновой контекст для LLM. В новой схеме приоритетны:

- `recipient_block`
- `subject_title`
- `reference_caption`
- `salutation`
- `body_text`
- `signer_title`
- `signer_department`
- `signer_name`

Входы:

- `forwarding_text`
- `forwarding_parsed`
- `appeal_text`
- `appeal_parsed`

Код:

```python
def pick(*values):
    for value in values:
        if isinstance(value, str):
            value = value.strip()
        if value:
            return value
    return ""


def main(
    forwarding_text: str,
    forwarding_parsed: dict,
    appeal_text: str,
    appeal_parsed: dict,
) -> dict:
    forwarding_parsed = forwarding_parsed or {}
    appeal_parsed = appeal_parsed or {}

    applicant_name = pick(
        appeal_parsed.get("applicant_name"),
        forwarding_parsed.get("applicant_name"),
    )
    applicant_email = pick(
        appeal_parsed.get("applicant_email"),
        forwarding_parsed.get("applicant_email"),
    )

    recipient_block = pick(
        appeal_parsed.get("recipient_block"),
        forwarding_parsed.get("recipient_block"),
    )
    if not recipient_block:
        parts = [part for part in [applicant_name, applicant_email] if part]
        recipient_block = "\n".join(parts)

    merged_parsed = {
        "applicant_name": applicant_name,
        "applicant_email": applicant_email,
        "recipient_block": recipient_block,
        "subject_title": pick(
            appeal_parsed.get("subject_title"),
            forwarding_parsed.get("subject_title"),
            "О рассмотрении обращения гражданина",
        ),
        "reference_caption": pick(
            forwarding_parsed.get("reference_caption"),
            appeal_parsed.get("reference_caption"),
            "На обращение гражданина",
        ),
        "salutation": pick(
            appeal_parsed.get("salutation"),
            forwarding_parsed.get("salutation"),
            "Уважаемый заявитель!",
        ),
        "signer_title": "Директор",
        "signer_department": "Департамент бюджетного планирования, государственных программ и национальных проектов",
        "signer_name": "Т.С. Митюков",
        "body_text": pick(
            appeal_parsed.get("body_text"),
            forwarding_parsed.get("body_text"),
        ),
        "topic": pick(
            appeal_parsed.get("topic"),
            forwarding_parsed.get("topic"),
        ),
    }

    forwarding_text = (forwarding_text or "").strip()
    appeal_text = (appeal_text or "").strip()
    combined_text = "\n\n".join(part for part in [forwarding_text, appeal_text] if part).strip()
    knowledge_query = "\n".join(
        part
        for part in [
            merged_parsed.get("topic", ""),
            appeal_text,
            forwarding_text,
        ]
        if part
    ).strip()

    return {
        "forwarding_text": forwarding_text,
        "appeal_text": appeal_text,
        "combined_text": combined_text,
        "knowledge_query": knowledge_query,
        "merged_parsed": merged_parsed,
    }
```

Выходы:

- `forwarding_text` -> `String`
- `appeal_text` -> `String`
- `combined_text` -> `String`
- `knowledge_query` -> `String`
- `merged_parsed` -> `Object`

## 7. Knowledge Retrieval -> retrieve_context

- `Query`: `merge_inputs.knowledge_query`
- Используйте базу знаний со стилевым каноном и Указом № 309
- `top_k`: 4-6

## 8. LLM -> draft_response

Используйте шаблон из:

- [dify-prompt-template.md](/mnt/c/Users/Admin/Desktop/Опять работа/docx-service/docx-service/docs/dify-prompt-template.md)

Во входы prompt подайте:

- `merge_inputs.forwarding_text`
- `merge_inputs.appeal_text`
- `merge_inputs.merged_parsed`
- `retrieve_context.result`
- `instructions`

Включите `Structured Output`.

## 9. Code -> normalize_json

Входы:

- `llm_output`
- `parsed`
- `original_text`

Привязки:

- `llm_output` = structured output LLM-узла или его текстовый output
- `parsed` = `merge_inputs.merged_parsed`
- `original_text` = `merge_inputs.appeal_text`

Код:

```python
def main(llm_output, parsed: dict, original_text: str) -> dict:
    import json

    data = {}

    if isinstance(llm_output, dict):
        data = llm_output
    elif isinstance(llm_output, str):
        raw = llm_output.strip()

        if raw.startswith("```json"):
            raw = raw[7:]
        elif raw.startswith("```"):
            raw = raw[3:]
        if raw.endswith("```"):
            raw = raw[:-3]

        raw = raw.strip()
        if raw:
            try:
                data = json.loads(raw)
            except Exception:
                start = raw.find("{")
                end = raw.rfind("}")
                if start != -1 and end != -1 and end > start:
                    data = json.loads(raw[start:end + 1])

    parsed = parsed or {}

    return {
        "text": original_text or "",
        "applicant_name": data.get("applicant_name") or parsed.get("applicant_name", ""),
        "recipient_block": data.get("recipient_block") or parsed.get("recipient_block", ""),
        "subject_title": data.get("subject_title") or parsed.get("subject_title", "") or "О рассмотрении обращения гражданина",
        "reference_caption": data.get("reference_caption") or parsed.get("reference_caption", "") or "На обращение гражданина",
        "salutation": data.get("salutation") or parsed.get("salutation", "") or "Уважаемый заявитель!",
        "signer_title": data.get("signer_title") or parsed.get("signer_title", "") or "Директор",
        "signer_department": data.get("signer_department") or parsed.get("signer_department", "") or "Департамент бюджетного планирования, государственных программ и национальных проектов",
        "signer_name": data.get("signer_name") or parsed.get("signer_name", "") or "Т.С. Митюков",
        "body_text": data.get("body_text") or parsed.get("body_text", ""),
    }
```

Выходы:

- `text` -> `String`
- `applicant_name` -> `String`
- `recipient_block` -> `String`
- `subject_title` -> `String`
- `reference_caption` -> `String`
- `salutation` -> `String`
- `signer_title` -> `String`
- `signer_department` -> `String`
- `signer_name` -> `String`
- `body_text` -> `String`

## 10. HTTP Request -> render_docx

- `Method`: `POST`
- `URL`: `http://docx-service:8000/generate`
- если через host:
  `http://host.docker.internal:8119/generate`
- `Body`: `JSON`
- `Headers`:
  - `Content-Type: application/json`

JSON body:

```json
{
  "text": "{{normalize_json.text}}",
  "applicant_name": "{{normalize_json.applicant_name}}",
  "recipient_block": "{{normalize_json.recipient_block}}",
  "subject_title": "{{normalize_json.subject_title}}",
  "reference_caption": "{{normalize_json.reference_caption}}",
  "salutation": "{{normalize_json.salutation}}",
  "signer_title": "{{normalize_json.signer_title}}",
  "signer_department": "{{normalize_json.signer_department}}",
  "signer_name": "{{normalize_json.signer_name}}",
  "body_text": "{{normalize_json.body_text}}"
}
```

Используйте выход `files`, а не `body`.

## 11. Answer

- текст: `Файл подготовлен.`
- файл: `render_docx.files`

Если в конкретной версии Dify `Answer` не принимает сразу `Array[File]`, возьмите первый элемент массива через отдельный узел или picker.
