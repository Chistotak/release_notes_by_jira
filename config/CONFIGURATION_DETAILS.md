# Руководство по конфигурации генератора Release Notes

Этот документ подробно описывает настройку генератора Release Notes через файлы `.env` и `config/config.yaml`.

## Файл `.env`

Файл `.env` предназначен для хранения чувствительных данных. Он должен находиться в корневой директории проекта.

### `JIRA_COOKIE_STRING`
*   **Описание**: Полная строка Cookie для аутентификации в JIRA.
*   **Как получить**: (См. инструкции в предыдущей версии README или этого файла)
*   **Пример**: `JIRA_COOKIE_STRING="JSESSIONID=...; ..."`
*   **Важно**: Куки имеют ограниченное время жизни. Обновляйте их при необходимости. Если эта переменная не найдена, скрипт запросит ее интерактивно.

---

## Файл `config/config.yaml`

Основной конфигурационный файл, расположенный в `config/`.

### Секция `defaults` (Опционально)

Эта секция позволяет задать значения по умолчанию для часто используемых параметров запуска.
**Приоритет определения параметров:**
1.  Значение из аргумента командной строки (если передан).
2.  Значение из этой секции `defaults` в `config.yaml` (если параметр не передан в CLI и указан здесь).
3.  Интерактивный запрос у пользователя (если параметр не передан в CLI и не указан/пуст в `defaults`).

*   **`filter_id`**:
    *   **Описание**: ID JIRA-фильтра по умолчанию.
    *   **Тип**: Строка или число.
    *   **Пример**: `filter_id: "12345"`
*   **`output_dir`**:
    *   **Описание**: Путь к директории по умолчанию для сохранения сгенерированных Release Notes.
    *   **Тип**: Строка.
    *   **Пример**: `output_dir: "./generated_notes"` (можно использовать `./` для текущей директории)

---

### Секция `jira`

Настройки, связанные с подключением к JIRA и запросом данных.

*   **`server_url`**:
    *   **Описание**: Полный базовый URL вашего JIRA-сервера.
    *   **Пример**: `https://jira.mycompany.com/`
*   **`timeout`**:
    *   **Описание**: Максимальное время ожидания ответа от JIRA в секундах.
    *   **Тип**: Число.
    *   **Пример**: `30`
*   **`max_results_per_request`**:
    *   **Описание**: Максимальное общее количество задач, которое скрипт попытается загрузить по указанному ID фильтра (с учетом внутренней пагинации API запросов).
    *   **Тип**: Число.
    *   **Пример**: `1000`
*   **`issue_fields_to_request`**:
    *   **Описание**: Список строковых идентификаторов полей JIRA, которые необходимо запросить. Эти поля будут доступны для использования в шаблонах `issue_display_template`.
    *   **Тип**: Список строк.
    *   **Значения**:
        *   Стандартные поля: `key`, `summary`, `description`, `issuetype`, `priority`, `status`, `resolution`, `assignee`, `reporter`, `created`, `updated`, `labels`, `components`, `fixVersions`.
        *   **Связанные задачи**: `issuelinks` (для использования с плейсхолдером `{formatted_issuelinks}`).
        *   Кастомные поля: Указываются по их ID, например, `customfield_10010`.
    *   **Важно**: Поле `fixVersions` обязательно для парсинга версий. Все поля, используемые в плейсхолдерах `{...}` в `issue_display_template` (кроме специального `{content}` и автоматически генерируемого `{formatted_issuelinks}`), должны быть явно перечислены здесь.
    *   **Пример**:
        ```yaml
        issue_fields_to_request:
          - "key"
          - "summary"
          - "issuetype"   # Для {issuetype_name}
          - "priority"    # Для {priority_name}
          - "assignee"    # Для {assignee_name}
          - "status"      # Для {status_name}
          - "labels"      # Для {labels}
          - "issuelinks"  # Для {formatted_issuelinks}
          - "fixVersions"
          - "customfield_10400" # Пример поля для {content} в одной из секций
        ```
