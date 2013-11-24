import urllib
import json
import uuid
from datetime import datetime
from google.appengine.api import memcache
from google.appengine.api import users
from google.appengine.ext import db
import cgi
import random

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'lib'))

import pytz
from dateutil import parser
from icalendar import Calendar, Event

opml="""<?xml version="1.0" encoding="utf-8"?>
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

		#u = urllib.urlopen('http://dl.dropbox.com/u/1120779/proglist.json')
		#programmes = json.load(u)
		#u.close()

		if os.environ['PATH_INFO'].endswith('.ics'):
			print 'Content-Type: text/calendar'
			print

			cal = Calendar()
			cal.add('prodid', '-//Events Calendar//iCal4j 1.0//EN')
			cal.add('version', '2.0')
			cal.add('x-wr-calname', 'Programmes')
			#cal.add('x-wr-caldesc', 'Programmes')

			for programme in programmes:
				j = memcache.get(programme)
				if j is None:
					#u = urllib.urlopen('http://www.bbc.co.uk/programmes/%s/episodes/upcoming.json' % programme)
					u = urllib.urlopen('http://www.bbc.co.uk/programmes/%s/episodes/upcoming/debut.json' % programme)
					try:
						j = json.load(u)
					except ValueError:
						continue
					finally:
						u.close()
					memcache.add(programme, j, 60 * 60 * random.randint(24, 48)) #cache for between 24 and 48 hours (inclusive)
				for broadcast in j['broadcasts']:
					if broadcast['start'] == broadcast['programme']['first_broadcast_date'] and broadcast['service']['title'] in programmes[programme]:
					#if broadcast['service']['title'] in programmes[programme]:
						episode = broadcast['programme']
						series = episode['programme'] if 'programme' in episode['programme'] else None
						brand = episode['programme']['programme'] if 'programme' in episode['programme'] else episode['programme']

						summary = '%s (%s)' % (brand['title'], broadcast['service']['title'])
						description = 'Series %s, Episode %s of %s - ' % (series['position'], episode['position'], series['expected_child_count']) if series else ''
						description += '%s: %s' % (episode['title'], episode['short_synopsis'])

						event = Event()
						# event.add('dtstart', parser.parse(broadcast['start'], ignoretz=True))
						# event.add('dtend', parser.parse(broadcast['end'], ignoretz=True))
						# event.add('dtstamp', parser.parse(broadcast['start'], ignoretz=True))
						event.add('dtstart', parser.parse(broadcast['start']).astimezone(pytz.timezone("Europe/London")))
						event.add('dtend', parser.parse(broadcast['end']).astimezone(pytz.timezone("Europe/London")))
						event.add('dtstamp', parser.parse(broadcast['start']).astimezone(pytz.timezone("Europe/London")))
						event.add('summary', summary)
						event['uid'] = str(uuid.uuid4())
						event.add('description', description)
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
				element = xml.find(".//outline[@htmlUrl=\"http://www.bbc.co.uk/programmes/%s\"]" % programme)
				if element is not None:
					outlines.append('<outline text="%s" type="rss" xmlUrl="%s"/>' % (element.get('text'), element.get('xmlUrl')))
			print opml % '\n'.join(outlines)
	else:
		print 'Content-Type: application/json'
		print

		user = users.get_current_user()
		userprefs = db.Query(UserPrefs).filter('id =', user.user_id()).get()

		print json.dumps({'u': str(userprefs.key()), 'programmes': json.loads(userprefs.programmes)}) if userprefs else '{}'
