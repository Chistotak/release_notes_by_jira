# src/jira_client.py
import requests
import json  # Для парсинга JSON и логирования ошибок
import logging

logger = logging.getLogger(__name__)


class JiraClient:
    def __init__(self, server_url: str, headers: dict | None = None, cookie_string: str | None = None,
                 timeout: int = 30):
        self.server_url = server_url.rstrip('/')
        self.timeout = timeout
        self.session = requests.Session()  # Используем сессию для сохранения кук и заголовков

        # Устанавливаем заголовки по умолчанию для сессии
        default_session_headers = {
            "Accept": "application/json",  # По умолчанию ожидаем JSON
            # User-Agent может быть переопределен из config.yaml
            "User-Agent": "Python Release Notes Generator (DefaultClient/1.0)"
        }
        self.session.headers.update(default_session_headers)

        # Если переданы дополнительные заголовки из конфига, обновляем ими дефолтные
        if headers:
            self.session.headers.update(headers)
            logger.debug(f"Пользовательские заголовки применены: {headers}")

        # Устанавливаем куки, если они переданы
        if cookie_string:
            # requests.Session ожидает куки в виде словаря, но также может принимать строку через headers['Cookie']
            self.session.headers['Cookie'] = cookie_string
            logger.info("JiraClient: Строка Cookie установлена в заголовки сессии.")
        else:
            # Это уже логируется в config_loader, но можно добавить и здесь, если клиент создается напрямую
            logger.warning("JiraClient: Строка Cookie не предоставлена. Запросы к JIRA могут быть неаутентифицированы.")

        logger.info(f"JiraClient инициализирован для URL: {self.server_url}")
        logger.debug(f"Итоговые заголовки сессии для запросов: {self.session.headers}")

    def _make_request(self, method: str, endpoint: str, params: dict | None = None,
                      data: dict | None = None) -> requests.Response | None:
        """Вспомогательный метод для выполнения HTTP-запросов."""
        url = f"{self.server_url}{endpoint}"
        logger.debug(f"Выполнение запроса: {method} {url}, Params: {params}, Data: {data}")

        try:
            if method.upper() == 'GET':
                response = self.session.get(url, params=params, timeout=self.timeout)
            elif method.upper() == 'POST':
                response = self.session.post(url, params=params, json=data,
                                             timeout=self.timeout)  # Отправляем data как JSON
            # Добавить другие методы (PUT, DELETE) при необходимости
            else:
                logger.error(f"Неподдерживаемый HTTP метод: {method}")
                return None

            response.raise_for_status()  # Вызовет HTTPError для кодов 4xx/5xx
            return response

        except requests.exceptions.HTTPError as http_err:
            logger.error(
                f"HTTP ошибка: {http_err.response.status_code} {http_err.response.reason} для {http_err.request.url}")
            logger.error(
                f"Тело ответа (если есть, до 500 симв.): {http_err.response.text[:500] if http_err.response else 'Нет тела ответа'}")
        except requests.exceptions.ConnectionError as conn_err:
            logger.error(f"Ошибка соединения с {url}: {conn_err}")
        except requests.exceptions.Timeout as timeout_err:
            logger.error(f"Таймаут запроса к {url}: {timeout_err}")
        except requests.exceptions.RequestException as req_err:
            logger.error(f"Общая ошибка запроса к {url}: {req_err}")
        return None

    def check_connection_myself(self) -> dict | None:
        """
        Проверяет соединение и аутентификацию, запрашивая информацию о текущем пользователе.
        Эндпоинт: /rest/api/2/myself
        """
        endpoint = "/rest/api/2/myself"
        logger.info(f"Проверка соединения и аутентификации через {endpoint}...")

        response = self._make_request('GET', endpoint)
        if response:
            try:
                user_data = response.json()
                logger.info(
                    f"Успешный ответ от {endpoint}. Пользователь: {user_data.get('displayName', user_data.get('name', 'Неизвестно'))}")
                return user_data
            except json.JSONDecodeError as json_err:
                logger.error(f"Ошибка декодирования JSON из ответа {endpoint}: {json_err}")
                logger.error(f"Текст ответа (до 500 симв.): {response.text[:500]}")
        return None

    def get_filter_jql(self, filter_id: str) -> str | None:
        """
        Получает JQL-запрос для существующего фильтра JIRA по его ID.
        Эндпоинт: /rest/api/2/filter/{filter_id}
        """
        if not filter_id:
            logger.error("ID фильтра не предоставлен для get_filter_jql.")
            return None

        endpoint = f"/rest/api/2/filter/{filter_id}"
        logger.info(f"Запрос JQL для фильтра ID {filter_id} (эндпоинт: {endpoint})...")

        response = self._make_request('GET', endpoint)
        if response:
            try:
                filter_data = response.json()
                jql = filter_data.get('jql')
                if jql:
                    logger.info(f"JQL для фильтра ID {filter_id} успешно получен: '{jql}'")
                    return jql
                else:
                    logger.error(f"JQL не найден в ответе для фильтра ID {filter_id}. Ответ: {filter_data}")
            except json.JSONDecodeError as json_err:
                logger.error(f"Ошибка декодирования JSON для фильтра ID {filter_id}: {json_err}")
                logger.error(f"Текст ответа (до 500 симв.): {response.text[:500]}")
        return None

    def get_issues_by_jql(self, jql_query: str, fields: list[str] | None = None, max_results: int = 50,
                          start_at: int = 0) -> list[dict]:
        """
        Получает задачи из JIRA по JQL-запросу с пагинацией.
        Эндпоинт: /rest/api/2/search
        """
        if not jql_query:
            logger.error("JQL запрос не предоставлен для get_issues_by_jql.")
            return []

        endpoint = "/rest/api/2/search"
        params = {
            'jql': jql_query,
            'maxResults': max_results,
            'startAt': start_at,
            'validateQuery': 'strict'  # Валидация JQL на стороне JIRA
        }
        if fields:
            # Убедимся, что 'key' всегда запрашивается, т.к. он критичен
            if 'key' not in fields:
                fields_to_request = ['key'] + fields
            else:
                fields_to_request = fields
            params['fields'] = ",".join(fields_to_request)
        else:  # Если fields не указаны, запросим только key и summary для базовой информации
            params['fields'] = "key,summary"

        logger.info(
            f"Запрос задач по JQL: '{jql_query}', поля: {params.get('fields')}, startAt: {start_at}, maxResults: {max_results}...")

        response = self._make_request('GET', endpoint, params=params)
        if response:
            try:
                search_results = response.json()
                issues = search_results.get('issues', [])
                total_issues = search_results.get('total', 0)
                logger.info(
                    f"По JQL '{jql_query}' найдено {len(issues)} задач (из {total_issues} всего) на текущей странице.")
                # В будущем можно реализовать обработку пагинации, если total_issues > max_results + start_at
                return issues
            except json.JSONDecodeError as json_err:
                logger.error(f"Ошибка декодирования JSON при поиске по JQL '{jql_query}': {json_err}")
                logger.error(f"Текст ответа (до 500 симв.): {response.text[:500]}")
        return []

    def get_issues_by_filter_id(self, filter_id: str, fields: list[str] | None = None, max_results_total: int = 1000) -> \
    list[dict]:
        """
        Основной метод: получает JQL для фильтра, затем получает ВСЕ задачи по этому JQL с обработкой пагинации.
        max_results_total - общее максимальное количество задач, которое мы хотим получить по этому фильтру.
        """
        jql = self.get_filter_jql(filter_id)
        if not jql:
            logger.error(f"Не удалось получить задачи, так как JQL для фильтра ID {filter_id} не был получен.")
            return []

        all_issues = []
        start_at = 0
        # Определяем размер страницы для запросов (можно взять из конфига, если есть)
        page_size = 50  # Типичный размер страницы для JIRA API

        while True:
            logger.info(
                f"Запрос страницы задач для фильтра ID {filter_id} (JQL: '{jql}'), startAt: {start_at}, pageSize: {page_size}")
            current_page_issues = self.get_issues_by_jql(jql, fields=fields, max_results=page_size, start_at=start_at)

            if not current_page_issues:  # Если страница пустая или ошибка
                logger.info(
                    f"Получена пустая страница или произошла ошибка при запросе задач для JQL: '{jql}' на startAt={start_at}.")
                break

            all_issues.extend(current_page_issues)

            if len(current_page_issues) < page_size:
                # Это была последняя страница
                logger.info(
                    f"Получена последняя страница задач (получено {len(current_page_issues)}, запрошено {page_size}).")
                break

            start_at += page_size

            if start_at >= max_results_total:
                logger.warning(
                    f"Достигнут лимит max_results_total ({max_results_total}) при получении задач по фильтру ID {filter_id}.")
                break

        logger.info(f"Всего получено {len(all_issues)} задач по фильтру ID {filter_id}.")
        return all_issues