*   **`request_headers`**:
    *   **Описание**: Словарь дополнительных HTTP-заголовков для запросов к JIRA API.
    *   **Тип**: Словарь.
    *   **Пример**: `User-Agent: "My Release Notes Bot/1.1"`

---

### Секция `release_notes`

Настройки, определяющие структуру и основное содержание документа Release Notes.

*   **`title_template`**:
    *   **Описание**: Шаблон для заголовка Release Notes.
    *   **Плейсхолдеры**: `{global_version}`, `{current_date}`.
    *   **Пример**: `"Release Notes - версия {global_version} - {current_date}"`
*   **`date_format`**:
    *   **Описание**: Формат для `{current_date}` (синтаксис `strftime` Python).
    *   **Пример**: `"%d.%m.%Y"`
*   **`sections`**:
    *   **Описание**: Словарь, определяющий разделы документа. Порядок ключей определяет порядок секций.
    *   **Параметры для каждой секции** (`ключ_секции`):
        *   `title` (строка): Отображаемый заголовок секции.
        *   `source_custom_field_id` (строка): ID кастомного поля JIRA, содержимое которого будет основным текстом для задач в этой секции (плейсхолдер `{content}`). Если поле пусто, задача не попадет в эту секцию.
        *   `disable_grouping` (булево, опционально, по умолчанию `false`): Если `true`, задачи в этой секции выводятся единым списком, игнорируя группировку по микросервисам и типам. `group_by_issue_type` в этом случае не используется.
        *   `group_by_issue_type` (булево, опционально, по умолчанию `false`): Актуально только если `disable_grouping: false`. Если `true`, задачи внутри микросервиса группируются по типу.
        *   `issue_display_template` (строка, многострочная с `|`): Шаблон отображения задачи.
            *   **Плейсхолдеры**:
                *   Стандартные: `{key}`, `{summary}`, `{issuetype_name}`, `{priority_name}`, `{status_name}`, `{resolution_name}`, `{assignee_name}`, `{reporter_name}`, `{created}`, `{updated}`, `{labels}`, `{components}`.
                *   Кастомные поля: `{customfield_XXXXX}` (если ID указан в `jira.issue_fields_to_request`).
                *   Специальные:
                    *   `{content}`: Значение поля из `source_custom_field_id` текущей секции.
                    *   `{formatted_issuelinks}`: Строка "Связанные задачи: LINK1; LINK2...", если есть связанные задачи. Если связей нет, этот плейсхолдер заменяется на пустую строку (и заголовок "Связанные задачи:" не появляется). Для работы требует `"issuelinks"` в `jira.issue_fields_to_request`.
                    *   `{linked_microservices_names}`: Список имен микросервисов, к которым привязана задача (полезно для секций с `disable_grouping: true`).
            *   **Пример**:
                ```yaml
                issue_display_template: |
                  **[{key}]** {summary}
                  Тип: {issuetype_name}, Статус: {status_name}
                  {content}
                  {formatted_issuelinks}
                ```
*   **`microservices_table`**:
    *   **Описание**: Настройки таблицы микросервисов.
    *   `enabled` (булево), `title` (строка).
    *   `columns` (список словарей): Каждый словарь с `header` (строка) и `value_placeholder` (строка, например, `{name}`, `{version}`).

---

### Секция `version_parsing`

(Описание секции `version_parsing` остается таким же: `global_version.extraction_patterns`, `microservice_version` с `extraction_pattern`, `prefix_group_index`, `version_group_index`, и `microservice_mapping`)

---

### Секция `output_formats`

(Описание секции `output_formats.markdown` остается таким же: `..._level`, `task_list_item_marker`, `output_filename_template`, `output_directory`)

---

Тщательная настройка этих параметров позволит вам генерировать Release Notes, максимально соответствующие вашим требованиям и форматам.