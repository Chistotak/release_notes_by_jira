# Руководство по конфигурации генератора Release Notes

Этот документ подробно описывает настройку генератора Release Notes через файлы `.env` и `config/config.yaml`.

## Файл `.env`

(Описание `JIRA_COOKIE_STRING` остается прежним)

---

## Файл `config/config.yaml`

Основной конфигурационный файл, расположенный в `config/`.

### Секция `defaults` (Опционально)

(Описание секции `defaults` с `filter_id` и `output_dir` остается прежним)

---

### Секция `jira`

(Описание `server_url`, `timeout`, `max_results_per_request` остается прежним)

*   **`issue_fields_to_request`**:
    *   **Описание**: Список полей JIRA для запроса. Эти поля будут доступны в шаблонах `issue_display_template`.
    *   **Важно**: Включите `"issuelinks"` для работы `{formatted_issuelinks}` и ID вашего кастомного поля клиента (например, `"customfield_12902"`) для работы `{client_name}` и `{formatted_client_info}`.
    *   **Пример**:
        ```yaml
        issue_fields_to_request:
          - "key"
          - "summary"
          - "issuetype"
          - "fixVersions"
          - "issuelinks"        # Для связанных задач
          - "customfield_12902" # Для информации о клиенте
          - "customfield_10400" # Пример поля для {content}
        ```
*   **`request_headers`**: (Описание остается прежним)

---

### Секция `release_notes`

(Описание `title_template`, `date_format` остается прежним)

*   **`filter_issuelinks_by_project_prefixes`** (опционально):
    *   **Описание**: Список строковых префиксов проектов JIRA. В секции `{formatted_issuelinks}` будут отображаться только те связанные задачи, ключи которых начинаются с одного из этих префиксов (например, "CCSSUP-"). Если список пуст или отсутствует, отображаются все связи.
    *   **Тип**: Список строк.
    *   **Пример**: `filter_issuelinks_by_project_prefixes: ["CCSSUP", "PROJ"]`
*   **`sections`**:
    *   **Параметры для каждой секции**:
        *   `title`, `source_custom_field_id`, `disable_grouping`, `group_by_issue_type` (описания остаются прежними).
        *   `issue_display_template` (строка, многострочная): Шаблон отображения задачи.
            *   **Плейсхолдеры**:
                *   (Список стандартных плейсхолдеров остается прежним: `{key}`, `{summary}`, `{issuetype_name}` и т.д.)
                *   `{content}`: Значение из `source_custom_field_id`.
                *   `{formatted_issuelinks}`: Строка "Связанные задачи: LINK1; LINK2...", содержащая только отфильтрованные по `filter_issuelinks_by_project_prefixes` связи. Если релевантных связей нет, плейсхолдер заменяется на пустую строку.
                *   `{client_name}`: Имя клиента, извлеченное из кастомного поля (например, `customfield_12902`).
                *   `{formatted_client_info}`: Строка "Клиент: ИМЯ_КЛИЕНТА". Отображается **только если** было извлечено имя клиента **и** для задачи есть хотя бы одна отфильтрованная (релевантная) связанная задача. В противном случае плейсхолдер заменяется на пустую строку.
                *   `{linked_microservices_names}`: Имена микросервисов задачи.
            *   **Пример**:
                ```yaml
                issue_display_template: |
                  **{key}** {summary}
                  {content}
                  {formatted_issuelinks} {formatted_client_info} 
                ```
*   **`microservices_table`**: (Описание остается прежним)

---

### Секция `version_parsing`

(Описание секции `version_parsing` остается прежним)

---

### Секция `output_formats`

*   **`markdown`**: (Описание остается прежним)
*   **`word`**:
    *   **Описание**: Настройки для вывода в формате Word (.docx).
    *   **Тип**: Словарь.
    *   **Параметры**:
        *   `enabled` (булево, `true`/`false`): Включить/выключить генерацию `.docx`.
        *   `template_path` (строка, опционально): Путь к файлу шаблона `.docx`. Если указан, новый документ будет создан на его основе, наследуя стили. Путь может быть относительным от корня проекта (например, `config/templates/my_template.docx`).
        *   `output_filename_template` (строка): Шаблон имени выходного файла. Плейсхолдеры: `{global_version}`, `{current_date_filename}`.
        *   `styles` (словарь, опционально): Маппинг на имена стилей Word. Используется, если шаблон не указан или нужно переопределить стандартные имена стилей, которые скрипт пытается использовать по умолчанию (`Heading 1`, `Heading 2`, `List Bullet` и т.д.).
            *   **Пример**:
                ```yaml
                styles:
                  main_title: "Мой Стиль Главного Заголовка"
                  section_title: "Стиль Заголовка Раздела"
                  list_bullet: "Мой Маркированный Список"
                  table_style: "МояКрасиваяТаблица" # Имя стиля таблицы в Word
                ```

---
(Секция `logging` остается прежней)

Тщательная настройка этих параметров позволит вам генерировать Release Notes, максимально соответствующие вашим требованиям и форматам.