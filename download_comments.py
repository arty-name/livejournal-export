#!/usr/bin/env python3

import os
import json
import requests
import xml.etree.ElementTree as ET

def fetch_xml(params, cookies, headers):
    response = requests.get(
        'https://www.livejournal.com/export_comments.bml',
        params=params,
        headers=headers,
        cookies=cookies
    )

    return response.text


def get_users_map(xml):
    users = {}

    for user in xml.iter('usermap'):
        users[user.attrib['id']] = user.attrib['user']

    with open('comments-json/usermap.json', 'w', encoding='utf-8') as f:
        f.write(json.dumps(users, ensure_ascii=False, indent=2))

    return users


def get_comment_property(name, comment_xml, comment):
    if name in comment_xml.attrib:
        comment[name] = int(comment_xml.attrib[name])


def get_comment_element(name, comment_xml, comment):
    elements = comment_xml.findall(name)
    if len(elements) > 0:
        comment[name] = elements[0].text


def get_more_comments(start_id, users, cookies, headers):
    comments = []
    local_max_id = -1

    xml = fetch_xml({'get': 'comment_body', 'startid': start_id}, cookies, headers)
    with open('comments-xml/comment_body-{0}.xml'.format(start_id), 'w', encoding='utf-8') as f:
        f.write(xml)

    for comment_xml in ET.fromstring(xml).iter('comment'):
        comment = {
            'jitemid': int(comment_xml.attrib['jitemid']),
            'id': int(comment_xml.attrib['id']),
            'children': []
        }
        get_comment_property('parentid', comment_xml, comment)
        get_comment_property('posterid', comment_xml, comment)
        get_comment_element('date', comment_xml, comment)
        get_comment_element('subject', comment_xml, comment)
        get_comment_element('body', comment_xml, comment)

        if 'state' in comment_xml.attrib:
            comment['state'] = comment_xml.attrib['state']

        if 'posterid' in comment:
            comment['author'] = users.get(str(comment['posterid']), "deleted-user")

        local_max_id = max(local_max_id, comment['id'])
        comments.append(comment)

    return local_max_id, comments

def download_comments(cookies, headers):
    os.makedirs('comments-xml', exist_ok=True)
    os.makedirs('comments-json', exist_ok=True)

    metadata_xml = fetch_xml({'get': 'comment_meta', 'startid': 0}, cookies, headers)
    with open('comments-xml/comment_meta.xml', 'w', encoding='utf-8') as f:
        f.write(metadata_xml)

    metadata = ET.fromstring(metadata_xml)
    users = get_users_map(metadata)

    all_comments = []
    start_id = 0
    max_id = int(metadata.find('maxid').text)
    while start_id < max_id:
        start_id, comments = get_more_comments(start_id + 1, users, cookies, headers)
        all_comments.extend(comments)

    with open('comments-json/all.json', 'w', encoding='utf-8') as f:
        f.write(json.dumps(all_comments, ensure_ascii=False, indent=2))

    return all_comments


if __name__ == '__main__':
    download_comments()
