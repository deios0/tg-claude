# Telegram + Claude — Архитектура

Как подключить Claude к Telegram-боту с инструментами, памятью и фоновыми задачами.

## Схема

```
┌─────────────┐         ┌──────────────┐         ┌─────────┐
│  Telegram    │ webhook │  FastAPI      │         │   БД    │
│  (юзер)     ├────────►│  + bot.py     │◄───────►│ SQLAlch │
│             │◄────────┤              │         │ emy     │
└─────────────┘ ответ   │  handlers.py  │         └─────────┘
                        │       │       │
                        │       ▼       │
                        │   chat.py     │         ┌──────────┐
                        │       │       ├────────►│ Claude   │
                        │       │       │◄────────┤ API      │
                        │       ▼       │         │ (Sonnet) │
                        │  tool loop    │         └──────────┘
                        │   ┌───────┐   │
                        │   │ save  │   │
                        │   │ query │   │
                        │   │ create│   │
                        │   └───┬───┘   │
                        │       │       │
                        │       ▼ БД    │
                        └───────────────┘
                              │
                        ┌─────┴──────┐
                        │ Scheduler  │
                        │ (APSched)  │
                        │ cron/inter │
                        └────────────┘
```

## Компоненты

### 1. Telegram → Handler

```python
# bot.py — регистрация хендлеров
app = ApplicationBuilder().token(BOT_TOKEN).build()
app.add_handler(MessageHandler(filters.TEXT, handle_message))
app.add_handler(CallbackQueryHandler(handle_callback))
```

Сообщение приходит → `handle_message()` определяет состояние юзера → вызывает `chat_response()`.

### 2. Контекст для Claude

Перед каждым вызовом Claude бот собирает контекст из БД:

```python
async def chat_response(user_message, user_id, history):
    # 1. Загрузить всё что Claude должен знать
    context = await _load_context(user_id)
    #    → факты о юзере, календарь, задачи, письма

    # 2. Системный промпт с контекстом
    system = f"""Ты ассистент.
    Сегодня: {now}
    Факты: {context.facts}
    Календарь: {context.events}
    ..."""

    # 3. История последних N сообщений
    messages = history + [{"role": "user", "content": user_message}]
```

Ключевой принцип: **Claude не помнит между сообщениями** — каждый раз получает свежий контекст из БД + последние N сообщений из истории.

### 3. Tool Use Loop

Claude получает список инструментов и сам решает, какой вызвать:

```python
    # 4. Вызов Claude с инструментами
    response = await client.messages.create(
        model="claude-sonnet-4-5-20250929",
        system=system,
        messages=messages,
        tools=TOOLS,        # ← список инструментов
        max_tokens=4000,
    )

    # 5. Цикл: Claude может вызвать несколько инструментов подряд
    while response.stop_reason == "tool_use":
        tool_results = []
        for block in response.content:
            if block.type == "tool_use":
                result = await execute_tool(block.name, block.input)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": str(result),
                })

        # Отправляем результаты обратно Claude
        messages.append({"role": "assistant", "content": response.content})
        messages.append({"role": "user", "content": tool_results})

        # Claude анализирует результат и решает:
        # → вызвать ещё инструмент, или → ответить текстом
        response = await client.messages.create(
            model="claude-sonnet-4-5-20250929",
            system=system,
            messages=messages,
            tools=TOOLS,
        )

    # 6. Финальный текстовый ответ
    return response.content[0].text
```

Цикл крутится пока Claude не решит, что инструменты больше не нужны и пора ответить текстом.

### 4. Определение инструмента

```python
TOOLS = [
    {
        "name": "create_event",
        "description": "Создать событие в календаре",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "start_at": {"type": "string", "description": "ISO datetime"},
            },
            "required": ["title", "start_at"],
        },
    },
    # ... другие инструменты
]
```

Claude читает `description` и `input_schema` и сам понимает когда и как вызвать инструмент. Чем точнее описание — тем лучше работает.

### 5. Обработчик инструмента

```python
async def execute_tool(name, params):
    if name == "create_event":
        event = CalendarEvent(
            title=params["title"],
            start_at=parse_datetime(params["start_at"]),
        )
        session.add(event)
        await session.commit()
        return f"Событие создано (id={event.id})"

    elif name == "search_flights":
        flights = await search_ryanair(params["origin"], params["destination"], params["date"])
        return format_flights(flights)

    elif name == "save_fact":
        # Claude сам решает что запомнить
        fact = Fact(text=params["fact"], category=params["category"])
        session.add(fact)
        await session.commit()
        return "Запомнил"
```

