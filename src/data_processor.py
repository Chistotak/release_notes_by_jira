# src/data_processor.py
import re
import logging
from datetime import datetime
from collections import defaultdict

logger = logging.getLogger(__name__)


def _extract_global_version(issues_data: list[dict], patterns: list[str]) -> str | None:
    """
    Извлекает "чистую" глобальную версию релиза из `fixVersions` задач.
    Использует первый совпавший паттерн из списка. Проверяет консистентность
    найденных версий по всем задачам.

    Args:
        issues_data (list[dict]): Список задач, полученных из JIRA.
        patterns (list[str]): Список regex-паттернов для извлечения версии.
                              Первая захватывающая группа должна содержать версию.

    Returns:
        str | None: Строка с "чистой" глобальной версией или None, если не найдена
                    или найдено несколько разных версий (с предупреждением).
    """
    if not issues_data:
        logger.debug("Нет задач для извлечения глобальной версии.")
        return None

    global_versions_found = set()
    for issue in issues_data:
        fix_versions_field = issue.get('fields', {}).get('fixVersions', [])
        if not fix_versions_field: continue

        issue_specific_gv = None
        for version_obj in fix_versions_field:
            version_name = version_obj.get('name')
            if not version_name: continue
            for pattern_str in patterns:
                match = re.match(pattern_str, version_name)
                if match and match.groups():
                    issue_specific_gv = match.group(1)
                    break
            if issue_specific_gv: break
        if issue_specific_gv:
            global_versions_found.add(issue_specific_gv)

    if not global_versions_found:
        logger.warning("Глобальная версия не найдена ни в одной из задач по заданным паттернам.")
        return None

    if len(global_versions_found) > 1:
        first_found_version = list(global_versions_found)[0]
        logger.warning(f"Найдено несколько разных глобальных версий: {global_versions_found}. "
                       f"Используется первая из найденных: {first_found_version}.")
        return first_found_version

    final_global_version = list(global_versions_found)[0]
    logger.info(f"Определена глобальная версия релиза: {final_global_version}")
    return final_global_version


def _get_raw_global_version_strings_from_issue(issue_data: dict, patterns: list[str]) -> list[str]:
    """
    Находит и возвращает список "сырых" строк глобальных версий (например, "2.3.3 (global)")
    из поля fixVersions одной задачи, которые соответствуют паттернам глобальной версии.

    Args:
        issue_data (dict): Словарь с данными одной задачи JIRA.
        patterns (list[str]): Список regex-паттернов для глобальной версии.

    Returns:
        list[str]: Список "сырых" строк глобальных версий, найденных в задаче.
    """
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
    """
    Парсит версии микросервисов из поля fixVersions одной задачи, исключая глобальные версии.

    Args:
        fix_versions_field (list[dict]): Содержимое поля fixVersions задачи.
        raw_global_version_strings_in_issue (list[str]): Список "сырых" строк глобальных версий для этой задачи.
        mv_pattern_str (str): Regex-паттерн для парсинга версий микросервисов.
        prefix_group_idx (int): Индекс группы для префикса в mv_pattern_str.
        version_group_idx (int): Индекс группы для версии в mv_pattern_str.
        service_mapping (dict): Словарь для маппинга префиксов на полные имена МС.
        global_version_patterns (list[str]): Список regex-паттернов для глобальной версии (для доп. проверки).

    Returns:
        list[tuple[str, str, str]]: Список кортежей (префикс, полное_имя_МС, версия_МС).
    """
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
            logger.debug(f"МС Парсер: Строка '{version_name_str}' пропущена (точное совпадение с raw global).")
            continue

        is_global_by_general_pattern = False
        for gv_pattern in global_version_patterns:
            if re.match(gv_pattern, version_name_str) and re.match(gv_pattern, version_name_str).groups():
                is_global_by_general_pattern = True
                break
        if is_global_by_general_pattern:
            logger.debug(f"МС Парсер: Строка '{version_name_str}' пропущена (общий паттерн global).")
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
                        f"  Распознан МС: '{service_full_name}' ({prefix}), v.{ms_version} из '{version_name_str}'")
                else:
                    logger.warning(
                        f"  Не найден маппинг для префикса МС '{prefix}' из строки '{version_name_str}'. Проверьте 'version_parsing.microservice_mapping'.")
            except IndexError:  # Должно быть покрыто проверкой len(match.groups())
                logger.warning(
                    f"  Ошибка индекса группы при парсинге '{version_name_str}' с паттерном '{mv_pattern_str}'.")
        # else:
        # logger.debug(f"МС Парсер: Строка '{version_name_str}' не соответствует паттерну МС '{mv_pattern_str}'.")
    return microservices


