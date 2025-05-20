# src/word_generator.py
import logging
from pathlib import Path
from docx import Document
from docx.shared import Pt, Inches  # Inches может понадобиться для отступов
from docx.enum.style import WD_STYLE_TYPE  # Для возможной проверки типов стилей
from docx.enum.text import WD_ALIGN_PARAGRAPH  # Если нужно выравнивание
import re

logger = logging.getLogger(__name__)


# Вспомогательная функция _format_template_string
def _format_template_string(template_str: str, data_dict: dict) -> str:
    """Заменяет плейсхолдеры вида {key} в строке template_str значениями из data_dict."""

    def replace_match(match):
        key = match.group(1)
        value = data_dict.get(key)
        return str(value) if value is not None else ""

    return re.sub(r"\{([\w_.-]+)\}", replace_match, template_str)


def _add_paragraph_with_style(doc_obj: Document, text: str | None, style_name: str | None,
                              fallback_style: str = 'Normal'):
    """Добавляет параграф с текстом и стилем, с фоллбэком на Normal, если стиль не найден."""
    if text is None: text = ""  # Гарантируем, что текст - это строка
    try:
        p = doc_obj.add_paragraph(text, style=style_name)
        logger.debug(f"Добавлен параграф со стилем '{style_name}'. Текст: '{text[:50]}...'")
    except KeyError:
        logger.warning(f"Стиль параграфа '{style_name}' не найден. Используется стиль '{fallback_style}'.")
        p = doc_obj.add_paragraph(text, style=fallback_style)
    except ValueError as ve:  # Если стиль есть, но не того типа (маловероятно для add_paragraph)
        logger.warning(f"Ошибка применения стиля '{style_name}': {ve}. Используется стиль '{fallback_style}'.")
        p = doc_obj.add_paragraph(text, style=fallback_style)
    return p


def _add_heading_with_style(doc_obj: Document, text: str | None, style_name: str | None, default_level: int = 1):
    """Добавляет заголовок, пытаясь применить стиль. Если стиль не найден или не является стилем параграфа,
    использует add_heading с default_level."""
    if not text: return

    # Пытаемся использовать add_paragraph со стилем, так как это более гибко
    # и позволяет использовать любые именованные стили параграфов из шаблона.
    # add_heading(level=X) жестко привязан к встроенным уровням заголовков Word.
    try:
        # Проверяем, существует ли стиль и является ли он стилем параграфа
        # Это немного избыточно, так как add_paragraph сам выбросит KeyError или ValueError
        style_obj = doc_obj.styles[style_name]
        if style_obj.type != WD_STYLE_TYPE.PARAGRAPH:
            raise ValueError(f"Стиль '{style_name}' не является стилем параграфа (тип: {style_obj.type}).")

        doc_obj.add_paragraph(text, style=style_name)
        logger.debug(f"Добавлен заголовок '{text}' со стилем '{style_name}' (как параграф).")
    except (KeyError, ValueError) as e_style:
        logger.warning(
            f"Не удалось применить стиль '{style_name}' для заголовка '{text}': {e_style}. Используется doc.add_heading(level={default_level}).")
        doc_obj.add_heading(text, level=default_level)


