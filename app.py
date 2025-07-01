# app.py
import customtkinter as ctk
from tkinter import filedialog
import threading
import logging
import sys
from pathlib import Path
from src.settings_window import SettingsWindow
import yaml
from pathlib import Path

# --- Импортируем нашу логику ---
# Убедись, что Python может найти папку src.
# Если app.py в корне, а модули в src/, то это должно сработать.
try:
    from src.config_loader import get_correct_path
except ImportError:
    # Фоллбэк, если запускаем app.py напрямую
    project_root = Path(__file__).resolve().parent
    sys.path.insert(0, str(project_root))
    from src.config_loader import get_correct_path

CONFIG_PATH = get_correct_path("config/config.yaml")

try:
    from src.config_loader import load_config, load_environment_variables
    from src.core_logic import run_generation_process
except ImportError:
    # Добавляем путь к src, если скрипт запущен так, что src не виден
    project_root = Path(__file__).resolve().parent
    sys.path.insert(0, str(project_root))
    from src.config_loader import load_config, load_environment_variables
    from src.core_logic import run_generation_process


# --- Настройка логирования (как в предыдущей версии) ---
# ... (Код для CTkTextboxHandler и настройка корневого логгера остаются)
class CTkTextboxHandler(logging.Handler):
    """Обработчик логов, который перенаправляет записи в CTkTextbox."""

    def __init__(self, textbox):
        super().__init__()
        self.textbox = textbox

    def emit(self, record):
        msg = self.format(record)
        # Выполняем обновление GUI в главном потоке через after()
        self.textbox.after(0, self.update_textbox, msg)

    def update_textbox(self, msg):
        self.textbox.configure(state="normal")
        self.textbox.insert("end", msg + "\n")
        self.textbox.see("end")
        self.textbox.configure(state="disabled")


