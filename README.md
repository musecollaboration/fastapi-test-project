# FastAPI Test Project

[![Python](https://img.shields.io/badge/Python-3.14-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-005571?style=flat&logo=fastapi)](https://fastapi.tiangolo.com/)
[![Docker](https://img.shields.io/badge/Docker-2496ED?style=flat&logo=docker&logoColor=white)](https://www.docker.com/)
[![GitLab CI/CD](https://img.shields.io/badge/GitLab_CI/CD-FC6D26?style=flat&logo=gitlab&logoColor=white)](https://about.gitlab.com/)

Тестовый проект для изучения **FastAPI**, контейнеризации и автоматического деплоя. 
Проект представляет собой небольшое REST API на FastAPI для работы с сущностями `Item` (товары/элементы) и демонстрирует базовый процесс CI/CD через GitLab и Docker.

## 📖 Описание проекта

Этот проект создан как учебный пример для:
* Изучения FastAPI и асинхронного API;
* Работы с Pydantic-моделями;
* Запуска приложения в контейнере Docker;
* Деплоя через Docker Compose на удалённый сервер;
* Настройки базового CI/CD пайплайна.

Приложение предоставляет простой CRUD-интерфейс для элементов:
* Создание нового элемента;
* Получение списка элементов;
* Получение элемента по ID;
* Удаление элемента.

> ⚠️ **Важно:** Данные хранятся в памяти (in-memory `fake_db`), то есть при перезапуске приложения база сбрасывается.

## 🛠 Технологии

* **Python 3.14**
* **FastAPI**
* **Uvicorn**
* **Pydantic**
* **Docker / Docker Compose**
* **Poetry**
* **Pytest**
* **Ruff**
* **GitLab CI/CD**

## 📁 Структура проекта

```text
fastapi-test-project/
├── .gitignore
├── .gitlab-ci.yml
├── Dockerfile
├── docker-compose.yml
├── main.py
├── pyproject.toml
├── requirements.txt
├── poetry.lock
├── tests/
│   ├── __init__.py
│   └── test_main.py
└── README.md
```

## 🚀 Основной функционал

В проекте реализованы следующие HTTP-эндпоинты:

### 1. Главная страница
`GET /`

**Ответ:**
```json
{
  "message": "OK. Deployed via CI/CD!"
}
```

### 2. Получить список всех элементов
`GET /items`

**Ответ:**
```json
[
  {
    "id": "3d6fd2bf-0f4a-4db0-84d9-5b5b7d4f42d9",
    "name": "First item",
    "description": "This is the first item",
    "created_at": "2026-10-27T12:34:56.789012"
  }
]
```

### 3. Получить элемент по ID
`GET /items/{item_id}`

*Если элемент не найден:*
```json
{
  "detail": "Item not found"
}
```

### 4. Создать элемент
`POST /items`

**Пример запроса:**
```json
{
  "name": "Test item",
  "description": "Test description"
}
```

**Ответ:**
```json
{
  "id": "3d6fd2bf-0f4a-4db0-84d9-5b5b7d4f42d9",
  "name": "Test item",
  "description": "Test description",
  "created_at": "2026-10-27T12:34:56.789012"
}
```

### 5. Удалить элемент
`DELETE /items/{item_id}`

**Ответ:**
```json
{
  "message": "Item 3d6fd2bf-0f4a-4db0-84d9-5b5b7d4f42d9 deleted"
}
```

---

## 💻 Запуск проекта локально

### Вариант 1: через Poetry

1. Установите зависимости:
   ```bash
   poetry install --with dev
   ```
2. Запустите приложение:
   ```bash
   poetry run uvicorn main:app --host 0.0.0.0 --port 8000 --reload
   ```

Приложение будет доступно в браузере по адресу: `http://localhost:8000`  
Документация Swagger: `http://localhost:8000/docs`

### Вариант 2: через Python + requirements.txt

Если вы используете виртуальное окружение напрямую:

```bash
python -m venv .venv
source .venv/bin/activate  # Для Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

---

## 🐳 Запуск через Docker

**Сборка образа:**
```bash
docker build -t fastapi-test-project .
```

**Запуск контейнера:**
```bash
docker run -d -p 8000:8000 --name fastapi-app fastapi-test-project
```
После этого API будет доступно на: `http://localhost:8000`

### Запуск через Docker Compose

В проекте есть файл `docker-compose.yml`, который поднимает сервис:

```yaml
services:
  fastapi:
    image: ghcr.io/musecollaboration/fastapi-test-project:latest
    container_name: fastapi-container
    ports:
      - "8000:8000"
    restart: always
```

**Запуск:**
```bash
docker compose up -d
```

**Проверка:**
```bash
docker compose ps
```

**Остановка:**
```bash
docker compose down
```

---

## 🧪 Тестирование

Проект включает базовые тесты для проверки работы API. Тесты находятся в директории `tests/test_main.py`.

**Запуск всех тестов:**
```bash
poetry run pytest
```

**Линтинг:**
```bash
poetry run ruff check .
```

---

## ⚙️ CI/CD

Проект настроен для автоматического запуска пайплайна через GitLab CI (`.gitlab-ci.yml`).

**Этапы пайплайна:**
1. **`test`**: установка зависимостей; запуск `ruff check .`; запуск `pytest`.
2. **`build`**: сборка Docker-образа; загрузка образа в Container Registry.
3. **`deploy`**: подключение к удалённому серверу по SSH; загрузка свежего контейнера; перезапуск приложения через `docker compose`.

Это позволяет автоматически разворачивать проект после пуша в ветку `main`.

### Переменные окружения и параметры деплоя

Для деплоя используются переменные GitLab CI/CD, например:
* `CI_REGISTRY`
* `CI_REGISTRY_IMAGE`
* `CI_REGISTRY_USER`
* `CI_REGISTRY_PASSWORD`
* `VPS_HOST`
* `SSH_PRIVATE_KEY`

Эти параметры обеспечивают безопасный вход в Docker Registry, на удалённый сервер и в Docker Compose на месте деплоя.

---

## 📡 Примеры запросов (cURL)

**Проверка корневого маршрута:**
```bash
curl http://localhost:8000/
```

**Получить все элементы:**
```bash
curl http://localhost:8000/items
```

**Создать элемент:**
```bash
curl -X POST "http://localhost:8000/items" \
  -H "Content-Type: application/json" \
  -d '{"name":"New item","description":"Example description"}'
```

**Получить один элемент:**
```bash
curl http://localhost:8000/items/{item_id}
```

**Удалить элемент:**
```bash
curl -X DELETE http://localhost:8000/items/{item_id}
```

---

## ⚠️ Ограничения текущей реализации

На данном этапе проект является учебным и имеет ряд ограничений:
* Данные хранятся только в памяти;
* Нет подключения к базе данных;
* Нет авторизации и пользователей;
* Нет полноценной модели хранения данных;
* Нет миграций и постоянного хранилища.

Это делает проект хорошей отправной точкой для дальнейшего расширения.

## 🔮 Возможные улучшения

В будущем проект можно расширить:
* Подключить **PostgreSQL** или **SQLite**;
* Добавить миграции через **Alembic**;
* Реализовать CRUD для пользователей;
* Добавить JWT-аутентификацию;
* Добавить валидацию и обработку ошибок;
* Настроить логирование;
* Добавить Docker `healthcheck`;
* Разбить проект на модули (`api/`, `models/`, `services/`, `core/`).

---

## 🎯 Заключение

Этот проект является простым, но практичным примером:
* FastAPI API;
* Контейнеризации с Docker;
* Автоматического деплоя через GitLab CI/CD;
* Запуска приложения в продакшн-среде.

Проект отлично подходит для изучения основ backend-разработки и процесса развёртывания веб-приложений.
