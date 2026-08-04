# Чеклист: Настройка кэширования в FastAPI

## 1. Установка зависимостей

- [ ] Добавить `fastapi-cache2` в `pyproject.toml`:
  ```toml
  "fastapi-cache2 (>=0.2.0,<0.3.0)"
  "jinja2 (>=3.1.0,<4.0.0)"
  ```
- [ ] Экспортировать зависимости в `requirements.txt`:
  ```bash
  poetry export --without-hashes --format requirements.txt --output requirements.txt
  ```
- [ ] Установить зависимости локально:
  ```bash
  poetry install
  ```

## 2. Настройка cache.py

- [ ] Создать файл `cache.py` с fallback на InMemoryBackend:

  ```python
  from fastapi_cache import FastAPICache
  from fastapi_cache.backends.redis import RedisBackend
  from fastapi_cache.backends.inmemory import InMemoryBackend
  from redis import asyncio as aioredis
  from config import settings

  async def init_cache():
      try:
          redis = aioredis.from_url(settings.REDIS_URL, encoding="utf8", decode_responses=True)
          FastAPICache.init(RedisBackend(redis), prefix="fastapi-cache")
      except Exception:
          # Fallback на in-memory кэш если Redis недоступен
          FastAPICache.init(InMemoryBackend(), prefix="fastapi-cache")
  ```

## 3. Настройка main.py

- [ ] Импортировать кэш в `main.py`:
  ```python
  from cache import init_cache
  from fastapi_cache import FastAPICache
  from fastapi_cache.decorator import cache
  ```
- [ ] Инициализировать кэш в lifespan:
  ```python
  @asynccontextmanager
  async def lifespan(app: FastAPI):
      await init_cache()
      yield
  ```
- [ ] Добавить декоратор `@cache` на GET-эндпоинты, которые нужно кэшировать:
  ```python
  @app.get("/items", response_model=list[ItemOut])
  @cache(expire=60)  # кэшировать на 60 секунд
  async def get_items(session: SessionDep):
      ...
  ```

## 4. Сброс кэша при изменении данных

- [ ] В POST-эндпоинте добавить сброс кэша после создания:
  ```python
  await session.commit()
  await FastAPICache.clear()  # сбросить кэш списка
  return new_item
  ```
- [ ] В PUT-эндпоинте добавить сброс кэша после обновления:
  ```python
  await session.commit()
  await FastAPICache.clear()  # сбросить кэш списка
  return item
  ```
- [ ] В DELETE-эндпоинте добавить сброс кэша после удаления:
  ```python
  await session.commit()
  await FastAPICache.clear()  # сбросить кэш списка
  return None
  ```

## 5. Настройка тестов (conftest.py)

- [ ] Добавить фикстуру для инициализации in-memory кэша в тестах:

  ```python
  import pytest
  from fastapi_cache import FastAPICache

  @pytest.fixture(autouse=True)
  async def setup_cache():
      """Инициализация in-memory кэша для тестов."""
      from fastapi_cache.backends.inmemory import InMemoryBackend

      FastAPICache.reset()
      FastAPICache.init(InMemoryBackend(), prefix="fastapi-cache-test")
      yield
      FastAPICache.reset()
  ```

## 6. Настройка Dockerfile

- [ ] Убедиться, что `Dockerfile` использует `requirements.txt`:
  ```dockerfile
  FROM python:3.13-slim
  WORKDIR /app
  COPY requirements.txt .
  RUN pip install --no-cache-dir -r requirements.txt
  COPY . .
  CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
  ```

## 7. Настройка docker-compose.yml

- [ ] Использовать локальную сборку для разработки:
  ```yaml
  fastapi:
    build: .
    container_name: fastapi-container
    ports:
      - "8000:8000"
    volumes:
      - ./:/app
    command: uvicorn main:app --host 0.0.0.0 --port 8000 --reload
    depends_on:
      - db
      - redis
    environment:
      DATABASE_URL: postgresql+asyncpg://fastapi_user:fastapi_pass@db:5432/fastapi_db
      REDIS_URL: redis://redis:6379/0
  ```

