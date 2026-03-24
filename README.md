# DOCX Response Generator

Микросервис принимает обращение в виде:

- `PDF` файла;
- текстового файла `txt`;
- обычного текста в `JSON` или `multipart/form-data`.

На выходе сервис возвращает `DOCX`, собранный по шаблону [shablon_minek.docx](/Users/vladislavdemin/Desktop/Опять работа/docx-service/shablon_minek.docx).

## Что делает сервис

1. Извлекает текст из `PDF`.
2. Если `PDF` сканированный и прямого текста нет, пытается снять текст через OCR.
3. Эвристически выделяет ФИО заявителя, тему обращения и реквизиты письма.
4. Подставляет данные в шаблон и формирует итоговый `docx`.

Если какие-то реквизиты извлечь автоматически не удалось или нужна точная формулировка, их можно передать вручную в полях запроса: `applicant_name`, `reference_line`, `body_text`, `source_line1`, `source_line2` и т.д.

## Запуск

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
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
  "body_text": "Первый абзац ответа.\n\nВторой абзац ответа."
}
```

### Вариант 2. multipart/form-data

Поля:

- `file` или `text`
- `applicant_name`
- `subject_title`
- `source_title`
- `source_line1`
- `source_line2`
- `reference_line`
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

1. `Start` с входным файлом `pdf`
2. `HTTP Request` на `/extract`
3. `LLM` для генерации текста ответа и уточнения реквизитов
4. `Code` для нормализации JSON после LLM
5. `HTTP Request` на `/generate`
6. `Answer` с возвратом `docx`

Подробная схема узлов и примеры промптов: [docs/dify-workflow.md](/Users/vladislavdemin/Desktop/Опять работа/docx-service/docs/dify-workflow.md)

## Тесты

```bash
PYTHONPATH=. python3 -m unittest discover -s tests
```

## Ограничения

- В папке проекта сейчас есть только шаблон, без исходных примеров обращений и ответов, поэтому разбор реквизитов построен на эвристиках.
- Если входные документы имеют нестандартную структуру, лучше передавать реквизиты явно через поля запроса.
