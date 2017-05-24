import urllib
import json
import uuid
from datetime import datetime
from google.appengine.api import memcache
from google.appengine.api import users
from google.appengine.ext import db
from google.appengine.api import urlfetch
import cgi
import random
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'lib'))
import pytz
from dateutil import parser
from icalendar import Calendar, Event
from bs4 import BeautifulSoup

opml = """<?xml version="1.0" encoding="utf-8"?>
<opml version="1.1">
  <head>
  </head>
  <body>
    <outline text="BBC Radio Podcasts">
%s
    </outline>
  </body>
</opml>"""


class UserPrefs(db.Model):
    id = db.StringProperty()
    email = db.StringProperty()
    programmes = db.TextProperty()


if os.environ['REQUEST_METHOD'] == 'POST':
    print 'Content-Type: text/plain'
    print

    user = users.get_current_user()
    userprefs = db.Query(UserPrefs).filter('id =', user.user_id()).get()
    if not userprefs:
        userprefs = UserPrefs(id=user.user_id(), email=user.email())
    userprefs.programmes = sys.stdin.read()
    userprefs.put()

    print userprefs.key(),
else:
    if 'u' in cgi.FieldStorage():
        userprefs = UserPrefs.get(cgi.FieldStorage()['u'].value)
        programmes = json.loads(userprefs.programmes)

        if os.environ['PATH_INFO'].endswith('.ics'):
            print 'Content-Type: text/calendar'
            print

            cal = Calendar()
            cal.add('prodid', '-//Events Calendar//iCal4j 1.0//EN')
            cal.add('version', '2.0')
            cal.add('x-wr-calname', 'Programmes')

            urlfetch.set_default_fetch_deadline(10)
            for programme in programmes:
                html = memcache.get(programme)
                if html is None:
                    html = urllib.urlopen('http://www.bbc.co.uk/programmes/%s/broadcasts/upcoming' % programme).read()
                    memcache.add(programme, html, 60 * 60 * random.randint(24, 48))  # cache for between 24 and 48 hours (inclusive)
                soup = BeautifulSoup(html, 'html.parser')
                title = soup.find(class_='br-masthead__title').text.strip()
                for e in soup.find_all(class_='broadcast'):
                    description = e.find(class_='programme__synopsis').text.strip()
                    if '(R)' not in description:
                        start = e.find(attrs={'property': 'startDate'})['content']
                        end = e.find(attrs={'property': 'endDate'})['content']
                        summary = e.find(class_='programme__title').text.strip()
                        event = Event()
                        event.add('dtstart', parser.parse(start).astimezone(pytz.timezone('Europe/London')))
                        event.add('dtend', parser.parse(end).astimezone(pytz.timezone('Europe/London')))
                        event.add('dtstamp', parser.parse(start).astimezone(pytz.timezone('Europe/London')))
                        event.add('summary', title)
                        event['uid'] = str(uuid.uuid4())
                        event.add('description', '%s: %s' % (summary, description))
                        cal.add_component(event)

            print cal.to_ical(),
        elif os.environ['PATH_INFO'].endswith('.opml'):
            print 'Content-Type: application/xml'
            print

            from xml.etree import ElementTree
            u = urllib.urlopen('http://www.bbc.co.uk/podcasts.opml')
            xml = ElementTree.parse(u)
            u.close()
            outlines = []
            for programme in programmes:
                element = xml.find('.//outline[@htmlUrl=\"http://www.bbc.co.uk/programmes/%s\"]' % programme)
                if element is not None:
                    outlines.append('<outline text="%s" type="rss" xmlUrl="%s"/>' % (element.get('text'), element.get('xmlUrl')))
            print opml % '\n'.join(outlines)
    else:
        print 'Content-Type: application/json'
        print

        user = users.get_current_user()
        userprefs = db.Query(UserPrefs).filter('id =', user.user_id()).get()

        print json.dumps({'u': str(userprefs.key()), 'programmes': json.loads(userprefs.programmes)}) if userprefs else '{}'
