#!/usr/bin/env python3

import json
import os
import requests
from sys import exit as sysexit
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta

DATE_FORMAT = '%Y-%m'

try:
    start_month = datetime.strptime(input("Enter start month in YYYY-MM format: "), DATE_FORMAT)
except Exception as e:
    print(f"\nError with start month entered. Error: {e}. Exiting...")
    sysexit(1)

try:
    end_month = datetime.strptime(input("Enter end month in YYYY-MM format: "), DATE_FORMAT)
except Exception as e:
    print(f"\nError with end month entered. Error: {e}. Exiting...")
    sysexit(1)


def fetch_month_posts(year, month, cookies, headers):
    response = requests.post(
        'https://www.livejournal.com/export_do.bml',
        headers=headers,
        cookies=cookies,
        data={
            'what': 'journal',
            'year': year,
            'month': '{0:02d}'.format(month),
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

def xml_to_json(xml):
    def f(field):
        return xml.find(field).text

    return {
        'id': f('itemid'),
        'date': f('logtime'),
        'subject': f('subject') or '',
        'body': f('event'),
        'eventtime': f('eventtime'),
        'security': f('security'),
        'allowmask': f('allowmask'),
        'current_music': f('current_music'),
        'current_mood': f('current_mood')
    }

def download_posts(cookies, headers):
    os.makedirs('posts-xml', exist_ok=True)
    os.makedirs('posts-json', exist_ok=True)

    xml_posts = []
    month_cursor = start_month

    while month_cursor <= end_month:
        year = month_cursor.year
        month = month_cursor.month

        xml = fetch_month_posts(year, month, cookies, headers)
        xml_posts.extend(list(ET.fromstring(xml).iter('entry')))

        with open('posts-xml/{0}-{1:02d}.xml'.format(year, month), 'w+', encoding='utf-8') as file:
            file.write(xml)
        
        month_cursor = month_cursor + relativedelta(months=1)  

    json_posts = list(map(xml_to_json, xml_posts))
    with open('posts-json/all.json', 'w', encoding='utf-8') as f:
        f.write(json.dumps(json_posts, ensure_ascii=False, indent=2))

    return json_posts

if __name__ == '__main__':
    download_posts()
