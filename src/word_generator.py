# src/word_generator.py
import logging
import re
from typing import Optional, List, Dict  # Добавляем Optional, List, Dict для аннотаций

from docx import Document
from docx.shared import Pt, Inches
from docx.enum.text import WD_ALIGN_PARAGRAPH

logger = logging.getLogger(__name__)

STYLE_NORMAL = 'Normal'
STYLE_HEADING_1 = 'Heading 1'
STYLE_HEADING_2 = 'Heading 2'
STYLE_HEADING_3 = 'Heading 3'
STYLE_HEADING_4 = 'Heading 4'
STYLE_LIST_BULLET = 'List Bullet'
STYLE_TABLE_DEFAULT = 'Table Grid'


def _format_template_string(template_str: str, data_dict: Dict) -> str:  # Используем Dict
    def replace_match(match_obj):
        key_in_placeholder = match_obj.group(1)
        value_from_data = data_dict.get(key_in_placeholder)
        return str(value_from_data) if value_from_data is not None else ""

    return re.sub(r"\{([\w_.-]+)\}", replace_match, template_str)


def _add_heading_with_style(document: Document, text: Optional[str], level: int,
                            default_style_name: str):  # Используем Optional и Document
    if not text or not text.strip():
        logger.debug("Пропуск добавления пустого заголовка.")
        return
    actual_level = max(1, min(4, level))
    try:
        heading_paragraph = document.add_heading(level=actual_level)
        heading_paragraph.text = text.strip()
        if default_style_name and default_style_name not in [f"Heading {i}" for i in range(1, 5)]:
            try:
                heading_paragraph.style = default_style_name
                logger.debug(f"Применен кастомный стиль заголовка '{default_style_name}' для текста: '{text[:30]}...'")
            except KeyError:
                logger.warning(
                    f"Стиль заголовка '{default_style_name}' не найден. Использован стандартный Heading {actual_level}.")
    except Exception as e:
        logger.error(f"Ошибка при добавлении заголовка '{text[:30]}...': {e}")


def _add_task_entry(document: Document, template_str: str, task_data_dict: Dict, list_item_style: str,
                    subsequent_line_style: Optional[str] = None,
                    indent_pt: Optional[Pt] = None):  # Используем Optional и Pt
    if indent_pt is None:  # Устанавливаем значение по умолчанию для Pt, если оно None
        indent_pt = Pt(20)

    formatted_task_entry_str = _format_template_string(template_str, task_data_dict)
    lines_of_task_entry = formatted_task_entry_str.strip().splitlines()

    if not lines_of_task_entry:
        logger.debug(f"Задача {task_data_dict.get('key', 'UKNOWN_KEY')} не дала видимого контента по шаблону.")
        return

    first_line = True
    for line_text in lines_of_task_entry:
        stripped_line = line_text.strip()
        if not stripped_line and not first_line:
            continue

        if first_line:
            p = document.add_paragraph(stripped_line, style=list_item_style)
            first_line = False
        else:
            style_to_use = subsequent_line_style if subsequent_line_style else STYLE_NORMAL
            p = document.add_paragraph(stripped_line, style=style_to_use)
            if style_to_use == STYLE_NORMAL and indent_pt is not None:
                p.paragraph_format.left_indent = indent_pt


