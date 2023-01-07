#!/usr/bin/python3

import json
import os
import re
import html2text
import markdown
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from operator import itemgetter
from download_posts import download_posts
from download_comments import download_comments

COMMENTS_HEADER = 'Комментарии'

TAG = re.compile(r'\[!\[(.*?)\]\(http:\/\/utx.ambience.ru\/img\/.*?\)\]\(.*?\)')
USER = re.compile(r'<lj user="?(.*?)"?>')
TAGLESS_NEWLINES = re.compile('(?<!>)\n')
NEWLINES = re.compile('(\s*\n){3,}')
TIME_ZONE = 3 # GMT+03:00 for Moscow
SLUGS = {}

# TODO: lj-cut


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
        subject=json['subject'] or json['eventtime'],
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


def deescape(escaped_str) -> str:
    # Remove extra \ before . or -
    return re.sub(r'[\\]+([\.\-])', r'\1', escaped_str)


def json_to_markdown(json):
    body = TAGLESS_NEWLINES.sub('<br>', json['body'])

    h = html2text.HTML2Text()
    h.body_width = 0
    h.unicode_snob = True
    body = h.handle(body)
    body = NEWLINES.sub('\n\n', body)

    # read UTX tags
    tags = TAG.findall(body)
    json['tags'] = len(tags) and '\ntags: {0}'.format(', '.join(tags)) or ''

    # remove UTX tags from text
    json['body'] = TAG.sub('', body).strip()

    json['slug'] = get_slug(json)
    json['subject'] = json['subject'] or json['eventtime']

    return """id: {id}
title: {subject}
slug: {slug}
date: {eventtime}{tags}

{body}
""".format(**json)


def json_to_alt_markdown(json):
    body = TAGLESS_NEWLINES.sub('<br>', json['body'])

    h = html2text.HTML2Text()
    h.body_width = 0
    h.unicode_snob = True
    body = h.handle(body)
    body = NEWLINES.sub('\n\n', body)

    # read UTX tags
    tags = TAG.findall(body)
    json['tags'] = len(tags) and '\ntags: {0}'.format(', '.join(tags)) or ''

    # remove UTX tags from text
    json['body'] = TAG.sub('', body).strip()

    json['slug'] = get_slug(json)
    json['subject'] = json['subject'] or json['eventtime']

    # get post time
    post_date = str(datetime.strptime(json['eventtime'],"%Y-%m-%d %H:%M:%S"))
    post_time = post_date[11:16] # Post's time = HH:MM
    note_header = '## {0}\n_{1}_\n'.format(json['subject'], post_time)

    attrs = {
        'current_music': 'music',
        'current_mood': 'mood',
        'tags': 'tags',
    }

    post_attributes = ''.join([attrs[attr] + ':: ' + json[attr] + '\n' for attr in attrs if (attr in json and json[attr] not in (None, ''))])

    if len(post_attributes) > 0 : post_attributes += '\n'

    return note_header + post_attributes + deescape(json['body'])


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
        html += '\n' + markdown.markdown(TAGLESS_NEWLINES.sub('<br>\n', comment['body']))

    if len(comment['children']) > 0:
        html += '\n' + comments_to_html(comment['children'])

    subject_class = 'subject' in comment and ' class=subject' or ''
    return '<li{0}>{1}\n</li>'.format(subject_class, html)


def comment_to_li_markdown(comment):
    if 'state' in comment and comment['state'] == 'D':
        return ''

    comment_date = str(datetime.strptime(comment['date'],"%Y-%m-%dT%H:%M:%SZ") + timedelta(hours = TIME_ZONE))

    html = '#### [[{0}]]:\n_{1}_\n'.format(comment.get('author', 'anonym'), comment_date[:16])

    if 'subject' in comment:
        html += '**' + comment['subject'] + '**\n'

    if 'body' in comment:
        html += comment['body'] + '\n\n'

    if len(comment['children']) > 0:
        html += comments_to_markdown(comment['children'])

    return html


def comments_to_html(comments):
    return '<ul>\n{0}\n</ul>'.format('\n'.join(map(comment_to_li, sorted(comments, key=itemgetter('id')))))


def comments_to_markdown(comments):
    return ''.join(map(comment_to_li_markdown, sorted(comments, key=itemgetter('id'))))

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


def save_together_as_markdown(id, subfolder, json_post, post_comments_html):
    subfolder = json_post['eventtime'][:4] # Note's year
    note_name = json_post['eventtime'][:10] # Note's file name = YYYY-MM-DD
    os.makedirs('posts-and-comments-markdown/{0}'.format(subfolder), exist_ok=True)
    with open('posts-and-comments-markdown/{0}/{1}.md'.format(subfolder, note_name), 'a', encoding='utf-8') as f:
        f.write(json_to_alt_markdown(json_post) + '\n\n')
        if post_comments_html:
            f.write('### Комментарии\n\n' + post_comments_html)


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
    os.makedirs('posts-and-comments-markdown', exist_ok=True)

    posts_comments = group_comments_by_post(all_comments)

    for json_post in all_posts:
        id = json_post['id']
        jitemid = int(id) >> 8

        date = datetime.strptime(json_post['eventtime'], '%Y-%m-%d %H:%M:%S')
        subfolder = '{0.year}-{0.month:02d}-{0.day:02d}'.format(date)

        post_comments = jitemid in posts_comments and nest_comments(posts_comments[jitemid]) or None
        post_comments_html = post_comments and comments_to_html(post_comments) or ''
        post_comments_markdown = post_comments and comments_to_markdown(post_comments) or ''

        fix_user_links(json_post)

        save_as_json(id, json_post, post_comments)
        save_as_html(id, subfolder, json_post, post_comments_html)
        save_as_markdown(id, subfolder, json_post, post_comments_html)
        save_together_as_markdown(id, subfolder, json_post, post_comments_markdown)


if __name__ == '__main__':
    if True:
        all_posts = download_posts()
        all_comments = download_comments()

    else:
        with open('posts-json/all.json', 'r', encoding='utf-8') as f:
            all_posts = json.load(f)
        with open('comments-json/all.json', 'r', encoding='utf-8') as f:
            all_comments = json.load(f)

    combine(all_posts, all_comments)
