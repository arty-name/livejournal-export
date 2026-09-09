#!/usr/bin/python3

import os
import json
from pathlib import Path
import xml.etree.ElementTree as ET

from authentication import authenticated_request_params, bind_export_account
from download_posts import _atomic_write
import requests

from utilities import ExportError


def fetch_xml(params):
    response = requests.get(
        'https://www.livejournal.com/export_comments.bml',
        params=params,
        **authenticated_request_params(),
    )
    return response.text


def _validated_batch(xml, kind, path, *, cached):
    """Reject error pages and incomplete batches before accepting a cache."""
    try:
        root = ET.fromstring(xml)
        allowed = ({'comments', 'usermaps', 'maxid', 'nextid'}
                   if kind == 'comment_meta' else {'comments'})
        if (root.tag != 'livejournal' or (root.text or '').strip()
                or any(child.tag not in allowed or (child.tail or '').strip()
                       for child in root)
                or len(root.findall('comments')) != 1
                or any(len(root.findall(tag)) > 1 for tag in allowed)):
            raise ValueError('Unexpected comments export structure')
        comments = root.find('comments')
        if ((comments.text or '').strip()
                or any(child.tag != 'comment' or (child.tail or '').strip()
                       for child in comments)):
            raise ValueError('Unexpected comments list')
        for comment in comments:
            int(comment.attrib['id'])
            if kind == 'comment_body':
                int(comment.attrib['jitemid'])
                for attribute in ('parentid', 'posterid'):
                    if attribute in comment.attrib:
                        int(comment.attrib[attribute])
                if any(child.tag not in {'date', 'subject', 'body'} for child in comment):
                    raise ValueError('Unexpected comment body structure')
        if kind == 'comment_meta':
            if int(root.findtext('maxid')) < 0:
                raise ValueError('Invalid maximum comment ID')
            if root.find('nextid') is not None:
                int(root.findtext('nextid'))
            for user in root.iter('usermap'):
                user.attrib['id']
                user.attrib['user']
        return root
    except (ET.ParseError, ValueError, TypeError, KeyError):
        detail = ('The existing file was kept. Inspect it or move it aside before retrying.'
                  if cached else 'No comment batch was saved. Retry with --resume.')
        raise ExportError(
            f'{path}: invalid LiveJournal {kind} XML. {detail}'
        ) from None


def _load_batch(kind, start_id, *, resume):
    path = Path(f'comments-xml/{kind}-{start_id}.xml')
    cached = resume and path.exists()
    if cached:
        try:
            xml = path.read_text(encoding='utf-8')
        except (OSError, UnicodeError):
            raise ExportError(
                f'{path}: could not read the cached comment batch. '
                'The existing file was kept; check its encoding and permissions.'
            ) from None
        print(f'Using saved {kind} from ID {start_id}...', flush=True)
    else:
        print(f'Downloading {kind} from ID {start_id}...', flush=True)
        xml = fetch_xml({'get': kind, 'startid': start_id})
    root = _validated_batch(xml, kind, path, cached=cached)
    if kind == 'comment_body':
        ids = [int(comment.attrib['id']) for comment in root.find('comments')]
        if not ids or max(ids) < start_id:
            detail = ('The existing file was kept; inspect it or move it aside before retrying.'
                      if cached else 'No comment batch was saved; retry with --resume.')
            raise ExportError(
                f'{path}: comment export made no progress before the advertised maximum ID. '
                f'{detail}'
            )
    if kind == 'comment_meta':
        next_id = root.findtext('nextid')
        if next_id is not None and int(next_id) <= start_id:
            detail = ('The existing file was kept; inspect it or move it aside before retrying.'
                      if cached else 'No comment batch was saved; retry with --resume.')
            raise ExportError(
                f'{path}: comment metadata returned a non-advancing next ID. {detail}'
            )
    if not cached:
        _atomic_write(path, xml, replace=not resume)
    return root

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


def get_more_comments(start_id, users, resume=False):
    comments = []
    local_max_id = -1

    root = _load_batch('comment_body', start_id, resume=resume)

    for comment_xml in root.iter('comment'):
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


def comment_meta(resume=False):
    start_id = 0
    last_id = -1

    while start_id is not None and start_id > last_id:
        metadata = _load_batch('comment_meta', start_id, resume=resume)
        yield metadata

        last_id = start_id
        next_id = metadata.findtext('nextid')
        start_id = next_id and int(next_id)


def download_comments(resume=False):
    bind_export_account(resume=resume)
    os.makedirs('comments-xml', exist_ok=True)
    os.makedirs('comments-json', exist_ok=True)

    users = {}
    max_id = None

    for metadata in comment_meta(resume=resume):
        users.update(get_users_map(metadata))

        if max_id is None:
            max_id = int(metadata.findtext('maxid'))

    _atomic_write('comments-json/usermap.json',
                  json.dumps(users, ensure_ascii=False, indent=2), replace=True)

    all_comments = []
    start_id = 0
    while max_id is not None and start_id < max_id:
        next_id, comments = get_more_comments(start_id + 1, users, resume=resume)
        if next_id <= start_id:
            raise ExportError(
                f'comments-xml/comment_body-{start_id + 1}.xml: comment export made no '
                'progress before the advertised maximum ID. Existing files were kept; '
                'inspect this batch before retrying with --resume.'
            )
        start_id = next_id
        all_comments.extend(comments)

    _atomic_write('comments-json/all.json',
                  json.dumps(all_comments, ensure_ascii=False, indent=2), replace=True)

    return all_comments


if __name__ == '__main__':
    download_comments()
