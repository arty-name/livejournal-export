#!/usr/bin/python3

import os
import requests
from sys import exit as sysexit
import xml.etree.ElementTree as ET
from datetime import datetime
from dateutil.relativedelta import relativedelta
from pathlib import Path

from authentication import authenticated_request_params
from utilities import save_json_file, save_text_file
from utilities import xml_post_to_json as xml_to_json

DATE_FORMAT = '%Y-%m'


def get_months():
    try:
        start_month = datetime.strptime(input('Enter start month in YYYY-MM format: '), DATE_FORMAT)
    except Exception as e:
        print(f'\nError with start month entered. Error: {e}. Exiting...')
        sysexit(1)

    try:
        end_month = datetime.strptime(input('Enter end month in YYYY-MM format: '), DATE_FORMAT)
    except Exception as e:
        print(f'\nError with end month entered. Error: {e}. Exiting...')
        sysexit(1)

    return start_month, end_month


def fetch_month_posts(year, month):
    response = requests.post(
        'https://www.livejournal.com/export_do.bml',
        **authenticated_request_params(),
        data={
            'what': 'journal',
            'year': year,
            'month': f'{month:02d}',
            'format': 'xml',
            'header': 'on',
            'encid': '2',
            'field_itemid': 'on',
            'field_eventtime': 'on',
            'field_logtime': 'on',
            'field_subject': 'on',
            'field_event': 'on',
            'field_security': 'on',
            'field_allowmask': 'on',
            'field_currents': 'on'
        }
    )
    return response.text


def download_posts():
    os.makedirs('posts-xml', exist_ok=True)
    os.makedirs('posts-json', exist_ok=True)

    start_month, end_month = get_months()

    xml_posts = []
    month_cursor = start_month

    while month_cursor <= end_month:
        year = month_cursor.year
        month = month_cursor.month

        xml = fetch_month_posts(year, month)
        xml_posts.extend(list(ET.fromstring(xml).iter('entry')))

        save_text_file(f'posts-xml/{year}-{month:02d}.xml', xml)

        month_cursor = month_cursor + relativedelta(months=1)

    json_posts = list(map(xml_to_json, xml_posts))
    save_json_file('posts-json/all.json', json_posts)

    return json_posts


def convert_posts():
    xml_posts = Path('posts-xml')
    all_json = Path('posts-json/all.json')
    if not xml_posts.is_dir():
        raise NotADirectoryError("Haven't got a posts-xml directory")
    if not all_json.parent.exists():
        all_json.parent.mkdir()
    if not all_json.parent.is_dir():
        raise NotADirectoryError(f'Not a directory: {all_json.parent}')
    json_posts = []
    maxid = 0
    for xml in xml_posts.iterdir():
        if xml.suffix == '.xml':
            for json_post in map(xml_to_json, ET.fromstring(xml.read_text()).iter('entry')):
                if json_post['id'] is None:
                    maxid = json_post['id'] = maxid + 1
                else:
                    maxid = max((int(json_post['id']), maxid))
                json_posts.append(json_post)

    save_json_file(str(all_json), json_posts)


if __name__ == '__main__':
    download_posts()
