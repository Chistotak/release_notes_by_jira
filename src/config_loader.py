# src/config_loader.py
import yaml
import os
from dotenv import load_dotenv
from pathlib import Path
import logging
import sys

logger = logging.getLogger(__name__)  # Логгер для этого модуля

def get_correct_path(relative_path_str: str) -> Path:
    """
    Возвращает корректный путь к ресурсу, работающий как в режиме скрипта,
    так и в собранном PyInstaller приложении.
    """
    try:
        # Если приложение собрано PyInstaller (_MEIPASS есть у onefile и onedir сборок)
        base_path = Path(sys._MEIPASS)
        logger.debug(f"PyInstaller режим: _MEIPASS = {base_path}")
    except AttributeError:
        # Если запущено как обычный Python скрипт
        # Путь от корня проекта (где лежит папка src, config и т.д.)
        base_path = Path(__file__).resolve().parent.parent
        logger.debug(f"Режим скрипта: base_path = {base_path} (относительно {__file__})")
    final_path = base_path / relative_path_str
    logger.debug(f"get_correct_path: relative='{relative_path_str}', absolute='{final_path}'")
    return final_path

# Пути определяются относительно текущего файла для надежности
CONFIG_FILE_PATH = Path(__file__).resolve().parent.parent / "config" / "config.yaml"
ENV_FILE_PATH = Path(__file__).resolve().parent.parent / ".env"


def load_config() -> dict:
    """
    Загружает основную конфигурацию скрипта из YAML-файла (config/config.yaml).

    Файл конфигурации должен находиться по пути 'корень_проекта/config/config.yaml'.

    Returns:
        dict: Словарь с конфигурацией, загруженной из YAML-файла.

    Raises:
        FileNotFoundError: Если файл конфигурации 'config/config.yaml' не найден.
        ValueError: Если файл конфигурации пуст, имеет неверный формат YAML,
                    или загруженная конфигурация не является словарем Python.
        Exception: Любые другие неожиданные ошибки при чтении или парсинге файла.
    """
    if not CONFIG_FILE_PATH.exists():
        # Это критическая ошибка, так как без конфига скрипт не может работать
        logger.critical(f"Файл конфигурации не найден по пути: {CONFIG_FILE_PATH}")
        raise FileNotFoundError(f"Файл конфигурации не найден: {CONFIG_FILE_PATH}")

    logger.info(f"Загрузка конфигурации из файла: {CONFIG_FILE_PATH}")
    try:
        with open(CONFIG_FILE_PATH, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)

        # Проверка, что YAML успешно распарсился и является словарем
        if not isinstance(config, dict):
            logger.critical(
                f"Содержимое файла конфигурации {CONFIG_FILE_PATH} пустое или не является словарем (получен тип: {type(config)}).")
            raise ValueError(f"Конфигурация из {CONFIG_FILE_PATH} должна быть словарем.")

        logger.debug("Файл конфигурации успешно загружен и распарсен.")
        return config
    except yaml.YAMLError as e:
        logger.critical(f"Ошибка парсинга YAML в файле {CONFIG_FILE_PATH}: {e}")
        raise ValueError(f"Ошибка парсинга YAML файла конфигурации: {e}")
    except Exception as e:
        logger.critical(f"Неожиданная ошибка при загрузке или парсинге конфигурационного файла {CONFIG_FILE_PATH}: {e}",
                        exc_info=True)
        raise  # Пробрасываем исключение дальше


def load_environment_variables() -> dict:
    """
    Загружает переменные окружения из файла .env (если он существует в корне проекта)
    и из системного окружения. Переменные из .env имеют приоритет.

    Файл .env должен находиться в корневой директории проекта.

    Returns:
        dict: Словарь, содержащий значения для 'JIRA_COOKIE_STRING' (может быть None, если не найдена).
    """
    env_vars = {}
    if ENV_FILE_PATH.exists():
        logger.info(f"Загрузка переменных окружения из файла: {ENV_FILE_PATH}")
        load_dotenv(dotenv_path=ENV_FILE_PATH, override=True)
    else:
        logger.info(
            f"Файл {ENV_FILE_PATH} не найден. Используются только системные переменные окружения (если установлены).")

    # Явно запрашиваем только те переменные, которые нам нужны
    env_vars['JIRA_COOKIE_STRING'] = os.getenv('JIRA_COOKIE_STRING')

    # Закомментированные переменные, которые могут понадобиться для других методов аутентификации
    # env_vars['JIRA_USERNAME'] = os.getenv('JIRA_USERNAME')
    # env_vars['JIRA_PASSWORD'] = os.getenv('JIRA_PASSWORD')

    if not env_vars.get('JIRA_COOKIE_STRING'):
        # Это предупреждение, так как core_logic.py может запросить куку интерактивно
        logger.warning("Переменная окружения JIRA_COOKIE_STRING не установлена ни в .env, ни в системном окружении.")
    else:
        logger.debug("JIRA_COOKIE_STRING успешно загружена из переменных окружения.")

    return env_vars