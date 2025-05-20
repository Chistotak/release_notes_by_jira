# src/main.py
import argparse
import sys
import logging
import json
from pathlib import Path
from datetime import datetime
import re
import getpass

# Добавляем корень проекта в sys.path
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from src.config_loader import load_config, load_environment_variables
from src.jira_client import JiraClient
from src.data_processor import process_jira_issues
from src.markdown_generator import generate_markdown_content

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
    parser.add_argument(
        "filter_id",
        nargs='?',
        default=None,
        help="ID фильтра JIRA. Если не указан, используется значение из config.yaml (defaults.filter_id) или запрашивается интерактивно."
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Директория для сохранения файла. Если не указана, используется значение из config.yaml (defaults.output_dir) или запрашивается интерактивно (по умолчанию: './')."
    )
    parser.add_argument(
        "--loglevel",
        default="info",
        choices=['debug', 'info', 'warning', 'error', 'critical'],
        help="Уровень детализации логов."
    )
    args = parser.parse_args()

    numeric_level = getattr(logging, args.loglevel.upper(), logging.INFO)
    logging.getLogger().setLevel(numeric_level)

    logger.info("=" * 30 + " Запуск Release Notes генератора " + "=" * 30)

    try:
        # --- Шаг II: Загрузка конфигурации и переменных окружения ---
        logger.info("1. Загрузка конфигурации...")
        app_config = load_config()
        env_vars = load_environment_variables()
        logger.info("Конфигурация и переменные окружения успешно загружены.")

        # Получаем секцию defaults из конфига, если она есть
        defaults_config = app_config.get('defaults', {})
        logger.debug(f"Загружены defaults из config.yaml: {defaults_config}")

        # --- Шаг I: Определение filter_id и output_dir с учетом приоритетов ---
        # 1. ID Фильтра: CLI > config.defaults > interactive
        filter_id_to_use = args.filter_id
        source_filter_id = "аргумента командной строки"
        if not filter_id_to_use:
            filter_id_to_use = defaults_config.get('filter_id')
            if filter_id_to_use:  # Проверяем, что значение не пустое/None
                source_filter_id = "config.yaml (defaults.filter_id)"
            else:  # Если нет ни в CLI, ни в конфиге (или в конфиге пустое)
                logger.info("ID фильтра JIRA не указан ни в аргументах, ни в config.yaml (defaults.filter_id).")
                filter_id_to_use = get_interactive_input("Введите ID JIRA-фильтра")
                source_filter_id = "интерактивного ввода"
                if not filter_id_to_use:
                    logger.critical("КРИТИЧНО: ID фильтра JIRA не был предоставлен. Завершение работы.")
                    return
        logger.info(f"Используется фильтр JIRA ID: {filter_id_to_use} (источник: {source_filter_id})")

        # 2. Директория вывода: CLI > config.defaults > interactive (с дефолтом './')
        output_dir_to_use = args.output_dir
        source_output_dir = "аргумента командной строки"
        if not output_dir_to_use:
            output_dir_to_use = defaults_config.get('output_dir')
            if output_dir_to_use:  # Проверяем, что значение не пустое/None
                source_output_dir = "config.yaml (defaults.output_dir)"
            else:  # Если нет ни в CLI, ни в конфиге (или в конфиге пустое)
                logger.info(
                    "Директория для сохранения не указана ни в аргументах, ни в config.yaml (defaults.output_dir).")
                output_dir_to_use = get_interactive_input("Укажите директорию для сохранения Release Notes",
                                                          default=".")
                source_output_dir = "интерактивного ввода (или дефолт './')"

        logger.info(
            f"Директория для вывода Release Notes: {Path(output_dir_to_use).resolve()} (источник: {source_output_dir})")
        logger.debug(f"Установлен уровень логирования: {args.loglevel.upper()}")

        # --- Проверка и интерактивный запрос JIRA_COOKIE_STRING (логика остается прежней) ---
        jira_cookie_to_use = env_vars.get('JIRA_COOKIE_STRING')
        if not jira_cookie_to_use:
            logger.warning("Переменная JIRA_COOKIE_STRING не найдена в .env или системных переменных.")
            print("\n" + "=" * 20 + " ЗАПРОС JIRA COOKIE " + "=" * 20)
            jira_cookie_to_use = get_interactive_input(
                "Пожалуйста, введите вашу JIRA Cookie строку (ввод будет скрыт для безопасности)",
                is_secret=True
            )
            print("=" * (40 + len(" ЗАПРОС JIRA COOKIE ")) + "\n")
            if not jira_cookie_to_use:
                logger.critical("КРИТИЧНО: JIRA Cookie строка не была предоставлена. Завершение работы.")
                return
            logger.info("JIRA Cookie строка получена интерактивно.")

        # --- Шаг III: Проверка критически важных частей конфигурации ---
        logger.debug("Проверка наличия критически важных секций конфигурации...")
        jira_cfg = app_config.get('jira', {})
        jira_url = jira_cfg.get('server_url')
        fields_to_request = jira_cfg.get('issue_fields_to_request')
        version_parsing_cfg = app_config.get('version_parsing')
        release_notes_cfg = app_config.get('release_notes')
        markdown_output_cfg = app_config.get('output_formats', {}).get('markdown')

        critical_configs_ok = True
        if not jira_url:
            logger.critical("КРИТИЧНО: URL JIRA (jira.server_url) не указан в config.yaml.")
            critical_configs_ok = False
        if not fields_to_request:
            logger.critical(
                "КРИТИЧНО: Список полей для запроса к JIRA (jira.issue_fields_to_request) пуст или отсутствует.")
            critical_configs_ok = False
        if not version_parsing_cfg or not version_parsing_cfg.get('global_version') or \
                not version_parsing_cfg.get('microservice_version') or not version_parsing_cfg.get(
            'microservice_mapping'):
            logger.critical(
                "КРИТИЧНО: Секция 'version_parsing' (или ее важные подсекции: global_version, microservice_version, microservice_mapping) отсутствует или неполна в config.yaml.")
            critical_configs_ok = False
        if not release_notes_cfg or not release_notes_cfg.get('sections'):
            logger.critical(
                "КРИТИЧНО: Секция 'release_notes' (или ее подсекция 'sections') отсутствует или неполна в config.yaml.")
            critical_configs_ok = False
        if not markdown_output_cfg or not markdown_output_cfg.get('output_filename_template'):
            logger.critical(
                "КРИТИЧНО: Секция 'output_formats.markdown' (или ее ключ 'output_filename_template') отсутствует в config.yaml.")
            critical_configs_ok = False

        if not critical_configs_ok:
            logger.error(
                "Обнаружены критические проблемы с конфигурацией. Пожалуйста, исправьте config.yaml. Завершение работы.")
            return

        # --- Шаг IV: Инициализация и подключение к JIRA ---
        logger.info("2. Инициализация клиента JIRA...")
        jira = JiraClient(
            server_url=jira_url,
            headers=jira_cfg.get('request_headers'),
            cookie_string=jira_cookie_to_use,
            timeout=jira_cfg.get('timeout', 30)
        )

        logger.info("Проверка подключения к JIRA (через /rest/api/2/myself)...")
        user_details = jira.check_connection_myself()
        if not user_details:
            logger.error("Не удалось подтвердить подключение к JIRA. Завершение работы.")
            return
        logger.info(
            f"Подключение к JIRA успешно подтверждено для пользователя: {user_details.get('displayName', 'N/A')}")

        # --- Шаг V: Получение задач из JIRA ---
        logger.info(f"3. Получение задач из JIRA для фильтра ID: {filter_id_to_use}...")
        raw_issues_data = jira.get_issues_by_filter_id(
            filter_id_to_use,
            fields=fields_to_request,
            max_results_total=jira_cfg.get('max_results_per_request', 1000)
        )

        if not raw_issues_data:
            logger.warning("Задачи по указанному фильтру не найдены или произошла ошибка при их получении.")
        else:
            logger.info(f"Успешно получено {len(raw_issues_data)} задач(и) из JIRA.")

        # --- Шаг VI: Обработка полученных данных ---
        logger.info("4. Обработка данных задач...")
        processed_release_data = process_jira_issues(raw_issues_data, app_config)
        logger.info("Данные успешно обработаны и структурированы.")

        if logger.isEnabledFor(logging.DEBUG):
            logger.debug("--- Структурированные данные для Release Notes (JSON DEBUG) ---")
            try:
                debug_output_json = json.dumps(processed_release_data, indent=2, ensure_ascii=False, default=str)
                logger.debug(debug_output_json)
            except TypeError:
                logger.debug(str(processed_release_data))
            logger.debug("--- Конец JSON DEBUG ---")

        # --- Шаг VII: Генерация Markdown контента ---
        logger.info("5. Генерация Markdown контента...")
        markdown_content = generate_markdown_content(processed_release_data, app_config)
        logger.info("Markdown контент успешно сгенерирован.")

        # --- Шаг VIII: Сохранение Markdown в файл ---
        logger.info("6. Сохранение Release Notes в файл...")
        filename_template = markdown_output_cfg.get('output_filename_template',
                                                    "ReleaseNotes_{global_version}_{current_date_filename}.md")

        global_version_str = str(processed_release_data.get("global_version", "UNKNOWN")).strip()
        safe_global_version = re.sub(r'[^\w\._-]', '_', global_version_str)
        if not safe_global_version: safe_global_version = "UNKNOWN_VERSION"

        date_for_filename = datetime.now().strftime('%Y-%m-%d')

        output_filename_str = filename_template.format(
            global_version=safe_global_version,
            current_date_filename=date_for_filename
        )

        output_dir_final_path = Path(output_dir_to_use).resolve()

        try:
            output_dir_final_path.mkdir(parents=True, exist_ok=True)
            logger.info(f"Файл будет сохранен в директорию: {output_dir_final_path}")
        except OSError as e:
            logger.error(f"Не удалось создать директорию для вывода {output_dir_final_path}: {e}. "
                         f"Попытка сохранить в текущую директорию ({Path('.').resolve()}).")
            output_dir_final_path = Path(".").resolve()

        final_output_file_path = output_dir_final_path / output_filename_str

        try:
            with open(final_output_file_path, 'w', encoding='utf-8') as f:
                f.write(markdown_content)
            logger.info(f"Release Notes успешно сохранены в файл: {final_output_file_path}")
        except IOError as e:
            logger.error(f"Ошибка при сохранении файла {final_output_file_path}: {e}")

        logger.info("=" * 30 + " Скрипт успешно завершил работу! " + "=" * 30)

    except FileNotFoundError as e:
        logger.critical(f"КРИТИЧНО: Файл конфигурации не найден - {e}", exc_info=True)
    except ValueError as e:
        logger.critical(f"КРИТИЧНО: Ошибка значения при обработке конфигурации или аргументов - {e}", exc_info=True)
    except KeyError as e:
        logger.critical(f"КРИТИЧНО: Отсутствует необходимый ключ в конфигурации - {e}. Проверьте config.yaml.",
                        exc_info=True)
    except Exception as e:
        logger.critical(f"Произошла непредвиденная критическая ошибка в работе скрипта: {e}", exc_info=True)


if __name__ == "__main__":
    main()