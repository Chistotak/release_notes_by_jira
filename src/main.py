# src/main.py
import argparse
import sys
import logging
import json
from pathlib import Path
from datetime import datetime
import re
import getpass

project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from src.config_loader import load_config, load_environment_variables
from src.jira_client import JiraClient
from src.data_processor import process_jira_issues
from src.markdown_generator import generate_markdown_content
from src.word_generator import generate_word_document

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def get_interactive_input(prompt: str, default: str | None = None, is_secret: bool = False) -> str:
    display_prompt = prompt
    if default:
        display_prompt += f" (по умолчанию: {default})"
    display_prompt += ": "

    while True:
        try:
            if is_secret:
                user_input = getpass.getpass(display_prompt)
            else:
                user_input = input(display_prompt).strip()
        except KeyboardInterrupt:
            logger.info("\nВвод отменен пользователем. Завершение работы.")
            sys.exit(0)
        except EOFError:
            logger.info("\nВвод завершен (EOF). Завершение работы.")
            sys.exit(0)

        if user_input:
            return user_input
        elif default is not None:
            logger.info(f"Используется значение по умолчанию: {default}")
            return default
        else:
            logger.warning("Это поле не может быть пустым. Пожалуйста, введите значение.")


def main():
    parser = argparse.ArgumentParser(
        description="Генератор Release Notes из JIRA.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument("filter_id", nargs='?', default=None, help="ID фильтра JIRA.")
    parser.add_argument("--output-dir", default=None, help="Директория для сохранения файла.")
    parser.add_argument("--loglevel", default="info", choices=['debug', 'info', 'warning', 'error', 'critical'],
                        help="Уровень логов.")
    args = parser.parse_args()

    numeric_level = getattr(logging, args.loglevel.upper(), logging.INFO)
    logging.getLogger().setLevel(numeric_level)

    logger.info("=" * 30 + " Запуск Release Notes генератора " + "=" * 30)

    try:
        logger.info("1. Загрузка конфигурации...")
        app_config = load_config()
        env_vars = load_environment_variables()
        logger.info("Конфигурация и переменные окружения успешно загружены.")

        defaults_config = app_config.get('defaults', {})
        logger.debug(f"Загружены defaults из config.yaml: {defaults_config}")

        filter_id_to_use = args.filter_id
        source_filter_id = "аргумента командной строки"
        if not filter_id_to_use:
            filter_id_to_use = defaults_config.get('filter_id')
            if filter_id_to_use:
                source_filter_id = "config.yaml (defaults.filter_id)"
            else:
                logger.info("ID фильтра JIRA не указан.")
                filter_id_to_use = get_interactive_input("Введите ID JIRA-фильтра")
                source_filter_id = "интерактивного ввода"
                if not filter_id_to_use:
                    logger.critical("КРИТИЧНО: ID фильтра JIRA не предоставлен. Завершение.");
                    return
        logger.info(f"Используется фильтр JIRA ID: {filter_id_to_use} (источник: {source_filter_id})")

        output_dir_to_use = args.output_dir
        source_output_dir = "аргумента командной строки"
        if not output_dir_to_use:
            output_dir_to_use = defaults_config.get('output_dir')
            if output_dir_to_use:
                source_output_dir = "config.yaml (defaults.output_dir)"
            else:
                logger.info("Директория для сохранения не указана.")
                output_dir_to_use = get_interactive_input("Укажите директорию для сохранения Release Notes",
                                                          default=".")
                source_output_dir = "интерактивного ввода (или дефолт './')"

        logger.info(
            f"Директория для вывода Release Notes: {Path(output_dir_to_use).resolve()} (источник: {source_output_dir})")
        logger.debug(f"Установлен уровень логирования: {args.loglevel.upper()}")

        jira_cookie_to_use = env_vars.get('JIRA_COOKIE_STRING')
        if not jira_cookie_to_use:
            logger.warning("JIRA_COOKIE_STRING не найдена.")
            print("\n" + "=" * 20 + " ЗАПРОС JIRA COOKIE " + "=" * 20)
            jira_cookie_to_use = get_interactive_input("Введите JIRA Cookie строку (ввод скрыт)", is_secret=True)
            print("=" * (40 + len(" ЗАПРОС JIRA COOKIE ")) + "\n")
            if not jira_cookie_to_use:
                logger.critical("КРИТИЧНО: JIRA Cookie не предоставлена. Завершение.");
                return
            logger.info("JIRA Cookie строка получена интерактивно.")

        logger.debug("Проверка критических секций конфигурации...")
        jira_cfg = app_config.get('jira', {})
        jira_url = jira_cfg.get('server_url')
        fields_to_request = jira_cfg.get('issue_fields_to_request')
        version_parsing_cfg = app_config.get('version_parsing')
        release_notes_cfg = app_config.get('release_notes')
        output_formats_cfg = app_config.get('output_formats', {})
        markdown_output_cfg = output_formats_cfg.get('markdown')
        critical_configs_ok = True
        if not jira_url: logger.critical("КРИТИЧНО: jira.server_url не указан."); critical_configs_ok = False
        if not fields_to_request: logger.critical(
            "КРИТИЧНО: jira.issue_fields_to_request пуст."); critical_configs_ok = False
        if not (version_parsing_cfg and version_parsing_cfg.get('global_version') and version_parsing_cfg.get(
                'microservice_version') and version_parsing_cfg.get('microservice_mapping')):
            logger.critical("КРИТИЧНО: 'version_parsing' или подсекции неполны.");
            critical_configs_ok = False
        if not (release_notes_cfg and release_notes_cfg.get('sections')):
            logger.critical("КРИТИЧНО: 'release_notes' или 'sections' отсутствует/неполна.");
            critical_configs_ok = False
        word_output_cfg = output_formats_cfg.get('word', {})
        markdown_enabled = markdown_output_cfg and markdown_output_cfg.get('enabled', True)
        word_enabled = word_output_cfg and word_output_cfg.get('enabled', False)
        if not markdown_enabled and not word_enabled:
            logger.critical("КРИТИЧНО: Ни один формат вывода не включен.");
            critical_configs_ok = False
        if markdown_enabled and (not markdown_output_cfg or not markdown_output_cfg.get('output_filename_template')):
            logger.critical(
                "КРИТИЧНО: Markdown включен, но output_formats.markdown.output_filename_template отсутствует.");
            critical_configs_ok = False
        if word_enabled and (not word_output_cfg or not word_output_cfg.get('output_filename_template')):
            logger.critical("КРИТИЧНО: Word включен, но output_formats.word.output_filename_template отсутствует.");
            critical_configs_ok = False
        if not critical_configs_ok:
            logger.error("Проблемы с конфигурацией. Завершение.");
            return

        logger.info("2. Инициализация клиента JIRA...")
        jira = JiraClient(server_url=jira_url, headers=jira_cfg.get('request_headers'),
                          cookie_string=jira_cookie_to_use, timeout=jira_cfg.get('timeout', 30))
        logger.info("Проверка подключения к JIRA...")
        user_details = jira.check_connection_myself()
        if not user_details:
            logger.error("Не удалось подключиться к JIRA. Завершение.");
            return
        logger.info(f"Подключение к JIRA успешно (пользователь: {user_details.get('displayName', 'N/A')})")

        logger.info(f"3. Получение задач из JIRA для фильтра ID: {filter_id_to_use}...")
        raw_issues_data = jira.get_issues_by_filter_id(filter_id_to_use, fields=fields_to_request,
                                                       max_results_total=jira_cfg.get('max_results_per_request', 1000))
        if not raw_issues_data:
            logger.warning("Задачи не найдены или ошибка получения.")
        else:
            logger.info(f"Получено {len(raw_issues_data)} задач(и) из JIRA.")

        logger.info("4. Обработка данных задач...")
        processed_release_data = process_jira_issues(raw_issues_data, app_config)
        logger.info("Данные обработаны.")
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug("--- Структурированные данные (JSON DEBUG) ---")
            try:
                logger.debug(json.dumps(processed_release_data, indent=2, ensure_ascii=False, default=str))
            except TypeError:
                logger.debug(str(processed_release_data))
            logger.debug("--- Конец JSON DEBUG ---")

        global_version_str = str(processed_release_data.get("global_version", "UNKNOWN")).strip()
        safe_global_version = re.sub(r'[^\w\._-]', '_', global_version_str)
        if not safe_global_version: safe_global_version = "UNKNOWN_VERSION"
        date_for_filename = datetime.now().strftime('%Y-%m-%d')
        output_dir_final_path = Path(output_dir_to_use).resolve()
        try:
            output_dir_final_path.mkdir(parents=True, exist_ok=True)
            logger.info(f"Директория для сохранения: {output_dir_final_path}")
        except OSError as e:
            logger.error(
                f"Не удалось создать директорию {output_dir_final_path}: {e}. Сохранение в {Path('.').resolve()}.")
            output_dir_final_path = Path(".").resolve()

        if markdown_enabled:
            logger.info("5. Генерация Markdown...")
            markdown_content = generate_markdown_content(processed_release_data, app_config)
            logger.info("Markdown сгенерирован.")
            logger.info("6. Сохранение Markdown файла...")
            md_filename_template = markdown_output_cfg.get('output_filename_template')
            md_output_filename_str = md_filename_template.format(global_version=safe_global_version,
                                                                 current_date_filename=date_for_filename)
            md_final_output_file_path = output_dir_final_path / md_output_filename_str
            try:
                with open(md_final_output_file_path, 'w', encoding='utf-8') as f:
                    f.write(markdown_content)
                logger.info(f"Markdown сохранен: {md_final_output_file_path}")
            except IOError as e:
                logger.error(f"Ошибка сохранения Markdown {md_final_output_file_path}: {e}")
        else:
            logger.info("Генерация Markdown отключена.")

        if word_enabled:
            logger.info("7. Генерация Word (.docx)...")
            # project_root определен в начале файла main.py
            word_document = generate_word_document(processed_release_data, app_config,
                                                   project_root_dir=project_root)  # <--- ИСПРАВЛЕНО
            if word_document:
                word_filename_template = word_output_cfg.get('output_filename_template')
                word_output_filename_str = word_filename_template.format(global_version=safe_global_version,
                                                                         current_date_filename=date_for_filename)
                word_final_output_file_path = output_dir_final_path / word_output_filename_str
                try:
                    word_document.save(word_final_output_file_path)
                    logger.info(f"Word документ сохранен: {word_final_output_file_path}")
                except Exception as e:
                    logger.error(f"Ошибка сохранения Word {word_final_output_file_path}: {e}", exc_info=True)
            else:
                logger.warning("Генерация Word не удалась (метод вернул None).")
        else:
            logger.info("Генерация Word отключена.")

        logger.info("=" * 30 + " Скрипт успешно завершил работу! " + "=" * 30)

    except FileNotFoundError as e:
        logger.critical(f"КРИТИЧНО: Файл конфигурации не найден - {e}", exc_info=True)
    except ValueError as e:
        logger.critical(f"КРИТИЧНО: Ошибка значения - {e}", exc_info=True)
    except KeyError as e:
        logger.critical(f"КРИТИЧНО: Отсутствует ключ в конфигурации - {e}.", exc_info=True)
    except Exception as e:
        logger.critical(f"Непредвиденная критическая ошибка: {e}", exc_info=True)


if __name__ == "__main__":
    main()