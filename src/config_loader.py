# src/config_loader.py
import yaml
import os
from dotenv import load_dotenv
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

# Путь к файлу конфигурации относительно этого файла (config_loader.py)
# __file__ -> src/config_loader.py
# .parent -> src/
# .parent -> release-notes-generator/ (корень проекта)
CONFIG_FILE_PATH = Path(__file__).resolve().parent.parent / "config" / "config.yaml"
ENV_FILE_PATH = Path(__file__).resolve().parent.parent / ".env"


def load_config() -> dict:
    """
    Загружает конфигурацию из YAML-файла.
    """
    if not CONFIG_FILE_PATH.exists():
        logger.critical(f"КРИТИЧНО: Файл конфигурации не найден по пути {CONFIG_FILE_PATH}")
        raise FileNotFoundError(f"Файл конфигурации не найден: {CONFIG_FILE_PATH}")

    logger.info(f"Загрузка конфигурации из файла: {CONFIG_FILE_PATH}")
    try:
        with open(CONFIG_FILE_PATH, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        if not isinstance(config, dict):  # Проверка, что YAML успешно распарсился в словарь
            logger.critical(f"КРИТИЧНО: Файл конфигурации {CONFIG_FILE_PATH} пуст или имеет неверный формат YAML.")
            raise ValueError(f"Конфигурация из {CONFIG_FILE_PATH} не является словарем.")
        return config
    except yaml.YAMLError as e:
        logger.critical(f"КРИТИЧНО: Ошибка парсинга YAML файла {CONFIG_FILE_PATH}: {e}")
        raise ValueError(f"Ошибка парсинга YAML: {e}")
    except Exception as e:
        logger.critical(f"КРИТИЧНО: Неожиданная ошибка при загрузке конфигурации {CONFIG_FILE_PATH}: {e}")
        raise


def load_environment_variables() -> dict:
    """
    Загружает переменные окружения из .env файла и системных переменных.
    Переменные из .env файла имеют приоритет, если .env файл существует.
    """
    env_vars = {}
    if ENV_FILE_PATH.exists():
        logger.info(f"Загрузка переменных окружения из файла: {ENV_FILE_PATH}")
        load_dotenv(dotenv_path=ENV_FILE_PATH, override=True)
    else:
        logger.info(f"Файл {ENV_FILE_PATH} не найден. Используются только системные переменные окружения.")

    # Загружаем чувствительные переменные, которые нам нужны
    env_vars['JIRA_COOKIE_STRING'] = os.getenv('JIRA_COOKIE_STRING')
    # Можно добавить другие, если понадобятся (например, JIRA_USERNAME, JIRA_PASSWORD для Basic Auth)

    if not env_vars.get('JIRA_COOKIE_STRING'):
        logger.warning(
            "Предупреждение: Переменная окружения JIRA_COOKIE_STRING не установлена. Аутентификация JIRA может не работать.")

    return env_vars


if __name__ == '__main__':
    # Настройка логирования для теста этого модуля
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    logger.info("Тестирование загрузчика конфигурации...")
    try:
        app_config = load_config()
        logger.info("Конфигурация из config.yaml успешно загружена:")
        # Выводим только часть конфига для краткости
        logger.debug(f"JIRA URL: {app_config.get('jira', {}).get('server_url')}")
        logger.debug(
            f"Markdown output template: {app_config.get('output_formats', {}).get('markdown', {}).get('output_filename_template')}")

        env_variables = load_environment_variables()
        logger.info("Переменные окружения загружены:")
        for key, value in env_variables.items():
            # Скрываем значение куки в логе
            if "COOKIE" in key.upper() and value:
                logger.debug(f"{key}: ****** (длина: {len(value)})")
            else:
                logger.debug(f"{key}: {value}")
        logger.info("Тестирование загрузчика конфигурации завершено.")

    except (FileNotFoundError, ValueError) as e:
        logger.error(f"Ошибка в процессе тестирования загрузчика: {e}")
    except Exception as e:
        logger.error(f"Неожиданная ошибка в процессе тестирования загрузчика: {e}", exc_info=True)