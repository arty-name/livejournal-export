from getpass import getpass
from sys import exit as sysexit

from http_client import request


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

        response = request('GET', '/', headers=headers)

        return get_cookie_value(response, 'luid')
    except Exception as exception:
        print(f'Could not retrieve pre-connection cookie from www.livejournal.com. Error: {exception}. Exiting.')
        sysexit(1)


def get_authenticated_cookies():
    cookies = {
        'luid': get_luid_cookie()
    }

    credentials = {
        'user': input('Enter LiveJournal Username: '),
        'password': getpass('Enter LiveJournal Password: ')
    }

    # login with user credentials and retrieve the two cookies required for the main script functions
    response = request('POST', '/login.bml', data=credentials, cookies=cookies)

    if not response.ok:
        print(f'Error! Return code: {response.status_code}')
        sysexit(1)

    # prepare two cookies necessary for the authenticated requests
    authenticated_cookies = {
        'ljloggedin': get_cookie_value(response, 'ljloggedin'),
        'ljmastersession': get_cookie_value(response, 'ljmastersession')
    }
    print('Login successful!')
    return authenticated_cookies


headers = {
    'User-Agent': 'https://github.com/arty-name/livejournal-export; me@arty.name'
}

cachedCookies = None


def authenticated_request_params():
    global cachedCookies

    if cachedCookies is None:
        cachedCookies = get_authenticated_cookies()

    return {
        'headers': headers,
        'cookies': cachedCookies,
    }
