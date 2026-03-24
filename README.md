# DOCX Response Generator

Микросервис принимает обращение в виде:

- `PDF` файла;
- текстового файла `txt`;
- обычного текста в `JSON` или `multipart/form-data`.

На выходе сервис возвращает `DOCX`, собранный по шаблону `shablon_minek.docx`.

## Что делает сервис

1. Извлекает текст из `PDF`.
2. Если `PDF` сканированный и прямого текста нет, пытается снять текст через OCR.
3. Эвристически выделяет ФИО заявителя, тему обращения и реквизиты письма.
4. Подставляет данные в шаблон реального ответа Минэкономразвития России и формирует итоговый `docx`.

Если какие-то реквизиты извлечь автоматически не удалось или нужна точная формулировка, их можно передать вручную в полях запроса: `applicant_name`, `recipient_block`, `reference_caption`, `salutation`, `body_text` и т.д.

## Запуск

Рекомендуемая версия Python: `3.12`.

На `Python 3.13` сервис тоже запускается, но без OCR для сканированных PDF, потому что `rapidocr-onnxruntime` пока не ставится на `3.13`.

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Для `PowerShell`:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## Docker

Сборка образа:

```bash
docker build -t docx-service .
```

Запуск контейнера:

```bash
docker run --rm -p 8000:8000 --name docx-service docx-service
```

Через `docker compose`:

```bash
docker compose up --build -d
```

Остановка:

```bash
docker compose down
```

## API

### `GET /health`

Проверка доступности сервиса.

### `POST /generate`

Поддерживаемые форматы:

- `application/json`
- `multipart/form-data`

### `POST /extract`

Возвращает извлечённый текст и черновые реквизиты в JSON.

Поддерживаемые форматы:

- `application/json` с полем `text`
- `multipart/form-data` с полем `file` или `text`
- raw body `application/pdf`, `application/octet-stream`, `text/plain`

### Вариант 1. JSON

```json
{
  "text": "Заявитель: Иванов Иван Иванович\nТема: О предоставлении разъяснений...",
  "reference_line": "от 9 января 2025 г. № П48-5533-1",
  "reference_caption": "На обращение гражданина от 9 января 2025 г. № П48-5533-1",
  "salutation": "Уважаемый Иван Иванович!",
  "body_text": "Первый абзац ответа.\n\nВторой абзац ответа."
}
```

### Вариант 2. multipart/form-data

Поля:

- `file` или `text`
- `applicant_name`
- `recipient_block`
- `subject_title`
- `source_title`
- `source_line1`
- `source_line2`
- `reference_line`
- `reference_caption`
- `salutation`
- `body_text`
- `signer_name`
- `executor_name`
- `executor_phone`
- `executor_department`

## Примеры запросов

Текстом:

```bash
curl -X POST "http://127.0.0.1:8000/generate" \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Заявитель: Иванов Иван Иванович\nТема: О предоставлении разъяснений по мерам поддержки малого бизнеса.",
    "reference_line": "от 9 января 2025 г. № П48-5533-1"
  }' \
  --output response.docx
```

PDF:

```bash
curl -X POST "http://127.0.0.1:8000/generate" \
  -F "file=@/absolute/path/to/appeal.pdf" \
  -F "recipient_block=Иванов И.И.\nivanov@example.com" \
  -F "salutation=Уважаемый Иван Иванович!" \
  -F "body_text=Подготовленный текст ответа." \
  --output response.docx
```

Извлечение текста из PDF:

```bash
curl -X POST "http://127.0.0.1:8000/extract" \
  -H "Content-Type: application/pdf" \
  -H "X-Filename: appeal.pdf" \
  --data-binary "@/absolute/path/to/appeal.pdf"
```

## Dify + LLM

Для Dify рекомендована цепочка:

1. `Start` с двумя входными файлами `forwarding_pdf` и `appeal_pdf`
2. `HTTP Request` на `/extract` для `forwarding_pdf`
3. `Code` для парсинга JSON первого ответа
4. `HTTP Request` на `/extract` для `appeal_pdf`
5. `Code` для парсинга JSON второго ответа
6. `Code` для объединения реквизитов из двух документов
7. `Knowledge Retrieval` по стилевому канону и Указу № 309
8. `LLM` для генерации текста ответа и уточнения `recipient_block`, `reference_caption`, `salutation`
9. `Code` для нормализации JSON после LLM
10. `HTTP Request` на `/generate`
11. `Answer` с возвратом `docx`

Файлы для настройки Dify:

- подробная схема узлов: [docs/dify-workflow.md](/mnt/c/Users/Admin/Desktop/Опять работа/docx-service/docx-service/docs/dify-workflow.md)
- готовый prompt template: [docs/dify-prompt-template.md](/mnt/c/Users/Admin/Desktop/Опять работа/docx-service/docx-service/docs/dify-prompt-template.md)
- knowledge base по стилю ответа: [docs/dify-kb/response-style-reference.md](/mnt/c/Users/Admin/Desktop/Опять работа/docx-service/docx-service/docs/dify-kb/response-style-reference.md)
- knowledge base по Указу № 309: [docs/dify-kb/ukaz-309-economic-priorities.md](/mnt/c/Users/Admin/Desktop/Опять работа/docx-service/docx-service/docs/dify-kb/ukaz-309-economic-priorities.md)

## Тесты

```bash
PYTHONPATH=. python3 -m unittest discover -s tests
```

## Ограничения

- Шаблон теперь ближе к реальному письму, включая изображения и компоновку, но итоговое качество всё равно зависит от корректного извлечения реквизитов и настройки prompt в Dify.
- Если входные документы имеют нестандартную структуру, лучше передавать реквизиты явно через поля запроса.