def generate_word_document(processed_data: Dict, app_config: Dict) -> Optional[Document]:  # ИСПРАВЛЕНО ЗДЕСЬ
    """
    Генерирует документ Word (.docx) на основе обработанных данных и конфигурации.
    (остальная часть docstring без изменений)
    """
    logger.info("Начало генерации Word (.docx) документа...")

    word_cfg = app_config.get('output_formats', {}).get('word', {})
    if not word_cfg or not word_cfg.get('enabled', False):
        logger.info("Генерация Word документа отключена в конфигурации или секция 'word' отсутствует.")
        return None

    template_path = word_cfg.get('template_path')
    document: Document  # Аннотация для переменной
    if template_path:
        try:
            document = Document(template_path)
            logger.info(f"Используется Word шаблон: {template_path}")
        except Exception as e:
            logger.warning(
                f"Не удалось загрузить Word шаблон '{template_path}': {e}. Будет создан документ со стилями по умолчанию.")
            document = Document()
    else:
        document = Document()
        logger.info("Word шаблон не указан, создается документ со стилями по умолчанию.")

    styles_cfg = word_cfg.get('styles', {})
    s_main_title = styles_cfg.get('main_title', STYLE_HEADING_1)
    s_table_title = styles_cfg.get('table_title', STYLE_HEADING_2)
    s_section_title = styles_cfg.get('section_title', STYLE_HEADING_2)
    s_ms_group = styles_cfg.get('microservice_group', STYLE_HEADING_3)
    s_issue_type_group = styles_cfg.get('issue_type_group', STYLE_HEADING_4)
    s_list_item = styles_cfg.get('list_bullet', STYLE_LIST_BULLET)
    s_list_multiline_indent = styles_cfg.get('list_bullet_multiline_indent', STYLE_NORMAL)
    s_table = styles_cfg.get('table_style', STYLE_TABLE_DEFAULT)

    rn_config = app_config.get('release_notes', {})

    gv = processed_data.get("global_version", "N/A")
    cd = processed_data.get("current_date", "N/A")
    title_tpl = rn_config.get('title_template', "Release Notes - {global_version} - {current_date}")
    main_title = _format_template_string(title_tpl, {"global_version": gv, "current_date": cd})
    _add_heading_with_style(document, main_title, level=1, default_style_name=s_main_title)

    ms_table_cfg = rn_config.get('microservices_table', {})
    ms_summary = processed_data.get("microservices_summary", [])  # Используем List[Dict]
    if ms_table_cfg.get('enabled', True) and ms_summary:
        table_title_str = ms_table_cfg.get('title')
        _add_heading_with_style(document, table_title_str, level=2, default_style_name=s_table_title)

        cols_cfg: List[Dict] = ms_table_cfg.get('columns', [])  # Аннотация
        tbl_headers: List[str] = [col.get('header', '') for col in cols_cfg]  # Аннотация

        if tbl_headers and any(h.strip() for h in tbl_headers):
            try:
                table = document.add_table(rows=1, cols=len(tbl_headers))
                table.style = s_table
                hdr_cells = table.rows[0].cells
                for i, h_text in enumerate(tbl_headers): hdr_cells[i].text = h_text
                for ms_item_data in ms_summary:
                    row_cells = table.add_row().cells
                    for i, col_config in enumerate(cols_cfg):
                        placeholder = col_config.get('value_placeholder', '')
                        cell_val = _format_template_string(placeholder, ms_item_data)
                        row_cells[i].text = cell_val
                document.add_paragraph()
            except Exception as e:
                logger.error(f"Ошибка при создании таблицы микросервисов: {e}")
        elif tbl_headers and not ms_summary:
            logger.info("Таблица микросервисов: нет данных для строк.")

    sections_data_map = processed_data.get("sections_data", {})
    sections_meta_map = rn_config.get('sections', {})

    for section_id_key, section_meta_config in sections_meta_map.items():
        current_section_proc_data = sections_data_map.get(section_id_key)
        if not current_section_proc_data:
            logger.debug(f"Секция '{section_id_key}' пропущена (нет данных).")
            continue

        _add_heading_with_style(document, current_section_proc_data.get('title'), level=2,
                                default_style_name=s_section_title)

        template_for_issue = section_meta_config.get('issue_display_template')
        if not template_for_issue:
            logger.warning(f"Для секции '{section_id_key}' отсутствует 'issue_display_template'.")
            p = document.add_paragraph(style=s_list_item)
            p.add_run("* Конфигурация отображения задач отсутствует.*")
            document.add_paragraph()
            continue

        is_flat_mode = current_section_proc_data.get("disable_grouping", False)

        if is_flat_mode:
            flat_task_list: List[Dict] = current_section_proc_data.get("tasks_flat_list", [])  # Аннотация
            if not flat_task_list:
                p = document.add_paragraph(style=s_list_item)
                p.add_run("* Нет задач для отображения в этой секции.*")
            else:
                sorted_tasks = sorted(flat_task_list, key=lambda tsk_dict: str(tsk_dict.get("key", "")))
                for task_dict_item in sorted_tasks:
                    _add_task_entry(document, template_for_issue, task_dict_item, s_list_item, s_list_multiline_indent)
            document.add_paragraph()
        else:
            ms_map_in_section = current_section_proc_data.get('microservices', {})
            if not ms_map_in_section:
                logger.debug(f"В секции '{section_id_key}' нет МС с задачами (группировка).")
                continue
            for ms_name_str in sorted(ms_map_in_section.keys()):
                ms_data_for_render = ms_map_in_section[ms_name_str]
                has_tasks_for_this_ms = any(
                    ms_data_for_render.get('issue_types', {}).values()) or ms_data_for_render.get(
                    'tasks_without_type_grouping')
                if not has_tasks_for_this_ms:
                    logger.debug(f"МС '{ms_name_str}' в '{section_id_key}' не содержит задач.")
                    continue
                _add_heading_with_style(document, ms_name_str, level=3, default_style_name=s_ms_group)
                group_by_type_flag = current_section_proc_data.get('group_by_issue_type', False)
                render_queue_for_ms: List[Dict] = []  # Аннотация
                if group_by_type_flag:
                    issue_types_data = ms_data_for_render.get('issue_types', {})
                    for type_name_str in sorted(issue_types_data.keys()):
                        tasks_of_type = issue_types_data[type_name_str]
                        if tasks_of_type:
                            render_queue_for_ms.append(
                                {"is_header": True, "text": type_name_str, "level_style": s_issue_type_group})
                            render_queue_for_ms.extend([{"is_header": False, "data": t_data_dict} for t_data_dict in
                                                        sorted(tasks_of_type, key=lambda t: str(t.get("key", "")))])
                else:
                    tasks_list_no_type_group = ms_data_for_render.get('tasks_without_type_grouping', [])
                    if tasks_list_no_type_group:
                        render_queue_for_ms.extend([{"is_header": False, "data": t_data_dict} for t_data_dict in
                                                    sorted(tasks_list_no_type_group,
                                                           key=lambda t: str(t.get("key", "")))])
                if not render_queue_for_ms: continue
                for item_to_add in render_queue_for_ms:
                    if item_to_add.get("is_header"):
                        _add_heading_with_style(document, item_to_add["text"], level=4,
                                                default_style_name=item_to_add["level_style"])
                    else:
                        _add_task_entry(document, template_for_issue, item_to_add["data"], s_list_item,
                                        s_list_multiline_indent)
                document.add_paragraph()

    logger.info("Генерация Word документа завершена.")
    return document