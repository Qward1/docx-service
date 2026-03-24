# Dify Workflow Для PDF -> LLM -> DOCX

Рекомендуемый вариант для Dify: использовать `Chatflow`, а не обычный `Workflow`, если итоговый `docx` нужно сразу отдавать пользователю в чате.

## Рекомендуемая схема узлов

1. `Start`
2. `HTTP Request` (`extract_pdf`)
3. `LLM` (`draft_response`)
4. `Code` (`normalize_json`)
5. `HTTP Request` (`render_docx`)
6. `Answer`

## Что делает каждый узел

### 1. `Start`

Добавьте входную переменную:

- `pdf` типа `Single File`

Если хотите поддержать и ручной текст, добавьте ещё:

- `manual_text` типа `Paragraph`

### 2. `HTTP Request` -> `extract_pdf`

Цель: отправить загруженный PDF в сервис и получить нормализованный текст плюс черновые реквизиты.

Настройки:

- Method: `POST`
- URL: `http://docx-service:8000/extract`
- Body: `Binary`
- Binary variable: `pdf`
- Headers:
  - `Content-Type: application/pdf`
  - `X-Filename: appeal.pdf`

Ожидаемый JSON-ответ:

```json
{
  "text": "полный текст обращения",
  "parsed": {
    "applicant_name": "Иванов И.И.",
    "reference_line": "от 9 января 2025 г. № П48-5533-1",
    "source_line1": "Письмо Аппарата Правительства",
    "source_line2": "Российской Федерации",
    "body_text": "черновой текст",
    "topic": "О ...",
    "subject_title": "О рассмотрении обращения"
  }
}
```

### 3. `LLM` -> `draft_response`

Цель: на основе извлечённого текста подготовить итоговый текст ответа и уточнить реквизиты.

Входные переменные для промпта:

- `extract_pdf.body.text`
- `extract_pdf.body.parsed`

Рекомендуемый system prompt:

```text
Ты готовишь официальный ответ на обращение в деловом стиле государственного ведомства.
На входе есть полный текст обращения и черновые реквизиты, извлечённые автоматически.

Верни только JSON-объект без markdown и без пояснений.
Строго верни поля:
- applicant_name
- subject_title
- source_line1
- source_line2
- reference_line
- body_text

Требования:
- applicant_name в формате "Фамилия И.О."
- subject_title обычно "О рассмотрении обращения"
- source_line1 и source_line2 короткие строки для шапки
- reference_line в формате "от ... № ..."
- body_text это 2-4 абзаца официального ответа на русском языке
- не выдумывай факты, которых нет во входном тексте
- если поле нельзя уверенно восстановить, используй значение из parsed
```

Рекомендуемый user prompt:

```text
Текст обращения:
{{#extract_pdf.body.text#}}

Черновые поля:
{{#extract_pdf.body.parsed#}}
```

Режим ответа:

- включить `Structured output` или строгий JSON, если модель это поддерживает;
- температура `0.1-0.3`.

### 4. `Code` -> `normalize_json`

Цель: безопасно распарсить JSON из LLM и заполнить пропуски дефолтами из `extract_pdf.body.parsed`.

Пример Python-кода:

```python
def main(llm_output: str, parsed: dict, original_text: str) -> dict:
    import json

    data = json.loads(llm_output)

    return {
        "text": original_text,
        "applicant_name": data.get("applicant_name") or parsed.get("applicant_name"),
        "subject_title": data.get("subject_title") or parsed.get("subject_title") or "О рассмотрении обращения",
        "source_line1": data.get("source_line1") or parsed.get("source_line1"),
        "source_line2": data.get("source_line2") or parsed.get("source_line2"),
        "reference_line": data.get("reference_line") or parsed.get("reference_line"),
        "body_text": data.get("body_text") or parsed.get("body_text"),
    }
```

Подайте в него:

- `llm_output` = текстовый ответ из `draft_response`
- `parsed` = `extract_pdf.body.parsed`
- `original_text` = `extract_pdf.body.text`

### 5. `HTTP Request` -> `render_docx`

Цель: передать в сервис итоговый текст и поля для рендера документа.

Настройки:

- Method: `POST`
- URL: `http://docx-service:8000/generate`
- Content-Type: `application/json`

Body:

```json
{
  "text": "{{#normalize_json.text#}}",
  "applicant_name": "{{#normalize_json.applicant_name#}}",
  "subject_title": "{{#normalize_json.subject_title#}}",
  "source_line1": "{{#normalize_json.source_line1#}}",
  "source_line2": "{{#normalize_json.source_line2#}}",
  "reference_line": "{{#normalize_json.reference_line#}}",
  "body_text": "{{#normalize_json.body_text#}}"
}
```

Этот запрос возвращает бинарный `docx`.

### 6. `Answer`

В ответе пользователю выведите:

- короткий текст, например `Документ подготовлен.`
- файл из узла `render_docx`

Если в вашем инстансе Dify удобнее работать через API workflow, а не через чат, вместо `Answer` используйте выход workflow и верните файл клиенту на своей стороне.

## Почему именно так

- `extract` вынесен в отдельный HTTP-вызов, чтобы поддерживать и обычные PDF, и сканированные PDF через OCR внутри сервиса.
- `LLM` отвечает только за смысловую часть: выделение реквизитов и генерацию текста ответа.
- `generate` отвечает только за форматирование и сборку `docx` по шаблону.
- Такая схема проще отлаживается: видно отдельно текст после OCR, отдельно JSON после LLM, отдельно итоговый файл.

## Упрощённый вариант

Если PDF всегда текстовый, можно вместо узла `HTTP Request` `extract_pdf` использовать узел `Doc Extractor`, а дальше оставить ту же цепочку:

1. `Start`
2. `Doc Extractor`
3. `LLM`
4. `Code`
5. `HTTP Request`
6. `Answer`

Но для сканов рекомендован именно endpoint `/extract`.
