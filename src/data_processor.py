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
        # else:
        # logger.debug(f"Строка '{version_name_str}' не матчит паттерн МС '{mv_pattern_str}'.")
    return microservices


def _extract_field_value_for_template(field_name_or_id: str, raw_value: any) -> any:
    if raw_value is None: return None
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
        if not raw_value: return None  # Пустой список тоже None для шаблона, если не хотим пустые "Labels: "
        if all(isinstance(item, dict) for item in raw_value):
            return ", ".join(filter(None, [item.get('name') or item.get('value') for item in raw_value]))
        elif all(isinstance(item, str) for item in raw_value):
            return ", ".join(filter(None, raw_value))
        else:
            return ", ".join(filter(None, [str(item) for item in raw_value]))
    elif isinstance(raw_value, dict):
        return raw_value.get('value') or raw_value.get('name') or str(raw_value)
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
    if "key" not in jira_fields_names_to_extract:  # Убедимся, что key всегда запрашивается неявно, если забыли
        logger.debug("'key' не был в jira.issue_fields_to_request, добавляем его для внутренней логики.")
        # Это не добавит его в реальный запрос к JIRA, если его там нет,
        # но гарантирует, что мы попытаемся его извлечь из `fields_from_jira_api`

    for issue_raw_data in issues_data:
        task_key = issue_raw_data.get('key')  # Получаем ключ задачи из корневого уровня объекта задачи
        if not task_key:
            logger.warning(
                f"Обнаружена задача без ключа ('key') в данных от JIRA: {str(issue_raw_data)[:100]}... Пропуск.")
            continue

        fields_from_jira_api = issue_raw_data.get('fields', {})
        if not fields_from_jira_api:
            logger.warning(f"Задача {task_key} не содержит блока 'fields'. Пропуск.")
            continue

        logger.debug(f"Обработка полей для {task_key}: '{fields_from_jira_api.get('summary', '')}'")

        task_fields_for_template = {"key": task_key}  # Ключ задачи всегда добавляется
        for field_id_from_config in jira_fields_names_to_extract:
            # Пропускаем 'key', так как он уже добавлен и не находится в 'fields'
            if field_id_from_config == "key":
                continue

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

            if field_id_from_config == "issuelinks":  # Сохраняем сырые данные issuelinks
                task_fields_for_template[template_key_name] = raw_value_from_jira
                continue
            task_fields_for_template[template_key_name] = _extract_field_value_for_template(field_id_from_config,
                                                                                            raw_value_from_jira)

        if 'summary' not in task_fields_for_template:  # Гарантируем наличие summary
            task_fields_for_template['summary'] = fields_from_jira_api.get('summary', 'Без заголовка')

        raw_issuelinks_data_for_task = fields_from_jira_api.get("issuelinks")
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
                formatted_links_text_list)
        else:
            task_fields_for_template["formatted_issuelinks"] = None

        raw_global_version_strings_for_this_issue = _get_raw_global_version_strings_from_issue(issue_raw_data,
                                                                                               global_version_patterns)
        task_microservices_parsed_list = []
        if can_parse_microservices:
            task_microservices_parsed_list = _parse_microservice_versions(
                fields_from_jira_api.get('fixVersions', []),
                raw_global_version_strings_for_this_issue,
                mv_pattern, mv_prefix_idx, mv_version_idx, service_mapping, global_version_patterns
            )
        linked_ms_names_str = ", ".join(sorted(list(set(name for _, name, _ in task_microservices_parsed_list))))
        task_fields_for_template["linked_microservices_names"] = linked_ms_names_str if linked_ms_names_str else None

        for section_key, current_section_proc_data in processed_data["sections_data"].items():
            source_cf_id = current_section_proc_data.get('source_custom_field_id')
            main_content = fields_from_jira_api.get(source_cf_id)
            if main_content is not None:
                task_data_for_section_item = task_fields_for_template.copy()
                task_data_for_section_item["content"] = main_content
                # Гарантируем базовые поля еще раз, на всякий случай если они не пришли из task_fields_for_template
                # (хотя должны были, если 'key' и 'summary' всегда есть)
                if "key" not in task_data_for_section_item: task_data_for_section_item["key"] = task_key
                if "summary" not in task_data_for_section_item: task_data_for_section_item[
                    "summary"] = task_fields_for_template.get('summary', 'N/A')
                if "issuetype_name" not in task_data_for_section_item: task_data_for_section_item[
                    "issuetype_name"] = task_fields_for_template.get('issuetype_name', 'N/A')

                if current_section_proc_data.get("disable_grouping"):
                    is_already_added = any(
                        t.get("key") == task_key for t in current_section_proc_data.get("tasks_flat_list", []))
                    if not is_already_added:
                        current_section_proc_data["tasks_flat_list"].append(task_data_for_section_item)
                        logger.debug(f"Задача {task_key} добавлена в плоский список секции '{section_key}'.")
                elif task_microservices_parsed_list:
                    unique_microservices_for_task_in_section = set()  # Для избежания дублирования задачи в одной секции под разными МС, если она привязана к одному МС несколько раз (нетипично)
                    for prefix, service_full_name, ms_version in task_microservices_parsed_list:
                        if (prefix, service_full_name) not in all_microservices_in_release:
                            all_microservices_in_release[(prefix, service_full_name)] = set()
                        all_microservices_in_release[(prefix, service_full_name)].add(ms_version)

                        if service_full_name not in unique_microservices_for_task_in_section:
                            service_group = current_section_proc_data["microservices"][service_full_name]
                            task_type = task_data_for_section_item.get("issuetype_name", "Неизвестный тип")
                            if current_section_proc_data.get("group_by_issue_type"):
                                service_group["issue_types"][task_type].append(task_data_for_section_item)
                            else:
                                service_group["tasks_without_type_grouping"].append(task_data_for_section_item)
                            unique_microservices_for_task_in_section.add(service_full_name)
                            logger.debug(
                                f"Задача {task_key} добавлена в '{section_key}' (групп. по МС) для МС '{service_full_name}'.")

    sorted_ms_tuples = sorted(all_microservices_in_release.items(), key=lambda item: item[0][1])
    for (prefix, name), version_set in sorted_ms_tuples:
        version_str = ", ".join(sorted(list(version_set)))
        processed_data["microservices_summary"].append({"prefix": prefix, "name": name, "version": version_str})

    logger.info("Обработка задач завершена.")
    return processed_data


