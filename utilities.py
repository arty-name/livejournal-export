import json


class ExportError(Exception):
    """An export cannot continue safely without user intervention."""


def save_text_file(name, text):
    with open(name, 'w', encoding='utf-8') as file:
        file.write(text)


def save_json_file(name, data):
    save_text_file(name, json.dumps(data, ensure_ascii=False, indent=2))
