#!/usr/bin/python3

import json
import os 
import requests 
from sys import exit as sysexit
import xml.etree.ElementTree as ET

# At original import time, first request range of years. We'll add 1 to the end year automatically.
try:
    startYear = int(input("Enter first year you want to export: "))
    endYear = int(input("Enter last year you want to export: "))
except:
    print("\nI'm guessing you didn't enter a whole number there, did ya? Wanna try again? Exiting...")
    sysexit(1)

YEARS = range(startYear, endYear + 1)  # first to (last + 1)

# Added cookies and headers to the definition for scope
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

# Added cookies and headers to the definition as they'll now be passed by the main python script
def download_posts(cookies, headers):
    cookies = cookies
    headers = headers
    os.makedirs('posts-xml', exist_ok=True)
    os.makedirs('posts-json', exist_ok=True)

    xml_posts = []
    for year in YEARS:
        for month in range(1, 13):
            xml = fetch_month_posts(year, month, cookies, headers)
            #print("XML content:", xml)
            xml_posts.extend(list(ET.fromstring(xml).iter('entry')))

            with open('posts-xml/{0}-{1:02d}.xml'.format(year, month), 'w+', encoding='utf-8') as file:
                file.write(xml)

    json_posts = list(map(xml_to_json, xml_posts))
    with open('posts-json/all.json', 'w', encoding='utf-8') as f:
        f.write(json.dumps(json_posts, ensure_ascii=False, indent=2))

    return json_posts

if __name__ == '__main__':
    download_posts()
