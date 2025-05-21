# src/main.py
import argparse
import sys
import logging
import json
from pathlib import Path
from datetime import datetime
import re
import getpass

# Добавляем корень проекта в sys.path для корректных импортов,
# если скрипт запускается не из корневой директории.
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# Импорты наших модулей
from src.config_loader import load_config, load_environment_variables
from src.jira_client import JiraClient
from src.data_processor import process_jira_issues
from src.markdown_generator import generate_markdown_content
from src.word_generator import generate_word_document

# Настройка базового формата логирования.
# Уровень будет установлен из аргументов командной строки.
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - [%(module)s.%(funcName)s:%(lineno)d] - %(message)s')
logger = logging.getLogger(__name__)  # Логгер для текущего модуля (main.py)


def get_interactive_input(prompt_message: str, default_value: str | None = None, is_secret_input: bool = False) -> str:
    """
    Запрашивает ввод у пользователя интерактивно.

    Args:
        prompt_message (str): Сообщение-приглашение для пользователя.
        default_value (str | None, optional): Значение по умолчанию, если пользователь ничего не ввел.
        is_secret_input (bool, optional): Если True, ввод будет скрыт (для паролей/токенов).

    Returns:
        str: Строка, введенная пользователем, или значение по умолчанию.
             Завершает программу, если ввод обязателен, но не предоставлен.
    """
    display_prompt = prompt_message
    if default_value:
        display_prompt += f" (по умолчанию: {default_value})"
    display_prompt += ": "

    while True:
        try:
            if is_secret_input:
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
        elif default_value is not None:
            logger.info(f"Используется значение по умолчанию: {default_value}")
            return default_value
        else:
            logger.warning("Это поле не может быть пустым. Пожалуйста, введите значение.")
            # Цикл запроса ввода продолжится


