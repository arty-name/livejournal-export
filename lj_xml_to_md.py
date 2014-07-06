#!/usr/bin/python3

SOURCE_FOLDER = '/tmp/blog/'

import glob
import xml.etree.ElementTree as ET
from datetime import datetime
from bs4 import BeautifulSoup
import html2text
import re

TAG = re.compile(r'!\[(.*?)\]\(http:\/\/utx.ambience.ru\/img\/_arty.*?\)')
USER = re.compile(r'<lj user="(.*?)">')


def get_plain_subject(subject, date):
    plain_subject = subject.replace('/', '-')
    if '<' in plain_subject:
        plain_subject = BeautifulSoup('<p>' + plain_subject + '<p>').text
    if len(plain_subject):
        plain_subject = '-' + plain_subject
    else:
        plain_subject = date.strftime('-%d %H:%M:%S')
    return plain_subject


for filename in glob.glob('%s*.xml' % SOURCE_FOLDER):
    for entry in ET.parse(filename).iter('entry'):
        
        def g(field):
            return entry.find(field).text

        # get fields
        id = g('itemid')
        date = datetime.strptime(g('logtime'), '%Y-%m-%d %H:%M:%S')
        subject = g('subject') or ''
        body = g('event')

        # fix common issues with source
        body = body.replace('\n', '<br>')
        body = body.replace('&mdash;', '—')
        # replace user links with usernames
        body = USER.sub(r'\1', body)

        # convert html to markdown
        h = html2text.HTML2Text()
        h.body_width = 0
        body = h.handle(body)

        # read UTX tags
        tags = TAG.findall(body)
        # remove UTX tags from text
        body = TAG.sub('', body)

        plain_subject = get_plain_subject(subject, date)

        with open(u'%smd/%d-%02d%s.md' % (SOURCE_FOLDER, date.year, date.month, plain_subject), 'w+') as file:

            file.writelines((
                '---\n',
                ('id: %s\n' % id),
                ('title: %s\n' % subject),
                ('date: %s\n' % date)
            ))

            if len(tags):
                file.writelines('tags:\n')
                file.writelines(map(lambda t: '- %s\n' % t, tags))

            file.writelines([
                '---\n',
                '\n'
            ])
            file.write(body)
