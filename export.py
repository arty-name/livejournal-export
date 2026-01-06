#!/usr/bin/python3

import os
import json
import re
import html2text
import requests
from sys import exit as sysexit
from bs4 import BeautifulSoup
from getpass import getpass
from datetime import datetime
from markdown import markdown
from operator import itemgetter
from download_posts import download_posts
from download_comments import download_comments
from utilities import save_json_file, save_text_file


def get_cookie_value(response, cName):
    try:
        header = response.headers.get('Set-Cookie')

        if header:
            return header.split(f'{cName}=')[1].split(';')[0]
        else:
            raise ValueError(f'Cookie {cName} not found in response.')

    except Exception as e:
        print(f"Error extracting required cookie: {cName}. Error: {e}. Exiting...")
        sysexit(1)


# Generic headers to prevent LiveJournal from throwing out this random solicitation
headers = {
    "Upgrade-Insecure-Requests": "1",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36 OPR/113.0.0.0",
    "sec-ch-ua": '"Chromium";v="127"',
    "sec-ch-ua-platform": '"Windows"',
}

# Get a "luid" cookie so it'll accept our form login.
try:
    response = requests.get("https://www.livejournal.com/", headers=headers)
except Exception as e:
    # If attempt to reach LiveJournal fails, error out.
    print(f"Could not retrieve pre-connection cookie from www.livejournal.com. Error: {e}. Exiting.")
    sysexit(1)

cookies = {
    'luid': get_cookie_value(response, 'luid')
}

# Populate dictionary for request
credentials = {
    'user': input("Enter LiveJournal Username: "),
    'password': getpass("Enter LiveJournal Password: ")
}

# Login with user credentials and retrieve the two cookies required for the main script functions
response = requests.post("https://www.livejournal.com/login.bml", data=credentials, cookies=cookies)

# If not successful, whine about it.
if response.status_code != 200:
    print("Error - Return code:", response.status_code)

# If successful, then get the 'Set-Cookie' key from the headers dict and parse it for the two cookies, placing them in a cookies dict
cookies = {
    'ljloggedin': get_cookie_value(response, 'ljloggedin'),
    'ljmastersession': get_cookie_value(response, 'ljmastersession')
}

# Credit to the Author!
headers = {
    'User-Agent': 'https://github.com/arty-name/livejournal-export; me@arty.name'
}

# Now that we have the cookies, notify the user that we'll grab the LJ posts and comments
print("Login successful. Downloading posts and comments.")
print(
    "When complete, you will find post-... and comment-... folders in the current location\ncontaining the differently formated versions of your content.")

COMMENTS_HEADER = 'Комментарии'

TAG = re.compile(r' src="http://utx.ambience.ru/img/.*?/(.*?)/"')
TAG_MD = re.compile(r'\[!\[(.*?)]\(http://utx.ambience.ru/img/.*?\)]\(.*?\)')
USER = re.compile(r'<lj user="?(.*?)"?>')
TAGLESS_NEWLINES = re.compile(r'(?<!>)\n')
NEWLINES = re.compile(r'(\s*\n){3,}')

SLUGS = {}


# TODO: lj-cut


def fix_user_links(json):
    """ replace user links with usernames """
    if 'subject' in json:
        json['subject'] = USER.sub(r'\1', json['subject'])

    if 'body' in json:
        json['body'] = USER.sub(r'\1', json['body'])


def json_to_html(json):
    subject = json['subject'] or json['date']
    body = TAGLESS_NEWLINES.sub('<br>\n', json['body'])

    return f"""<!doctype html>
<meta charset="utf-8">
<title>{subject}</title>
<article>
<h1>{subject}</h1>
{body}
</article>
"""


def get_slug(json):
    slug = json['subject']
    if not len(slug):
        slug = json['id']

    if '<' in slug or '&' in slug:
        slug = BeautifulSoup(f'<p>{slug}</p>', features='lxml').text

    slug = re.compile(r'\W+').sub('-', slug)
    slug = re.compile(r'^-|-$').sub('', slug)

    if slug in SLUGS:
        slug += (len(slug) and '-' or '') + json['id']

    SLUGS[slug] = True

    return slug


def enrich_post(json):
    json['subject'] = json['subject'] or json['date']
    json['slug'] = get_slug(json)
    json['tags'] = TAG.findall(json['body'])


