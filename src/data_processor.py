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

    Args:
        issues_data (list[dict]): Список "сырых" данных задач из JIRA.
        config (dict): Полная конфигурация приложения.

    Returns:
        dict: Словарь с обработанными и структурированными данными.
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
    mv_pattern = mv_config.get('extraction_pattern');
    mv_prefix_idx = mv_config.get('prefix_group_index');
    mv_version_idx = mv_config.get('version_group_index')
    service_mapping = version_cfg.get('microservice_mapping', {});
    can_parse_microservices = all([mv_pattern, mv_prefix_idx is not None, mv_version_idx is not None, service_mapping])
    if not can_parse_microservices: logger.warning(
        "Конфигурация парсинга МС неполная. Группировка по МС может не работать корректно.")

    all_microservices_in_release = {}
    jira_fields_to_extract_config = config.get('jira', {}).get('issue_fields_to_request', [])
    issuelink_project_prefixes_filter = rn_config.get('filter_issuelinks_by_project_prefixes', [])
    logger.debug(
        f"Фильтр для issuelinks по префиксам: {issuelink_project_prefixes_filter if issuelink_project_prefixes_filter else '(нет, показывать все)'}")

    for issue_raw in issues_data:
        task_key = issue_raw.get('key')
        if not task_key: logger.warning(f"Задача без ключа: {str(issue_raw)[:100]}... Пропуск."); continue
        jira_task_fields = issue_raw.get('fields', {})
        if not jira_task_fields: logger.warning(f"Задача {task_key} без 'fields'. Пропуск."); continue

        logger.debug(f"Обработка полей для задачи {task_key}: '{jira_task_fields.get('summary', '')}'")
        # Собираем все поля, которые могут понадобиться для шаблонов или внутренней логики
        template_ready_fields = {"key": task_key}
        for field_id in jira_fields_to_extract_config:
            if field_id == "key": continue
            raw_jira_value = jira_task_fields.get(field_id)
            template_field_name = field_id
            # Преобразование имен стандартных полей для удобства в шаблонах
            if field_id == "issuetype":
                template_field_name = "issuetype_name"
            elif field_id == "priority":
                template_field_name = "priority_name"
            elif field_id == "assignee":
                template_field_name = "assignee_name"
            elif field_id == "reporter":
                template_field_name = "reporter_name"
            elif field_id == "status":
                template_field_name = "status_name"
            elif field_id == "resolution":
                template_field_name = "resolution_name"

            # Сырые данные для 'issuelinks' и 'customfield_12902' сохраняем под их оригинальными ID.
            # Отформатированные версии ('formatted_issuelinks', 'client_name', 'formatted_client_info')
            # будут созданы ниже и добавлены в template_ready_fields.
            if field_id in ["issuelinks", "customfield_12902"]:
                template_ready_fields[field_id] = raw_jira_value
                continue  # Пропускаем _extract_field_value_for_template для них здесь
            template_ready_fields[template_field_name] = _extract_field_value_for_template(field_id, raw_jira_value)

        if 'summary' not in template_ready_fields:  # Гарантируем наличие summary
            template_ready_fields['summary'] = jira_task_fields.get('summary', 'Без заголовка')

        # Формирование {formatted_issuelinks}
        raw_links = template_ready_fields.get("issuelinks")
        filtered_link_texts = [];
        has_relevant_links = False
        if isinstance(raw_links, list):
            for link in raw_links:
                link_type = link.get("type", {});
                l_key = None;
                verb = "";
                target_issue = None
                if "outwardIssue" in link:
                    verb = link_type.get("outward", "~"); target_issue = link.get("outwardIssue", {})
                elif "inwardIssue" in link:
                    verb = link_type.get("inward", "~"); target_issue = link.get("inwardIssue", {})
                if target_issue: l_key = target_issue.get("key")
                if verb and l_key:
                    show = not issuelink_project_prefixes_filter or \
                           any(isinstance(p, str) and p and l_key.startswith(p.upper() + "-") for p in
                               issuelink_project_prefixes_filter)
                    if show: filtered_link_texts.append(f"{verb.capitalize()} {l_key}"); has_relevant_links = True
        template_ready_fields["formatted_issuelinks"] = (
                    "Связанные задачи: " + "; ".join(sorted(filtered_link_texts))) if filtered_link_texts else None
        logger.debug(
            f"  {task_key} -> has_relevant_links: {has_relevant_links}, formatted_issuelinks: '{template_ready_fields['formatted_issuelinks']}'")

        # Формирование {client_name} и {formatted_client_info}
        raw_client_val = template_ready_fields.get("customfield_12902")
        client_str_to_parse = None
        if isinstance(raw_client_val, dict):
            client_str_to_parse = raw_client_val.get("value")
        elif isinstance(raw_client_val, str):
            client_str_to_parse = raw_client_val

        extracted_client_name = None
        logger.debug(f"  {task_key}: Исходное для клиента: '{client_str_to_parse}'")
        if isinstance(client_str_to_parse, str) and client_str_to_parse.strip():
            parts = client_str_to_parse.split(" - ", 1);
            name_part = parts[0].strip()
            if "#" in name_part:
                extracted_client_name = name_part.split("#", 1)[0].strip()
            else:
                extracted_client_name = name_part
            if not extracted_client_name.strip(): extracted_client_name = None
        template_ready_fields["client_name"] = extracted_client_name
        logger.debug(f"  {task_key} -> extracted_client_name: '{extracted_client_name}'")
        if extracted_client_name and has_relevant_links:
            template_ready_fields["formatted_client_info"] = f"Клиент: {extracted_client_name}"
        else:
            template_ready_fields["formatted_client_info"] = None
            if not extracted_client_name: logger.debug(f"  {task_key}: formatted_client_info=None (нет client_name)")
            if not has_relevant_links: logger.debug(
                f"  {task_key}: formatted_client_info=None (нет релевантных связей, даже если client_name='{extracted_client_name}')")
        logger.debug(f"  {task_key} -> formatted_client_info: '{template_ready_fields.get('formatted_client_info')}'")

        # Парсинг микросервисов
        raw_fix_versions = jira_task_fields.get('fixVersions', [])
        raw_global_versions = _get_raw_global_version_strings_from_issue(issue_raw, global_version_patterns)
        task_ms_list = []
        if can_parse_microservices:
            task_ms_list = _parse_microservice_versions(raw_fix_versions, raw_global_versions, mv_pattern,
                                                        mv_prefix_idx, mv_version_idx, service_mapping,
                                                        global_version_patterns)
        ms_names = ", ".join(sorted(list(set(name for _, name, _ in task_ms_list))))
        template_ready_fields["linked_microservices_names"] = ms_names if ms_names else None

        # Распределение по секциям
        for section_id, section_proc_data in processed_data["sections_data"].items():
            source_cf = section_proc_data.get('source_custom_field_id')
            task_content_for_section = jira_task_fields.get(source_cf)
            if task_content_for_section is not None:
                current_task_data_for_section = template_ready_fields.copy()
                current_task_data_for_section["content"] = task_content_for_section
                # Гарантируем наличие ключевых полей для шаблона
                for f_name in ["key", "summary", "issuetype_name"]:
                    if f_name not in current_task_data_for_section:
                        current_task_data_for_section[f_name] = template_ready_fields.get(f_name,
                                                                                          'N/A' if f_name != "key" else task_key)

                if section_proc_data.get("disable_grouping"):
                    if not any(t.get("key") == task_key for t in section_proc_data.get("tasks_flat_list", [])):
                        section_proc_data["tasks_flat_list"].append(current_task_data_for_section)
                        logger.debug(f"  Задача {task_key} добавлена в плоский список секции '{section_id}'.")
                elif task_ms_list:  # Группировка включена И есть МС у задачи
                    unique_ms_added_to_this_section_for_task = set()
                    for pfx, srv_name, srv_ver in task_ms_list:
                        # Обновляем общую сводку по МС релиза
                        if (pfx, srv_name) not in all_microservices_in_release: all_microservices_in_release[
                            (pfx, srv_name)] = set()
                        all_microservices_in_release[(pfx, srv_name)].add(srv_ver)
                        # Добавляем задачу в текущую секцию под этим МС (только один раз)
                        if srv_name not in unique_ms_added_to_this_section_for_task:
                            ms_group_in_section = section_proc_data["microservices"][srv_name]
                            task_type_name = current_task_data_for_section.get("issuetype_name", "Неизвестный тип")
                            if section_proc_data.get("group_by_issue_type"):
                                ms_group_in_section["issue_types"][task_type_name].append(current_task_data_for_section)
                            else:
                                ms_group_in_section["tasks_without_type_grouping"].append(current_task_data_for_section)
                            unique_ms_added_to_this_section_for_task.add(srv_name)
                            logger.debug(
                                f"  Задача {task_key} добавлена в секцию '{section_id}' (группировка по МС) для МС '{srv_name}'.")
            # else:
            # logger.debug(f"  Основное поле {source_cf} для задачи {task_key} пусто. Не добавлено в секцию '{section_id}'.")

    # Формирование итоговой сводки по МС
    sorted_ms_tuples_summary = sorted(all_microservices_in_release.items(), key=lambda i: i[0][1])
    for (p, n), v_set in sorted_ms_tuples_summary:
        processed_data["microservices_summary"].append(
            {"prefix": p, "name": n, "version": ", ".join(sorted(list(v_set)))})

    logger.info(f"Обработка задач завершена. Собрано {len(processed_data['microservices_summary'])} МС для сводки.")
    return processed_data