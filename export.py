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

# Generic headers to prevent LiveJournal from throwing out this random solicitation
headers = {
    "Upgrade-Insecure-Requests": "1",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36 OPR/113.0.0.0",
    "sec-ch-ua": '"Chromium";v="127"',
    "sec-ch-ua-platform": '"Windows"',
}

try:
    # Get a "luid" cookie so it'll accept our form login.
    cookies = {
        'luid': requests.get("https://www.livejournal.com/", headers=headers).headers.get('Set-Cookie').split('luid=')[1].split(';')[0]
    }

except:
    # If attempt to reach LiveJournal fails, error out.
    print("Couldn't reach www.livejournal.com, please check internet connection. Exiting.")
    sysexit(1)

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
curlOUTPUT = response.headers.get('Set-Cookie')
ljloggedin_match = re.search(r'ljloggedin=([^\s;]+)', curlOUTPUT)
ljmastersession_match = re.search(r'ljmastersession=([^\s;]+)', curlOUTPUT)
cookies = {
    'ljloggedin': ljloggedin_match.group(1) if ljloggedin_match else None,
    'ljmastersession': ljmastersession_match.group(1) if ljmastersession_match else None,
}

# Credit to the Author!
headers = {
    'User-Agent': 'https://github.com/arty-name/livejournal-export; me@arty.name'
}

# If a cookie could not be successfully acquired, error out. Otherwise, get to work.
if any(value is None for value in cookies.values()):
    print("Could not extract cookie data despite successful login.")
    sysexit(1)
else: 
    print("Login successful. Downloading posts and comments.")
    print("When complete, you will find post-... and comment-... folders in the current location contained the different versions of your content.")

# The real work:
COMMENTS_HEADER = 'Комментарии'

TAG = re.compile(r'\[!\[(.*?)\]\(http:\/\/utx.ambience.ru\/img\/.*?\)\]\(.*?\)')
USER = re.compile(r'<lj user="?(.*?)"?>')
TAGLESS_NEWLINES = re.compile(r'(?<!>)\n')
NEWLINES = re.compile(r'(\s*\n){3,}')

SLUGS = {}

def fix_user_links(json):
    """ replace user links with usernames """
    if 'subject' in json:
        json['subject'] = USER.sub(r'\1', json['subject'])

    if 'body' in json:
        json['body'] = USER.sub(r'\1', json['body'])

def json_to_html(json):
    return """<!doctype html>
<meta charset="utf-8">
<title>{subject}</title>
<article>
<h1>{subject}</h1>
{body}
</article>
""".format(
        subject=json['subject'] or json['date'],
        body=TAGLESS_NEWLINES.sub('<br>\n', json['body'])
    )

def get_slug(json):
    slug = json['subject']
    if not len(slug):
        slug = json['id']

    if '<' in slug or '&' in slug:
        slug = BeautifulSoup('<p>{0}</p>'.format(slug), features='lxml').text

    slug = re.compile(r'\W+').sub('-', slug)
    slug = re.compile(r'^-|-$').sub('', slug)

    if slug in SLUGS:
        slug += (len(slug) and '-' or '') + json['id']

    SLUGS[slug] = True

    return slug


def json_to_markdown(json):
    body = TAGLESS_NEWLINES.sub('<br>', json['body'])

    h = html2text.HTML2Text()
    h.body_width = 0
    h.unicode_snob = True
    body = h.handle(body)
    body = NEWLINES.sub('\n\n', body)
    tags = TAG.findall(body)
    json['tags'] = len(tags) and '\ntags: {0}'.format(', '.join(tags)) or ''
    json['body'] = TAG.sub('', body).strip()
    json['slug'] = get_slug(json)
    json['subject'] = json['subject'] or json['date']
    return """id: {id}
title: {subject}
slug: {slug}
date: {date}{tags}

{body}
""".format(**json)


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

    html = '<h3>{0}: {1}</h3>'.format(comment.get('author', 'anonym'), comment.get('subject', ''))
    html += '\n<a id="comment-{0}"></a>'.format(comment['id'])

    if 'body' in comment:
        html += '\n' + markdown(TAGLESS_NEWLINES.sub('<br>\n', comment['body']))

    if len(comment['children']) > 0:
        html += '\n' + comments_to_html(comment['children'])

    subject_class = 'subject' in comment and ' class=subject' or ''
    return '<li{0}>{1}\n</li>'.format(subject_class, html)


def comments_to_html(comments):
    return '<ul>\n{0}\n</ul>'.format('\n'.join(map(comment_to_li, sorted(comments, key=itemgetter('id')))))

def save_as_json(id, json_post, post_comments):
    json_data = {'id': id, 'post': json_post, 'comments': post_comments}
    with open('posts-json/{0}.json'.format(id), 'w', encoding='utf-8') as f:
        f.write(json.dumps(json_data, ensure_ascii=False, indent=2))

def save_as_markdown(id, subfolder, json_post, post_comments_html):
    os.makedirs('posts-markdown/{0}'.format(subfolder), exist_ok=True)
    with open('posts-markdown/{0}/{1}.md'.format(subfolder, id), 'w', encoding='utf-8') as f:
        f.write(json_to_markdown(json_post))
    if post_comments_html:
        with open('comments-markdown/{0}.md'.format(json_post['slug']), 'w', encoding='utf-8') as f:
            f.write(post_comments_html)

def save_as_html(id, subfolder, json_post, post_comments_html):
    os.makedirs('posts-html/{0}'.format(subfolder), exist_ok=True)
    with open('posts-html/{0}/{1}.html'.format(subfolder, id), 'w', encoding='utf-8') as f:
        f.writelines(json_to_html(json_post))
        if post_comments_html:
            f.write('\n<h2>{0}</h2>\n'.format(COMMENTS_HEADER) + post_comments_html)

def combine(all_posts, all_comments):
    os.makedirs('posts-html', exist_ok=True)
    os.makedirs('posts-markdown', exist_ok=True)
    os.makedirs('comments-markdown', exist_ok=True)

    posts_comments = group_comments_by_post(all_comments)

    for json_post in all_posts:
        id = json_post['id']
        jitemid = int(id) >> 8

        date = datetime.strptime(json_post['date'], '%Y-%m-%d %H:%M:%S')
        subfolder = '{0.year}-{0.month:02d}'.format(date)

        post_comments = jitemid in posts_comments and nest_comments(posts_comments[jitemid]) or None
        post_comments_html = post_comments and comments_to_html(post_comments) or ''

        fix_user_links(json_post)

        save_as_json(id, json_post, post_comments)
        save_as_html(id, subfolder, json_post, post_comments_html)
        save_as_markdown(id, subfolder, json_post, post_comments_html)

if __name__ == '__main__':
    if True:
        # modified these calls to include cookies and headers since they can't be imported from auth.py anymore
        all_posts = download_posts(cookies, headers)
        all_comments = download_comments(cookies, headers)

    else:
        with open('posts-json/all.json', 'r', encoding='utf-8') as f:
            all_posts = json.load(f)
        with open('comments-json/all.json', 'r', encoding='utf-8') as f:
            all_comments = json.load(f)

    combine(all_posts, all_comments)