if __name__ == '__main__':
    # Настройка логирования для теста этого модуля
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    # Для тестирования нужно загрузить реальный config и .env
    # Предполагается, что config_loader.py находится в той же директории 'src'
    try:
        from config_loader import load_config, load_environment_variables

        logger.info("Тестирование JiraClient...")
        app_cfg = load_config()  # Загрузит из ../config/config.yaml
        env_vars = load_environment_variables()  # Загрузит из ../.env

        jira_section_cfg = app_cfg.get('jira', {})
        server = jira_section_cfg.get('server_url')
        req_headers = jira_section_cfg.get('request_headers')
        cookie_str = env_vars.get('JIRA_COOKIE_STRING')
        tout = jira_section_cfg.get('timeout', 30)
        fields_to_req_test = jira_section_cfg.get('issue_fields_to_request', ['key', 'summary', 'issuetype', 'status'])

        if not server or not cookie_str:
            logger.critical("КРИТИЧНО для теста: URL JIRA или строка кук не настроены. Проверьте config.yaml и .env")
        else:
            client = JiraClient(server_url=server, headers=req_headers, cookie_string=cookie_str, timeout=tout)

            logger.info("\n--- Тест: Проверка /myself ---")
            user_info = client.check_connection_myself()
            if user_info:
                logger.info(f"Тест /myself: Успешно. Пользователь: {user_info.get('displayName')}")
            else:
                logger.error("Тест /myself: Не удалось получить информацию о пользователе.")

            logger.info("\n--- Тест: Получение задач по ID фильтра ---")
            # Используй РЕАЛЬНЫЙ ID фильтра из твоего JIRA для теста
            test_filter_id_real = "34665"  # ЗАМЕНИ НА СУЩЕСТВУЮЩИЙ ID ФИЛЬТРА

            logger.info(f"Тестируем с filter_id: {test_filter_id_real} и полями: {fields_to_req_test}")
            issues_data = client.get_issues_by_filter_id(test_filter_id_real, fields=fields_to_req_test,
                                                         max_results_total=10)  # Ограничим для теста

            if issues_data:
                logger.info(f"Тест get_issues_by_filter_id: Успешно получено {len(issues_data)} задач.")
                for i, issue_data_item in enumerate(issues_data):
                    if i >= 3:  # Выведем детали только для первых 3х задач
                        logger.info("... и другие задачи.")
                        break
                    key = issue_data_item.get('key')
                    fields_dict = issue_data_item.get('fields', {})
                    summary = fields_dict.get('summary', 'N/A')
                    issuetype_name = fields_dict.get('issuetype', {}).get('name', 'N/A')
                    status_name = fields_dict.get('status', {}).get('name', 'N/A')
                    logger.info(f"  Задача: {key} - {summary} (Тип: {issuetype_name}, Статус: {status_name})")
                    # logger.debug(f"    Raw fields for {key}: {fields_dict}") # Для детальной отладки
            else:
                logger.warning(
                    f"Тест get_issues_by_filter_id: Задачи по фильтру ID {test_filter_id_real} не найдены или произошла ошибка.")
        logger.info("Тестирование JiraClient завершено.")

    except (FileNotFoundError, ValueError) as e:
        logger.critical(f"Ошибка конфигурации при тестировании JiraClient: {e}")
    except ImportError:
        logger.error(
            "Не удалось импортировать config_loader. Убедитесь, что вы запускаете тест из корневой папки проекта или src имеет __init__.py и корень в sys.path.")
    except Exception as e:
        logger.critical(f"Неожиданная ошибка при тестировании JiraClient: {e}", exc_info=True)