# Блок if __name__ == '__main__': остается таким же, как в предыдущей полной версии data_processor.py.
# Убедитесь, что mock_config_for_dp_test["jira"]["issue_fields_to_request"] содержит "key".
if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    mock_config_for_dp_test = {
        "jira": {
            "issue_fields_to_request": [
                "key", "summary", "issuetype", "priority", "assignee", "reporter",
                "created", "updated", "labels", "components", "status", "resolution",
                "fixVersions", "customfield_10400", "customfield_12001", "issuelinks"
            ]
        },
        "release_notes": {
            "date_format": "%d.%m.%Y",
            "sections": {
                "changes": {"title": "Изменения", "source_custom_field_id": "customfield_10400",
                            "group_by_issue_type": True, "disable_grouping": False},
                "install_guide": {"title": "Инструкция", "source_custom_field_id": "customfield_12001",
                                  "group_by_issue_type": False, "disable_grouping": False},
                "all_flat": {"title": "Все задачи плоско", "source_custom_field_id": "customfield_10400",
                             "disable_grouping": True}
            }
        },
        "version_parsing": {
            "global_version": {"extraction_patterns": ['^(.*?)\\s*\\(global\\)$', '^(\\d+\\.\\d+\\.\\d+)$']},
            "microservice_version": {"extraction_pattern": '^([A-Z]+)(\\d+\\.\\d+\\.\\d+(?:-[A-Za-z0-9_]+)*)$',
                                     "prefix_group_index": 1, "version_group_index": 2},
            "microservice_mapping": {"IN": "Integration Service", "AUTH": "Auth Service", "CORE": "Core Platform"}
        }
    }
    mock_issues_data_for_dp_test = [
        {"key": "PROJ-101", "fields": {"summary": "Func X", "issuetype": {"name": "Story"},
                                       "fixVersions": [{"name": "2.5.0 (global)"}, {"name": "IN2.5.0"}],
                                       "customfield_10400": "Desc X.", "issuelinks": [
                {"id": "101", "type": {"outward": "blocks"}, "outwardIssue": {"key": "PROJ-200"}}]}},
        {"key": "PROJ-102",
         "fields": {"summary": "Bug Y", "issuetype": {"name": "Bug"}, "fixVersions": [{"name": "IN2.5.1"}],
                    "customfield_10400": "Desc Y."}},
        {"key": "PROJ-103",
         "fields": {"summary": "No key task in fields, but has root key", "fixVersions": [{"name": "CORE1.0.0"}],
                    "customfield_10400": "Content 103"}},  # Пример без key в fields
        {"key": None, "fields": {"summary": "Task with None key at root", "fixVersions": [{"name": "CORE1.0.1"}],
                                 "customfield_10400": "Content NoneKey"}}  # Пример с None key на верхнем уровне
    ]
    logger.info("Запуск тестовой обработки data_processor...")
    processed_result = process_jira_issues(mock_issues_data_for_dp_test, mock_config_for_dp_test)
    import json

    print("\n--- Результат обработки data_processor (JSON) ---")
    print(json.dumps(processed_result, indent=2, ensure_ascii=False))

    # Проверка, что PROJ-101 имеет ключ
    proj101_data_ch = next(t for t_list in
                           processed_result["sections_data"]["changes"]["microservices"]["Integration Service"][
                               "issue_types"].values() for t in t_list if t["key"] == "PROJ-101")
    assert proj101_data_ch["key"] == "PROJ-101"
    assert "Связанные задачи: Blocks PROJ-200" in proj101_data_ch["formatted_issuelinks"]

    # Проверка, что PROJ-103 (без key в fields, но есть на верхнем уровне) обработался и есть ключ
    proj103_data_ch = next(t for t_list in
                           processed_result["sections_data"]["changes"]["microservices"]["Core Platform"][
                               "issue_types"].values() for t in t_list if
                           t.get("summary") == "No key task in fields, but has root key")
    assert proj103_data_ch["key"] == "PROJ-103"

    # Проверка плоского списка
    assert len(processed_result["sections_data"]["all_flat"][
                   "tasks_flat_list"]) >= 2  # PROJ-101, PROJ-102, PROJ-103 (если у них есть customfield_10400)
    flat_proj101 = next(
        t for t in processed_result["sections_data"]["all_flat"]["tasks_flat_list"] if t["key"] == "PROJ-101")
    assert flat_proj101["key"] == "PROJ-101"

    logger.info("Тестовая обработка data_processor завершена.")