def _extract_field_value_for_template(field_name_or_id: str, raw_value: any) -> any:
    """
    Извлекает и форматирует значение поля JIRA для использования в плейсхолдерах шаблона.
    Возвращает None, если значение отсутствует или его представление не имеет смысла.
    """
    if raw_value is None: return None

    # Обработка стандартных полей-объектов JIRA
    if field_name_or_id == "issuetype" and isinstance(raw_value, dict): return raw_value.get("name")
    if field_name_or_id == "priority" and isinstance(raw_value, dict): return raw_value.get("name")
    if field_name_or_id == "status" and isinstance(raw_value, dict): return raw_value.get("name")
    if field_name_or_id == "resolution" and isinstance(raw_value, dict): return raw_value.get("name")
    if field_name_or_id == "assignee" and isinstance(raw_value, dict): return raw_value.get(
        "displayName") or raw_value.get("name")
    if field_name_or_id == "reporter" and isinstance(raw_value, dict): return raw_value.get(
        "displayName") or raw_value.get("name")

    if isinstance(raw_value, list):
        if not raw_value: return None
        # Не обрабатываем здесь 'fixVersions' и 'issuelinks' для основного значения шаблона,
        # они обрабатываются специально для formatted_... полей или парсинга.
        # Эта ветка для 'labels', 'components' и других списков.
        if field_name_or_id not in ["fixVersions", "issuelinks"]:
            if all(isinstance(item, dict) for item in raw_value):  # например, components
                names = [item.get('name') or item.get('value') for item in raw_value if
                         item.get('name') or item.get('value')]
                return ", ".join(names) if names else None
            elif all(isinstance(item, str) for item in raw_value):  # например, labels
                strings = [item for item in raw_value if item and item.strip()]
                return ", ".join(strings) if strings else None
            else:  # Смешанный список
                str_items = [str(item) for item in raw_value if item is not None]
                return ", ".join(str_items) if str_items else None
        else:  # Для fixVersions и issuelinks, если их кто-то вызвал через этот экстрактор, вернем None
            # так как их представление для шаблона готовится отдельно (например, formatted_issuelinks)
            # или они используются для внутренней логики в сыром виде.
            logger.debug(
                f"Поле '{field_name_or_id}' является списком, но обрабатывается отдельно, возвращаем None для простого извлечения.")
            return None  # или можно вернуть строку имен, как было раньше:
            # names = [item.get('name') for item in raw_value if isinstance(item, dict) and item.get('name')]
            # return ", ".join(names) if names else None

    if isinstance(raw_value, dict):  # Для кастомных полей-объектов
        return raw_value.get('value') or raw_value.get('name') or str(raw_value)

    return raw_value  # Для простых типов (строка, число, bool)


