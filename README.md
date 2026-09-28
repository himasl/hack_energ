# Архитектор BPMN-диаграмм

ИИ-помощник, который строит BPMN 2.0 диаграмму по текстовому описанию
бизнес-процесса. Хакатон «ИИ-ассистенты для энергетики», первый этап.

> Статус: каркас проекта. Разделы, помеченные TODO, заполняются по ходу работы.

## Как это работает

```
описание процесса
   → LLM пишет Python-код на API DIAGRAM
   → песочница выполняет код → граф процесса
   → валидация и автопочинка (ошибки → обратно в LLM, до 2 попыток)
   → автоматическая раскладка (участники — дорожки, слева направо)
   → BPMN 2.0 XML с координатами (DI)
   → открывается и редактируется в bpmn.io
```

LLM отвечает только за смысл: участников, шаги, условия и параллельные ветки.
Валидность XML и читаемую компоновку обеспечивает детерминированный код,
поэтому результат всегда открывается в bpmn.io.

## Быстрый старт

### Docker

```bash
cp .env.example .env      # указать LLM_BASE_URL, LLM_API_KEY, LLM_MODEL
docker compose up --build
```

Открыть http://localhost:8000.

### Локально

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env

uvicorn web.app:app --reload                                           # веб-интерфейс
python -m bpmn_gen examples/01_repair_request/input.txt -o out.bpmn    # CLI с LLM
python -m bpmn_gen --code examples/01_repair_request/code.py -o out.bpmn  # без LLM
pytest                                                                 # тесты
```

Файл `out.bpmn` открывается на [demo.bpmn.io](https://demo.bpmn.io)
(перетащить файл в окно) или в Camunda Modeler.

## API для генерации кода

Модель пишет код на API из ТЗ; перед выполнением заданы `ROOT_PROCESS_ID`,
`ROOT_START_TASK_ID`, `ROOT_END_TASK_ID`.

| Метод | Что создаёт |
| --- | --- |
| `add_task / add_user_task / add_script_task(name, parent)` | задачу |
| `add_exclusive / parallel / inclusive_gateway(name, parent)` | шлюз |
| `add_pool(parent, [lanes])` → `(pool_id, lane_ids)` | пул с дорожками |
| `create_subprocess(name, parent)` | развёрнутый подпроцесс |
| `add_group(name, parent)` | группу (рамку) |
| `add_link(source, target, name='')` | связь; `name` — подпись ветки (наше расширение) |

## Структура

```
bpmn_gen/
  graph.py      ProcessGraph — общая модель процесса (контракт)
  diagram.py    фреймворк DIAGRAM
  validate.py   проверки и автопочинка
  layout.py     автоматическая раскладка
  render.py     BPMN 2.0 XML + DI
  sandbox.py    безопасное выполнение кода модели
  llm.py        запросы к модели, промпты в prompts/
  pipeline.py   сквозной конвейер
  cli.py        командная строка
web/            FastAPI + интерфейс на bpmn-js
examples/       входные описания и полученные схемы
tests/          тесты, XSD BPMN 2.0 от OMG в tests/xsd
```

## Примеры

См. [examples/](examples/README.md). TODO: таблица «описание → схема» с картинками.

## Возможности и ограничения

TODO: заполнить к сдаче.

## Команда

TODO: участники и роли.
