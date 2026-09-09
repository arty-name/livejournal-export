from getpass import getpass
from sys import exit as sysexit
import json
import os
from pathlib import Path
import tempfile

import requests

from utilities import ExportError


def get_cookie_value(response, name):
    try:
        # get the 'Set-Cookie' key from the headers dict and parse it
        header = response.headers.get('Set-Cookie')

        if header:
            return header.split(f'{name}=')[1].split(';')[0]
        else:
            raise ValueError(f'Cookie {name} not found in response.')

    except Exception as exception:
        print(f'Error extracting required cookie: {name}. Error: {exception}. Exiting.')
        sysexit(1)


def get_luid_cookie():
    """ This cookie is required for submitting authentication requests """
    try:
        # generic headers to prevent LiveJournal from throwing out this random solicitation
        headers = {
            'Upgrade-Insecure-Requests': '1',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36 OPR/113.0.0.0',
            'sec-ch-ua': '"Chromium";v="127"',
            'sec-ch-ua-platform': '"Windows"',
        }

        response = requests.get('https://www.livejournal.com/', headers=headers)

        return get_cookie_value(response, 'luid')
    except Exception as exception:
        print(f'Could not retrieve pre-connection cookie from www.livejournal.com. Error: {exception}. Exiting.')
        sysexit(1)


def get_authenticated_cookies():
    global cachedUsername
    cookies = {
        'luid': get_luid_cookie()
    }

    credentials = {
        'user': input('Enter LiveJournal Username: ').strip(),
        'password': getpass('Enter LiveJournal Password: ')
    }

    # login with user credentials and retrieve the two cookies required for the main script functions
    response = requests.post('https://www.livejournal.com/login.bml', data=credentials, cookies=cookies)

    if not response.ok:
        print(f'Error! Return code: {response.status_code}')
        sysexit(1)

    # prepare two cookies necessary for the authenticated requests
    authenticated_cookies = {
        'ljloggedin': get_cookie_value(response, 'ljloggedin'),
        'ljmastersession': get_cookie_value(response, 'ljmastersession')
    }
    cachedUsername = credentials['user'].casefold()
    print('Login successful!')
    return authenticated_cookies


headers = {
    'User-Agent': 'https://github.com/arty-name/livejournal-export; me@arty.name'
}

cachedCookies = None
cachedUsername = None


def authenticated_request_params():
    global cachedCookies

    if cachedCookies is None:
        cachedCookies = get_authenticated_cookies()

    return {
        'headers': headers,
        'cookies': cachedCookies,
    }


def bind_export_account(*, resume=False):
    """Bind new or legacy exports on first use; every later run checks ownership."""
    authenticated_request_params()
    if not cachedUsername:
        raise ExportError('Cannot identify the account for the saved export.')
    folder = Path('posts-xml')
    folder.mkdir(exist_ok=True)
    manifest = folder / '.account.json'

    def check_existing():
        try:
            account = json.loads(manifest.read_text(encoding='utf-8'))['username']
        except (OSError, ValueError, KeyError, TypeError):
            raise ExportError('Cannot read posts-xml/.account.json; cache left unchanged.') from None
        if account != cachedUsername:
            raise ExportError(
                'The saved export belongs to another account. Use that account '
                'for this directory, or a separate directory for a different journal.'
            )

    if manifest.exists():
        check_existing()
        return
    fd, temporary = tempfile.mkstemp(prefix='.account-', dir=folder)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as file:
            json.dump({'username': cachedUsername}, file)
            file.flush()
            os.fsync(file.fileno())
        try:
            os.link(temporary, manifest)
        except FileExistsError:
            check_existing()
    finally:
        os.unlink(temporary)
