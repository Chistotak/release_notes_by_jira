from docx import Document
from docx.enum.style import WD_STYLE_TYPE


def list_styles(docx_filepath):
    try:
        document = Document(docx_filepath)
        styles = document.styles

        print(f"Стили документа: {docx_filepath}")
        print("-" * 30)

        print("\nСтили параграфов (включая заголовки, списки):")
        for s in styles:
            if s.type == WD_STYLE_TYPE.PARAGRAPH:
                print(f"  Имя: '{s.name}' (ID: {s.style_id})")

        print("\nСтили символов:")
        for s in styles:
            if s.type == WD_STYLE_TYPE.CHARACTER:
                print(f"  Имя: '{s.name}' (ID: {s.style_id})")

        print("\nСтили таблиц:")
        for s in styles:
            if s.type == WD_STYLE_TYPE.TABLE:
                print(f"  Имя: '{s.name}' (ID: {s.style_id})")

        # Стили нумерации не всегда явно видны как отдельные именованные стили в document.styles,
        # они больше связаны с определением нумерации.
        # Стиль "List Bullet" или "List Paragraph" - это стили параграфа.

    except Exception as e:
        print(f"Ошибка при чтении файла {docx_filepath}: {e}")


if __name__ == "__main__":
    # ЗАМЕНИ ЭТОТ ПУТЬ НА ПУТЬ К ТВОЕМУ ШАБЛОНУ DOCX
    template_file = r"C:\Users\haranski\PycharmProjects\release_notes_by_jira\config\templates\rn_template.docx"
    # Если запускаешь этот скрипт из корневой папки проекта,
    # и шаблон лежит в config/templates/rn_template.docx

    # или абсолютный путь:
    # template_file = r"C:\Users\haranski\PycharmProjects\release_notes_by_jira\config\templates\rn_template.docx"

    # Проверяем, что python-docx установлен
    try:
        import docx

        print(f"python-docx version: {docx.__version__}")
    except ImportError:
        print("Библиотека python-docx не установлена. Установите ее: pip install python-docx")
        exit()

    list_styles(template_file)