def generate_word_document(processed_data: dict, app_config: dict, project_root_dir: Path):
    logger.info("Начало генерации Word документа...")

    word_cfg = app_config.get('output_formats', {}).get('word', {})
    if not word_cfg.get('enabled', False):
        logger.info("Генерация Word документа отключена в конфигурации.")
        return None

    template_path_str = word_cfg.get('template_path')
    document: Document

    if template_path_str:
        template_file_path = Path(template_path_str)
        if not template_file_path.is_absolute():
            template_file_path = project_root_dir / template_file_path

        resolved_template_path_str = str(template_file_path.resolve())
        logger.info(f"Попытка использовать Word шаблон: {resolved_template_path_str}")

        if template_file_path.exists() and template_file_path.is_file():
            try:
                document = Document(template_file_path)
                logger.info(f"Успешно загружен Word шаблон: {resolved_template_path_str}")
            except Exception as e:
                logger.error(
                    f"Не удалось загрузить Word шаблон '{resolved_template_path_str}': {e}. Будет создан документ по умолчанию.",
                    exc_info=True)
                document = Document()
        else:
            logger.warning(
                f"Файл шаблона Word НЕ НАЙДЕН по пути: {resolved_template_path_str}. Будет создан документ по умолчанию.")
            document = Document()
    else:
        document = Document()
        logger.info("Word шаблон не указан, создается документ со стилями по умолчанию.")

    styles_cfg = word_cfg.get('styles', {})
    # Дефолтные имена стилей, если в конфиге не указаны другие
    STYLE_HEADING_1_DEFAULT = 'Heading 1'
    STYLE_HEADING_2_DEFAULT = 'Heading 2'
    STYLE_HEADING_3_DEFAULT = 'Heading 3'
    STYLE_HEADING_4_DEFAULT = 'Heading 4'
    STYLE_NORMAL_DEFAULT = 'Normal'
    STYLE_LIST_BULLET_DEFAULT = 'List Bullet'
    STYLE_TABLE_DEFAULT = 'TableGrid'  # 'Table Grid' (с пробелом) часто вызывает KeyError

    style_main_title = styles_cfg.get('main_title', STYLE_HEADING_1_DEFAULT)
    style_table_title = styles_cfg.get('table_title', STYLE_HEADING_2_DEFAULT)
    style_section_title = styles_cfg.get('section_title', STYLE_HEADING_2_DEFAULT)
    style_ms_group = styles_cfg.get('microservice_group', STYLE_HEADING_3_DEFAULT)
    style_issue_type_group = styles_cfg.get('issue_type_group', STYLE_HEADING_4_DEFAULT)
    style_list_item_first = styles_cfg.get('list_bullet_first_line', STYLE_LIST_BULLET_DEFAULT)
    style_list_item_multiline = styles_cfg.get('list_bullet_multiline_indent', STYLE_NORMAL_DEFAULT)
    style_table_for_ms_summary = styles_cfg.get('table_style', STYLE_TABLE_DEFAULT)

    rn_config = app_config.get('release_notes', {})

    # --- 1. Главный заголовок ---
    global_version_val = processed_data.get("global_version", "N/A")
    current_date_str_val = processed_data.get("current_date", "N/A")
    title_template_str_val = rn_config.get('title_template', "Release Notes - {global_version} - {current_date}")
    title_format_data_dict = {"global_version": global_version_val, "current_date": current_date_str_val}
    main_title_text_val = _format_template_string(title_template_str_val, title_format_data_dict)
    _add_heading_with_style(document, main_title_text_val, style_main_title, default_level=1)
    document.add_paragraph()  # Пустой параграф для отступа

    # --- 2. Таблица микросервисов ---
    microservices_table_cfg = rn_config.get('microservices_table', {})
    microservices_summary_list = processed_data.get("microservices_summary", [])
    if microservices_table_cfg.get('enabled', False) and microservices_summary_list:
        table_title_text_val = microservices_table_cfg.get('title')
        if table_title_text_val:
            _add_heading_with_style(document, table_title_text_val, style_table_title, default_level=2)

        column_configs_list_ms = microservices_table_cfg.get('columns', [])
        table_headers_list_ms = [col_cfg.get('header', '') for col_cfg in column_configs_list_ms]

        if table_headers_list_ms and any(h.strip() for h in table_headers_list_ms):
            table = document.add_table(rows=1, cols=len(table_headers_list_ms))
            if style_table_for_ms_summary:
                try:
                    table.style = style_table_for_ms_summary
                except (KeyError, ValueError) as e_style_table:
                    logger.warning(
                        f"Стиль таблицы '{style_table_for_ms_summary}' не найден или не подходит: {e_style_table}. Используется стиль по умолчанию.")

            hdr_cells = table.rows[0].cells
            for i, header_txt_val in enumerate(table_headers_list_ms):
                hdr_cells[i].text = header_txt_val

            for ms_item_dict_val in microservices_summary_list:
                row_cells = table.add_row().cells
                for i, col_cfg_item_val in enumerate(column_configs_list_ms):
                    cell_text_val_str = _format_template_string(col_cfg_item_val.get('value_placeholder', ''),
                                                                ms_item_dict_val)
                    row_cells[i].text = cell_text_val_str
            document.add_paragraph()

            # --- 3. Генерация Секций ---
    sections_data_map = processed_data.get("sections_data", {})
    configured_sections_meta_map = rn_config.get('sections', {})

    for section_key_str, section_meta_config_yaml in configured_sections_meta_map.items():
        current_section_data_proc = sections_data_map.get(section_key_str)
        if not current_section_data_proc: continue

        _add_heading_with_style(document, current_section_data_proc.get('title'), style_section_title, default_level=2)

        issue_template_for_section_str = section_meta_config_yaml.get('issue_display_template')
        if not issue_template_for_section_str:
            logger.warning(f"Шаблон 'issue_display_template' не найден для секции '{section_key_str}'.")
            _add_paragraph_with_style(document, "*Конфигурация отображения задач отсутствует.*", style_list_item_first)
            continue

        is_flat_list_mode_active = current_section_data_proc.get("disable_grouping", False)

        if is_flat_list_mode_active:
            tasks_flat_list_data = current_section_data_proc.get("tasks_flat_list", [])
            sorted_tasks_data_list = sorted(tasks_flat_list_data, key=lambda t: str(t.get("key", "")))
            if not sorted_tasks_data_list:
                _add_paragraph_with_style(document, "*Нет задач для отображения в этой секции.*", style_list_item_first)
            for task_dict_item in sorted_tasks_data_list:
                formatted_task_lines = _format_template_string(issue_template_for_section_str,
                                                               task_dict_item).strip().splitlines()
                first_line_of_task = True
                for line_content in formatted_task_lines:
                    if not line_content.strip() and not first_line_of_task: continue
                    p_style = style_list_item_first if first_line_of_task else style_list_item_multiline
                    p = _add_paragraph_with_style(document, line_content.strip(), p_style)
                    if not first_line_of_task and p_style == style_list_item_multiline and style_list_item_multiline == STYLE_NORMAL_DEFAULT:
                        p.paragraph_format.left_indent = Pt(36)
                    first_line_of_task = False
        else:
            microservices_in_section_map = current_section_data_proc.get('microservices', {})
            if not microservices_in_section_map: continue
            sorted_ms_names_list_val = sorted(microservices_in_section_map.keys())
            for ms_name_val in sorted_ms_names_list_val:
                ms_specific_data_dict = microservices_in_section_map[ms_name_val]
                has_tasks_in_ms = any(
                    ms_specific_data_dict.get('issue_types', {}).values()) or ms_specific_data_dict.get(
                    'tasks_without_type_grouping')
                if not has_tasks_in_ms: continue

                _add_heading_with_style(document, ms_name_val, style_ms_group, default_level=3)

                should_group_by_type_flag = current_section_data_proc.get('group_by_issue_type', False)
                render_items_list_for_ms = []
                if should_group_by_type_flag:
                    types_map_val = ms_specific_data_dict.get('issue_types', {})
                    for type_name_str_val in sorted(types_map_val.keys()):
                        tasks_list_val = types_map_val[type_name_str_val]
                        if tasks_list_val:
                            render_items_list_for_ms.append(
                                {"is_header": True, "text": type_name_str_val, "style": style_issue_type_group,
                                 "level": 4})
                            render_items_list_for_ms.extend([{"is_header": False, "data": t_dict_val} for t_dict_val in
                                                             sorted(tasks_list_val,
                                                                    key=lambda tsk: str(tsk.get("key", "")))])
                else:
                    tasks_list_flat_ms = ms_specific_data_dict.get('tasks_without_type_grouping', [])
                    if tasks_list_flat_ms:
                        render_items_list_for_ms.extend([{"is_header": False, "data": t_dict_val} for t_dict_val in
                                                         sorted(tasks_list_flat_ms,
                                                                key=lambda tsk: str(tsk.get("key", "")))])

                if not render_items_list_for_ms: continue

                for item_to_render_val in render_items_list_for_ms:
                    if item_to_render_val["is_header"]:
                        _add_heading_with_style(document, item_to_render_val["text"], item_to_render_val["style"],
                                                item_to_render_val["level"])
                    else:
                        task_data_dict_val = item_to_render_val["data"]
                        formatted_task_lines_list_val = _format_template_string(issue_template_for_section_str,
                                                                                task_data_dict_val).strip().splitlines()
                        first_line_in_task_item_val = True
                        for line_text_val_str in formatted_task_lines_list_val:
                            if not line_text_val_str.strip() and not first_line_in_task_item_val: continue
                            para_style_val = style_list_item_first if first_line_in_task_item_val else style_list_item_multiline
                            p_task = _add_paragraph_with_style(document, line_text_val_str.strip(), para_style_val)
                            if not first_line_in_task_item_val and para_style_val == style_list_item_multiline and style_list_item_multiline == STYLE_NORMAL_DEFAULT:
                                p_task.paragraph_format.left_indent = Pt(36)
                            first_line_in_task_item_val = False
                document.add_paragraph()
        document.add_paragraph()

    logger.info("Генерация Word документа (содержимое) завершена.")
    return document


