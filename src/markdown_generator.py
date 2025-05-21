# src/markdown_generator.py
import logging
import re
from typing import Optional, List, Dict # <--- ДОБАВЬ ЭТУ СТРОКУ
from datetime import datetime  # Хотя current_date приходит из processed_data, может понадобиться для дефолтов

logger = logging.getLogger(__name__)


def _generate_title(title_text: str | None, level: int) -> str:
    """
    Генерирует строку Markdown для заголовка указанного уровня.

    Args:
        title_text (str | None): Текст заголовка. Если None или пустой, возвращается пустая строка.
        level (int): Уровень заголовка (1-6).

    Returns:
        str: Строка Markdown-заголовка (например, "## Мой заголовок\n") или пустая строка.
    """
    if not title_text or not title_text.strip():
        return ""
    # Убедимся, что уровень заголовка в допустимых пределах для Markdown
    clamped_level = max(1, min(6, level))
    return f"{'#' * clamped_level} {title_text.strip()}\n"


def _generate_table(headers: list[str], rows: list[list[str]]) -> str:
    """
    Генерирует строку Markdown для таблицы.

    Args:
        headers (list[str]): Список строк для заголовков колонок.
        rows (list[list[str]]): Список списков, где каждый внутренний список - это строка таблицы.
                                 Ожидается, что элементы уже преобразованы в строки или None.

    Returns:
        str: Строка Markdown-таблицы или пустая строка, если нет заголовков или строк данных.
    """
    if not headers or not any(h.strip() for h in headers) or not rows:
        logger.debug("Пропуск генерации таблицы: нет валидных заголовков или строк данных.")
        return ""

    table_parts = []
    # Заголовок таблицы
    table_parts.append(f"| {' | '.join(headers)} |")
    # Разделитель заголовка ( :---: для выравнивания по центру, --- для левого)
    table_parts.append(f"|{'|'.join(['---'] * len(headers))}|")

    # Строки таблицы
    for row in rows:
        # Преобразуем все элементы строки в строки, None в пустую строку
        processed_row = [str(item).strip() if item is not None else "" for item in row]
        table_parts.append(f"| {' | '.join(processed_row)} |")

    # Добавляем пустую строку после таблицы для лучшего рендеринга в некоторых Markdown-просмотрщиках
    return "\n".join(table_parts) + "\n\n"


def _format_template_string(template_str: str, data_dict: dict) -> str:
    """
    Заменяет плейсхолдеры вида {ключ} в строке-шаблоне значениями из словаря data_dict.
    Если плейсхолдер не найден в data_dict или его значение None, он заменяется на пустую строку.

    Args:
        template_str (str): Строка-шаблон с плейсхолдерами.
        data_dict (dict): Словарь с данными для подстановки.

    Returns:
        str: Строка с замененными плейсхолдерами.
    """

    def replace_match(match_obj):
        key_in_placeholder = match_obj.group(1)
        value_from_data = data_dict.get(key_in_placeholder)
        # Возвращаем пустую строку, если значение None, чтобы не выводить "None"
        return str(value_from_data) if value_from_data is not None else ""

        # Ищем плейсхолдеры: буквы, цифры, подчеркивание, точка, дефис

    return re.sub(r"\{([\w_.-]+)\}", replace_match, template_str)


