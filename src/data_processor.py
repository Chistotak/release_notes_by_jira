# src/data_processor.py
import re
import logging
from datetime import datetime
from collections import defaultdict

logger = logging.getLogger(__name__)


def _extract_global_version(issues_data: list[dict], patterns: list[str]) -> str | None:
    if not issues_data:
        logger.debug("Нет задач для извлечения глобальной версии.")
        return None
    global_versions_found_in_issues = set()
    for issue in issues_data:
        fix_versions_field = issue.get('fields', {}).get('fixVersions', [])
        if not fix_versions_field: continue
        current_issue_global_version = None
        for version_obj in fix_versions_field:
            version_name = version_obj.get('name')
            if not version_name: continue
            for pattern_str in patterns:
                match = re.match(pattern_str, version_name)
                if match and match.groups():
                    current_issue_global_version = match.group(1)
                    break
            if current_issue_global_version: break
        if current_issue_global_version:
            global_versions_found_in_issues.add(current_issue_global_version)
    if not global_versions_found_in_issues:
        logger.warning("Глобальная версия не найдена ни в одной из задач по заданным паттернам.")
        return None
    if len(global_versions_found_in_issues) > 1:
        logger.warning(
            f"Найдено несколько разных глобальных версий: {global_versions_found_in_issues}. Используется первая: {list(global_versions_found_in_issues)[0]}.")
        return list(global_versions_found_in_issues)[0]
    final_global_version = list(global_versions_found_in_issues)[0]
    logger.info(f"Определена глобальная версия релиза: {final_global_version}")
    return final_global_version


def _get_raw_global_version_strings_from_issue(issue_data: dict, patterns: list[str]) -> list[str]:
    raw_global_strings = []
    fix_versions_field = issue_data.get('fields', {}).get('fixVersions', [])
    if not fix_versions_field: return raw_global_strings
    for version_obj in fix_versions_field:
        version_name = version_obj.get('name')
        if not version_name: continue
        for pattern_str in patterns:
            match = re.match(pattern_str, version_name)
            if match and match.groups():
                raw_global_strings.append(version_name)
                break
    return raw_global_strings


def _parse_microservice_versions(
        fix_versions_field: list[dict],
        raw_global_version_strings_in_issue: list[str],
        mv_pattern_str: str,
        prefix_group_idx: int,
        version_group_idx: int,
        service_mapping: dict,
        global_version_patterns: list[str]
) -> list[tuple[str, str, str]]:
    microservices = []
    if not fix_versions_field: return microservices
    try:
        mv_regex = re.compile(mv_pattern_str)
    except re.error as e:
        logger.error(f"Ошибка компиляции regex для МС '{mv_pattern_str}': {e}")
        return microservices
    for version_obj in fix_versions_field:
        version_name_str = version_obj.get('name')
        if not version_name_str: continue
        if version_name_str in raw_global_version_strings_in_issue:
            logger.debug(f"Строка '{version_name_str}' пропущена (raw global).")
            continue
        is_global_by_general_pattern = False
        for gv_pattern in global_version_patterns:
            if re.match(gv_pattern, version_name_str) and re.match(gv_pattern, version_name_str).groups():
                is_global_by_general_pattern = True
                break
        if is_global_by_general_pattern:
            logger.debug(f"Строка '{version_name_str}' пропущена (общий паттерн global).")
            continue
        match = mv_regex.match(version_name_str)
        if match and len(match.groups()) >= max(prefix_group_idx, version_group_idx):
            try:
                prefix = match.group(prefix_group_idx)
                ms_version = match.group(version_group_idx)
                service_full_name = service_mapping.get(prefix)
                if service_full_name:
                    microservices.append((prefix, service_full_name, ms_version))
                    logger.debug(
                        f"Распознан МС: '{service_full_name}' ({prefix}), v.{ms_version} из '{version_name_str}'")
                else:
                    logger.warning(f"Нет маппинга для префикса МС '{prefix}' из '{version_name_str}'.")
            except IndexError:
                logger.warning(f"Ошибка индекса группы при парсинге '{version_name_str}' с '{mv_pattern_str}'")
    return microservices


