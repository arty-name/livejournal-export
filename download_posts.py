#!/usr/bin/python3

import os
import json
import tempfile
from pathlib import Path
from sys import exit as sysexit
import xml.etree.ElementTree as ET
from datetime import datetime
from dateutil.relativedelta import relativedelta

from authentication import authenticated_request_params, bind_export_account
import requests

from utilities import ExportError

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


max_id = 0


def get_max_id():
    global max_id
    max_id += 1
    return max_id


def xml_to_json(xml):
    def f(field):
        return xml.findtext(field)

    item_id = f('itemid')
    return {
        'id': int(item_id) if item_id is not None else get_max_id(),
        'date': f('logtime') or f('eventtime'),
        'subject': f('subject') or '',
        'body': f('event'),
        'eventtime': f('eventtime'),
        'security': f('security'),
        'allowmask': f('allowmask'),
        'current_music': f('current_music'),
        'current_mood': f('current_mood')
    }


def _month_entries(xml, path, *, cached):
    """Accept only the monthly export envelope, never an error or login page."""
    try:
        root = ET.fromstring(xml)
        if (root.tag != 'livejournal' or (root.text or '').strip()
                or any(child.tag != 'entry' or (child.tail or '').strip() for child in root)):
            raise ValueError('Unexpected export structure')
        return list(root)
    except (ET.ParseError, ValueError):
        if cached:
            detail = ('The existing file was kept. Inspect it or move it aside '
                      'before retrying this month.')
        else:
            detail = 'No month file was saved. Retry the export to resume.'
        raise ExportError(
            f'{path}: invalid monthly LiveJournal XML. {detail}'
        ) from None


def _atomic_write(path, content, *, replace):
    """Publish complete files only; a new monthly cache must never clobber a file."""
    path = Path(path)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
                mode='w', encoding='utf-8', dir=path.parent,
                prefix=f'.{path.name}.', suffix='.tmp', delete=False) as output:
            temporary = Path(output.name)
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
        if replace:
            os.replace(temporary, path)
        else:
            # link() atomically creates the target and fails if it already exists.
            os.link(temporary, path)
    except OSError:
        raise ExportError(
            f'{path}: could not save the completed export. '
            'Existing files were kept; check available space and file permissions.'
        ) from None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def download_posts(resume=False):
    start_month, end_month = get_months()
    if end_month < start_month:
        raise ExportError('End month must not be earlier than start month.')

    # Check ownership before reading caches or overwriting any previous export.
    bind_export_account(resume=resume)
    os.makedirs('posts-xml', exist_ok=True)
    os.makedirs('posts-json', exist_ok=True)

    xml_posts = []
    month_cursor = start_month

    while month_cursor <= end_month:
        year = month_cursor.year
        month = month_cursor.month

        path = Path(f'posts-xml/{year}-{month:02d}.xml')
        if resume and path.exists():
            try:
                xml = path.read_text(encoding='utf-8')
            except (OSError, UnicodeError):
                raise ExportError(
                    f'{path}: could not read the cached month. '
                    'The existing file was kept; check its encoding and permissions.'
                ) from None
            entries = _month_entries(xml, path, cached=True)
            print(f'Using saved posts for {year}-{month:02d} ({len(entries)} entries)...',
                  flush=True)
        else:
            print(f'Downloading posts for {year}-{month:02d}...', flush=True)
            xml = fetch_month_posts(year, month)
            entries = _month_entries(xml, path, cached=False)
            _atomic_write(path, xml, replace=not resume)
        xml_posts.extend(entries)

        month_cursor = month_cursor + relativedelta(months=1)

    json_posts = list(map(xml_to_json, xml_posts))
    _atomic_write('posts-json/all.json',
                  json.dumps(json_posts, ensure_ascii=False, indent=2), replace=True)

    return json_posts


if __name__ == '__main__':
    download_posts()