def generate_markdown_content(processed_data: Dict, app_config: Dict) -> str:
    # ... (начало функции, генерация главного заголовка и таблицы МС - без изменений) ...
    logger.info("Начало генерации Markdown контента...")
    md_parts = []
    md_format_config = app_config.get('output_formats', {}).get('markdown', {})
    release_notes_config = app_config.get('release_notes', {})
    h_main_lvl = md_format_config.get('main_title_level', 1)
    h_table_lvl = md_format_config.get('table_title_level', 2)
    h_section_lvl = md_format_config.get('section_title_level', 2)
    h_ms_lvl = md_format_config.get('microservice_group_level', 3)
    h_type_lvl = md_format_config.get('issue_type_group_level', 4)
    task_item_marker = md_format_config.get('task_list_item_marker', '-')
    # ... (код для главного заголовка и таблицы МС как раньше) ...
    gv_text = processed_data.get("global_version", "N/A");
    date_text = processed_data.get("current_date", "N/A")
    title_tpl = release_notes_config.get('title_template', "Release Notes - {global_version} - {current_date}")
    main_title_str = _format_template_string(title_tpl, {"global_version": gv_text, "current_date": date_text})
    md_parts.append(_generate_title(main_title_str, h_main_lvl))
    ms_table_cfg_data = release_notes_config.get('microservices_table', {});
    ms_summary_list = processed_data.get("microservices_summary", [])
    if ms_table_cfg_data.get('enabled', True) and ms_summary_list:
        table_title_heading = ms_table_cfg_data.get('title')
        md_parts.append(_generate_title(table_title_heading, h_table_lvl))
        cols_cfg: List[Dict] = ms_table_cfg_data.get('columns', []);
        tbl_headers: List[str] = [col.get('header', '') for col in cols_cfg]
        tbl_rows = [[_format_template_string(col.get('value_placeholder', ''), item) for col in cols_cfg] for item in
                    ms_summary_list]
        if tbl_headers and any(h.strip() for h in tbl_headers) and tbl_rows: md_parts.append(
            _generate_table(tbl_headers, tbl_rows))

    # --- Генерация Секций ---
    sections_content_map = processed_data.get("sections_data", {})
    configured_section_metadata = release_notes_config.get('sections', {})

    for section_id, section_meta_cfg in configured_section_metadata.items():
        current_section_data = sections_content_map.get(section_id)
        if not current_section_data: continue

        _add_title_to_parts(md_parts, current_section_data.get('title'), h_section_lvl)  # Используем новую функцию

        # Получаем шаблон ТОЛЬКО для "шапки"
        header_template_str = section_meta_cfg.get('issue_header_template')
        # source_custom_field_id все еще нужен data_processor'у для поля {content}

        if not header_template_str:  # Если нет даже шаблона шапки, выводим предупреждение
            logger.warning(
                f"Шаблон 'issue_header_template' не найден для секции '{section_id}'. Задачи могут отображаться некорректно.")
            # Можно просто выводить content, если он есть, или плейсхолдер
            # md_parts.append(f"{task_item_marker} *Конфигурация отображения шапки задач отсутствует.*\n\n")
            # continue # Решаем, пропускать ли всю секцию или пытаться вывести только content

        is_flat_mode = current_section_data.get("disable_grouping", False)

        task_lists_to_iterate = []
        if is_flat_mode:
            tasks_for_flat_list = current_section_data.get("tasks_flat_list", [])
            if not tasks_for_flat_list:
                md_parts.append(f"{task_item_marker} *Нет задач для отображения в этой секции.*\n\n")
            else:
                task_lists_to_iterate.append({"is_header_block": False, "tasks": sorted(tasks_for_flat_list,
                                                                                        key=lambda t: str(
                                                                                            t.get("key", "")))})
        else:  # Группировка по МС
            ms_map = current_section_data.get('microservices', {})
            if not ms_map: logger.debug(
                f"В секции '{section_id}' нет МС с задачами.");  # continue # Можно не выводить ничего если нет МС

            for ms_name_val in sorted(ms_map.keys()):
                ms_render_data = ms_map[ms_name_val]
                has_tasks = any(ms_render_data.get('issue_types', {}).values()) or ms_render_data.get(
                    'tasks_without_type_grouping')
                if not has_tasks: continue

                task_lists_to_iterate.append({"is_header_block": True, "text": ms_name_val, "level": h_ms_lvl})

                group_by_type_flag = current_section_data.get('group_by_issue_type', False)
                if group_by_type_flag:
                    issue_types_data = ms_render_data.get('issue_types', {})
                    for type_name_str in sorted(issue_types_data.keys()):
                        tasks = issue_types_data[type_name_str]
                        if tasks:
                            task_lists_to_iterate.append(
                                {"is_header_block": True, "text": type_name_str, "level": h_type_lvl})
                            task_lists_to_iterate.append(
                                {"is_header_block": False, "tasks": sorted(tasks, key=lambda t: str(t.get("key", "")))})
                else:
                    tasks_no_group = ms_render_data.get('tasks_without_type_grouping', [])
                    if tasks_no_group:
                        task_lists_to_iterate.append({"is_header_block": False, "tasks": sorted(tasks_no_group,
                                                                                                key=lambda t: str(
                                                                                                    t.get("key", "")))})

        # Общий цикл рендеринга для собранных списков задач или заголовков
        for item_group in task_lists_to_iterate:
            if item_group.get("is_header_block"):
                _add_title_to_parts(md_parts, item_group["text"], item_group["level"])
            else:
                for task_data_item in item_group.get("tasks", []):
                    # Формируем "шапку" задачи
                    task_header_str = ""
                    if header_template_str:  # Используем шаблон шапки, если он есть
                        task_header_str = _format_template_string(header_template_str, task_data_item).strip()

                    # Получаем "контент" задачи
                    task_content_str = str(task_data_item.get('content', '')).strip()

                    if not task_header_str and not task_content_str:  # Если и шапка, и контент пустые
                        logger.debug(f"Задача {task_data_item.get('key')} не дала видимого контента (шапка и тело).")
                        continue

                    # Выводим шапку (жирным), если она есть
                    if task_header_str:
                        header_lines = [line.strip() for line in task_header_str.splitlines() if line.strip()]
                        first_line_of_header = True
                        for h_line in header_lines:
                            if first_line_of_header:
                                md_parts.append(f"{task_item_marker} **{h_line}**\n")
                                first_line_of_header = False
                            else:
                                md_parts.append(f"  **{h_line}**\n")  # Последующие строки шапки тоже жирные с отступом

                    # Выводим контент (обычным текстом)
                    if task_content_str:
                        content_lines = [line.strip() for line in task_content_str.splitlines() if line.strip()]
                        # Если шапки не было, первая строка контента получает маркер списка (не жирным)
                        if not task_header_str and content_lines:
                            md_parts.append(f"{task_item_marker} {content_lines[0]}\n")
                            for c_line_idx, c_line in enumerate(content_lines):
                                if c_line_idx > 0:  # Последующие строки контента с отступом
                                    md_parts.append(f"  {c_line}\n")
                        # Если шапка была, контент идет с отступом без своего маркера
                        elif task_header_str and content_lines:
                            for c_line in content_lines:
                                md_parts.append(f"  {c_line}\n")

                    if task_header_str or task_content_str:  # Добавляем пустую строку только если что-то было выведено
                        md_parts.append("\n")

    logger.info("Генерация Markdown контента завершена.")
    return "".join(md_parts)

def _add_title_to_parts(parts_list: list, title_text: Optional[str], level: int):
    """Генерирует и добавляет заголовок в список, если текст не пуст."""
    if title_text and title_text.strip():
        parts_list.append(_generate_title(title_text, level))