def json_to_markdown(json):
    body = TAGLESS_NEWLINES.sub('<br>', json['body'])

    h = html2text.HTML2Text()
    h.body_width = 0
    h.unicode_snob = True
    body = h.handle(body)
    body = NEWLINES.sub('\n\n', body)

    # remove UTX tags from text
    body = TAG_MD.sub('', body).strip()

    tags = json['tags']
    tags_text = len(tags) and f'\ntags: {', '.join(tags)}' or ''

    return f"""id: {json['id']}
title: {json['subject']}
slug: {json['slug']}
date: {json['date']}{tags_text}

{body}
"""


def group_comments_by_post(comments):
    posts = {}

    for comment in comments:
        post_id = comment['jitemid']

        if post_id not in posts:
            posts[post_id] = {}

        post = posts[post_id]
        post[comment['id']] = comment

    return posts


def nest_comments(comments):
    post = []

    for comment in comments.values():
        fix_user_links(comment)

        if 'parentid' not in comment:
            post.append(comment)
        else:
            comments[comment['parentid']]['children'].append(comment)

    return post


def comment_to_li(comment):
    if 'state' in comment and comment['state'] == 'D':
        return ''

    author = comment.get('author', 'anonym')
    subject = comment.get('subject', '')
    html = f'<h3>{author}: {subject}</h3>'
    html += f'\n<a id="comment-{comment['id']}"></a>'

    if 'body' in comment:
        html += '\n' + markdown(TAGLESS_NEWLINES.sub('<br>\n', comment['body']))

    if len(comment['children']) > 0:
        html += '\n' + comments_to_html(comment['children'])

    subject_class = 'subject' in comment and ' class=subject' or ''
    return f'<li{subject_class}>{html}\n</li>'


def comments_to_html(comments):
    children = '\n'.join(map(comment_to_li, sorted(comments, key=itemgetter('id'))))
    return f'<ul>\n{children}\n</ul>'


def save_as_json(id, json_post, post_comments):
    json_data = {'id': id, 'post': json_post, 'comments': post_comments}
    save_json_file(f'posts-json/{id}.json', json_data)


def save_as_markdown(id, subfolder, json_post, post_comments_html):
    os.makedirs(f'posts-markdown/{subfolder}', exist_ok=True)
    save_text_file(f'posts-markdown/{subfolder}/{id}.md', json_to_markdown(json_post))
    if post_comments_html:
        save_text_file(f'comments-markdown/{json_post['slug']}.md', post_comments_html)


def save_as_html(id, subfolder, json_post, post_comments_html):
    os.makedirs(f'posts-html/{subfolder}', exist_ok=True)

    html = json_to_html(json_post)
    if post_comments_html:
        html += f'\n<h2>{COMMENTS_HEADER}</h2>\n{post_comments_html}'

    save_text_file(f'posts-html/{subfolder}/{id}.html', html)


def combine(all_posts, all_comments):
    os.makedirs('posts-html', exist_ok=True)
    os.makedirs('posts-markdown', exist_ok=True)
    os.makedirs('comments-markdown', exist_ok=True)

    posts_comments = group_comments_by_post(all_comments)

    for json_post in all_posts:
        id = json_post['id']
        jitemid = int(id) >> 8

        date = datetime.strptime(json_post['date'], '%Y-%m-%d %H:%M:%S')
        subfolder = f'{date.year}-{date.month:02d}'

        post_comments = jitemid in posts_comments and nest_comments(posts_comments[jitemid]) or None
        post_comments_html = post_comments and comments_to_html(post_comments) or ''

        fix_user_links(json_post)
        enrich_post(json_post)

        save_as_json(id, json_post, post_comments)
        save_as_html(id, subfolder, json_post, post_comments_html)
        save_as_markdown(id, subfolder, json_post, post_comments_html)


if __name__ == '__main__':
    if True:
        all_posts = download_posts(cookies, headers)
        all_comments = download_comments(cookies, headers)

    else:
        with open('posts-json/all.json', 'r', encoding='utf-8') as f:
            all_posts = json.load(f)
        with open('comments-json/all.json', 'r', encoding='utf-8') as f:
            all_comments = json.load(f)

    combine(all_posts, all_comments)
