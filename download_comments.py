#!/usr/bin/python3

import os
import requests
import xml.etree.ElementTree as ET

from authentication import authenticated_request_params
from utilities import save_json_file, save_text_file


def fetch_xml(params):
    response = requests.get(
        'https://www.livejournal.com/export_comments.bml',
        params=params,
        **authenticated_request_params(),
    )

    return response.text


def get_users_map(xml):
    users = {}

    for user in xml.iter('usermap'):
        users[user.attrib['id']] = user.attrib['user']

    return users


def get_comment_property(name, comment_xml, comment):
    if name in comment_xml.attrib:
        comment[name] = int(comment_xml.attrib[name])


def get_comment_element(name, comment_xml, comment):
    elements = comment_xml.findall(name)
    if len(elements) > 0:
        comment[name] = elements[0].text


def get_more_comments(start_id, users):
    comments = []
    local_max_id = -1

    xml = fetch_xml({'get': 'comment_body', 'startid': start_id})
    save_text_file(f'comments-xml/comment_body-{start_id}.xml', xml)

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
            comment['author'] = users.get(str(comment['posterid']), 'deleted-user')

        local_max_id = max(local_max_id, comment['id'])
        comments.append(comment)

    return local_max_id, comments


def comment_meta():
    start_id = 0
    last_id = -1

    while start_id is not None and start_id > last_id:
        xml = fetch_xml({'get': 'comment_meta', 'startid': start_id})
        save_text_file(f'comments-xml/comment_meta-{start_id}.xml', xml)

        metadata = ET.fromstring(xml)
        yield metadata

        last_id = start_id
        next_id = metadata.findtext('nextid')
        start_id = next_id and int(next_id)


def download_comments():
    os.makedirs('comments-xml', exist_ok=True)
    os.makedirs('comments-json', exist_ok=True)

    users = {}
    max_id = None

    for metadata in comment_meta():
        users.update(get_users_map(metadata))

        if max_id is None:
            max_id = int(metadata.findtext('maxid'))

    save_json_file('comments-json/usermap.json', users)

    all_comments = []
    start_id = 0
    while max_id is not None and start_id < max_id:
        start_id, comments = get_more_comments(start_id + 1, users)
        all_comments.extend(comments)

    save_json_file('comments-json/all.json', all_comments)

    return all_comments


if __name__ == '__main__':
    download_comments()