Результат — строка. Claude получает её и формулирует ответ юзеру.

### 6. Inline-кнопки (undo)

После создания события/напоминания — добавить кнопку отмены:

```python
# В handler после получения ответа от Claude:
if tool_calls and "create_event" in tool_calls:
    event_id = tool_calls["create_event"]["result_id"]
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("❌ Отменить", callback_data=f"undo_event_{event_id}")
    ]])
    msg = await update.message.reply_text(response, reply_markup=keyboard)

    # Убрать кнопки через 60 секунд
    context.job_queue.run_once(remove_keyboard, 60, data=msg)
```

### 7. Фоновые задачи (Scheduler)

```python
# main.py — при старте приложения
scheduler = AsyncIOScheduler()

# Утренний дайджест — AI генерирует сводку из контекста
scheduler.add_job(send_digest, CronTrigger(hour=8, timezone="Europe/Paris"))

# Проверка напоминаний — каждую минуту
scheduler.add_job(check_reminders, IntervalTrigger(minutes=1))

# Синхронизация почты — каждые 6 часов
scheduler.add_job(poll_emails, IntervalTrigger(hours=6))

scheduler.start()
```

Дайджест — это отдельный вызов Claude с промптом "сгенерируй сводку" и данными из БД.

### 8. Dashboard (веб)

FastAPI отдаёт и API, и HTML-страницы:

```python
# Одно приложение — бот + API + дашборд
app = FastAPI()
app.include_router(api_router)        # /api/* — JSON
app.include_router(dashboard_router)  # /* — HTML страницы
app.include_router(oauth_router)      # /oauth/* — подключение почты
```

Дашборд использует те же данные из БД что и бот.

## Поток данных

```
Юзер: "запиши что у Влады аллергия на орехи"
  │
  ▼
Claude получает:
  - системный промпт с контекстом
  - историю (10 сообщений)
  - список инструментов
  │
  ▼
Claude решает: tool_use → save_fact(category="health", fact="У Влады аллергия на орехи")
  │
  ▼
execute_tool("save_fact", {...}) → INSERT INTO facts → "Запомнил"
  │
  ▼
Claude получает результат "Запомнил"
  │
  ▼
Claude отвечает: "Записала! Буду учитывать аллергию Влады на орехи 🥜"
  │
  ▼
Ответ → Telegram
```

```
Юзер: "найди рейс в Барселону на 25 марта"
  │
  ▼
Claude: tool_use → search_flights(origin="HHN", destination="BCN", date="2026-03-25")
  │
  ▼
execute_tool → GET ryanair.com/api/booking/v4/availability?... → 3 рейса
  │
  ▼
Claude получает список рейсов
  │
  ▼
Claude: "Нашла 3 рейса HHN→BCN на 25 марта:
  ✈️ FR1680 10:00→12:40 — 29€ (12 мест)
  ✈️ FR1682 15:40→18:20 — 45€ (3 места)
  ..."
```

## Стек

| Слой | Технология |
|------|-----------|
| AI | Claude API (Anthropic SDK) |
| Бот | python-telegram-bot |
| Сервер | FastAPI + uvicorn |
| БД | SQLAlchemy async + MySQL/PostgreSQL |
| Scheduler | APScheduler |
| Почта | MS Graph API / Gmail API (OAuth2) |
| Deploy | Docker Compose + nginx |

## Файловая структура

```
src/
├── ai/
│   ├── chat.py          # Claude API + tool loop
│   ├── tools.py         # определения инструментов (JSON Schema)
│   └── client.py        # инициализация Anthropic SDK
├── telegram/
│   ├── bot.py           # создание бота, регистрация хендлеров
│   └── handlers.py      # обработка сообщений, кнопок, голоса
├── scheduler/
│   ├── digest.py        # утренний дайджест (AI-генерация)
│   ├── jobs.py          # напоминания, почта, рекурренты
│   └── recurring.py     # логика повторяющихся событий
├── dashboard/
│   ├── routes.py        # HTML-страницы
│   ├── api.py           # REST API (JSON)
│   └── auth.py          # JWT-авторизация
├── models/              # SQLAlchemy модели
├── main.py              # FastAPI app + scheduler + startup
└── database.py          # подключение к БД
```