def main():
    """
    Главная функция скрипта для генерации Release Notes.
    Оркестрирует загрузку конфигурации, взаимодействие с JIRA, обработку данных
    и генерацию выходных файлов (Markdown, Word).
    """
    parser = argparse.ArgumentParser(
        description="Генератор Release Notes из JIRA на основе ID фильтра.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument(
        "filter_id",
        nargs='?',
        default=None,
        help="ID фильтра JIRA. Если не указан, используется значение из config.yaml или запрашивается интерактивно."
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Директория для сохранения файлов. Если не указана, используется config.yaml или запрашивается (дефолт: './')."
    )
    parser.add_argument(
        "--loglevel",
        default="info",
        choices=['debug', 'info', 'warning', 'error', 'critical'],
        help="Уровень детализации логов."
    )
    args = parser.parse_args()

    numeric_level = getattr(logging, args.loglevel.upper(), logging.INFO)
    logging.getLogger().setLevel(numeric_level)  # Устанавливаем уровень для корневого логгера

    logger.info("=" * 30 + " Запуск Release Notes генератора " + "=" * 30)

    try:
        # --- Шаг 1: Загрузка конфигурации и переменных окружения ---
        logger.info("1. Загрузка конфигурации...")
        app_config = load_config()
        env_vars = load_environment_variables()
        logger.info("Конфигурация и переменные окружения успешно загружены.")

        defaults_config = app_config.get('defaults', {})
        logger.debug(f"Загружены defaults из config.yaml: {defaults_config}")

        # --- Шаг 2: Определение filter_id и output_dir ---
        filter_id_to_use = args.filter_id
        source_filter_id = "аргумента командной строки"
        if not filter_id_to_use:
            filter_id_to_use = defaults_config.get('filter_id')
            if filter_id_to_use:
                source_filter_id = "config.yaml (defaults.filter_id)"
            else:
                logger.info("ID фильтра JIRA не указан (CLI/config).")
                filter_id_to_use = get_interactive_input("Введите ID JIRA-фильтра")
                source_filter_id = "интерактивного ввода"
                if not filter_id_to_use: logger.critical("ID фильтра не предоставлен. Выход."); return
        logger.info(f"Используется фильтр JIRA ID: {filter_id_to_use} (источник: {source_filter_id})")

        output_dir_to_use = args.output_dir
        source_output_dir = "аргумента командной строки"
        if not output_dir_to_use:
            output_dir_to_use = defaults_config.get('output_dir')
            if output_dir_to_use:
                source_output_dir = "config.yaml (defaults.output_dir)"
            else:
                logger.info("Директория для сохранения не указана (CLI/config).")
                output_dir_to_use = get_interactive_input("Укажите директорию для сохранения Release Notes",
                                                          default=".")
                source_output_dir = "интерактивного ввода (или дефолт './')"
        logger.info(f"Директория для вывода: {Path(output_dir_to_use).resolve()} (источник: {source_output_dir})")
        logger.debug(f"Уровень логирования: {args.loglevel.upper()}")

        jira_cookie_to_use = env_vars.get('JIRA_COOKIE_STRING')
        if not jira_cookie_to_use:
            logger.warning("JIRA_COOKIE_STRING не найдена в окружении.")
            print("\n" + "=" * 20 + " ЗАПРОС JIRA COOKIE " + "=" * 20)
            jira_cookie_to_use = get_interactive_input("Введите JIRA Cookie строку (ввод будет скрыт)",
                                                       is_secret_input=True)
            print("=" * (40 + len(" ЗАПРОС JIRA COOKIE ")) + "\n")
            if not jira_cookie_to_use: logger.critical("JIRA Cookie не предоставлена. Выход."); return
            logger.info("JIRA Cookie строка получена интерактивно.")

        # --- Шаг 3: Проверка критически важных частей конфигурации ---
        logger.debug("Проверка критических секций конфигурации...")
        jira_cfg = app_config.get('jira', {});
        jira_url = jira_cfg.get('server_url')
        fields_to_request = jira_cfg.get('issue_fields_to_request')
        version_parsing_cfg = app_config.get('version_parsing');
        release_notes_cfg = app_config.get('release_notes')
        output_formats_cfg = app_config.get('output_formats', {})
        md_cfg = output_formats_cfg.get('markdown');
        word_cfg = output_formats_cfg.get('word', {})

        critical_ok = True
        if not jira_url: logger.critical("jira.server_url не указан."); critical_ok = False
        if not fields_to_request: logger.critical("jira.issue_fields_to_request пуст."); critical_ok = False
        if not (version_parsing_cfg and version_parsing_cfg.get('global_version') and version_parsing_cfg.get(
                'microservice_version') and version_parsing_cfg.get('microservice_mapping')):
            logger.critical("Секция 'version_parsing' или ее подсекции неполны.");
            critical_ok = False
        if not (release_notes_cfg and release_notes_cfg.get('sections')):
            logger.critical("Секция 'release_notes' или 'sections' отсутствует/неполна.");
            critical_ok = False

        md_enabled = md_cfg and md_cfg.get('enabled', True)  # Markdown по умолчанию включен, если секция есть
        word_enabled = word_cfg and word_cfg.get('enabled', False)
        if not md_enabled and not word_enabled: logger.critical(
            "Ни один формат вывода (MD/Word) не включен."); critical_ok = False
        if md_enabled and (not md_cfg or not md_cfg.get('output_filename_template')): logger.critical(
            "MD включен, но 'output_formats.markdown.output_filename_template' отсутствует."); critical_ok = False
        if word_enabled and (not word_cfg or not word_cfg.get('output_filename_template')): logger.critical(
            "Word включен, но 'output_formats.word.output_filename_template' отсутствует."); critical_ok = False
        if not critical_ok: logger.error("Критические проблемы с конфигурацией. Выход."); return

        # --- Шаг 4: Инициализация и подключение к JIRA ---
        logger.info("2. Инициализация клиента JIRA...")
        jira = JiraClient(jira_url, jira_cfg.get('request_headers'), jira_cookie_to_use, jira_cfg.get('timeout', 30))
        logger.info("Проверка подключения к JIRA...")
        if not jira.check_connection_myself(): logger.error("Не удалось подтвердить подключение к JIRA. Выход."); return
        logger.info(f"Подключение к JIRA успешно подтверждено.")

        # --- Шаг 5: Получение задач ---
        logger.info(f"3. Получение задач из JIRA для фильтра ID: {filter_id_to_use}...")
        raw_issues = jira.get_issues_by_filter_id(filter_id_to_use, fields_to_request,
                                                  jira_cfg.get('max_results_per_request', 1000))
        if not raw_issues:
            logger.warning("Задачи по фильтру не найдены или ошибка получения.")
        else:
            logger.info(f"Успешно получено {len(raw_issues)} задач(и) из JIRA.")

        # --- Шаг 6: Обработка данных ---
        logger.info("4. Обработка данных задач...")
        processed_data = process_jira_issues(raw_issues, app_config)
        logger.info("Данные успешно обработаны.")
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug("--- Структурированные данные (JSON DEBUG) ---")
            try:
                logger.debug(json.dumps(processed_data, indent=2, ensure_ascii=False, default=str))
            except TypeError:
                logger.debug(str(processed_data))  # Фоллбэк, если несериализуемые объекты
            logger.debug("--- Конец JSON DEBUG ---")

        # --- Подготовка к сохранению файлов ---
        global_ver_str = str(processed_data.get("global_version", "UNKNOWN")).strip()
        safe_gv = re.sub(r'[^\w\._-]', '_', global_ver_str)
        if not safe_gv: safe_gv = "UNKNOWN_VERSION"
        date_fn_str = datetime.now().strftime('%Y-%m-%d')
        output_path = Path(output_dir_to_use).resolve()
        try:
            output_path.mkdir(parents=True, exist_ok=True)
            logger.info(f"Файлы будут сохранены в: {output_path}")
        except OSError as e:
            logger.error(
                f"Не удалось создать директорию {output_path}: {e}. Попытка сохранить в {Path('.').resolve()}.")
            output_path = Path(".").resolve()

        # --- Шаг 7: Генерация и сохранение Markdown ---
        if md_enabled:
            logger.info("5. Генерация Markdown...")
            md_content = generate_markdown_content(processed_data, app_config)
            logger.info("Markdown контент сгенерирован.")
            md_fn_tpl = md_cfg.get('output_filename_template')
            md_fn = md_fn_tpl.format(global_version=safe_gv, current_date_filename=date_fn_str)
            md_fpath = output_path / md_fn
            try:
                with open(md_fpath, 'w', encoding='utf-8') as f:
                    f.write(md_content)
                logger.info(f"Markdown Release Notes сохранены: {md_fpath}")
            except IOError as e:
                logger.error(f"Ошибка сохранения Markdown файла {md_fpath}: {e}")
        else:
            logger.info("Генерация Markdown отключена.")

        # --- Шаг 8: Генерация и сохранение Word ---
        if word_enabled:
            logger.info("6. Генерация Word (.docx)...")
            word_doc = generate_word_document(processed_data, app_config)
            if word_doc:
                word_fn_tpl = word_cfg.get('output_filename_template')
                word_fn = word_fn_tpl.format(global_version=safe_gv, current_date_filename=date_fn_str)
                word_fpath = output_path / word_fn
                try:
                    word_doc.save(word_fpath)
                    logger.info(f"Word документ сохранен: {word_fpath}")
                except Exception as e:
                    logger.error(f"Ошибка сохранения Word документа {word_fpath}: {e}", exc_info=True)
            else:
                logger.warning("Генерация Word документа не удалась (метод вернул None).")
        else:
            logger.info("Генерация Word документа отключена.")

        logger.info("=" * 30 + " Скрипт успешно завершил работу! " + "=" * 30)

    except FileNotFoundError as e:
        logger.critical(f"КРИТИЧНО: Файл конфигурации не найден - {e}", exc_info=True)
    except ValueError as e:
        logger.critical(f"КРИТИЧНО: Ошибка значения (конфигурация/аргументы) - {e}", exc_info=True)
    except KeyError as e:
        logger.critical(f"КРИТИЧНО: Отсутствует ключ в конфигурации - {e}.", exc_info=True)
    except Exception as e:
        logger.critical(f"Непредвиденная критическая ошибка: {e}", exc_info=True)


if __name__ == "__main__":
    main()