# Блок if __name__ == '__main__': остается таким же, как в предыдущей полной версии word_generator.py
# Убедитесь, что project_root_dir передается в generate_word_document при тестировании.
if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)  # Устанавливаем DEBUG для теста
    logger.info("Тестирование word_generator...")

    mock_processed_data_word = {
        "global_version": "1.0-WordTest", "current_date": "21.05.2025",
        "microservices_summary": [{"name": "Omega Service", "version": "1.0"},
                                  {"name": "Alpha Module", "version": "2.1"}],
        "sections_data": {
            "main_changes": {
                "title": "Основные изменения", "disable_grouping": False, "group_by_issue_type": True,
                "microservices": {
                    "Omega Service": {
                        "issue_types": {
                            "Feature": [{"key": "OMEGA-1", "summary": "New Omega Feature",
                                         "content": "Details of Omega feature.\nSecond line.",
                                         "issuetype_name": "Feature", "priority_name": "High"}],
                            "Bug": [{"key": "OMEGA-2", "summary": "Omega Bug Fix",
                                     "content": "Fixed critical bug in Omega.", "issuetype_name": "Bug",
                                     "priority_name": "Highest"}]
                        },
                        "tasks_without_type_grouping": []
                    }
                }
            },
            "flat_list_demo": {
                "title": "Все задачи (плоский список)", "disable_grouping": True, "group_by_issue_type": False,
                "tasks_flat_list": [
                    {"key": "ALPHA-5", "summary": "Alpha Task 1", "content": "Alpha task details.",
                     "issuetype_name": "Task", "linked_microservices_names": "Alpha Module"},
                    {"key": "OMEGA-1", "summary": "New Omega Feature (flat view)", "content": "Details for flat view.",
                     "issuetype_name": "Feature", "linked_microservices_names": "Omega Service"}
                ]
            }
        }
    }
    mock_app_config_word = {
        "release_notes": {
            "title_template": "Тест RN: {global_version}", "date_format": "%d.%m.%Y",
            "sections": {
                "main_changes": {"issue_display_template": "**{key}** {summary}\nТип: {issuetype_name}\n{content}"},
                "flat_list_demo": {
                    "issue_display_template": "Задача {key} ({issuetype_name}) для МС [{linked_microservices_names}]:\n{content}"}
            },
            "microservices_table": {"enabled": True, "title": "Компоненты в релизе",
                                    "columns": [{"header": "Компонент", "value_placeholder": "{name}"},
                                                {"header": "Версия", "value_placeholder": "{version}"}]}
        },
        "output_formats": {"word": {"enabled": True,
                                    # "template_path": "config/templates/rn_template.docx", # УКАЖИТЕ СВОЙ ШАБЛОН ИЛИ ОСТАВЬТЕ ЗАКОММЕНТИРОВАННЫМ
                                    "styles": {
                                        "main_title": "Title",
                                        "table_title": "Heading 1",
                                        "section_title": "Heading 1",
                                        "microservice_group": "Heading 2",
                                        "issue_type_group": "Heading 3",
                                        "list_bullet_first_line": "List Bullet",
                                        "list_bullet_multiline_indent": "Normal",  # Этот стиль будет с ручным отступом
                                        "table_style": "TableGrid"
                                    }
                                    }}
    }
    # Для теста нужен путь к корню проекта, чтобы word_generator мог найти шаблон, если путь относительный
    # В реальном main.py project_root передается. Здесь для теста установим вручную.
    test_project_root_path = Path(__file__).resolve().parent.parent

    doc = generate_word_document(mock_processed_data_word, mock_app_config_word,
                                 project_root_dir=test_project_root_path)
    if doc:
        try:
            output_filename_test = "test_rn_output_full.docx"
            doc.save(output_filename_test)
            logger.info(f"Тестовый Word документ сохранен как {output_filename_test} в {Path.cwd()}")
        except Exception as e_save:
            logger.error(f"Ошибка сохранения тестового Word документа: {e_save}", exc_info=True)