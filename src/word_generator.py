# src/word_generator.py
import logging
import re
from typing import Optional, List, Dict, Union

try:
    from src.config_loader import get_correct_path
except ImportError:
    import sys
    from pathlib import Path


    def get_correct_path(relative_path_str: str) -> Path:
        if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
            return Path(sys._MEIPASS) / relative_path_str
        return Path(__file__).resolve().parent.parent / relative_path_str


    if not logging.getLogger(__name__).hasHandlers():
        logging.basicConfig(level=logging.DEBUG)
    logger_fallback = logging.getLogger(__name__)
    logger_fallback.warning("Fallback get_correct_path in word_generator.")

from docx import Document  # type: ignore
from docx.document import Document as DocxDocument
from docx.shared import Pt, Inches, Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH

logger = logging.getLogger(__name__)

STYLE_NORMAL = 'Normal'
STYLE_HEADING_1 = 'Heading 1'
STYLE_HEADING_2 = 'Heading 2'
STYLE_HEADING_3 = 'Heading 3'
STYLE_HEADING_4 = 'Heading 4'
STYLE_LIST_BULLET = 'List Bullet'
STYLE_TABLE_DEFAULT = 'Table Grid'


def _format_template_string(template_str: str, data_dict: Dict) -> str:
    def replace_match(match_obj):
        key = match_obj.group(1)
        value = data_dict.get(key)
        return str(value) if value is not None else ""

    return re.sub(r"\{([\w_.-]+)\}", replace_match, template_str)


def _add_heading_styled(document: DocxDocument, text: Optional[str], level: int, style_to_apply: str):
    if not text or not text.strip():
        logger.debug("Пропуск добавления пустого заголовка в Word.")
        return
    doc_level = max(1, min(4, level))
    try:
        heading_paragraph = document.add_heading(text='', level=doc_level)
        heading_paragraph.text = text.strip()
        if style_to_apply:
            try:
                current_style_name = ""
                if heading_paragraph.style and hasattr(heading_paragraph.style, 'name'):
                    current_style_name = heading_paragraph.style.name
                if current_style_name != style_to_apply:
                    heading_paragraph.style = style_to_apply
                    logger.debug(f"К заголовку '{text[:30]}...' применен стиль '{style_to_apply}'.")
            except KeyError:
                logger.warning(
                    f"Стиль Word '{style_to_apply}' не найден для заголовка '{text[:30]}...'. Использован стандартный Heading {doc_level}.")
            except AttributeError:
                logger.warning(
                    f"Не удалось проверить/установить стиль '{style_to_apply}' для заголовка '{text[:30]}...'.")
            except Exception as e_style:
                logger.warning(f"Не удалось применить стиль '{style_to_apply}' к заголовку '{text[:30]}...': {e_style}")
    except Exception as e:
        logger.error(f"Ошибка при добавлении заголовка Word '{text[:30]}...': {e}", exc_info=True)


def _add_task_entry_to_document(
        document: DocxDocument,
        header_template_str: Optional[str],
        task_data: Dict,
        first_para_list_style: str,  # Стиль для самого первого параграфа элемента задачи
        header_text_bold: bool,  # Делать ли текст шапки жирным
        header_subsequent_para_style: str,  # Стиль для последующих параграфов шапки (если шапка > 1 строки)
        content_para_style: str,  # Стиль для параграфов контента
        subsequent_para_indent: Optional[Pt]  # Общий отступ для "вложенных" параграфов (после первого)
):
    header_text_formatted = ""
    if header_template_str:
        header_text_formatted = _format_template_string(header_template_str, task_data).strip()

    content_text_formatted = str(task_data.get('content', '')).strip()

    if not header_text_formatted and not content_text_formatted:
        logger.debug(f"Задача {task_data.get('key', 'UKNOWN_KEY')} не дала контента (шапка и тело) для Word.")
        return

    is_first_paragraph_of_this_task_entry = True

    if header_text_formatted:
        header_lines = [line.strip() for line in header_text_formatted.splitlines() if line.strip()]
        for h_line_text in header_lines:
            p_style = first_para_list_style if is_first_paragraph_of_this_task_entry else header_subsequent_para_style
            p = document.add_paragraph(style=p_style)
            run = p.add_run(h_line_text)
            if header_text_bold:
                run.bold = True
            if not is_first_paragraph_of_this_task_entry and subsequent_para_indent:
                p.paragraph_format.left_indent = subsequent_para_indent
            is_first_paragraph_of_this_task_entry = False  # Важно: сбрасываем после первого написанного параграфа

    if content_text_formatted:
        content_lines = [line.strip() for line in content_text_formatted.splitlines() if line.strip()]
        for c_line_text in content_lines:
            p_style = first_para_list_style if is_first_paragraph_of_this_task_entry else content_para_style
            p = document.add_paragraph(c_line_text, style=p_style)
            # Контент обычно не жирный, если только сам стиль это не определяет
            if not is_first_paragraph_of_this_task_entry and subsequent_para_indent:
                p.paragraph_format.left_indent = subsequent_para_indent
            is_first_paragraph_of_this_task_entry = False


