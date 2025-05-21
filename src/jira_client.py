# src/jira_client.py
import requests
import json
import logging

logger = logging.getLogger(__name__)


class JiraClient:
    """
    Клиент для взаимодействия с JIRA REST API.
    Использует сессию requests для выполнения HTTP-запросов и поддерживает
    аутентификацию через Cookie.
    """

    def __init__(self, server_url: str, headers: dict | None = None, cookie_string: str | None = None,
                 timeout: int = 30):
        """
        Инициализирует JiraClient.

        Args:
            server_url (str): Базовый URL JIRA-сервера (например, "https://jira.example.com").
            headers (dict | None, optional): Дополнительные HTTP-заголовки для всех запросов.
                                             По умолчанию None.
            cookie_string (str | None, optional): Строка Cookie для аутентификации.
                                                  По умолчанию None.
            timeout (int, optional): Таймаут для HTTP-запросов в секундах.
                                     По умолчанию 30.
        """
        if not server_url:
            logger.critical("URL JIRA-сервера (server_url) не может быть пустым.")
            raise ValueError("URL JIRA-сервера не предоставлен.")

        self.server_url = server_url.rstrip('/')
        self.timeout = timeout
        self.session = requests.Session()

        default_session_headers = {
            "Accept": "application/json",
            "User-Agent": "Python Release Notes Generator (JiraClient/1.1)"
        }
        self.session.headers.update(default_session_headers)

        if headers:  # Применяем пользовательские заголовки, если они есть
            self.session.headers.update(headers)
            logger.debug(f"Пользовательские HTTP-заголовки применены: {headers}")

        if cookie_string:
            self.session.headers['Cookie'] = cookie_string
            logger.info("JiraClient: Аутентификационные Cookie установлены в сессию.")
        else:
            logger.warning("JiraClient: Строка Cookie не предоставлена. Запросы к JIRA будут неаутентифицированы.")

        logger.info(f"JiraClient инициализирован для URL: {self.server_url}")
        logger.debug(f"Итоговые заголовки сессии для запросов: {self.session.headers}")

    def _make_request(self, method: str, endpoint: str, params: dict | None = None,
                      json_data: dict | None = None) -> requests.Response | None:
        """
        Вспомогательный приватный метод для выполнения HTTP-запросов к JIRA API.

        Args:
            method (str): HTTP метод ('GET', 'POST', etc.).
            endpoint (str): Путь к API эндпоинту (например, '/rest/api/2/myself').
            params (dict | None, optional): URL-параметры для GET-запросов.
            json_data (dict | None, optional): Тело запроса в формате JSON для POST/PUT.

        Returns:
            requests.Response | None: Объект ответа requests в случае успеха (статус 2xx),
                                      иначе None.
        """
        url = f"{self.server_url}{endpoint}"
        logger.debug(f"Выполнение запроса: {method.upper()} {url}")
        if params: logger.debug(f"  Параметры URL: {params}")
        if json_data: logger.debug(f"  Тело JSON: {json_data}")

        try:
            if method.upper() == 'GET':
                response = self.session.get(url, params=params, timeout=self.timeout)
            elif method.upper() == 'POST':  # Пример для POST, если понадобится
                response = self.session.post(url, params=params, json=json_data, timeout=self.timeout)
            else:
                logger.error(f"Неподдерживаемый HTTP метод: {method.upper()} для URL: {url}")
                return None

            response.raise_for_status()  # Генерирует HTTPError для кодов 4xx/5xx
            logger.debug(f"Успешный ответ {response.status_code} от {url}")
            return response

        except requests.exceptions.HTTPError as http_err:
            logger.error(
                f"HTTP ошибка: {http_err.response.status_code} {http_err.response.reason} для {http_err.request.url}")
            # Логируем тело ответа только если оно есть и ошибка не 404 (чтобы не засорять лог при "не найдено")
            if http_err.response is not None and http_err.response.status_code != 404:
                logger.error(
                    f"  Тело ответа (первые 500 символов): {http_err.response.text[:500] if http_err.response.text else '[пустое тело ответа]'}")
        except requests.exceptions.ConnectionError as conn_err:
            logger.error(f"Ошибка соединения с {url}: {conn_err}")
        except requests.exceptions.Timeout as timeout_err:
            logger.error(f"Таймаут запроса к {url}: {timeout_err}")
        except requests.exceptions.RequestException as req_err:  # Общий класс для других ошибок requests
            logger.error(f"Ошибка выполнения запроса к {url}: {req_err}")
        return None

    def check_connection_myself(self) -> dict | None:
        """
        Проверяет соединение и аутентификацию, запрашивая информацию о текущем пользователе.
        Использует эндпоинт /rest/api/2/myself.

        Returns:
            dict | None: Словарь с данными пользователя в случае успеха, иначе None.
        """
        endpoint = "/rest/api/2/myself"
        logger.info(f"Проверка соединения и аутентификации (GET {endpoint})...")

        response = self._make_request('GET', endpoint)
        if response:
            try:
                user_data = response.json()
                logger.info(
                    f"Успешный ответ от {endpoint}. Пользователь: {user_data.get('displayName', user_data.get('name', 'Неизвестно'))}")
                return user_data
            except json.JSONDecodeError as json_err:
                logger.error(f"Ошибка декодирования JSON из ответа {endpoint}: {json_err}")
                logger.debug(
                    f"Текст ответа (первые 500 символов): {response.text[:500] if response.text else '[пустое тело ответа]'}")
        return None

    def get_filter_jql(self, filter_id: str) -> str | None:
        """
        Получает JQL-строку для существующего фильтра JIRA по его ID.
        Использует эндпоинт /rest/api/2/filter/{filter_id}.

        Args:
            filter_id (str): ID фильтра JIRA.

        Returns:
            str | None: JQL-строка в случае успеха, иначе None.
        """
        if not filter_id or not str(filter_id).strip():  # Проверяем, что filter_id не пустой
            logger.error("ID фильтра не предоставлен или пуст для get_filter_jql.")
            return None

        endpoint = f"/rest/api/2/filter/{str(filter_id).strip()}"
        logger.info(f"Запрос JQL для фильтра ID '{filter_id}' (GET {endpoint})...")

        response = self._make_request('GET', endpoint)
        if response:
            try:
                filter_data = response.json()
                jql = filter_data.get('jql')
                if jql:
                    logger.info(f"JQL для фильтра ID '{filter_id}' успешно получен.")
                    logger.debug(f"  Полученный JQL: '{jql}'")
                    return jql
                else:
                    logger.error(f"JQL не найден в ответе для фильтра ID '{filter_id}'. Ответ: {filter_data}")
            except json.JSONDecodeError as json_err:
                logger.error(f"Ошибка декодирования JSON для фильтра ID '{filter_id}': {json_err}")
                logger.debug(
                    f"Текст ответа (первые 500 символов): {response.text[:500] if response.text else '[пустое тело ответа]'}")
        return None

    def _get_issues_page_by_jql(self, jql_query: str, fields: list[str] | None = None, max_results_per_page: int = 50,
                                start_at: int = 0) -> tuple[list[dict] | None, int]:
        """
        Вспомогательная функция для получения ОДНОЙ СТРАНИЦЫ задач по JQL.
        Возвращает кортеж (список_задач_или_None, общее_количество_задач_по_JQL).
        """
        endpoint = "/rest/api/2/search"
        params = {
            'jql': jql_query,
            'maxResults': max_results_per_page,
            'startAt': start_at,
            'validateQuery': 'strict'
        }
        fields_to_request_str = "key,summary"  # Минимальный набор по умолчанию
        if fields:
            # Убедимся, что 'key' всегда запрашивается
            current_fields = set(f.strip() for f in fields if f.strip())  # Очищаем и убираем дубликаты
            current_fields.add('key')
            fields_to_request_str = ",".join(sorted(list(current_fields)))
        params['fields'] = fields_to_request_str

        logger.debug(
            f"Запрос страницы задач: JQL='{jql_query}', поля='{params['fields']}', startAt={start_at}, maxResults={max_results_per_page}")

        response = self._make_request('GET', endpoint, params=params)
        if response:
            try:
                search_results = response.json()
                issues_on_page = search_results.get('issues', [])
                total_issues_for_jql = search_results.get('total', 0)
                logger.debug(
                    f"  Получено {len(issues_on_page)} задач на странице (всего по JQL: {total_issues_for_jql}).")
                return issues_on_page, total_issues_for_jql
            except json.JSONDecodeError as json_err:
                logger.error(f"Ошибка декодирования JSON при поиске по JQL '{jql_query}': {json_err}")
                logger.debug(
                    f"Текст ответа (первые 500 символов): {response.text[:500] if response.text else '[пустое тело ответа]'}")
        return None, 0  # Возвращаем None для задач и 0 для total в случае ошибки

    def get_issues_by_filter_id(self, filter_id: str, fields: list[str] | None = None,
                                max_results_total_limit: int = 1000) -> list[dict]:
        """
        Получает все задачи из JIRA по ID фильтра, обрабатывая пагинацию,
        до достижения общего лимита max_results_total_limit.

        Args:
            filter_id (str): ID фильтра JIRA.
            fields (list[str] | None, optional): Список полей для запроса.
            max_results_total_limit (int, optional): Максимальное общее количество задач для загрузки.
                                                По умолчанию 1000.

        Returns:
            list[dict]: Список словарей, представляющих задачи JIRA.
        """
        jql = self.get_filter_jql(filter_id)
        if not jql:
            logger.error(f"Не удалось получить задачи: JQL для фильтра ID '{filter_id}' не найден.")
            return []

        all_issues_collected = []
        current_start_at = 0
        api_page_size = 50  # Размер страницы для одного API-запроса к JIRA
        # total_jql_matches = -1 # Пока не знаем общее количество

        logger.info(f"Начало загрузки задач по JQL (из фильтра ID '{filter_id}'): '{jql}'")
        while True:
            logger.info(f"Запрос страницы задач: startAt={current_start_at}, pageSize={api_page_size}")

            page_issues, total_jql_matches_on_this_call = self._get_issues_page_by_jql(
                jql,
                fields=fields,
                max_results_per_page=api_page_size,
                start_at=current_start_at
            )

            # if total_jql_matches == -1 and total_jql_matches_on_this_call > 0 : # Фиксируем общее количество при первом успешном вызове
            #     total_jql_matches = total_jql_matches_on_this_call
            #     logger.info(f"Обнаружено {total_jql_matches} задач, соответствующих JQL.")

            if page_issues is None:  # Если _get_issues_page_by_jql вернул None, значит была ошибка запроса
                logger.error(
                    f"Ошибка при запросе страницы задач для JQL: '{jql}' (startAt={current_start_at}). Прекращение загрузки.")
                break

            if not page_issues:  # Если страница пустая (нет больше задач)
                logger.info(
                    f"Получена пустая страница задач для JQL: '{jql}' (startAt={current_start_at}). Завершение пагинации.")
                break

            all_issues_collected.extend(page_issues)
            logger.info(
                f"  Получено {len(page_issues)} задач на этой странице. Всего собрано: {len(all_issues_collected)}.")

            if len(page_issues) < api_page_size:
                # Это была последняя страница (JIRA вернула меньше, чем мы запросили)
                logger.info("Это была последняя страница задач.")
                break

            current_start_at += api_page_size  # Переходим к следующей странице

            if len(all_issues_collected) >= max_results_total_limit:
                logger.warning(
                    f"Достигнут или превышен общий лимит ({max_results_total_limit}) на количество загружаемых задач. "
                    f"Собрано {len(all_issues_collected)} задач. Прекращение загрузки.")
                # Если нужно ровно max_results_total_limit, можно обрезать:
                # all_issues_collected = all_issues_collected[:max_results_total_limit]
                break

        logger.info(
            f"Итого по фильтру ID '{filter_id}' загружено {len(all_issues_collected)} задач (с учетом лимита {max_results_total_limit}).")
        return all_issues_collected