# ... (Код класса App с изменениями) ...
class App(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.logger = logging.getLogger(__name__)
        self.title("Генератор Release Notes")
        self.geometry("800x650")
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(2, weight=1)

        # --- Создание виджетов (как раньше) ---
        self.input_frame = ctk.CTkFrame(self)  # ...
        self.input_frame.grid(row=0, column=0, columnspan=2, padx=20, pady=(20, 10), sticky="ew")
        self.input_frame.grid_columnconfigure(1, weight=1)
        self.label_filter_id = ctk.CTkLabel(self.input_frame, text="ID Фильтра JIRA:")  # ...
        self.label_filter_id.grid(row=0, column=0, padx=(20, 10), pady=10, sticky="w")
        self.entry_filter_id = ctk.CTkEntry(self.input_frame, placeholder_text="например, 12345")  # ...
        self.entry_filter_id.grid(row=0, column=1, padx=(0, 20), pady=10, sticky="ew")
        self.label_output_dir = ctk.CTkLabel(self.input_frame, text="Папка для сохранения:")  # ...
        self.label_output_dir.grid(row=1, column=0, padx=(20, 10), pady=10, sticky="w")
        self.entry_output_dir = ctk.CTkEntry(self.input_frame, placeholder_text="Выберите папку...")  # ...
        self.entry_output_dir.grid(row=1, column=1, padx=(0, 10), pady=10, sticky="ew")
        self.button_browse_dir = ctk.CTkButton(self.input_frame, text="Выбрать...", width=100,
                                               command=self.browse_output_directory)  # ...
        self.button_browse_dir.grid(row=1, column=2, padx=(0, 20), pady=10)
        self.control_frame = ctk.CTkFrame(self)  # ...
        self.control_frame.grid(row=1, column=0, columnspan=2, padx=20, pady=10, sticky="ew")
        self.control_frame.grid_columnconfigure(0, weight=1)
        self.button_generate = ctk.CTkButton(self.control_frame, text="Сгенерировать Release Notes",
                                             command=self.start_generation_process)  # ...
        self.button_generate.grid(row=0, column=0, padx=20, pady=10)
        self.button_settings = ctk.CTkButton(self.control_frame, text="Настройки", fg_color="gray",
                                             command=self.open_settings_window)  # ...
        self.button_settings.grid(row=0, column=1, padx=20, pady=10)
        self.log_textbox = ctk.CTkTextbox(self, state="disabled")  # ...
        self.log_textbox.grid(row=2, column=0, columnspan=2, padx=20, pady=10, sticky="nsew")
        self.progress_bar = ctk.CTkProgressBar(self)  # ...
        self.progress_bar.grid(row=3, column=0, columnspan=2, padx=20, pady=10, sticky="ew")
        self.progress_bar.grid_remove()
        self.status_label = ctk.CTkLabel(self, text="Готов к работе.", anchor="w")  # ...
        self.status_label.grid(row=4, column=0, columnspan=2, padx=20, pady=(10, 20), sticky="ew")

        self.settings_window_instance = None
        # Переменные для хранения данных
        self.config = {}
        self.env_vars = {}

        # --- Начальная загрузка данных ---
        self.load_defaults()

    def browse_output_directory(self):
        # ... (код остается таким же) ...
        directory = filedialog.askdirectory()
        if directory:
            self.entry_output_dir.delete(0, "end")
            self.entry_output_dir.insert(0, directory)
            self.logger.info(f"Выбрана папка для сохранения: {directory}")

    def update_status(self, message: str):
        """Безопасное обновление строки состояния из любого потока."""
        self.status_label.configure(text=message)

    def start_generation_process(self):
        """Запускает процесс генерации в отдельном потоке, чтобы не блокировать GUI."""
        # 1. Сбор данных из GUI
        filter_id = self.entry_filter_id.get().strip()
        output_dir = self.entry_output_dir.get().strip()
        jira_cookie = self.env_vars.get('JIRA_COOKIE_STRING')

        if not filter_id:
            self.logger.error("ID фильтра не может быть пустым.")
            self.update_status("Ошибка: введите ID фильтра.")
            return

        # 2. Блокировка интерфейса
        self.button_generate.configure(state="disabled")
        self.button_settings.configure(state="disabled")
        self.progress_bar.grid()
        self.progress_bar.start()
        self.update_status("Запуск процесса генерации...")

        # 3. Создание и запуск потока
        # Передаем self, чтобы поток мог вызывать методы GUI (например, update_status)
        generation_thread = threading.Thread(
            target=self.run_generation_in_thread,
            args=(filter_id, output_dir, jira_cookie)
        )
        generation_thread.start()

    def run_generation_in_thread(self, filter_id, output_dir, jira_cookie):
        """Метод, который будет выполняться в отдельном потоке."""
        try:
            # Вызываем основную логику
            success = run_generation_process(filter_id, output_dir, jira_cookie)

            # Обновляем GUI после завершения
            if success:
                self.after(0, self.update_status, f"Успешно завершено! Файлы сохранены в {output_dir}")
            else:
                self.after(0, self.update_status, "Процесс завершился с ошибкой. См. логи для деталей.")

        except Exception as e:
            self.logger.critical(f"Неперехваченная ошибка в рабочем потоке: {e}", exc_info=True)
            self.after(0, self.update_status, "Критическая ошибка в рабочем потоке!")

        finally:
            # Разблокировка интерфейса в любом случае
            self.after(0, self.on_generation_complete)

    def on_generation_complete(self):
        """Восстанавливает состояние GUI после завершения генерации."""
        self.button_generate.configure(state="normal")
        self.button_settings.configure(state="normal")
        self.progress_bar.stop()
        self.progress_bar.grid_remove()

    def open_settings_window(self):
        """Открывает окно настроек."""
        # Проверяем, не открыто ли уже окно настроек
        if self.settings_window_instance is None or not self.settings_window_instance.winfo_exists():
            if not self.config:  # Если конфиг еще не загружен
                self.logger.warning("Конфигурация не загружена. Попытка загрузить перед открытием настроек.")
                self.load_defaults()
                if not self.config:  # Если и после этого не загрузился
                    self.logger.error("Не удалось загрузить конфигурацию для окна настроек.")
                    self.update_status("Ошибка: Не удалось загрузить конфигурацию.")
                    return

            # Создаем новое окно, передаем ему родителя (self), текущий конфиг и callback-функцию для сохранения
            self.settings_window_instance = SettingsWindow(parent=self, config=self.config,
                                                           save_callback=self.save_config)
            self.logger.info("Окно настроек открыто.")
        else:
            self.settings_window_instance.focus()  # Если уже открыто, просто переводим на него фокус

    def save_config(self, new_config_data: dict[str, any]):
        """Callback-функция для сохранения конфигурации из окна настроек."""
        self.logger.info("Попытка сохранения обновленной конфигурации...")
        try:
            with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
                yaml.dump(new_config_data, f, allow_unicode=True, sort_keys=False)
            self.logger.info(f"Конфигурация успешно сохранена в {CONFIG_PATH}")
            self.update_status("Настройки сохранены. Перезагрузка дефолтов...")
            # Перезагружаем конфиг и обновляем главный экран
            self.load_defaults()
        except Exception as e:
            self.logger.error(f"Ошибка при сохранении файла конфигурации: {e}", exc_info=True)
            self.update_status(f"Ошибка сохранения конфигурации: {e}")

    def load_defaults(self):
        """Загружает значения по умолчанию из config.yaml и .env."""
        # ... (существующий код load_defaults) ...
        self.logger.info("Загрузка конфигурации и значений по умолчанию...")
        try:
            self.config = load_config()
            self.env_vars = load_environment_variables()

            defaults = self.config.get('defaults', {})
            default_filter_id = defaults.get('filter_id', '')
            default_output_dir = defaults.get('output_dir', '')

            self.entry_filter_id.delete(0, "end")
            self.entry_filter_id.insert(0, str(default_filter_id))

            self.entry_output_dir.delete(0, "end")
            self.entry_output_dir.insert(0, default_output_dir)

            self.update_status("Конфигурация загружена. Готов к работе.")
            self.logger.info("Значения по умолчанию успешно загружены в интерфейс.")

        except FileNotFoundError:
            self.logger.error(f"Файл {CONFIG_PATH} не найден. Пожалуйста, создайте его или проверьте путь.")
            self.update_status(f"Ошибка: {CONFIG_PATH.name} не найден.")
            # Здесь можно предложить создать его интерактивно в будущем
        except Exception as e:
            self.logger.critical(f"Критическая ошибка при загрузке конфигурации: {e}", exc_info=True)
            self.update_status(f"Ошибка загрузки конфигурации: {e}")

# --- Запуск приложения ---
if __name__ == "__main__":
    app = App()

    # Настройка обработчика для вывода логов в текстовое поле GUI
    textbox_handler = CTkTextboxHandler(app.log_textbox)
    log_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    textbox_handler.setFormatter(log_formatter)

    # Добавляем обработчик к корневому логгеру, чтобы он ловил все сообщения
    logging.getLogger().addHandler(textbox_handler)
    logging.getLogger().setLevel(logging.INFO)  # Начальный уровень логов

    app.mainloop()