def process_jira_issues(issues_data: list[dict], config: dict) -> dict:
    """
    Обрабатывает список задач из JIRA и формирует структурированные данные
    для последующей генерации Release Notes.
    Исключает задачи, типы которых указаны в config.release_notes.exclude_issue_types.
    """
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
        logger.error("Паттерны для извлечения глобальной версии не найдены в config.yaml!")
    else:
        extracted_gv = _extract_global_version(issues_data, global_version_patterns)
        if extracted_gv:
            processed_data["global_version"] = extracted_gv

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
        logger.warning("Конфигурация парсинга МС неполная. Группировка по МС может не работать корректно.")

    all_microservices_in_release = {}
    jira_fields_names_to_extract = config.get('jira', {}).get('issue_fields_to_request', [])
    issuelink_project_prefixes_filter = rn_config.get('filter_issuelinks_by_project_prefixes', [])

    # --- ИЗВЛЕКАЕМ СПИСОК ТИПОВ ЗАДАЧ ДЛЯ ИСКЛЮЧЕНИЯ ---
    excluded_issue_type_names = rn_config.get('exclude_issue_types', [])
    # Для более надежного сравнения можно привести к одному регистру, если JIRA непостоянна,
    # но лучше полагаться на точное совпадение с тем, что возвращает API.
    excluded_issue_types_set = set(excluded_issue_type_names)
    if excluded_issue_types_set:
        logger.info(f"Задачи следующих типов будут исключены из обработки: {excluded_issue_types_set}")
    # --- КОНЕЦ ИЗВЛЕЧЕНИЯ СПИСКА ---

    for issue_raw_data in issues_data:
        task_key = issue_raw_data.get('key')
        if not task_key:
            logger.warning(f"Задача без ключа: {str(issue_raw_data)[:100]}... Пропуск.")
            continue
        fields_from_jira_api = issue_raw_data.get('fields', {})
        if not fields_from_jira_api:
            logger.warning(f"Задача {task_key} без 'fields'. Пропуск.")
            continue

        # --- ПРОВЕРКА И ИСКЛЮЧЕНИЕ ЗАДАЧИ ПО ТИПУ ---
        current_issue_type_name = None
        issuetype_field_data = fields_from_jira_api.get('issuetype')
        if isinstance(issuetype_field_data, dict):
            current_issue_type_name = issuetype_field_data.get('name')

        if current_issue_type_name and current_issue_type_name in excluded_issue_types_set:
            logger.info(
                f"Задача {task_key} (тип: '{current_issue_type_name}') исключена из обработки согласно конфигурации 'exclude_issue_types'.")
            continue  # Пропускаем всю дальнейшую обработку этой задачи
        # --- КОНЕЦ ПРОВЕРКИ И ИСКЛЮЧЕНИЯ ---

        logger.debug(f"Обработка полей для задачи {task_key}: '{fields_from_jira_api.get('summary', '')}'")
        task_fields_for_template = {"key": task_key}
        for field_id_from_config in jira_fields_names_to_extract:
            if field_id_from_config == "key": continue
            raw_value_from_jira = fields_from_jira_api.get(field_id_from_config)
            template_key_name = field_id_from_config
            if field_id_from_config == "issuetype":
                template_key_name = "issuetype_name"  # Это имя будет также использовано для группировки
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
            if field_id_from_config in ["issuelinks", "customfield_12902"]:
                task_fields_for_template[field_id_from_config] = raw_value_from_jira
                continue
            task_fields_for_template[template_key_name] = _extract_field_value_for_template(field_id_from_config,
                                                                                            raw_value_from_jira)

        if 'summary' not in task_fields_for_template:
            task_fields_for_template['summary'] = fields_from_jira_api.get('summary', 'Без заголовка')

        # ... (Формирование formatted_issuelinks, client_name, formatted_client_info - как в предыдущей рабочей версии) ...
        raw_issuelinks_data_for_task = task_fields_for_template.get("issuelinks")
        filtered_links_texts_list = [];
        has_relevant_filtered_links_for_this_task = False
        if isinstance(raw_issuelinks_data_for_task, list):
            for link_item in raw_issuelinks_data_for_task:
                link_type_obj = link_item.get("type", {});
                linked_issue_key_str = None;
                direction_verb_str = "";
                target_issue_obj = None
                if "outwardIssue" in link_item:
                    direction_verb_str = link_type_obj.get("outward", "~"); target_issue_obj = link_item.get(
                        "outwardIssue", {})
                elif "inwardIssue" in link_item:
                    direction_verb_str = link_type_obj.get("inward", "~"); target_issue_obj = link_item.get(
                        "inwardIssue", {})
                if target_issue_obj: linked_issue_key_str = target_issue_obj.get("key")
                if direction_verb_str and linked_issue_key_str:
                    show_this_link = not issuelink_project_prefixes_filter or \
                                     any(isinstance(p, str) and p and linked_issue_key_str.startswith(p.upper() + "-")
                                         for p in issuelink_project_prefixes_filter)
                    if show_this_link: filtered_links_texts_list.append(
                        f"{direction_verb_str.capitalize()} {linked_issue_key_str}"); has_relevant_filtered_links_for_this_task = True
        task_fields_for_template["formatted_issuelinks"] = ("Связанные задачи: " + "; ".join(
            sorted(filtered_links_texts_list))) if filtered_links_texts_list else None

        raw_client_val = task_fields_for_template.get("customfield_12902");
        client_str_to_parse = None
        if isinstance(raw_client_val, dict):
            client_str_to_parse = raw_client_val.get("value")
        elif isinstance(raw_client_val, str):
            client_str_to_parse = raw_client_val
        extracted_client_name = None
        if isinstance(client_str_to_parse, str) and client_str_to_parse.strip():
            parts = client_str_to_parse.split(" - ", 1);
            name_part = parts[0].strip()
            if "#" in name_part:
                extracted_client_name = name_part.split("#", 1)[0].strip()
            else:
                extracted_client_name = name_part
            if not extracted_client_name.strip(): extracted_client_name = None
        task_fields_for_template["client_name"] = extracted_client_name
        if extracted_client_name and has_relevant_filtered_links_for_this_task:
            task_fields_for_template["formatted_client_info"] = f"Клиент: {extracted_client_name}"
        else:
            task_fields_for_template["formatted_client_info"] = None
        # ... (Конец формирования formatted_issuelinks, client_name, formatted_client_info)

        # ... (Парсинг микросервисов и формирование linked_microservices_names - как в предыдущей рабочей версии) ...
        raw_fix_versions_list_for_parsing = fields_from_jira_api.get('fixVersions', [])
        raw_global_version_strings_for_this_issue = _get_raw_global_version_strings_from_issue(issue_raw_data,
                                                                                               global_version_patterns)
        task_microservices_parsed_list = []
        if can_parse_microservices:
            task_microservices_parsed_list = _parse_microservice_versions(
                raw_fix_versions_list_for_parsing, raw_global_version_strings_for_this_issue,
                mv_pattern, mv_prefix_idx, mv_version_idx, service_mapping, global_version_patterns
            )
        linked_ms_names_str = ", ".join(sorted(list(set(name for _, name, _ in task_microservices_parsed_list))))
        task_fields_for_template["linked_microservices_names"] = linked_ms_names_str if linked_ms_names_str else None
        # ... (Конец парсинга микросервисов)

        # ... (Распределение по секциям - как в предыдущей рабочей версии) ...
        # Важно: issuetype_name для группировки теперь берется из task_fields_for_template["issuetype_name"],
        # который уже содержит корректное имя типа (или "Неизвестный тип").
        for section_key, current_section_proc_data in processed_data["sections_data"].items():
            source_id = current_section_proc_data.get('source_custom_field_id')
            content = fields_from_jira_api.get(source_id)
            if content is not None:
                item_data_for_section = task_fields_for_template.copy()
                item_data_for_section["content"] = content
                # Гарантируем наличие ключевых полей еще раз
                for f_k_check in ["key", "summary", "issuetype_name"]:
                    if f_k_check not in item_data_for_section:
                        item_data_for_section[f_k_check] = task_fields_for_template.get(f_k_check,
                                                                                        'N/A' if f_k_check != "key" else task_key)

                if current_section_proc_data.get("disable_grouping"):
                    if not any(t.get("key") == task_key for t in current_section_proc_data.get("tasks_flat_list", [])):
                        current_section_proc_data["tasks_flat_list"].append(item_data_for_section)
                elif task_microservices_parsed_list or not can_parse_microservices:  # Условие для добавления, если есть МС или парсинг МС неактивен (для общих задач)
                    # Если парсинг МС неактивен, но группировка по МС включена, задачи могут не попасть ни в одну МС группу.
                    # Если task_microservices_parsed_list пуст (нет МС у задачи), задача не будет добавлена в группы по МС.
                    # Это поведение можно изменить, если нужно собирать задачи без МС в отдельную группу.
                    unique_ms_added_to_section_for_this_task = set()
                    for prefix, service_full_name, ms_version in task_microservices_parsed_list:
                        if (prefix, service_full_name) not in all_microservices_in_release:
                            all_microservices_in_release[(prefix, service_full_name)] = set()
                        all_microservices_in_release[(prefix, service_full_name)].add(ms_version)
                        if service_full_name not in unique_ms_added_to_section_for_this_task:
                            s_group = current_section_proc_data["microservices"][service_full_name]
                            task_type_val = item_data_for_section.get("issuetype_name",
                                                                      "Неизвестный тип")  # Используем подготовленное имя типа
                            if current_section_proc_data.get("group_by_issue_type"):
                                s_group["issue_types"][task_type_val].append(item_data_for_section)
                            else:
                                s_group["tasks_without_type_grouping"].append(item_data_for_section)
                            unique_ms_added_to_section_for_this_task.add(service_full_name)

    # ... (Формирование microservices_summary - остается) ...
    s_ms_tuples = sorted(all_microservices_in_release.items(), key=lambda i: i[0][1])
    for (p, n), v_set in s_ms_tuples:
        processed_data["microservices_summary"].append(
            {"prefix": p, "name": n, "version": ", ".join(sorted(list(v_set)))})

    logger.info("Обработка задач завершена.")
    return processed_data