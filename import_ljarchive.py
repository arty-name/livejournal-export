import os
import xml.etree.ElementTree as ET
from pathlib import Path

from download_posts import xml_to_json
from utilities import save_json_file


def convert_posts():
    xml_posts = Path('posts-xml')
    if not xml_posts.is_dir():
        raise NotADirectoryError('The xml files have to be in the posts-xml directory, but it doesn’t exist')

    files = [xml for xml in xml_posts.iterdir() if xml.suffix == '.xml']
    trees = [ET.fromstring(xml.read_text()) for xml in files]
    entries = [entry for tree in trees for entry in tree.iter('entry')]
    json_posts = list(map(xml_to_json, entries))

    save_json_file('posts-json/all.json', json_posts)


def import_ljarchive():
    os.makedirs('posts-json', exist_ok=True)
    os.makedirs('comments-json', exist_ok=True)

    convert_posts()
    save_json_file('comments-json/all.json', [])


if __name__ == '__main__':
    import_ljarchive()
