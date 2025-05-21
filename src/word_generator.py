# src/word_generator.py
import logging
import re
from typing import Optional, List, Dict  # Для аннотаций типов

from docx import Document  # type: ignore # Используем type: ignore, если линтер жалуется на Document из python-docx
from docx.document import Document as DocxDocument  # Более явный импорт для типа Document
from docx.shared import Pt, Inches

# from docx.enum.text import WD_ALIGN_PARAGRAPH # Если понадобится выравнивание

# Импортируем get_correct_path из config_loader
# Это предполагает, что config_loader.py находится в той же директории src
# и get_correct_path не является приватной (не начинается с _)
try:
    from src.config_loader import get_correct_path
except ImportError:
    # Фоллбэк, если запускаем word_generator отдельно или структура другая
    # (этот фоллбэк не идеален для собранного приложения, но поможет при автономном тесте модуля)
    import sys
    from pathlib import Path


    def get_correct_path(relative_path_str: str) -> Path:
        if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
            # PyInstaller создает временную папку и сохраняет путь в sys._MEIPASS
            return Path(sys._MEIPASS) / relative_path_str
        else:
            return Path(__file__).resolve().parent.parent / relative_path_str


    logger = logging.getLogger(__name__)  # Определяем логгер здесь, если импорт выше не сработал
    logger.warning("Не удалось импортировать get_correct_path из src.config_loader. Используется локальный фоллбэк.")

logger = logging.getLogger(__name__)

# Имена стилей Word (могут быть переопределены в config.yaml)
STYLE_NORMAL = 'Normal'
STYLE_HEADING_1 = 'Heading 1'
STYLE_HEADING_2 = 'Heading 2'
STYLE_HEADING_3 = 'Heading 3'
STYLE_HEADING_4 = 'Heading 4'
STYLE_LIST_BULLET = 'List Bullet'
STYLE_TABLE_DEFAULT = 'Table Grid'


def _format_template_string(template_str: str, data_dict: Dict) -> str:
    """
    Заменяет плейсхолдеры вида {ключ} в строке-шаблоне значениями из словаря data_dict.
    Если плейсхолдер не найден или его значение None, он заменяется на пустую строку.
    """

    def replace_match(match_obj):
        key_in_placeholder = match_obj.group(1)
        value_from_data = data_dict.get(key_in_placeholder)
        return str(value_from_data) if value_from_data is not None else ""

    return re.sub(r"\{([\w_.-]+)\}", replace_match, template_str)


def _add_heading_styled(document: DocxDocument, text: Optional[str], level: int, default_style_name: str):
    """
    Добавляет заголовок в документ, используя указанный уровень для определения
    стандартного стиля 'Heading X' и позволяя переопределить его стилем из конфига.
    """
    if not text or not text.strip():
        logger.debug("Пропуск добавления пустого заголовка в Word.")
        return

    # Уровни в python-docx для add_heading: 0 для 'Title', 1 для 'Heading 1', ...
    # Мы ожидаем level 1-4 от наших настроек для Heading 1-4.
    doc_level = max(1, min(4, level))  # Убедимся, что уровень в допустимых пределах для Heading 1-4

    try:
        heading_paragraph = document.add_heading(text='', level=doc_level)  # Создаем заголовок нужного уровня
        heading_paragraph.text = text.strip()  # Заполняем текст

        # Если в конфиге указан стиль и он отличается от стандартного "Heading X"
        # или если мы хотим быть уверены, что именно этот стиль применен.
        if style_name_from_config:
            try:
                # Если стиль из конфига совпадает со стандартным для этого уровня,
                # то он уже применен через add_heading(level=...).
                # Но явное применение не повредит и полезно для кастомных стилей.
                heading_paragraph.style = style_name_from_config
                logger.debug(f"К заголовку '{text[:30]}...' применен стиль '{style_name_from_config}'.")
            except KeyError:  # Если стиль с таким именем не найден в документе/шаблоне
                logger.warning(
                    f"Стиль Word '{style_name_from_config}' не найден для заголовка '{text[:30]}...'. Использован стандартный стиль для уровня {doc_level}.")
        # Если style_name_from_config не указан, используется стиль по умолчанию для document.add_heading(level=...)
    except Exception as e:
        logger.error(f"Ошибка при добавлении заголовка Word '{text[:30]}...': {e}")


