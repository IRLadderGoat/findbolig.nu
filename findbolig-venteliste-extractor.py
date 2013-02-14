import argparse
import logging
import urllib
import urllib2
from cookielib import CookieJar
import sys
import re
import time
import json
import csv
import datetime

log = logging.getLogger(__name__)
logging.getLogger('pyactiveresource').setLevel(logging.WARNING)

class FindBoligNuClient:
	URL_base = "http://www.findbolig.nu/"
	URL_secure_base = "https://www.findbolig.nu/"
	URL_login = URL_base+"logind.aspx"
	URL_venteliste = URL_base+"Findbolig-nu/Min-side/ventelisteboliger/opskrivninger.aspx?"
	URL_placement = URL_secure_base+"Services/WaitlistService.asmx/GetWaitlistRank"
	opener = None
	def __init__(self):
		log.info("Initializing the findbolig.nu client")
		cj = CookieJar()
		self.opener = urllib2.build_opener(urllib2.HTTPCookieProcessor(cj))
		response = self.opener.open(FindBoligNuClient.URL_base)
		if "Findbolig.nu" not in response.read():
			log.error("It seems like the findbolig.nu website is down or has changed a lot.")
			sys.exit(-1);

	def login(self, username, password):
		log.info("Logging into %s using username '%s'", FindBoligNuClient.URL_login, username)
		# Fetch the regular login page.
		request = urllib2.Request(self.URL_login)
		response = self.opener.open(request)
		# Extract input names and values
		data = dict()
		content = response.read()
		input_fields = re.findall("<input(.*)>", content, flags=re.IGNORECASE)
		for field in input_fields:
			name = re.findall('.*name="([^"]*)".*', field)
			value = re.findall('.*value="([^"]*)".*', field)
			if name:
				if value:
					data[name[0]] = value[0]
				else:
					data[name[0]] = ""
		data["ctl00$placeholdercontent_1$txt_UserName"] = username
		data["ctl00$placeholdercontent_1$txt_Password"] = password
		data["__EVENTTARGET"] = "ctl00$placeholdercontent_1$but_Login"
		data["__EVENTARGUMENT"] = ""

		# Encode the data
		data = urllib.urlencode(data)
		request = urllib2.Request(self.URL_login, data)
		response = self.opener.open(request)
		content = response.read()
		if "Log af" in content:
			# Extract users full name.
			name = re.search('<span id="fm1_lbl_userName">(.*)&nbsp;</span>', content)
			log.info("Logged in as %s", name.group(1))
			return True
		else:
			return False

	def extract_waitinglist_references(self):
		result = []
		response = self.opener.open(self.URL_venteliste)
		content = response.read()
		table_content = re.search('<table[^>]*id="GridView_Results"[^>]*>(.*?)</table>', content, flags=re.IGNORECASE|re.DOTALL)
		if table_content:
			table_content = table_content.group(1)
			rows = re.findall('<tr class="rowstyle"[^>]*>(.*?)</tr>', table_content, flags=re.IGNORECASE|re.DOTALL)
			for row in rows:
				#collumn = re.findall('<td[^>]*>(.*?)</td>', row, flags=re.IGNORECASE|re.DOTALL)
				bid = re.search('href="\/Ejendomspraesentation.aspx\?bid=([^"]*)"', row, flags=re.IGNORECASE|re.DOTALL)
				if bid:
					bid = int(bid.group(1))
					result.append(bid)
		return result

	def extract_waitinglist_placements(self, bids, sleep=1):
		result = {}
		for bid in bids:
			log.debug("Requesting placement on building #%u.", bid)
			data = "{buildingId:%u}" % bid
			request = urllib2.Request(self.URL_placement, data)
			request.add_header('Content-Type', 'application/json; charset=UTF-8')
			response = self.opener.open(request)
			if response:
				response = json.loads(response.read())
				if response["d"] and response["d"]["WaitPlacement"]:
					result[str(bid)] = int(response["d"]["WaitPlacement"])
					log.debug("It was %u.", result[str(bid)])
				else:
					raise RuntimeError("Error reading a placement: Error in JSON structure.")
			else:
				raise RuntimeError("Error reading a placement.")
			time.sleep(sleep)
		return result

def write_data(data):
	fieldnames_temp = set()
	try:
		output_file = open(args.output,'r')
		reader = csv.DictReader(output_file, delimiter=',')
		all_data = list(reader)

		# Extract the fieldnames
		if reader.fieldnames:
			for name in reader.fieldnames:
				if name != "date":
					fieldnames_temp.add(str(name))

		output_file.close()
	except IOError:
		log.info("There was no existing data in the datafile.")
		all_data = list()

	# Do a union over all elements of the list.
	fieldnames = ["date"]
	fieldnames_temp |= set(data.keys())
	fieldnames.extend(list(fieldnames_temp))

	# Insert the date as the first field.
	data["date"] = datetime.datetime.now().date().isoformat()
	# Add this datapoint as new data.
	all_data.append(data)

	output_file = open(args.output,'wb')
	writer = csv.DictWriter(output_file, delimiter=',', fieldnames=fieldnames)
	writer.writeheader()
	writer.writerows(all_data)
	output_file.close()

if __name__ == "__main__":
	parser = argparse.ArgumentParser()
	parser.add_argument('-u', '--username', help='Your username on findbolig.nu.', required=True)
	parser.add_argument('-p', '--password', help='Your password on findbolig.nu.', required=True)
	parser.add_argument('-o', '--output', help='The output file.', required=True)
	parser.add_argument('-l', '--log', help='Set the log level to debug.', default='WARNING')
	args = parser.parse_args()

	numeric_level = getattr(logging, args.log.upper(), None)
	if not isinstance(numeric_level, int):
		raise ValueError('Invalid log level: %s' % args.log)
	logging.basicConfig(format='%(levelname)s\t%(message)s', level=numeric_level)

	print "findbolig.nu venteliste extractor v.0.1\n"

	client = FindBoligNuClient()
	success = client.login(args.username, args.password)
	if not success:
		log.error("Couldn't login using the credentials provided.")
		sys.exit(-2)
	# Fetch bids for all buildings on the whishlist.
	venteliste_bids = client.extract_waitinglist_references()
	# Iterate the list of bids and return a dict of the placements.
	venteliste_placements = client.extract_waitinglist_placements(venteliste_bids, 0)
	# Append to the datafile.
	write_data(venteliste_placements)
