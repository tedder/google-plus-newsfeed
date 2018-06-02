#!/usr/bin/env python3

# https://developers.google.com/api-client-library/python/guide/aaa_apikeys
# https://developers.google.com/+/web/api/rest/latest/activities/list#examples

## COPYRIGHT, MIT license
#
# Copyright 2018 tedder.me
#
# Permission is hereby granted, free of charge, to any person obtaining a copy of this
# software and associated documentation files (the "Software"), to deal in the Software
# without restriction, including without limitation the rights to use, copy, modify,
# merge, publish, distribute, sublicense, and/or sell copies of the Software, and to
# permit persons to whom the Software is furnished to do so, subject to the following
# conditions:
#
# The above copyright notice and this permission notice shall be included in all copies
# or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR
# PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE
# LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT,
# TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE
# OR OTHER DEALINGS IN THE SOFTWARE.
#

#import oauth2client.client
import google.oauth2.service_account
import googleapiclient.discovery
import json
import boto3
import sys
from bs4 import BeautifulSoup

S3_KEY = 'rss/google-plus-eliasbakken.json'
DEBUG = 0

def get_secret(secret_name):
  sc = boto3.client('secretsmanager', region_name='us-east-1')
  sc_ret = sc.get_secret_value( SecretId=secret_name )

  if 'SecretString' in sc_ret:
    secret = sc_ret['SecretString']
    return secret
  else:
    if DEBUG: print(sc_ret)
    binary_secret_data = sc_ret['SecretBinary']
    return binary_secret_data


def build_attachment(att):
  #print("att: {}".format(att))
  ret = {
    'url': att['url'],
    'mime_type': att['fullImage']['type'],
    'url': att['fullImage']['url'],
    'title': att['displayName'],
  }
  return ret

def build_item_html(title, entry):
  #print(json.dumps(entry['object']['replies'], indent=2))
  #print("{object[replies][selfLink]}".format(**entry))
  counts = '<a href="{object[replies][selfLink]}">{object[replies][totalItems]} replies</a>, <a href="{object[plusoners][selfLink]}">{object[plusoners][totalItems]} +1s</a>, <a href="{object[resharers][selfLink]}">{object[resharers][totalItems]} reshares</a>'.format(**entry)
  img = ''
  #print("att: {}".format(entry['object'].get('attachments', [])))
  for att in entry['object'].get('attachments', []):
    if att['objectType'] == 'photo':
      img = '<img src="{}">'.format(att['fullImage']['url'])
      #print("img: {}".format(img))

  atts = ''
  for a in entry['object'].get('attachments', []):
    if a['objectType'] == 'photo':
      pass # handling this above.
    elif a['objectType'] != 'photo':
      # we should append weird stuff to html
      atts += '<br /><div>{}: <a href="{}">{}</a>'.format(a['objectType'], a['url'], a['displayName'])
      if a.get('image'):
        atts += '<img src="{}"><br />'.format(a['image']['url'])
      atts += "</div>\n"
      continue
    else: print('unknown object type {}: {}'.format(a['objectType'], a))

  ret = '<div style="font-weight: bold">{}</div><br />{}<br /><div>{}</div> {} {}'.format(title, entry['object']['content'], counts, atts, img)
  return ret

def build_item(entry,title_override=None):
  title = title_override or entry['title']
  ret = {
    'id': entry['id'],
    'date_published': entry['published'], # ex: "2017-12-23T01:05:48.127Z",
    'date_modified': entry['updated'],
    'url': entry['url'],
    'title': title,
    #'content_html': entry['object']['content'],
    'content_html': build_item_html(title, entry),
    'attachments': [],
  }

  # make a text version (no, it's ugly)
  #soup = BeautifulSoup(ret['content_html'], 'lxml')
  #ret['content'] = soup.get_text(soup.get_text())

  for a in entry['object'].get('attachments', []):
    # handling non-photos in build_item_html
    if a['objectType'] == 'photo':
      ret['attachments'].append(build_attachment(a))
  return ret

def main_template(items):
  ret = {
    'version': '1',
    'title': "EliasBakken's Google Plus feed",
    'home_page_url': 'https://plus.google.com/+EliasBakken',
    'feed_url': 'https://dyn.tedder.me/' + S3_KEY,
    'description': 'entries pulled by tedder from plus API.',
    'author': { 'name': 'Elias Bakken', 'url': 'https://plus.google.com/+EliasBakken' },
    'items': items,
  }
  return ret

def grab(service):
  activities_resource = service.activities()
  activities_document = activities_resource.list(
    userId='112892827905040807193',
    collection='public',
    maxResults='20').execute()

  if DEBUG: print(json.dumps(activities_document, indent=2))
  if DEBUG: sys.exit(0)

  items = []
  for activity in activities_document['items']:
    title_override = None
    if activity['verb'] == 'post' and activity['object']['objectType'] == 'note':
      pass # most likely activity
    elif activity['verb'] == 'share' and activity['object']['objectType'] == 'activity':
      title_override = activity['provider']['title'] + ':' + activity['annotation']
    elif activity['verb'] != 'post' or activity['object']['objectType'] != 'note':
      print('unknown activity {}, type {}\njson: {}'.format(activity['verb'], activity['object']['objectType'], json.dumps(activity, indent=2)))
      continue
    thisitem = build_item(activity, title_override=title_override)
    #print(json.dumps(thisitem, indent=2))
    items.append(thisitem)

    #request = service.activities().list_next(request, activities_document)

  feedtxt = main_template(items)
  s3 = boto3.client('s3')
  ztxt = json.dumps(feedtxt, indent=2)
  s3ret = s3.put_object(
    ACL='public-read',
    Body=ztxt,
    Bucket='dyn.tedder.me',
    Key=S3_KEY,
    ContentType='application/json',
    CacheControl='public, max-age=3600',
  )
  if DEBUG: print(ztxt)
  with open('tmp.json', 'w') as o:
    o.write(ztxt)

  if not s3ret['ResponseMetadata'].get('HTTPStatusCode') == 200:
    print("s3 upload failed? {}".format(s3ret))


  if DEBUG: print("-- {}".format(s3ret))


secrets = json.loads(get_secret('google_plus_api_ted'))
creds = google.oauth2.service_account.Credentials.from_service_account_info(secrets)
service = googleapiclient.discovery.build('plus', 'v1', credentials=creds)
grab(service)