def _extract_field_value_for_template(field_name_or_id: str, raw_value: any) -> any:
    """
    Извлекает и форматирует значение поля для использования в плейсхолдерах шаблона.
    Возвращает None, если значение отсутствует или не может быть meaningfully представлено.
    """
    if raw_value is None:
        return None

        # Специальная обработка для стандартных полей JIRA, которые часто являются объектами
    if field_name_or_id == "issuetype" and isinstance(raw_value, dict):
        return raw_value.get("name")
    elif field_name_or_id == "priority" and isinstance(raw_value, dict):
        return raw_value.get("name")
    elif field_name_or_id == "status" and isinstance(raw_value, dict):
        return raw_value.get("name")
    elif field_name_or_id == "resolution" and isinstance(raw_value, dict):
        return raw_value.get("name")
    elif field_name_or_id == "assignee" and isinstance(raw_value, dict):
        return raw_value.get("displayName") or raw_value.get("name")
    elif field_name_or_id == "reporter" and isinstance(raw_value, dict):
        return raw_value.get("displayName") or raw_value.get("name")
    elif isinstance(raw_value, list):
        if not raw_value:  # Пустой список
            return None

            # Для fixVersions мы хотим сохранить список объектов для дальнейшего парсинга,
        # но если кто-то захочет использовать {fixVersions} в шаблоне, вернем строку имен.
        # Однако, основная логика парсинга версий должна использовать сырой список.
        # Поэтому, если это поле не 'fixVersions', то обрабатываем как раньше.
        if field_name_or_id != "fixVersions":  # Для labels, components и других списков (кроме fixVersions)
            if all(isinstance(item, dict) for item in raw_value):
                # Список словарей (например, components)
                names = [item.get('name') or item.get('value') for item in raw_value if
                         item.get('name') or item.get('value')]
                return ", ".join(names) if names else None
            elif all(isinstance(item, str) for item in raw_value):
                # Список строк (например, labels)
                return ", ".join(item for item in raw_value if item) if any(raw_value) else None
            else:
                # Смешанный список или список других типов - просто преобразуем в строки
                str_items = [str(item) for item in raw_value if item is not None]
                return ", ".join(str_items) if str_items else None
        else:  # Если это fixVersions, возвращаем сырой список (он будет обработан отдельно)
            # Но если кто-то использует {fixVersions} в шаблоне, это вернет список.
            # Лучше для шаблона {fixVersions} тоже возвращать строку имен.
            names = [item.get('name') for item in raw_value if isinstance(item, dict) and item.get('name')]
            return ", ".join(names) if names else None

    elif isinstance(raw_value, dict):  # Для кастомных полей-объектов или других
        return raw_value.get('value') or raw_value.get('name') or str(raw_value)

        # Для простых типов (строка, число, булево)
    return raw_value


