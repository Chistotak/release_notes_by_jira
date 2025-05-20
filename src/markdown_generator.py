# src/markdown_generator.py
import logging
import re
from datetime import datetime

logger = logging.getLogger(__name__)


def _generate_title(title_text: str | None, level: int) -> str:
    if not title_text:
        return ""
    return f"{'#' * level} {title_text}\n"


def _generate_table(headers: list[str], rows: list[list[str]]) -> str:
    if not headers or not rows:
        logger.debug("Пропуск генерации таблицы: нет заголовков или строк.")
        return ""

    table_parts = [f"| {' | '.join(headers)} |", f"|{'|'.join(['---'] * len(headers))}|"]
    for row in rows:
        processed_row = [str(item) if item is not None else "" for item in row]
        table_parts.append(f"| {' | '.join(processed_row)} |")

    return "\n".join(table_parts) + "\n\n"


def _format_template_string(template_str: str, data_dict: dict) -> str:
    def replace_match(match):
        key = match.group(1)
        value = data_dict.get(key)
        return str(value) if value is not None else ""

    return re.sub(r"\{([\w_.-]+)\}", replace_match, template_str)


def generate_markdown_content(processed_data: dict, app_config: dict) -> str:
    logger.info("Начало генерации Markdown контента...")
    md_parts = []

    md_format_config = app_config.get('output_formats', {}).get('markdown', {})
    release_notes_config = app_config.get('release_notes', {})

    main_title_level = md_format_config.get('main_title_level', 1)
    table_title_level = md_format_config.get('table_title_level', 2)
    section_title_level = md_format_config.get('section_title_level', 2)
    microservice_group_level = md_format_config.get('microservice_group_level', 3)
    issue_type_group_level = md_format_config.get('issue_type_group_level', 4)
    task_list_item_marker = md_format_config.get('task_list_item_marker', '-')

    global_version = processed_data.get("global_version", "N/A")
    current_date_str = processed_data.get("current_date",
                                          datetime.now().strftime(release_notes_config.get('date_format', '%Y-%m-%d')))
    title_template = release_notes_config.get('title_template', "Release Notes - {global_version} - {current_date}")
    title_format_data = {"global_version": global_version, "current_date": current_date_str}
    main_title_text = _format_template_string(title_template, title_format_data)
    md_parts.append(_generate_title(main_title_text, main_title_level))

    microservices_table_config = release_notes_config.get('microservices_table', {})
    microservices_summary_data = processed_data.get("microservices_summary", [])
    if microservices_table_config.get('enabled', False) and microservices_summary_data:
        table_title_text = microservices_table_config.get('title')
        md_parts.append(_generate_title(table_title_text, table_title_level))
        column_configs = microservices_table_config.get('columns', [])
        table_headers = [col_cfg.get('header', '') for col_cfg in column_configs]
        table_rows = [
            [_format_template_string(col_cfg.get('value_placeholder', ''), ms_item) for col_cfg in column_configs]
            for ms_item in microservices_summary_data]
        if table_headers and any(h.strip() for h in table_headers) and table_rows:
            md_parts.append(_generate_table(table_headers, table_rows))

    sections_content_map = processed_data.get("sections_data", {})
    configured_section_metadata = release_notes_config.get('sections', {})

    for section_key, section_meta_from_config in configured_section_metadata.items():
        current_section_data_from_processor = sections_content_map.get(section_key)

        if not current_section_data_from_processor:
            logger.debug(f"Данные для секции '{section_key}' отсутствуют, секция пропускается.")
            continue

        section_title_text = current_section_data_from_processor.get('title')
        md_parts.append(_generate_title(section_title_text, section_title_level))

        issue_template_for_section = section_meta_from_config.get('issue_display_template')
        if not issue_template_for_section:
            logger.warning(f"Шаблон 'issue_display_template' не для секции '{section_key}'. Задачи не отображены.")
            md_parts.append(f"{task_list_item_marker} *Конфигурация отображения задач отсутствует.*\n\n")
            continue

        is_grouping_disabled = current_section_data_from_processor.get("disable_grouping", False)

        if is_grouping_disabled:
            tasks_flat_list = current_section_data_from_processor.get("tasks_flat_list", [])
            if not tasks_flat_list:
                md_parts.append(f"{task_list_item_marker} *Нет задач для отображения в этой секции.*\n\n")
            else:
                sorted_tasks_flat_list = sorted(tasks_flat_list, key=lambda t: str(t.get("key", "")))
                for task_data_dict in sorted_tasks_flat_list:
                    formatted_task_entry_str = _format_template_string(issue_template_for_section, task_data_dict)
                    lines = formatted_task_entry_str.strip().splitlines()
                    if lines:
                        md_parts.append(f"{task_list_item_marker} {lines[0].strip()}\n")
                        for line in lines[1:]: md_parts.append(f"  {line.strip()}\n")
                md_parts.append("\n")
        else:
            microservices_in_section = current_section_data_from_processor.get('microservices', {})
            if not microservices_in_section:
                continue

            sorted_ms_names = sorted(microservices_in_section.keys())
            for ms_name in sorted_ms_names:
                ms_data = microservices_in_section[ms_name]
                has_tasks = any(ms_data.get('issue_types', {}).values()) or ms_data.get('tasks_without_type_grouping')
                if not has_tasks: continue

                md_parts.append(_generate_title(ms_name, microservice_group_level))
                should_group_by_type = current_section_data_from_processor.get('group_by_issue_type', False)

                render_list = []
                if should_group_by_type:
                    types_map = ms_data.get('issue_types', {})
                    for type_name in sorted(types_map.keys()):
                        tasks = types_map[type_name]
                        if tasks:
                            render_list.append({"is_header": True, "text": type_name, "level": issue_type_group_level})
                            sorted_tasks = sorted(tasks, key=lambda task: str(task.get("key", "")))
                            render_list.extend([{"is_header": False, "data_dict": t} for t in sorted_tasks])
                else:
                    tasks_list = ms_data.get('tasks_without_type_grouping', [])
                    if tasks_list:
                        sorted_tasks = sorted(tasks_list, key=lambda task: str(task.get("key", "")))
                        render_list.extend([{"is_header": False, "data_dict": t} for t in sorted_tasks])

                if not render_list: continue

                for item in render_list:
                    if item["is_header"]:
                        md_parts.append(_generate_title(item["text"], item["level"]))
                    else:
                        task_data = item["data_dict"]
                        formatted_entry = _format_template_string(issue_template_for_section, task_data)
                        lines = formatted_entry.strip().splitlines()
                        if lines:
                            md_parts.append(f"{task_list_item_marker} {lines[0].strip()}\n")
                            for line in lines[1:]: md_parts.append(f"  {line.strip()}\n")
                md_parts.append("\n")

    logger.info("Генерация Markdown контента завершена.")
    return "".join(md_parts)


