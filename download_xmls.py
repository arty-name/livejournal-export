#!/usr/bin/python3

USERNAME = '_arty'
YEARS = range(2003, 2015)  # first to (last + 1)
TARGET_FOLDER = '/tmp/blog/'

# copy values of these cookies for LJ from your browser after logging in
cookies = {
    'ljident': 'TODO',
    'ljloggedin': 'TODO',
    'ljmastersession': 'TODO',
    'ljsession': 'TODO',
    'ljuniq': 'TODO'
}

import requests

for year in YEARS:
    for month in range(1, 13):
        r = requests.post(
            'http://www.livejournal.com/export_do.bml',
            params={'authas': USERNAME},
            cookies=cookies,
            data={
                'what': 'journal',
                'year': year,
                'month': ('%02d' % month),
                'format': 'xml',
                'header': 'on',
                'encid': '2',
                'field_itemid': 'on',
                'field_logtime': 'on',
                'field_subject': 'on',
                'field_event': 'on'
            }
        )
        with open('%s%d-%02d.xml' % (TARGET_FOLDER, year, month), 'w+') as file:
            file.write(r.text)