def process_jira_issues(issues_data: list[dict], config: dict) -> dict:
    logger.info(f"Начало обработки {len(issues_data)} задач...")
    rn_config = config.get('release_notes', {})
    processed_data = {
        "global_version": "N/A",
        "current_date": datetime.now().strftime(rn_config.get('date_format', '%Y-%m-%d')),
        "microservices_summary": [],
        "sections_data": {}
    }

    version_cfg = config.get('version_parsing', {})
    global_version_patterns = version_cfg.get('global_version', {}).get('extraction_patterns', [])
    if not global_version_patterns:
        logger.error("Паттерны глоб. версии не найдены в config!")
    else:
        extracted_gv = _extract_global_version(issues_data, global_version_patterns)
        if extracted_gv: processed_data["global_version"] = extracted_gv

    configured_sections_from_yaml = rn_config.get('sections', {})
    for section_key, section_config_yaml in configured_sections_from_yaml.items():
        is_grouping_disabled = section_config_yaml.get("disable_grouping", False)
        group_by_type_flag = section_config_yaml.get("group_by_issue_type",
                                                     False) if not is_grouping_disabled else False
        section_structure = {
            "title": section_config_yaml.get("title", section_key.replace("_", " ").title()),
            "source_custom_field_id": section_config_yaml.get("source_custom_field_id"),
            "disable_grouping": is_grouping_disabled,
            "group_by_issue_type": group_by_type_flag,
        }
        if is_grouping_disabled:
            section_structure["tasks_flat_list"] = []
        else:
            section_structure["microservices"] = defaultdict(
                lambda: {"issue_types": defaultdict(list), "tasks_without_type_grouping": []})
        processed_data["sections_data"][section_key] = section_structure

    mv_config = version_cfg.get('microservice_version', {})
    mv_pattern = mv_config.get('extraction_pattern')
    mv_prefix_idx = mv_config.get('prefix_group_index')
    mv_version_idx = mv_config.get('version_group_index')
    service_mapping = version_cfg.get('microservice_mapping', {})
    can_parse_microservices = all([mv_pattern, mv_prefix_idx is not None, mv_version_idx is not None, service_mapping])
    if not can_parse_microservices:
        logger.error("Конфигурация парсинга МС неполная. Группировка по МС не будет работать.")

    all_microservices_in_release = {}
    jira_fields_names_to_extract = config.get('jira', {}).get('issue_fields_to_request', [])

    for issue_raw_data in issues_data:
        task_key = issue_raw_data.get('key')
        if not task_key:
            logger.warning(f"Задача без ключа: {str(issue_raw_data)[:100]}... Пропуск.")
            continue
        fields_from_jira_api = issue_raw_data.get('fields', {})
        if not fields_from_jira_api:
            logger.warning(f"Задача {task_key} без 'fields'. Пропуск.")
            continue

        logger.debug(f"Обработка полей для {task_key}: '{fields_from_jira_api.get('summary', '')}'")
        task_fields_for_template = {"key": task_key}  # Ключ задачи всегда добавляется

        for field_id_from_config in jira_fields_names_to_extract:
            if field_id_from_config == "key": continue  # Уже добавили

            raw_value_from_jira = fields_from_jira_api.get(field_id_from_config)
            template_key_name = field_id_from_config

            if field_id_from_config == "issuetype":
                template_key_name = "issuetype_name"
            elif field_id_from_config == "priority":
                template_key_name = "priority_name"
            elif field_id_from_config == "assignee":
                template_key_name = "assignee_name"
            elif field_id_from_config == "reporter":
                template_key_name = "reporter_name"
            elif field_id_from_config == "status":
                template_key_name = "status_name"
            elif field_id_from_config == "resolution":
                template_key_name = "resolution_name"

            # Для issuelinks и fixVersions мы хотим сохранить СЫРЫЕ данные (список объектов)
            # под их оригинальными именами для внутренней обработки, если они запрошены.
            # _extract_field_value_for_template вернет строку для них, если кто-то захочет их в шаблон.
            if field_id_from_config == "issuelinks" or field_id_from_config == "fixVersions":
                task_fields_for_template[template_key_name] = raw_value_from_jira
                # Если нужно и отформатированное значение для прямого использования в шаблоне:
                if field_id_from_config == "fixVersions":
                    task_fields_for_template["fixVersions_names"] = _extract_field_value_for_template(
                        field_id_from_config, raw_value_from_jira)
                # Для issuelinks форматирование идет в formatted_issuelinks ниже
                continue

            task_fields_for_template[template_key_name] = _extract_field_value_for_template(field_id_from_config,
                                                                                            raw_value_from_jira)

        if 'summary' not in task_fields_for_template:  # Гарантируем наличие summary
            task_fields_for_template['summary'] = fields_from_jira_api.get('summary', 'Без заголовка')

        # --- Формирование formatted_issuelinks ---
        # Используем сырые данные из task_fields_for_template, если "issuelinks" был в запрошенных полях
        raw_issuelinks_data_for_task = task_fields_for_template.get("issuelinks")
        formatted_links_text_list = []
        if isinstance(raw_issuelinks_data_for_task, list):
            for link_item in raw_issuelinks_data_for_task:
                link_type_obj = link_item.get("type", {})
                linked_issue_key_str = None
                direction_verb_str = ""
                if "outwardIssue" in link_item:
                    direction_verb_str = link_type_obj.get("outward", "связана с")
                    linked_issue_obj = link_item.get("outwardIssue", {})
                    linked_issue_key_str = linked_issue_obj.get("key")
                elif "inwardIssue" in link_item:
                    direction_verb_str = link_type_obj.get("inward", "связана с")
                    linked_issue_obj = link_item.get("inwardIssue", {})
                    linked_issue_key_str = linked_issue_obj.get("key")
                if direction_verb_str and linked_issue_key_str:
                    formatted_links_text_list.append(f"{direction_verb_str.capitalize()} {linked_issue_key_str}")

        if formatted_links_text_list:
            task_fields_for_template["formatted_issuelinks"] = "Связанные задачи: " + "; ".join(
                sorted(formatted_links_text_list))  # Сортируем для порядка
        else:
            task_fields_for_template["formatted_issuelinks"] = None

            # --- Формирование client_name и formatted_client_info ---
        # Используем сырые данные из task_fields_for_template, если "customfield_12902" был в запрошенных полях
        client_contract_full_string = task_fields_for_template.get("customfield_12902")
        client_name_extracted = None

        logger.debug(
            f"Для задачи {task_key}: Попытка извлечь имя клиента из customfield_12902: '{client_contract_full_string}'")
        if isinstance(client_contract_full_string, str) and client_contract_full_string.strip():
            # Сначала пытаемся отсечь всё после " - " если он есть
            parts_by_hyphen = client_contract_full_string.split(" - ", 1)
            potential_client_name_part = parts_by_hyphen[0].strip()
            logger.debug(f"  Часть до ' - ' (или вся строка): '{potential_client_name_part}'")

            # Теперь в этой части ищем "#"
            if "#" in potential_client_name_part:
                client_name_extracted = potential_client_name_part.split("#", 1)[0].strip()
                logger.debug(f"    Отсекли по '#', результат: '{client_name_extracted}'")
            else:
                # Если '#' не было в этой части, то эта часть и есть имя клиента
                client_name_extracted = potential_client_name_part
                logger.debug(
                    f"    Символ '#' не найден в '{potential_client_name_part}', используем ее как имя: '{client_name_extracted}'")

            # Если после всех манипуляций осталась пустая строка, считаем, что имя не извлечено
            if not client_name_extracted.strip():
                client_name_extracted = None
                logger.debug(f"    Имя клиента после очистки оказалось пустым, сброшено в None.")
        else:
            logger.debug(f"  Строка customfield_12902 пустая, None или не строка. Имя клиента не будет извлечено.")

        task_fields_for_template["client_name"] = client_name_extracted
        logger.debug(f"  Итоговое client_name для шаблона: {task_fields_for_template['client_name']}")

        if client_name_extracted:  # Проверяем, что не None и не пустая строка (strip уже был)
            task_fields_for_template["formatted_client_info"] = f"Клиент: {client_name_extracted}"
        else:
            task_fields_for_template["formatted_client_info"] = None
        logger.debug(f"  formatted_client_info для шаблона: {task_fields_for_template['formatted_client_info']}")

        # --- Парсинг микросервисов ---
        # Используем СЫРОЙ список объектов fixVersions из fields_from_jira_api
        raw_fix_versions_list = fields_from_jira_api.get('fixVersions', [])
        raw_global_version_strings_for_this_issue = _get_raw_global_version_strings_from_issue(issue_raw_data,
                                                                                               global_version_patterns)

        task_microservices_parsed_list = []
        if can_parse_microservices:
            task_microservices_parsed_list = _parse_microservice_versions(
                raw_fix_versions_list,  # Передаем сырой список объектов
                raw_global_version_strings_for_this_issue,
                mv_pattern, mv_prefix_idx, mv_version_idx, service_mapping, global_version_patterns
            )
        linked_ms_names_str = ", ".join(sorted(list(set(name for _, name, _ in task_microservices_parsed_list))))
        task_fields_for_template["linked_microservices_names"] = linked_ms_names_str if linked_ms_names_str else None

        # --- Распределение по секциям ---
        for section_key, current_section_proc_data in processed_data["sections_data"].items():
            source_cf_id = current_section_proc_data.get('source_custom_field_id')
            main_content = fields_from_jira_api.get(source_cf_id)  # Берем контент из сырых полей JIRA

            if main_content is not None:
                item_data_for_section = task_fields_for_template.copy()  # Копируем все собранные поля
                item_data_for_section["content"] = main_content  # Добавляем специфичный для секции {content}

                # Гарантируем наличие базовых полей еще раз, на всякий случай
                if "key" not in item_data_for_section: item_data_for_section["key"] = task_key
                if "summary" not in item_data_for_section: item_data_for_section[
                    "summary"] = task_fields_for_template.get('summary', 'N/A')
                if "issuetype_name" not in item_data_for_section: item_data_for_section[
                    "issuetype_name"] = task_fields_for_template.get('issuetype_name', 'N/A')

                if current_section_proc_data.get("disable_grouping"):
                    # Проверка на дублирование для плоского списка
                    if not any(t.get("key") == task_key for t in current_section_proc_data.get("tasks_flat_list", [])):
                        current_section_proc_data["tasks_flat_list"].append(item_data_for_section)
                        logger.debug(f"Задача {task_key} добавлена в плоский список секции '{section_key}'.")
                elif task_microservices_parsed_list:  # Группировка включена И есть МС у задачи
                    unique_ms_added_to_section_for_this_task = set()
                    for prefix, service_full_name, ms_version in task_microservices_parsed_list:
                        # Обновляем all_microservices_in_release
                        if (prefix, service_full_name) not in all_microservices_in_release:
                            all_microservices_in_release[(prefix, service_full_name)] = set()
                        all_microservices_in_release[(prefix, service_full_name)].add(ms_version)

                        # Добавляем задачу в секцию под этим МС только один раз
                        if service_full_name not in unique_ms_added_to_section_for_this_task:
                            service_group_in_section = current_section_proc_data["microservices"][service_full_name]
                            task_type_for_grouping = item_data_for_section.get("issuetype_name", "Неизвестный тип")

                            if current_section_proc_data.get("group_by_issue_type"):
                                service_group_in_section["issue_types"][task_type_for_grouping].append(
                                    item_data_for_section)
                            else:
                                service_group_in_section["tasks_without_type_grouping"].append(item_data_for_section)
                            unique_ms_added_to_section_for_this_task.add(service_full_name)
                            logger.debug(
                                f"Задача {task_key} добавлена в '{section_key}' (групп. по МС) для МС '{service_full_name}'.")

    # --- Формирование итогового списка микросервисов для summary ---
    sorted_ms_tuples = sorted(all_microservices_in_release.items(),
                              key=lambda i: i[0][1])  # Сортировка по полному имени МС
    for (prefix, name), version_set in sorted_ms_tuples:
        version_str = ", ".join(sorted(list(version_set)))  # Версии внутри одного МС тоже сортируем
        processed_data["microservices_summary"].append({"prefix": prefix, "name": name, "version": version_str})

    logger.info("Обработка задач завершена.")
    return processed_data