## 8. Локальная разработка

- [ ] Запустить контейнеры:
  ```bash
  docker compose up --build -d
  ```
- [ ] Применить миграции Alembic:
  ```bash
  docker compose run --rm fastapi alembic upgrade head
  ```
- [ ] Проверить API:

  ```bash
  # Создать
  curl -X POST http://localhost:8000/items \
    -H 'Content-Type: application/json' \
    -d '{"name": "test"}'

  # Получить список (кэшируется)
  curl http://localhost:8000/items

  # Обновить
  curl -X PUT http://localhost:8000/items/{id} \
    -H 'Content-Type: application/json' \
    -d '{"name": "updated"}'

  # Получить список — должен быть обновлён!
  curl http://localhost:8000/items
  ```

## 9. Настройка GitHub Actions

### deploy-dev.yml

- [ ] Добавить Redis как сервис в workflow:

  ```yaml
  services:
    postgres:
      image: postgres:16
      env:
        POSTGRES_USER: fastapi_user
        POSTGRES_PASSWORD: fastapi_pass
        POSTGRES_DB: fastapi_db
      ports:
        - 5432:5432
      options: >-
        --health-cmd pg_isready
        --health-interval 10s
        --health-timeout 5s
        --health-retries 5

    redis:
      image: redis:7-alpine
      ports:
        - 6379:6379
      options: >-
        --health-cmd "redis-cli ping"
        --health-interval 10s
        --health-timeout 5s
        --health-retries 5
  ```

- [ ] Добавить `REDIS_URL` в переменные окружения для тестов:
  ```yaml
  - name: Install dependencies and run linter & tests
    env:
      DATABASE_URL: postgresql+asyncpg://fastapi_user:fastapi_pass@localhost:5432/fastapi_db
      REDIS_URL: redis://localhost:6379/0
    run: |
      poetry install --with dev
      poetry run ruff check .
      poetry run pytest
  ```

### deploy.yml

- [ ] Добавить Redis как сервис в production workflow (для миграций и тестов):
  ```yaml
  services:
    postgres:
      image: postgres:16
      # ... параметры
    redis:
      image: redis:7-alpine
      # ... параметры
  ```

### Деплой на VPS

- [ ] Убедиться, что в скрипте деплоя применяются миграции:
  ```yaml
  - name: Deploy to VPS (dev) via SSH
    uses: appleboy/ssh-action@v1.2.0
    with:
      host: ${{ secrets.VPS_HOST }}
      username: ${{ secrets.VPS_USER }}
      key: ${{ secrets.VPS_SSH_KEY }}
      script: |
        cd /srv/dev
        docker compose pull
        docker compose up -d db
        docker compose run --rm fastapi alembic upgrade head
        docker compose up -d
  ```

## 10. Проверка работы кэша

- [ ] Создать элемент → кэш сбрасывается автоматически
- [ ] Получить список → данные кэшируются на 60 секунд
- [ ] Обновить элемент → кэш сбрасывается автоматически
- [ ] Получить список → данные обновляются из БД
- [ ] Удалить элемент → кэш сбрасывается автоматически
- [ ] Получить список → удалённый элемент не отображается

## Важные заметки

1. **Alembic — единственный способ управления схемой**. Не использовать `Base.metadata.create_all()` в коде приложения.
2. **Миграции применяются через GitHub Actions** на сервере. Локально — вручную через `docker compose run --rm fastapi alembic upgrade head`.
3. **Redis в production, InMemory в dev/test**. Fallback в `cache.py` обеспечивает работу без Redis.
4. **Кэш сбрасывается через `FastAPICache.clear()`** после любых изменений данных (POST, PUT, DELETE).
5. **В тестах** используется `InMemoryBackend` — Redis не нужен для тестирования.
