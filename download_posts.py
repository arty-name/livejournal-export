#!/usr/bin/python3

import json
import os
import requests
from sys import exit as sysexit
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta

DATE_FORMAT = '%Y%m%d'

def get_date_input(prompt):
    try:
        start_date = int(input("Enter start date in YYYYMMDD format: "))
    except Exception as e:
        print(f"\nError: {e}. Exiting...")
        sysexit(1)

    try:
        end_date = int(input("Enter end date in YYYYMMDD format: "))
    except Exception as e:
        print(f"\nError: {e}. Exiting...")
        sysexit(1)
    return start_date, end_date

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
    print(response.text)
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

def increment_month(date):
    return date + relativedelta(months=1, day=1)

def download_posts(cookies, headers):
    os.makedirs('posts-xml', exist_ok=True)
    os.makedirs('posts-json', exist_ok=True)

    # Get start and end dates with validation
    start_date, end_date =  get_date_input("Enter start date in YYYYMMDD format: ")
    processing_datetime = datetime.strptime(str(start_date), DATE_FORMAT)
    end_date = datetime.strptime(str(end_date), DATE_FORMAT) #converting to datetime object
    xml_posts = []

    while processing_datetime <= end_date:
        year = processing_datetime.year
        month = processing_datetime.month

        xml = fetch_month_posts(year, month, cookies, headers)
        xml_posts.extend(list(ET.fromstring(xml).iter('entry')))

        with open('posts-xml/{0}-{1:02d}.xml'.format(year, month), 'w+', encoding='utf-8') as file:
            file.write(xml)
        
        processing_datetime = increment_month(processing_datetime)  # Move to next month

    json_posts = list(map(xml_to_json, xml_posts))
    with open('posts-json/all.json', 'w', encoding='utf-8') as f:
        f.write(json.dumps(json_posts, ensure_ascii=False, indent=2))

    return json_posts

if __name__ == '__main__':
    download_posts()
