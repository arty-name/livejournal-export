import json


def xml_post_to_json(xml):
    def f(field):
        return xml.findtext(field)

    return {
        'id': int(f('itemid') or -1),
        'date': f('logtime') or f('eventtime'),
        'subject': f('subject') or '',
        'body': f('event'),
        'eventtime': f('eventtime'),
        'security': f('security'),
        'allowmask': f('allowmask'),
        'current_music': f('current_music'),
        'current_mood': f('current_mood'),
    }


def save_text_file(name, text):
    with open(name, 'w', encoding='utf-8') as file:
        file.write(text)


def save_json_file(name, data):
    save_text_file(name, json.dumps(data, ensure_ascii=False, indent=2))