# Блок if __name__ == '__main__': остается таким же, как в предыдущей полной версии markdown_generator.py.
if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    mock_processed_data_for_md_test = {
        "global_version": "3.1.0", "current_date": "05.11.2023",
        "microservices_summary": [{"prefix": "WEB", "name": "WebApp Service", "version": "3.1.0"}],
        "sections_data": {
            "features": {"title": "Новые возможности", "disable_grouping": False, "group_by_issue_type": True,
                         "microservices": {"WebApp Service": {"issue_types": {"Story": [
                             {"key": "WEB-123", "summary": "Dark Theme", "issuetype_name": "Story",
                              "content": "Dark theme added."}]}, "tasks_without_type_grouping": []}}},
            "all_tasks_flat_section": {"title": "Все задачи плоско", "disable_grouping": True,
                                       "group_by_issue_type": False,
                                       "tasks_flat_list": [
                                           {"key": "WEB-123", "summary": "Dark Theme", "issuetype_name": "Story",
                                            "content": "Dark theme added.",
                                            "linked_microservices_names": "WebApp Service"},
                                           {"key": "API-456", "summary": "OAuth fix", "issuetype_name": "Bug",
                                            "content": "OAuth bug fixed.", "linked_microservices_names": "API Gateway"},
                                           {"key": None, "summary": "Task without key", "issuetype_name": "Task",
                                            "content": "Content for task without key."}
                                       ], "microservices": {}
                                       }
        }
    }
    mock_app_config_for_md_test = {
        "release_notes": {
            "title_template": "Релиз {global_version}", "date_format": "%d.%m.%Y",
            "sections": {
                "features": {"issue_display_template": "**{key}**: {summary}\n{content}"},
                "all_tasks_flat_section": {
                    "issue_display_template": "Задача {key} ({issuetype_name}) для МС [{linked_microservices_names}]: {summary}. Детали: {content}"}
            },
            "microservices_table": {"enabled": True, "title": "Компоненты",
                                    "columns": [{"header": "Имя", "value_placeholder": "{name}"}]}
        },
        "output_formats": {"markdown": {"main_title_level": 1, "table_title_level": 2, "section_title_level": 2,
                                        "microservice_group_level": 3, "issue_type_group_level": 4,
                                        "task_list_item_marker": "-"}}
    }
    logger.info("Запуск тестовой генерации Markdown (с disable_grouping)...")
    markdown_output_test = generate_markdown_content(mock_processed_data_for_md_test, mock_app_config_for_md_test)
    print("\n--- Результат генерации Markdown (Тест с disable_grouping) ---")
    print(markdown_output_test)

    assert "# Релиз 3.1.0" in markdown_output_test
    assert "## Компоненты" in markdown_output_test
    assert "| WebApp Service | 3.1.0 |" in markdown_output_test
    assert "## Новые возможности" in markdown_output_test
    assert "### WebApp Service" in markdown_output_test
    assert "#### Story" in markdown_output_test
    assert "- **WEB-123**: Dark Theme" in markdown_output_test
    assert "## Все задачи плоско" in markdown_output_test
    assert "- Задача None (Task) для МС []: Task without key. Детали: Content for task without key." in markdown_output_test
    assert "- Задача API-456 (Bug) для МС [API Gateway]: OAuth fix. Детали: OAuth bug fixed." in markdown_output_test
    assert "- Задача WEB-123 (Story) для МС [WebApp Service]: Dark Theme. Детали: Dark theme added." in markdown_output_test
    logger.info("Тестовая генерация Markdown (с disable_grouping) завершена.")