def generate_word_document(processed_data: Dict, app_config: Dict) -> Optional[DocxDocument]:
    logger.info("Начало генерации Word (.docx) документа...")
    word_cfg = app_config.get('output_formats', {}).get('word', {})
    if not word_cfg or not word_cfg.get('enabled', False):
        logger.info("Генерация Word отключена.");
        return None

    template_path_str = word_cfg.get('template_path')
    document_obj: DocxDocument
    if template_path_str:  # Логика загрузки шаблона...
        actual_template_file_path = get_correct_path(template_path_str)
        logger.info(f"Попытка использовать Word шаблон: {actual_template_file_path}")
        try:
            if actual_template_file_path.is_file():
                document_obj = Document(str(actual_template_file_path))
            else:
                logger.warning(
                    f"Шаблон не найден: {actual_template_file_path}. Создается пустой."); document_obj = Document()
        except Exception as e:
            logger.warning(f"Ошибка загрузки шаблона Word '{actual_template_file_path}': {e}.",
                           exc_info=True); document_obj = Document()
    else:
        document_obj = Document(); logger.info("Шаблон не указан, создается пустой документ.")

    # Вставка логотипа ...
    logo_config = word_cfg.get('logo', {});
    logo_image_path_str = logo_config.get('image_path')
    if logo_image_path_str:  # (логика вставки логотипа как раньше)
        actual_logo_path = get_correct_path(logo_image_path_str)
        if actual_logo_path.is_file():
            try:
                logo_width_cm = logo_config.get('width_cm');
                logo_height_cm = logo_config.get('height_cm')
                docx_width = Cm(logo_width_cm) if logo_width_cm is not None else None;
                docx_height = Cm(logo_height_cm) if logo_height_cm is not None else None
                logo_paragraph = document_obj.add_paragraph();
                logo_run = logo_paragraph.add_run()
                if docx_width and docx_height:
                    logo_run.add_picture(str(actual_logo_path), width=docx_width, height=docx_height)
                elif docx_width:
                    logo_run.add_picture(str(actual_logo_path), width=docx_width)
                elif docx_height:
                    logo_run.add_picture(str(actual_logo_path), height=docx_height)
                else:
                    logo_run.add_picture(str(actual_logo_path))
                logo_align_str = logo_config.get('alignment', 'left').upper()
                if logo_align_str == "CENTER":
                    logo_paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
                elif logo_align_str == "RIGHT":
                    logo_paragraph.alignment = WD_ALIGN_PARAGRAPH.RIGHT
                document_obj.add_paragraph()
            except Exception as e:
                logger.error(f"Ошибка вставки логотипа '{actual_logo_path}': {e}", exc_info=True)
        else:
            logger.warning(f"Файл логотипа '{actual_logo_path}' не найден.")

    styles_map = word_cfg.get('styles', {})
    s_main_title = styles_map.get('main_title', STYLE_HEADING_1)
    s_table_title = styles_map.get('table_title', STYLE_HEADING_2)
    s_section_title = styles_map.get('section_title', STYLE_HEADING_2)
    s_ms_group = styles_map.get('microservice_group', STYLE_HEADING_3)
    s_issue_type_group = styles_map.get('issue_type_group', STYLE_HEADING_4)
    # Используем эти имена при извлечении из styles_map
    s_list_item_first = styles_map.get('list_bullet_first_line', STYLE_LIST_BULLET)
    s_header_subsequent = styles_map.get('header_text_subsequent', STYLE_NORMAL)  # Новый стиль для >1 строк шапки
    s_content_text = styles_map.get('content_text', STYLE_NORMAL)  # Новый стиль для контента
    s_table = styles_map.get('table_style', STYLE_TABLE_DEFAULT)

    default_indent = Pt(20)

    rn_cfg_data = app_config.get('release_notes', {})
    gv_text = processed_data.get("global_version", "N/A");
    date_text = processed_data.get("current_date", "N/A")
    title_template_str = rn_cfg_data.get('title_template', "RN - {global_version} - {current_date}")
    main_title_str = _format_template_string(title_template_str, {"global_version": gv_text, "current_date": date_text})
    _add_heading_styled(document_obj, main_title_str, level=1, style_to_apply=s_main_title)

    ms_table_cfg_data = rn_cfg_data.get('microservices_table', {});
    ms_summary_list = processed_data.get("microservices_summary", [])
    if ms_table_cfg_data.get('enabled', True) and ms_summary_list:  # Логика таблицы...
        _add_heading_styled(document_obj, ms_table_cfg_data.get('title'), level=2, style_to_apply=s_table_title)
        cols_cfg = ms_table_cfg_data.get('columns', []);
        tbl_headers = [c.get('header', '') for c in cols_cfg]
        if tbl_headers and any(h.strip() for h in tbl_headers):
            rows_data = [[_format_template_string(c.get('value_placeholder', ''), item) for c in cols_cfg] for item in
                         ms_summary_list]
            if rows_data:
                tbl = document_obj.add_table(rows=1, cols=len(tbl_headers));
                tbl.style = s_table
                for i, h in enumerate(tbl_headers): tbl.rows[0].cells[i].text = h
                for r_data in rows_data:
                    cells = tbl.add_row().cells
                    for i, c_data in enumerate(r_data):
                        if i < len(cells): cells[i].text = c_data
                document_obj.add_paragraph()

    sections_data = processed_data.get("sections_data", {})
    sections_meta = rn_cfg_data.get('sections', {})
    for section_id, section_meta_cfg_item in sections_meta.items():
        current_section_data = sections_data.get(section_id)
        if not current_section_data: continue
        _add_heading_styled(document_obj, current_section_data.get('title'), level=2, style_to_apply=s_section_title)

        task_hdr_template = section_meta_cfg_item.get('issue_header_template')  # Шаблон для шапки
        if not task_hdr_template: logger.warning(f"Для секции '{section_id}' отсутствует 'issue_header_template'.")

        is_flat = current_section_data.get("disable_grouping", False)
        if is_flat:
            flat_tasks: List[Dict] = current_section_data.get("tasks_flat_list", [])
            if not flat_tasks:
                document_obj.add_paragraph("* Нет задач.*", style=s_list_item_first)
            else:
                for task_data in sorted(flat_tasks, key=lambda t: str(t.get("key", ""))):
                    _add_task_entry_to_document(document_obj, task_hdr_template, task_data,
                                                s_list_item_first, True, s_header_subsequent,
                                                s_content_text, default_indent)
            document_obj.add_paragraph()
        else:
            ms_map = current_section_data.get('microservices', {})
            if not ms_map: continue
            for ms_name in sorted(ms_map.keys()):
                ms_content = ms_map[ms_name]
                has_tasks_flag = any(ms_content.get('issue_types', {}).values()) or ms_content.get(
                    'tasks_without_type_grouping')
                if not has_tasks_flag: continue
                _add_heading_styled(document_obj, ms_name, level=3, style_to_apply=s_ms_group)

                group_by_type = current_section_data.get('group_by_issue_type', False)
                render_q: List[Dict] = []
                if group_by_type:
                    types_map_data = ms_content.get('issue_types', {})
                    for type_name in sorted(types_map_data.keys()):
                        tasks_list = types_map_data[type_name]
                        if tasks_list:
                            render_q.append(
                                {"is_header": True, "text": type_name, "level_style_name": s_issue_type_group})
                            render_q.extend([{"is_header": False, "data": t} for t in
                                             sorted(tasks_list, key=lambda tsk: str(tsk.get("key", "")))])
                else:
                    tasks_no_type = ms_content.get('tasks_without_type_grouping', [])
                    if tasks_no_type:
                        render_q.extend([{"is_header": False, "data": t} for t in
                                         sorted(tasks_no_type, key=lambda tsk: str(tsk.get("key", "")))])

                if not render_q: continue
                for item_render in render_q:
                    if item_render.get("is_header"):
                        _add_heading_styled(document_obj, item_render["text"], level=4,
                                            style_to_apply=item_render["level_style_name"])
                    else:
                        _add_task_entry_to_document(document_obj, task_hdr_template, item_render["data"],
                                                    s_list_item_first, True, s_header_subsequent,
                                                    s_content_text, default_indent)
                document_obj.add_paragraph()

    logger.info("Генерация Word документа успешно завершена.")
    return document_obj