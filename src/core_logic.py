# src/core_logic.py
import logging
import json
from pathlib import Path
from datetime import datetime
import re

# Импорты наших модулей
from src.config_loader import load_config, load_environment_variables
from src.jira_client import JiraClient
from src.data_processor import process_jira_issues
from src.markdown_generator import generate_markdown_content
from src.word_generator import generate_word_document

logger = logging.getLogger(__name__)


def run_generation_process(filter_id: str, output_dir: str, jira_cookie: str | None) -> bool:
    """
    Основная функция, выполняющая весь процесс генерации Release Notes.
    Возвращает True в случае успеха, False в случае критической ошибки.
    """
    try:
        logger.info("=" * 30 + " Запуск процесса генерации " + "=" * 30)

        # --- Шаг 1: Загрузка конфигурации ---
        # Предполагаем, что .env файл уже был прочитан или кука передана напрямую.
        # Загружаем только app_config.
        logger.info("1. Загрузка конфигурации...")
        app_config = load_config()
        logger.info("Конфигурация успешно загружена.")

        # --- Проверки конфигурации ---
        # (Этот блок можно оставить здесь или вынести в отдельную функцию)
        # ... (проверки из старого core_logic.py)
        jira_cfg = app_config.get('jira', {})
        jira_url = jira_cfg.get('server_url')
        if not jira_url: logger.critical("URL JIRA не указан."); return False
        if not jira_cookie: logger.critical("JIRA Cookie не предоставлена."); return False
        # ... (остальные проверки можно добавить для надежности)

        # --- Шаг 2: Инициализация и подключение к JIRA ---
        logger.info("2. Инициализация клиента JIRA...")
        jira = JiraClient(
            server_url=jira_url,
            headers=jira_cfg.get('request_headers'),
            cookie_string=jira_cookie,
            timeout=jira_cfg.get('timeout', 30)
        )
        logger.info("Проверка подключения к JIRA...")
        if not jira.check_connection_myself():
            logger.error("Не удалось подтвердить подключение к JIRA.")
            return False
        logger.info(f"Подключение к JIRA успешно подтверждено.")

        # --- Шаг 3: Получение и обработка данных ---
        logger.info(f"3. Получение задач из JIRA для фильтра ID: {filter_id}...")
        raw_issues = jira.get_issues_by_filter_id(filter_id, jira_cfg.get('issue_fields_to_request'),
                                                  jira_cfg.get('max_results_per_request', 1000))
        if not raw_issues:
            logger.warning("Задачи не найдены или произошла ошибка получения.")
        else:
            logger.info(f"Получено {len(raw_issues)} задач.")

        logger.info("4. Обработка данных задач...")
        processed_data = process_jira_issues(raw_issues, app_config)
        logger.info("Данные успешно обработаны.")

        # --- Шаг 4: Подготовка к сохранению ---
        output_formats_cfg = app_config.get('output_formats', {})
        md_cfg = output_formats_cfg.get('markdown', {})
        word_cfg = output_formats_cfg.get('word', {})
        md_enabled = md_cfg and md_cfg.get('enabled', True)
        word_enabled = word_cfg and word_cfg.get('enabled', False)

        global_ver_str = str(processed_data.get("global_version", "UNKNOWN")).strip()
        safe_gv = re.sub(r'[^\w\._-]', '_', global_ver_str)
        if not safe_gv: safe_gv = "UNKNOWN_VERSION"
        date_fn_str = datetime.now().strftime('%Y-%m-%d')
        output_path = Path(output_dir).resolve()
        output_path.mkdir(parents=True, exist_ok=True)
        logger.info(f"Файлы будут сохранены в: {output_path}")

        # --- Шаг 5: Генерация и сохранение файлов ---
        if md_enabled:
            logger.info("5.1. Генерация Markdown...")
            md_content = generate_markdown_content(processed_data, app_config)
            md_fn_tpl = md_cfg.get('output_filename_template')
            if md_fn_tpl:
                md_fn = md_fn_tpl.format(global_version=safe_gv, current_date_filename=date_fn_str)
                md_fpath = output_path / md_fn
                try:
                    with open(md_fpath, 'w', encoding='utf-8') as f:
                        f.write(md_content)
                    logger.info(f"Markdown сохранен: {md_fpath}")
                except IOError as e:
                    logger.error(f"Ошибка сохранения Markdown файла {md_fpath}: {e}")
            else:
                logger.warning("Шаблон имени файла для Markdown не найден в конфигурации.")

        if word_enabled:
            logger.info("5.2. Генерация Word (.docx)...")
            word_doc = generate_word_document(processed_data, app_config)
            if word_doc:
                word_fn_tpl = word_cfg.get('output_filename_template')
                if word_fn_tpl:
                    word_fn = word_fn_tpl.format(global_version=safe_gv, current_date_filename=date_fn_str)
                    word_fpath = output_path / word_fn
                    try:
                        word_doc.save(word_fpath)
                        logger.info(f"Word документ сохранен: {word_fpath}")
                    except Exception as e:
                        logger.error(f"Ошибка сохранения Word документа {word_fpath}: {e}", exc_info=True)
                else:
                    logger.warning("Шаблон имени файла для Word не найден в конфигурации.")
            else:
                logger.warning("Генерация Word не удалась (метод вернул None).")

        logger.info("=" * 30 + " Процесс генерации успешно завершен! " + "=" * 30)
        return True

    except Exception as e:
        logger.critical(f"Произошла критическая ошибка в процессе генерации: {e}", exc_info=True)
        return False