def _add_task_entry_to_document(
        document: DocxDocument,
        issue_template_str: str,
        task_data: Dict,
        first_line_style_name: str,
        subsequent_line_style_name: str,
        subsequent_line_indent: Optional[Pt] = None
):
    """
    Добавляет запись о задаче в Word документ, форматируя ее по шаблону.
    Каждая строка из отформатированного шаблона становится новым параграфом.
    """
    formatted_entry = _format_template_string(issue_template_str, task_data)
    lines = [line.strip() for line in formatted_entry.strip().splitlines() if line.strip()]  # Убираем пустые строки

    if not lines:
        logger.debug(f"Задача {task_data.get('key', 'UKNOWN_KEY')} не дала контента по шаблону для Word.")
        # Можно добавить параграф-плейсхолдер, если нужно
        # document.add_paragraph(f"[{task_data.get('key','TASK')}: нет данных по шаблону]", style=first_line_style_name)
        return

    for i, line_text in enumerate(lines):
        if i == 0:  # Первая строка
            p = document.add_paragraph(line_text, style=first_line_style_name)
        else:  # Последующие строки
            p = document.add_paragraph(line_text, style=subsequent_line_style_name)
            if subsequent_line_style_name == STYLE_NORMAL and subsequent_line_indent:
                # Применяем отступ только если это "Normal" стиль и отступ задан
                try:
                    p.paragraph_format.left_indent = subsequent_line_indent
                except Exception as e:
                    logger.warning(f"Не удалось применить отступ к параграфу для задачи {task_data.get('key')}: {e}")


