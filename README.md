# YM Unit Economy — SaaS-калькулятор юнит-экономики Я.Маркета

Веб-сервис для расчёта юнит-экономики по каждому SKU для магазинов на Яндекс Маркете. С мультитенантностью (несколько магазинов на одного пользователя), регистрацией/логином и **интеграцией с Yandex.Market Partner API** — карточки товаров подтягиваются одним кликом, без Excel-файлов.

## Возможности

- **Регистрация и логин** — email + пароль, JWT-токены.
- **Мультитенант:** несколько магазинов на аккаунт, приглашения в команду.
- **Настройки магазина:** 8 систем налогообложения (включая НДС 22%/2%), 5 вариантов эквайринга + свой %, ДРР, % возвратов.
- **Категории и комиссии** FBY/FBS — редактирование, добавление своих.
- **Импорт из Ya.Market API** — все офферы (карточки, цены, габариты) одним запросом.
- **Синхронизация цен** — периодически обновлять цены из Ya.Market.
- **Ручной ввод SKU** — с автоматическим пересчётом маржи.
- **Цветовая индикация** маржи: 🟢 ≥15%, 🟡 5–15%, 🔴 <5%.
- **Экспорт xlsx** (планируется добавить в UI).

## Стек

- **Backend:** FastAPI, SQLAlchemy 2.0, Pydantic v2, Alembic
- **DB:** PostgreSQL (SQLite для локальной разработки)
- **Auth:** JWT (python-jose) + bcrypt (passlib)
- **HTTP-клиент:** httpx (для Ya.Market API)
- **Frontend:** Tailwind CSS + Alpine.js (single-file HTML)
- **Deploy:** Docker + Railway

## Быстрый деплой на Railway

1. Регистрация на [railway.app](https://railway.app) через GitHub.
2. Создай новый репозиторий на GitHub, загрузи туда содержимое папки `ym_calc_saas/`.
3. В Railway: **New Project → Deploy from GitHub repo** → выбери свой репо.
4. Добавь плагин **PostgreSQL** (New → Database → PostgreSQL). Railway автоматически подставит `DATABASE_URL` в env-переменные приложения.
5. В **Variables** добавь:
   - `SECRET_KEY` — случайные 64 символа (сгенерируй, например, командой `openssl rand -hex 32`)
6. Deploy запустится автоматически. Через 1–2 минуты у тебя будет публичный URL вида `https://твой-проект.up.railway.app`.

## Локальный запуск (для разработки)

```bash
python3 -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

По умолчанию использует SQLite (`sqlite:///./local.db`). Открой http://localhost:8000.

## Как получить Ya.Market API-токен

1. Открой https://oauth.yandex.ru/ → «Зарегистрировать новое приложение».
2. Тип: **Веб-сервисы**. Callback URL: `https://oauth.yandex.ru/verification_code` (для ручного получения токена).
3. В разделе «Данные» → «Яндекс.Маркет для партнёров» отметь скоуп `market:partner`.
4. Сохрани → получишь `client_id`.
5. Открой в браузере:
   ```
   https://oauth.yandex.ru/authorize?response_type=token&client_id=ТВОЙ_CLIENT_ID
   ```
   → авторизуй → получишь `access_token` в URL.
6. В веб-сервисе → «Ya.Market API» → вставь токен, `business_id` (из ЛК Ya.Market Partner → Настройки), `campaign_id` (ID магазина внутри бизнеса).
7. Нажми «📥 Импорт из Ya.Market» — все офферы подтянутся.

## Структура

```
ym_calc_saas/
├── app/
│   ├── main.py               # FastAPI entry, CORS, роутеры
│   ├── config.py             # env-переменные (pydantic-settings)
│   ├── database.py           # SQLAlchemy engine, Base, sessionmaker
│   ├── security.py           # bcrypt + JWT
│   ├── deps.py               # current_user, current_workspace dependencies
│   ├── schemas.py            # Pydantic-схемы для API
│   ├── seed.py               # дефолтные категории/налоги/тарифы
│   ├── models/
│   │   ├── user.py           # User
│   │   ├── workspace.py      # Workspace, Membership + роли
│   │   ├── marketplace.py    # MarketplaceAccount (токен, business_id)
│   │   └── catalog.py        # Category, StoreSettings, Sku
│   ├── routes/
│   │   ├── auth.py           # register, login, me
│   │   ├── workspaces.py     # список моих магазинов, создание
│   │   ├── categories.py     # CRUD категорий
│   │   ├── settings.py       # настройки магазина + справочники
│   │   ├── skus.py           # CRUD SKU, bulk-upsert, calc
│   │   ├── marketplace.py    # управление API-токенами
│   │   └── ya_market.py      # интеграция с Ya.Market API
│   └── services/
│       ├── calculator.py     # ядро расчёта юнит-экономики
│       └── ya_market.py      # клиент Ya.Market Partner API
├── static/
│   ├── index.html            # интерфейс (Tailwind + Alpine.js)
│   └── app.js                # фронт-логика
├── Dockerfile
├── railway.toml
├── requirements.txt
├── .env.example
└── README.md
```

## API endpoints

Полный OpenAPI-спек — на `/docs` после запуска.

**Auth:**
- `POST /api/auth/register` — регистрация, возвращает JWT
- `POST /api/auth/login` — логин
- `GET  /api/auth/me` — текущий пользователь

**Workspaces:**
- `GET  /api/workspaces` — мои магазины
- `POST /api/workspaces` — создать новый

**Categories / Settings / SKU** — все под `/api/workspaces/{workspace_id}/...`

**Ya.Market:**
- `GET  /api/workspaces/{ws}/ya-market/campaigns` — магазины пользователя в кабинете
- `POST /api/workspaces/{ws}/ya-market/import-offers` — импорт всех карточек
- `POST /api/workspaces/{ws}/ya-market/sync-prices` — синхронизация цен

## Безопасность

- Пароли хранятся в bcrypt-хэше.
- JWT-токены с 30-дневным сроком жизни (настраивается через `ACCESS_TOKEN_EXPIRE_MINUTES`).
- API-токены Ya.Market хранятся в открытом виде в БД (для v1); в проде рекомендую добавить шифрование через `cryptography.Fernet` с ключом из env.
- CORS открыт для всех источников (`*`) — при boundary-развороте ограничь.

## План развития

- [ ] Приглашения в команду (пригласить email → отправка ссылки)
- [ ] Экспорт в xlsx с одной кнопки
- [ ] История изменения цен и маржи по SKU
- [ ] Расширение на Ozon и WB (одна кодовая база, три marketplace-клиента)
- [ ] Периодическая автосинхронизация цен (Celery/RQ + Redis)
- [ ] Двухфакторная аутентификация
- [ ] Реферальная программа
