# src/settings_window.py
import customtkinter as ctk
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)


class SettingsWindow(ctk.CTkToplevel):
    """
    Окно для редактирования конфигурации (config.yaml).
    """

    def __init__(self, parent, config: Dict[str, Any], save_callback):
        super().__init__(parent)

        self.title("Настройки")
        self.geometry("900x700")
        self.transient(parent)  # Окно будет поверх родительского
        self.grab_set()  # Модальное поведение: блокирует взаимодействие с родительским окном

        self.config_data = config
        self.save_callback = save_callback  # Функция, которая будет вызвана для сохранения

        # --- Создание виджетов ---

        # 1. Tab View для разделения настроек
        self.tab_view = ctk.CTkTabview(self, width=860, height=600)
        self.tab_view.pack(padx=20, pady=20, fill="both", expand=True)

        # Добавляем вкладки
        self.tab_jira = self.tab_view.add("JIRA и Задачи")
        self.tab_versions = self.tab_view.add("Версии и Микросервисы")
        self.tab_templates = self.tab_view.add("Шаблоны секций")
        # Можно добавить и другие вкладки...

        # 2. Заполняем каждую вкладку виджетами
        self.create_jira_tab_widgets()
        self.create_versions_tab_widgets()
        self.create_templates_tab_widgets()

        # 3. Кнопки внизу окна
        self.button_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.button_frame.pack(pady=10, padx=20, fill="x")

        self.button_save = ctk.CTkButton(self.button_frame, text="Сохранить и закрыть", command=self.save_and_close)
        self.button_save.pack(side="right", padx=10)

        self.button_cancel = ctk.CTkButton(self.button_frame, text="Отмена", fg_color="gray", command=self.destroy)
        self.button_cancel.pack(side="right")

        # 4. Загружаем данные в созданные виджеты
        self.load_settings_to_widgets()

    def create_jira_tab_widgets(self):
        """Создает виджеты для вкладки "JIRA и Задачи"."""
        tab = self.tab_jira
        tab.grid_columnconfigure(1, weight=1)

        # URL сервера JIRA
        ctk.CTkLabel(tab, text="URL JIRA-сервера:").grid(row=0, column=0, padx=10, pady=10, sticky="w")
        self.entry_jira_url = ctk.CTkEntry(tab)
        self.entry_jira_url.grid(row=0, column=1, padx=10, pady=10, sticky="ew")

        # Поля для запроса
        ctk.CTkLabel(tab, text="Поля JIRA для запроса (через запятую):").grid(row=1, column=0, padx=10, pady=10,
                                                                              sticky="w")
        self.entry_jira_fields = ctk.CTkEntry(tab)
        self.entry_jira_fields.grid(row=1, column=1, padx=10, pady=10, sticky="ew")

        # Исключаемые типы задач
        ctk.CTkLabel(tab, text="Исключаемые типы задач (через запятую):").grid(row=2, column=0, padx=10, pady=10,
                                                                               sticky="w")
        self.entry_exclude_types = ctk.CTkEntry(tab)
        self.entry_exclude_types.grid(row=2, column=1, padx=10, pady=10, sticky="ew")

        # Фильтр префиксов для issuelinks
        ctk.CTkLabel(tab, text="Префиксы проектов для issuelinks (через запятую):").grid(row=3, column=0, padx=10,
                                                                                         pady=10, sticky="w")
        self.entry_issuelink_prefixes = ctk.CTkEntry(tab)
        self.entry_issuelink_prefixes.grid(row=3, column=1, padx=10, pady=10, sticky="ew")

        # ID полей для секций (можно сделать более продвинуто, но для начала так)
        ctk.CTkLabel(tab, text="ID поля для секции 'Изменения':").grid(row=4, column=0, padx=10, pady=10, sticky="w")
        self.entry_field_changes = ctk.CTkEntry(tab)
        self.entry_field_changes.grid(row=4, column=1, padx=10, pady=10, sticky="ew")

        ctk.CTkLabel(tab, text="ID поля для секции 'Инструкции':").grid(row=5, column=0, padx=10, pady=10, sticky="w")
        self.entry_field_instructions = ctk.CTkEntry(tab)
        self.entry_field_instructions.grid(row=5, column=1, padx=10, pady=10, sticky="ew")

        ctk.CTkLabel(tab, text="ID поля для 'Клиент/Контракт':").grid(row=6, column=0, padx=10, pady=10, sticky="w")
        self.entry_field_client = ctk.CTkEntry(tab)
        self.entry_field_client.grid(row=6, column=1, padx=10, pady=10, sticky="ew")

    def create_versions_tab_widgets(self):
        """Создает виджеты для вкладки "Версии и Микросервисы"."""
        tab = self.tab_versions
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_rowconfigure(1, weight=1)  # Позволяем текстовым полям расширяться

        # Паттерны глобальной версии
        ctk.CTkLabel(tab, text="Паттерны для глобальной версии (каждый на новой строке):").grid(row=0, column=0,
                                                                                                padx=10, pady=(10, 0),
                                                                                                sticky="w")
        self.textbox_global_patterns = ctk.CTkTextbox(tab)
        self.textbox_global_patterns.grid(row=1, column=0, padx=10, pady=10, sticky="nsew")

        # Маппинг микросервисов
        ctk.CTkLabel(tab, text="Маппинг микросервисов (формат: ПРЕФИКС: Полное имя, каждый на новой строке):").grid(
            row=2, column=0, padx=10, pady=(10, 0), sticky="w")
        self.textbox_ms_mapping = ctk.CTkTextbox(tab)
        self.textbox_ms_mapping.grid(row=3, column=0, padx=10, pady=10, sticky="nsew")

    def create_templates_tab_widgets(self):
        """Создает виджеты для вкладки "Шаблоны секций"."""
        tab = self.tab_templates
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_rowconfigure(1, weight=1)
        tab.grid_rowconfigure(3, weight=1)

        # Шаблон для секции "Изменения"
        ctk.CTkLabel(tab, text="Шаблон для секции 'Изменения' (issue_display_template):").grid(row=0, column=0, padx=10,
                                                                                               pady=(10, 0), sticky="w")
        self.textbox_template_changes = ctk.CTkTextbox(tab)
        self.textbox_template_changes.grid(row=1, column=0, padx=10, pady=10, sticky="nsew")

        # Шаблон для секции "Инструкции"
        ctk.CTkLabel(tab, text="Шаблон для секции 'Инструкции' (issue_display_template):").grid(row=2, column=0,
                                                                                                padx=10, pady=(10, 0),
                                                                                                sticky="w")
        self.textbox_template_instructions = ctk.CTkTextbox(tab)
        self.textbox_template_instructions.grid(row=3, column=0, padx=10, pady=10, sticky="nsew")

    def load_settings_to_widgets(self):
        """Загружает данные из self.config_data в соответствующие виджеты."""
        logger.info("Загрузка текущих настроек в виджеты окна настроек...")

        # Вкладка JIRA
        self.entry_jira_url.insert(0, self.config_data.get('jira', {}).get('server_url', ''))
        self.entry_jira_fields.insert(0, ", ".join(self.config_data.get('jira', {}).get('issue_fields_to_request', [])))
        self.entry_exclude_types.insert(0, ", ".join(
            self.config_data.get('release_notes', {}).get('exclude_issue_types', [])))
        self.entry_issuelink_prefixes.insert(0, ", ".join(
            self.config_data.get('release_notes', {}).get('filter_issuelinks_by_project_prefixes', [])))

        # ID полей
        self.entry_field_changes.insert(0, self.config_data.get('release_notes', {}).get('sections', {}).get('changes',
                                                                                                             {}).get(
            'source_custom_field_id', ''))
        self.entry_field_instructions.insert(0, self.config_data.get('release_notes', {}).get('sections', {}).get(
            'installation_instructions', {}).get('source_custom_field_id', ''))
        # Пытаемся найти ID поля клиента в списке полей (это не очень надежно, но для начала сойдет)
        client_field_id = next(
            (f for f in self.config_data.get('jira', {}).get('issue_fields_to_request', []) if '12902' in f), '')
        self.entry_field_client.insert(0, client_field_id)

        # Вкладка Версии
        global_patterns = self.config_data.get('version_parsing', {}).get('global_version', {}).get(
            'extraction_patterns', [])
        self.textbox_global_patterns.insert("1.0", "\n".join(global_patterns))

        ms_mapping = self.config_data.get('version_parsing', {}).get('microservice_mapping', {})
        mapping_text = "\n".join([f"{key}: {value}" for key, value in ms_mapping.items()])
        self.textbox_ms_mapping.insert("1.0", mapping_text)

        # Вкладка Шаблоны
        self.textbox_template_changes.insert("1.0", self.config_data.get('release_notes', {}).get('sections', {}).get(
            'changes', {}).get('issue_display_template', ''))
        self.textbox_template_instructions.insert("1.0",
                                                  self.config_data.get('release_notes', {}).get('sections', {}).get(
                                                      'installation_instructions', {}).get('issue_display_template',
                                                                                           ''))

    def collect_settings_from_widgets(self) -> Dict[str, Any]:
        """Собирает данные из виджетов и возвращает их в виде словаря конфигурации."""
        logger.info("Сбор настроек из виджетов...")

        new_config = self.config_data.copy()  # Начинаем с существующего конфига, чтобы не потерять то, что не редактируем

        # Вкладка JIRA
        new_config['jira']['server_url'] = self.entry_jira_url.get().strip()
        new_config['jira']['issue_fields_to_request'] = [f.strip() for f in self.entry_jira_fields.get().split(',') if
                                                         f.strip()]
        new_config['release_notes']['exclude_issue_types'] = [f.strip() for f in
                                                              self.entry_exclude_types.get().split(',') if f.strip()]
        new_config['release_notes']['filter_issuelinks_by_project_prefixes'] = [f.strip() for f in
                                                                                self.entry_issuelink_prefixes.get().split(
                                                                                    ',') if f.strip()]

        # ID полей
        new_config['release_notes']['sections']['changes'][
            'source_custom_field_id'] = self.entry_field_changes.get().strip()
        new_config['release_notes']['sections']['installation_instructions'][
            'source_custom_field_id'] = self.entry_field_instructions.get().strip()
        # Поле клиента - просто добавляем/обновляем его в списке полей
        client_field_id_new = self.entry_field_client.get().strip()
        if client_field_id_new and client_field_id_new not in new_config['jira']['issue_fields_to_request']:
            new_config['jira']['issue_fields_to_request'].append(client_field_id_new)

        # Вкладка Версии
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

        # Вкладка Шаблоны
        new_config['release_notes']['sections']['changes'][
            'issue_display_template'] = self.textbox_template_changes.get("1.0", "end-1c")
        new_config['release_notes']['sections']['installation_instructions'][
            'issue_display_template'] = self.textbox_template_instructions.get("1.0", "end-1c")

        return new_config

    def save_and_close(self):
        """Собирает настройки, вызывает callback для сохранения и закрывает окно."""
        new_config_data = self.collect_settings_from_widgets()
        self.save_callback(new_config_data)  # Вызываем функцию сохранения, переданную из App
        self.destroy()  # Закрываем окно настроек