def generate_word_document(processed_data: Dict, app_config: Dict) -> Optional[DocxDocument]:
    """
    Генерирует документ Word (.docx) на основе обработанных данных и конфигурации.
    """
    logger.info("Начало генерации Word (.docx) документа...")

    word_config = app_config.get('output_formats', {}).get('word', {})
    if not word_config or not word_config.get('enabled', False):
        logger.info("Генерация Word документа отключена в конфигурации.")
        return None

    template_file_path_str = word_config.get('template_path')
    document_obj: DocxDocument
    if template_file_path_str:
        # Преобразуем относительный путь из конфига в абсолютный
        actual_template_file_path = get_correct_path(template_file_path_str)
        logger.info(f"Попытка использовать Word шаблон: {actual_template_file_path}")
        try:
            if actual_template_file_path.is_file():
                document_obj = Document(str(actual_template_file_path))  # Document ожидает строку или file-like object
                logger.info(f"Успешно использован Word шаблон: {actual_template_file_path}")
            else:
                logger.warning(f"Файл шаблона Word не найден: {actual_template_file_path}. Создается пустой документ.")
                document_obj = Document()
        except Exception as e:
            logger.warning(
                f"Не удалось загрузить Word шаблон '{actual_template_file_path}': {e}. Создается пустой документ.")
            document_obj = Document()
    else:
        document_obj = Document()
        logger.info("Word шаблон не указан, создается документ со стилями по умолчанию.")

    # Стили из конфигурации или значения по умолчанию
    styles_map = word_config.get('styles', {})
    style_h1 = styles_map.get('main_title', STYLE_HEADING_1)
    style_h2_table = styles_map.get('table_title', STYLE_HEADING_2)
    style_h2_section = styles_map.get('section_title', STYLE_HEADING_2)
    style_h3_ms = styles_map.get('microservice_group', STYLE_HEADING_3)
    style_h4_type = styles_map.get('issue_type_group', STYLE_HEADING_4)
    style_task_first_line = styles_map.get('list_bullet_first_line', STYLE_LIST_BULLET)
    style_task_multiline = styles_map.get('list_bullet_multiline_indent', STYLE_NORMAL)
    style_table_content = styles_map.get('table_style', STYLE_TABLE_DEFAULT)

    # Отступ по умолчанию для многострочных элементов списка, если стиль Normal
    default_multiline_indent = Pt(20)

    rn_cfg_data = app_config.get('release_notes', {})

    # 1. Главный заголовок
    gv_text = processed_data.get("global_version", "N/A")
    date_text = processed_data.get("current_date", "N/A")
    title_template_str = rn_cfg_data.get('title_template', "Release Notes - {global_version} - {current_date}")
    main_title_str = _format_template_string(title_template_str, {"global_version": gv_text, "current_date": date_text})
    _add_heading_styled(document_obj, main_title_str, level=1, default_style_name=style_h1)

    # 2. Таблица микросервисов
    ms_table_cfg_data = rn_cfg_data.get('microservices_table', {})
    ms_summary_data_list: List[Dict] = processed_data.get("microservices_summary", [])
    if ms_table_cfg_data.get('enabled', True) and ms_summary_data_list:
        table_title_heading = ms_table_cfg_data.get('title')
        _add_heading_styled(document_obj, table_title_heading, level=2, default_style_name=style_h2_table)

        cols_config_list: List[Dict] = ms_table_cfg_data.get('columns', [])
        table_col_headers: List[str] = [col.get('header', '') for col in cols_config_list]

        if table_col_headers and any(h.strip() for h in table_col_headers):
            try:
                created_table = document_obj.add_table(rows=1, cols=len(table_col_headers))
                created_table.style = style_table_content
                header_row_cells = created_table.rows[0].cells
                for i, header_name in enumerate(table_col_headers): header_row_cells[i].text = header_name
                for ms_item in ms_summary_data_list:
                    data_row_cells = created_table.add_row().cells
                    for i, col_cfg_item in enumerate(cols_config_list):
                        placeholder_str = col_cfg_item.get('value_placeholder', '')
                        cell_content_str = _format_template_string(placeholder_str, ms_item)
                        data_row_cells[i].text = cell_content_str
                document_obj.add_paragraph()  # Отступ после таблицы
            except Exception as e:
                logger.error(f"Ошибка при создании таблицы микросервисов в Word: {e}", exc_info=True)
        elif table_col_headers:  # Есть заголовки, но нет данных
            logger.info("Таблица микросервисов для Word: нет данных для строк.")

    # 3. Информационные секции
    sections_data = processed_data.get("sections_data", {})
    sections_meta = rn_cfg_data.get('sections', {})

    for section_id, section_meta_config_data in sections_meta.items():
        current_section_from_processor = sections_data.get(section_id)
        if not current_section_from_processor:
            logger.debug(f"Секция '{section_id}' пропущена в Word (нет данных).")
            continue

        _add_heading_styled(document_obj, current_section_from_processor.get('title'), level=2,
                            default_style_name=style_h2_section)

        issue_template = section_meta_config_data.get('issue_display_template')
        if not issue_template:
            logger.warning(f"Для секции '{section_id}' в Word отсутствует 'issue_display_template'.")
            document_obj.add_paragraph("* Конфигурация отображения задач отсутствует.*", style=style_task_first_line)
            document_obj.add_paragraph()
            continue

        is_flat_display = current_section_from_processor.get("disable_grouping", False)

        if is_flat_display:
            tasks_list_flat: List[Dict] = current_section_from_processor.get("tasks_flat_list", [])
            if not tasks_list_flat:
                document_obj.add_paragraph("* Нет задач для отображения в этой секции.*", style=style_task_first_line)
            else:
                for task_data_item in sorted(tasks_list_flat, key=lambda t: str(t.get("key", ""))):
                    _add_task_entry_to_document(document_obj, issue_template, task_data_item, style_task_first_line,
                                                style_task_multiline, default_multiline_indent)
            document_obj.add_paragraph()
        else:  # Группировка по МС
            ms_map = current_section_from_processor.get('microservices', {})
            if not ms_map:
                logger.debug(f"В секции '{section_id}' нет МС с задачами для Word (группировка).")
                continue
            for ms_name_val in sorted(ms_map.keys()):
                ms_render_data = ms_map[ms_name_val]
                has_tasks = any(ms_render_data.get('issue_types', {}).values()) or ms_render_data.get(
                    'tasks_without_type_grouping')
                if not has_tasks:
                    logger.debug(f"МС '{ms_name_val}' в '{section_id}' не содержит задач для Word.")
                    continue
                _add_heading_styled(document_obj, ms_name_val, level=3, default_style_name=style_h3_ms)

                group_by_type = current_section_from_processor.get('group_by_issue_type', False)
                render_queue: List[Dict] = []
                if group_by_type:
                    types_data = ms_render_data.get('issue_types', {})
                    for type_name_val in sorted(types_data.keys()):
                        tasks = types_data[type_name_val]
                        if tasks:
                            render_queue.append(
                                {"is_header": True, "text": type_name_val, "level_style_name": style_h4_type})
                            render_queue.extend([{"is_header": False, "data": t_dict} for t_dict in
                                                 sorted(tasks, key=lambda t: str(t.get("key", "")))])
                else:
                    tasks_no_group = ms_render_data.get('tasks_without_type_grouping', [])
                    if tasks_no_group:
                        render_queue.extend([{"is_header": False, "data": t_dict} for t_dict in
                                             sorted(tasks_no_group, key=lambda t: str(t.get("key", "")))])

                if not render_queue: continue
                for item in render_queue:
                    if item.get("is_header"):
                        _add_heading_styled(document_obj, item["text"], level=4,
                                            default_style_name=item["level_style_name"])
                    else:
                        _add_task_entry_to_document(document_obj, issue_template, item["data"], style_task_first_line,
                                                    style_task_multiline, default_multiline_indent)
                document_obj.add_paragraph()

    logger.info("Генерация Word документа успешно завершена.")
    return document_obj

# Блок if __name__ == '__main__': УДАЛЕН