# Блок if __name__ == '__main__' (для тестирования)
if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s [%(levelname)s] %(name)s: %(message)s')
    mock_config = {
        "jira": {
            "issue_fields_to_request": ["key", "summary", "issuetype", "fixVersions", "customfield_10400", "issuelinks",
                                        "customfield_12902"]},
        "release_notes": {"sections": {
            "changes": {"title": "Изменения", "source_custom_field_id": "customfield_10400",
                        "group_by_issue_type": True, "disable_grouping": False},
        }},
        "version_parsing": {
            "global_version": {"extraction_patterns": ['^(.*?)\\s*\\(global\\)$']},
            "microservice_version": {"extraction_pattern": '^([A-Z]+)(\\d+\\.\\d+)$', "prefix_group_index": 1,
                                     "version_group_index": 2},
            "microservice_mapping": {"IN": "Integration", "AUTH": "Auth"}
        }
    }
    mock_issues = [
        {"key": "T1", "fields": {
            "summary": "S1", "issuetype": {"name": "Story"},
            "fixVersions": [{"name": "1.0 (global)"}, {"name": "IN1.0"}],
            "customfield_10400": "C1",
            "customfield_12902": "Client A #1 - Details",  # <-- Сработает отсечение по #
            "issuelinks": [{"type": {"outward": "blocks"}, "outwardIssue": {"key": "T2"}}]
        }},
        {"key": "T2", "fields": {
            "summary": "S2", "issuetype": {"name": "Bug"},
            "fixVersions": [{"name": "IN1.0"}],
            "customfield_10400": "C2",
            "customfield_12902": "Client B - Details"  # <-- Сработает отсечение по " - "
        }},
        {"key": "T3", "fields": {
            "summary": "S3", "issuetype": {"name": "Task"},
            "fixVersions": [{"name": "AUTH1.1"}],
            "customfield_10400": "C3",
            "customfield_12902": "Client C"  # <-- Нет разделителей, возьмется вся строка
        }},
        {"key": "T4", "fields": {
            "summary": "S4", "issuetype": {"name": "Task"},
            "fixVersions": [{"name": "AUTH1.1"}],
            "customfield_10400": "C4",
            "customfield_12902": "#Client D with leading hash"
            # <-- Должен извлечь пустую строку, formatted_client_info будет None
        }},
        {"key": "T5", "fields": {
            "summary": "S5", "issuetype": {"name": "Task"},
            "fixVersions": [{"name": "AUTH1.1"}],
            "customfield_10400": "C5",
            "customfield_12902": None  # <-- None значение
        }}
    ]
    logger.info("Тест data_processor (formatted_client_info)...")
    result = process_jira_issues(mock_issues, mock_config)
    import json;

    # print(json.dumps(result, indent=2, ensure_ascii=False)) # Раскомментируй для полного вывода

    # Проверка client_name и formatted_client_info
    changes_section_data = result["sections_data"]["changes"]

    tasks_in_IN_story = changes_section_data["microservices"]["Integration"]["issue_types"]["Story"]
    task1_data = next(t for t in tasks_in_IN_story if t["key"] == "T1")
    assert task1_data["client_name"] == "Client A", f"T1 client_name: {task1_data['client_name']}"
    assert task1_data[
               "formatted_client_info"] == "Клиент: Client A", f"T1 formatted_client_info: {task1_data['formatted_client_info']}"

    tasks_in_IN_bug = changes_section_data["microservices"]["Integration"]["issue_types"]["Bug"]
    task2_data = next(t for t in tasks_in_IN_bug if t["key"] == "T2")
    assert task2_data["client_name"] == "Client B", f"T2 client_name: {task2_data['client_name']}"
    assert task2_data[
               "formatted_client_info"] == "Клиент: Client B", f"T2 formatted_client_info: {task2_data['formatted_client_info']}"

    tasks_in_AUTH_task = changes_section_data["microservices"]["Auth"]["issue_types"]["Task"]
    task3_data = next(t for t in tasks_in_AUTH_task if t["key"] == "T3")
    assert task3_data["client_name"] == "Client C", f"T3 client_name: {task3_data['client_name']}"
    assert task3_data[
               "formatted_client_info"] == "Клиент: Client C", f"T3 formatted_client_info: {task3_data['formatted_client_info']}"

    task4_data = next(t for t in tasks_in_AUTH_task if t["key"] == "T4")
    assert task4_data["client_name"] is None, f"T4 client_name: {task4_data['client_name']}"  # После "#" ничего нет
    assert task4_data[
               "formatted_client_info"] is None, f"T4 formatted_client_info: {task4_data['formatted_client_info']}"

    task5_data = next(t for t in tasks_in_AUTH_task if t["key"] == "T5")
    assert task5_data["client_name"] is None, f"T5 client_name: {task5_data['client_name']}"
    assert task5_data[
               "formatted_client_info"] is None, f"T5 formatted_client_info: {task5_data['formatted_client_info']}"

    logger.info("Тест data_processor (formatted_client_info) завершен.")