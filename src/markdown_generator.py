# src/markdown_generator.py
import logging
import re
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


def generate_markdown_content(processed_data: dict, app_config: dict) -> str:
    """
    Генерирует полный текст Release Notes в формате Markdown.

    Использует структурированные данные от data_processor и настройки
    форматирования из конфигурационного файла.

    Args:
        processed_data (dict): Словарь с обработанными данными от data_processor.
        app_config (dict): Полная конфигурация приложения.

    Returns:
        str: Строка, содержащая весь Markdown-документ.
    """
    logger.info("Начало генерации Markdown контента...")
    md_document_parts = []

    md_format_settings = app_config.get('output_formats', {}).get('markdown', {})
    release_notes_settings = app_config.get('release_notes', {})

    # Уровни заголовков и маркер списка из конфигурации
    h_main_lvl = md_format_settings.get('main_title_level', 1)
    h_table_lvl = md_format_settings.get('table_title_level', 2)
    h_section_lvl = md_format_settings.get('section_title_level', 2)
    h_ms_lvl = md_format_settings.get('microservice_group_level', 3)
    h_type_lvl = md_format_settings.get('issue_type_group_level', 4)
    task_item_marker = md_format_settings.get('task_list_item_marker', '-')

    # 1. Главный заголовок Release Notes
    rn_global_version = processed_data.get("global_version", "N/A")
    rn_current_date = processed_data.get("current_date",
                                         datetime.now().strftime(release_notes_settings.get('date_format', '%Y-%m-%d')))
    rn_title_template = release_notes_settings.get('title_template',
                                                   "Release Notes - {global_version} - {current_date}")
    main_title_text = _format_template_string(rn_title_template,
                                              {"global_version": rn_global_version, "current_date": rn_current_date})
    md_document_parts.append(_generate_title(main_title_text, h_main_lvl))

    # 2. Таблица микросервисов
    ms_table_config = release_notes_settings.get('microservices_table', {})
    ms_summary_list = processed_data.get("microservices_summary", [])
    if ms_table_config.get('enabled', True) and ms_summary_list:  # По умолчанию таблица включена, если есть данные
        table_title = ms_table_config.get('title')
        md_document_parts.append(_generate_title(table_title, h_table_lvl))

        cols_config = ms_table_config.get('columns', [])
        table_headers_list = [col.get('header', '') for col in cols_config]
        table_content_rows = []
        for ms_item in ms_summary_list:
            row = [_format_template_string(col.get('value_placeholder', ''), ms_item) for col in cols_config]
            table_content_rows.append(row)

        if table_headers_list and any(h.strip() for h in table_headers_list) and table_content_rows:
            md_document_parts.append(_generate_table(table_headers_list, table_content_rows))
        elif table_headers_list and any(h.strip() for h in table_headers_list):  # Есть заголовки, но нет строк
            logger.info("Таблица микросервисов не будет сгенерирована: нет данных для строк.")
            # md_document_parts.append(f"{task_item_marker} *Данные по микросервисам отсутствуют.*\n\n")

    # 3. Информационные секции
    sections_from_data_processor = processed_data.get("sections_data", {})
    sections_metadata_from_config = release_notes_settings.get('sections', {})

    for section_id, section_meta_cfg in sections_metadata_from_config.items():  # Итерация по конфигу для сохранения порядка
        section_data = sections_from_data_processor.get(section_id)
        if not section_data:
            logger.debug(f"Данные для секции '{section_id}' отсутствуют в processed_data, секция пропускается.")
            continue

        section_display_title = section_data.get('title')  # Заголовок уже подготовлен data_processor
        md_document_parts.append(_generate_title(section_display_title, h_section_lvl))

        task_display_template = section_meta_cfg.get('issue_display_template')
        if not task_display_template:
            logger.warning(
                f"Шаблон 'issue_display_template' не найден для секции '{section_id}'. Задачи этой секции не будут отображены.")
            md_document_parts.append(
                f"{task_item_marker} *Конфигурация отображения задач для этой секции отсутствует.*\n\n")
            continue

        is_flat_display_mode = section_data.get("disable_grouping", False)

        if is_flat_display_mode:
            tasks_for_flat_list = section_data.get("tasks_flat_list", [])
            if not tasks_for_flat_list:
                md_document_parts.append(f"{task_item_marker} *Нет задач для отображения в этой секции.*\n\n")
            else:
                # Сортировка задач в плоском списке по ключу для консистентности
                sorted_flat_tasks = sorted(tasks_for_flat_list, key=lambda t: str(t.get("key", "")))
                for task_render_data in sorted_flat_tasks:
                    formatted_task_md = _format_template_string(task_display_template, task_render_data)
                    task_lines = formatted_task_md.strip().splitlines()
                    if task_lines:
                        md_document_parts.append(f"{task_item_marker} {task_lines[0].strip()}\n")
                        for line in task_lines[1:]: md_document_parts.append(f"  {line.strip()}\n")
                md_document_parts.append("\n")
        else:  # Режим с группировкой по микросервисам
            microservices_map_for_section = section_data.get('microservices', {})
            if not microservices_map_for_section:
                # md_document_parts.append(f"{task_item_marker} *Нет данных по микросервисам для этой секции.*\n\n")
                logger.debug(f"В секции '{section_id}' нет микросервисов с задачами.")
                continue

            sorted_ms_names_list = sorted(microservices_map_for_section.keys())
            for ms_name_key in sorted_ms_names_list:
                ms_tasks_data = microservices_map_for_section[ms_name_key]
                # Проверяем, есть ли вообще задачи для этого МС в этой секции
                has_any_tasks_for_ms = any(ms_tasks_data.get('issue_types', {}).values()) or ms_tasks_data.get(
                    'tasks_without_type_grouping')
                if not has_any_tasks_for_ms:
                    logger.debug(
                        f"Микросервис '{ms_name_key}' в секции '{section_id}' не содержит задач, пропускается.")
                    continue

                md_document_parts.append(_generate_title(ms_name_key, h_ms_lvl))
                group_by_issue_type_flag = section_data.get('group_by_issue_type', False)

                items_to_render_for_ms = []  # Список словарей: {"is_header": bool, "text": str, "level": int} или {"is_header": False, "data_dict": dict}
                if group_by_issue_type_flag:
                    issue_types_map_for_ms = ms_tasks_data.get('issue_types', {})
                    for issue_type_key in sorted(issue_types_map_for_ms.keys()):  # Сортируем типы задач
                        tasks_list_for_type = issue_types_map_for_ms[issue_type_key]
                        if tasks_list_for_type:  # Только если есть задачи этого типа
                            items_to_render_for_ms.append(
                                {"is_header": True, "text": issue_type_key, "level": h_type_lvl})
                            sorted_tasks_for_type = sorted(tasks_list_for_type, key=lambda tsk: str(tsk.get("key", "")))
                            items_to_render_for_ms.extend(
                                [{"is_header": False, "data_dict": t_data} for t_data in sorted_tasks_for_type])
                else:  # Не группируем по типу, выводим задачи для МС списком
                    tasks_list_no_type_group = ms_tasks_data.get('tasks_without_type_grouping', [])
                    if tasks_list_no_type_group:
                        sorted_tasks_no_type = sorted(tasks_list_no_type_group, key=lambda tsk: str(tsk.get("key", "")))
                        items_to_render_for_ms.extend(
                            [{"is_header": False, "data_dict": t_data} for t_data in sorted_tasks_no_type])

                if not items_to_render_for_ms:
                    # md_document_parts.append(f"{task_item_marker} *Нет задач для отображения в этом микросервисе.*\n\n")
                    continue

                for item in items_to_render_for_ms:
                    if item["is_header"]:
                        md_document_parts.append(_generate_title(item["text"], item["level"]))
                    else:
                        task_render_data = item["data_dict"]
                        formatted_task_md = _format_template_string(task_display_template, task_render_data)
                        task_lines = formatted_task_md.strip().splitlines()
                        if task_lines:
                            md_document_parts.append(f"{task_item_marker} {task_lines[0].strip()}\n")
                            for line in task_lines[1:]: md_document_parts.append(f"  {line.strip()}\n")
                md_document_parts.append("\n")  # Отступ после всех задач/типов одного микросервиса

    logger.info("Генерация Markdown контента завершена.")
    return "".join(md_document_parts)
