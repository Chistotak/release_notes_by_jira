# src/settings_window.py
import customtkinter as ctk
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)


class SettingsWindow(ctk.CTkToplevel):
    def __init__(self, parent, config: Dict[str, Any], save_callback):
        # ... (код __init__ до создания виджетов остается прежним)
        super().__init__(parent)
        self.title("Настройки")
        self.geometry("900x700")
        self.transient(parent)
        self.grab_set()
        self.config_data = config
        self.save_callback = save_callback

        self.tab_view = ctk.CTkTabview(self, width=860, height=600)
        self.tab_view.pack(padx=20, pady=20, fill="both", expand=True)

        self.tab_general = self.tab_view.add("Общие и JIRA")  # Переименуем для ясности
        self.tab_versions = self.tab_view.add("Версии и Микросервисы")
        self.tab_sections = self.tab_view.add("Настройки Секций")  # Переименуем для ясности

        self.create_general_jira_tab_widgets()  # Обновленный метод
        self.create_versions_tab_widgets()
        self.create_sections_tab_widgets()  # Обновленный метод

        self.button_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.button_frame.pack(pady=10, padx=20, fill="x")
        self.button_save = ctk.CTkButton(self.button_frame, text="Сохранить и закрыть", command=self.save_and_close)
        self.button_save.pack(side="right", padx=10)
        self.button_cancel = ctk.CTkButton(self.button_frame, text="Отмена", fg_color="gray", command=self.destroy)
        self.button_cancel.pack(side="right")

        self.load_settings_to_widgets()

    def create_general_jira_tab_widgets(self):
        """Создает виджеты для вкладки "Общие и JIRA"."""
        # Этот метод теперь заменит create_jira_tab_widgets
        tab = self.tab_general
        tab.grid_columnconfigure(1, weight=1)

        # --- Общие настройки ---
        ctk.CTkLabel(tab, text="Общие настройки отображения:", font=ctk.CTkFont(weight="bold")).grid(row=0, column=0,
                                                                                                     columnspan=2,
                                                                                                     padx=10,
                                                                                                     pady=(10, 5),
                                                                                                     sticky="w")

        self.switch_ms_table_enabled = ctk.CTkSwitch(tab, text="Включить таблицу микросервисов")
        self.switch_ms_table_enabled.grid(row=1, column=0, columnspan=2, padx=20, pady=5, sticky="w")

        # Разделитель
        ctk.CTkFrame(tab, height=2, fg_color="gray50").grid(row=2, column=0, columnspan=2, padx=10, pady=10,
                                                            sticky="ew")

        # --- Настройки JIRA ---
        ctk.CTkLabel(tab, text="Настройки JIRA:", font=ctk.CTkFont(weight="bold")).grid(row=3, column=0, columnspan=2,
                                                                                        padx=10, pady=5, sticky="w")

        # ... (все остальные поля из create_jira_tab_widgets, но с новыми номерами строк)
        ctk.CTkLabel(tab, text="URL JIRA-сервера:").grid(row=4, column=0, padx=10, pady=10, sticky="w")
        self.entry_jira_url = ctk.CTkEntry(tab)
        self.entry_jira_url.grid(row=4, column=1, padx=10, pady=10, sticky="ew")

        ctk.CTkLabel(tab, text="Поля JIRA для запроса (через запятую):").grid(row=5, column=0, padx=10, pady=10,
                                                                              sticky="w")
        self.entry_jira_fields = ctk.CTkEntry(tab)
        self.entry_jira_fields.grid(row=5, column=1, padx=10, pady=10, sticky="ew")

        ctk.CTkLabel(tab, text="Исключаемые типы задач (через запятую):").grid(row=6, column=0, padx=10, pady=10,
                                                                               sticky="w")
        self.entry_exclude_types = ctk.CTkEntry(tab)
        self.entry_exclude_types.grid(row=6, column=1, padx=10, pady=10, sticky="ew")

        ctk.CTkLabel(tab, text="Префиксы проектов для issuelinks (через запятую):").grid(row=7, column=0, padx=10,
                                                                                         pady=10, sticky="w")
        self.entry_issuelink_prefixes = ctk.CTkEntry(tab)
        self.entry_issuelink_prefixes.grid(row=7, column=1, padx=10, pady=10, sticky="ew")

    def create_versions_tab_widgets(self):
        """(без изменений)"""
        tab = self.tab_versions
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_rowconfigure(1, weight=1)
        tab.grid_rowconfigure(3, weight=1)

        ctk.CTkLabel(tab, text="Паттерны для глобальной версии (каждый на новой строке):").grid(row=0, column=0,
                                                                                                padx=10, pady=(10, 0),
                                                                                                sticky="w")
        self.textbox_global_patterns = ctk.CTkTextbox(tab)
        self.textbox_global_patterns.grid(row=1, column=0, padx=10, pady=10, sticky="nsew")

        ctk.CTkLabel(tab, text="Маппинг микросервисов (ПРЕФИКС: Полное имя, каждый на новой строке):").grid(row=2,
                                                                                                            column=0,
                                                                                                            padx=10,
                                                                                                            pady=(10,
                                                                                                                  0),
                                                                                                            sticky="w")
        self.textbox_ms_mapping = ctk.CTkTextbox(tab)
        self.textbox_ms_mapping.grid(row=3, column=0, padx=10, pady=10, sticky="nsew")

    def create_sections_tab_widgets(self):
        """Создает виджеты для вкладки "Настройки Секций"."""
        # Этот метод заменит create_templates_tab_widgets
        tab = self.tab_sections
        tab.grid_columnconfigure(0, weight=1)

        # --- Настройки для секции "Изменения" ---
        frame_changes = ctk.CTkFrame(tab)
        frame_changes.grid(row=0, column=0, padx=10, pady=10, sticky="ew")
        frame_changes.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(frame_changes, text="Секция 'Изменения' (changes)", font=ctk.CTkFont(weight="bold")).grid(row=0,
                                                                                                               column=0,
                                                                                                               columnspan=2,
                                                                                                               padx=10,
                                                                                                               pady=5,
                                                                                                               sticky="w")

        ctk.CTkLabel(frame_changes, text="ID поля-источника:").grid(row=1, column=0, padx=10, sticky="w")
        self.entry_field_changes = ctk.CTkEntry(frame_changes)
        self.entry_field_changes.grid(row=1, column=1, padx=10, pady=5, sticky="ew")

        self.switch_changes_disable_grouping = ctk.CTkSwitch(frame_changes,
                                                             text="Отключить группировку (плоский список)")
        self.switch_changes_disable_grouping.grid(row=2, column=0, columnspan=2, padx=10, pady=5, sticky="w")

        self.switch_changes_group_by_type = ctk.CTkSwitch(frame_changes,
                                                          text="Группировать по типу задачи (внутри микросервиса)")
        self.switch_changes_group_by_type.grid(row=3, column=0, columnspan=2, padx=10, pady=5, sticky="w")

        ctk.CTkLabel(frame_changes, text="Шаблон отображения (issue_display_template):").grid(row=4, column=0,
                                                                                              columnspan=2, padx=10,
                                                                                              pady=(10, 0), sticky="w")
        self.textbox_template_changes = ctk.CTkTextbox(frame_changes, height=120)
        self.textbox_template_changes.grid(row=5, column=0, columnspan=2, padx=10, pady=5, sticky="ew")

        # --- Настройки для секции "Инструкции" ---
        frame_instructions = ctk.CTkFrame(tab)
        frame_instructions.grid(row=1, column=0, padx=10, pady=10, sticky="ew")
        frame_instructions.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(frame_instructions, text="Секция 'Инструкция по установке' (installation_instructions)",
                     font=ctk.CTkFont(weight="bold")).grid(row=0, column=0, columnspan=2, padx=10, pady=5, sticky="w")

        ctk.CTkLabel(frame_instructions, text="ID поля-источника:").grid(row=1, column=0, padx=10, sticky="w")
        self.entry_field_instructions = ctk.CTkEntry(frame_instructions)
        self.entry_field_instructions.grid(row=1, column=1, padx=10, pady=5, sticky="ew")

        self.switch_instructions_disable_grouping = ctk.CTkSwitch(frame_instructions,
                                                                  text="Отключить группировку (плоский список)")
        self.switch_instructions_disable_grouping.grid(row=2, column=0, columnspan=2, padx=10, pady=5, sticky="w")

        self.switch_instructions_group_by_type = ctk.CTkSwitch(frame_instructions,
                                                               text="Группировать по типу задачи (внутри микросервиса)")
        self.switch_instructions_group_by_type.grid(row=3, column=0, columnspan=2, padx=10, pady=5, sticky="w")

        ctk.CTkLabel(frame_instructions, text="Шаблон отображения (issue_display_template):").grid(row=4, column=0,
                                                                                                   columnspan=2,
                                                                                                   padx=10,
                                                                                                   pady=(10, 0),
                                                                                                   sticky="w")
        self.textbox_template_instructions = ctk.CTkTextbox(frame_instructions, height=120)
        self.textbox_template_instructions.grid(row=5, column=0, columnspan=2, padx=10, pady=5, sticky="ew")

    def load_settings_to_widgets(self):
        """(Обновленный метод) Загружает данные в виджеты."""
        logger.info("Загрузка текущих настроек в виджеты...")

        # Общие и JIRA
        ms_table_enabled = self.config_data.get('release_notes', {}).get('microservices_table', {}).get('enabled',
                                                                                                        False)
        if ms_table_enabled:
            self.switch_ms_table_enabled.select()
        else:
            self.switch_ms_table_enabled.deselect()

        self.entry_jira_url.insert(0, self.config_data.get('jira', {}).get('server_url', ''))
        self.entry_jira_fields.insert(0, ", ".join(self.config_data.get('jira', {}).get('issue_fields_to_request', [])))
        self.entry_exclude_types.insert(0, ", ".join(
            self.config_data.get('release_notes', {}).get('exclude_issue_types', [])))
        self.entry_issuelink_prefixes.insert(0, ", ".join(
            self.config_data.get('release_notes', {}).get('filter_issuelinks_by_project_prefixes', [])))

        # Секция "Изменения" (changes)
        changes_section_cfg = self.config_data.get('release_notes', {}).get('sections', {}).get('changes', {})
        self.entry_field_changes.insert(0, changes_section_cfg.get('source_custom_field_id', ''))
        if changes_section_cfg.get('disable_grouping', False): self.switch_changes_disable_grouping.select()
        if changes_section_cfg.get('group_by_issue_type', False): self.switch_changes_group_by_type.select()
        self.textbox_template_changes.insert("1.0", changes_section_cfg.get('issue_display_template', ''))

        # Секция "Инструкции" (installation_instructions)
        instructions_section_cfg = self.config_data.get('release_notes', {}).get('sections', {}).get(
            'installation_instructions', {})
        self.entry_field_instructions.insert(0, instructions_section_cfg.get('source_custom_field_id', ''))
        if instructions_section_cfg.get('disable_grouping', False): self.switch_instructions_disable_grouping.select()
        if instructions_section_cfg.get('group_by_issue_type', False): self.switch_instructions_group_by_type.select()
        self.textbox_template_instructions.insert("1.0", instructions_section_cfg.get('issue_display_template', ''))

        # Вкладка Версии (как раньше)
        global_patterns = self.config_data.get('version_parsing', {}).get('global_version', {}).get(
            'extraction_patterns', [])
        self.textbox_global_patterns.insert("1.0", "\n".join(global_patterns))
        ms_mapping = self.config_data.get('version_parsing', {}).get('microservice_mapping', {})
        mapping_text = "\n".join([f"{key}: {value}" for key, value in ms_mapping.items()])
        self.textbox_ms_mapping.insert("1.0", mapping_text)

    def collect_settings_from_widgets(self) -> Dict[str, Any]:
        """(Обновленный метод) Собирает данные из виджетов."""
        logger.info("Сбор настроек из виджетов...")
        new_config = self.config_data.copy()

        # Общие и JIRA
        new_config['release_notes']['microservices_table']['enabled'] = bool(self.switch_ms_table_enabled.get())
        new_config['jira']['server_url'] = self.entry_jira_url.get().strip()
        new_config['jira']['issue_fields_to_request'] = [f.strip() for f in self.entry_jira_fields.get().split(',') if
                                                         f.strip()]
        new_config['release_notes']['exclude_issue_types'] = [f.strip() for f in
                                                              self.entry_exclude_types.get().split(',') if f.strip()]
        new_config['release_notes']['filter_issuelinks_by_project_prefixes'] = [f.strip() for f in
                                                                                self.entry_issuelink_prefixes.get().split(
                                                                                    ',') if f.strip()]

        # Секция "Изменения" (changes)
        new_config['release_notes']['sections']['changes'][
            'source_custom_field_id'] = self.entry_field_changes.get().strip()
        new_config['release_notes']['sections']['changes']['disable_grouping'] = bool(
            self.switch_changes_disable_grouping.get())
        new_config['release_notes']['sections']['changes']['group_by_issue_type'] = bool(
            self.switch_changes_group_by_type.get())
        new_config['release_notes']['sections']['changes'][
            'issue_display_template'] = self.textbox_template_changes.get("1.0", "end-1c")

        # Секция "Инструкции" (installation_instructions)
        new_config['release_notes']['sections']['installation_instructions'][
            'source_custom_field_id'] = self.entry_field_instructions.get().strip()
        new_config['release_notes']['sections']['installation_instructions']['disable_grouping'] = bool(
            self.switch_instructions_disable_grouping.get())
        new_config['release_notes']['sections']['installation_instructions']['group_by_issue_type'] = bool(
            self.switch_instructions_group_by_type.get())
        new_config['release_notes']['sections']['installation_instructions'][
            'issue_display_template'] = self.textbox_template_instructions.get("1.0", "end-1c")

        # Вкладка Версии (как раньше)
        new_config['version_parsing']['global_version']['extraction_patterns'] = [p.strip() for p in
                                                                                  self.textbox_global_patterns.get(
                                                                                      "1.0", "end-1c").split('\n') if
                                                                                  p.strip()]
        ms_mapping_new = {}
        for line in self.textbox_ms_mapping.get("1.0", "end-1c").split('\n'):
            if ':' in line:
                key, value = line.split(':', 1)
                ms_mapping_new[key.strip()] = value.strip()
        new_config['version_parsing']['microservice_mapping'] = ms_mapping_new

        return new_config

    def save_and_close(self):
        # ... (метод без изменений)
        new_config_data = self.collect_settings_from_widgets()
        self.save_callback(new_config_data)
        self.destroy()