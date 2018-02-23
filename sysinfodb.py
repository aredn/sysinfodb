#!/usr/bin/python
#
# Part of AREDN -- Used for creating Amateur Radio Emergency Data Networks
# Copyright (C) 2018 Darryl Quinn
#  Additional contributors: Conrad Lara
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation version 3 of the License.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
# Additional Terms:
#
# Additional use restrictions exist on the AREDN(TM) trademark and logo.
#   See AREDNLicense.txt for more info.
#
# Attributions to the AREDN Project must be retained in the source code.
# If importing this code into a new or existing project attribution
# to the AREDN project must be added to the source code.
#
# You must not misrepresent the origin of the material contained within.
#
# Modified versions must be modified to attribute to the original source
# and be marked in reasonable ways as differentiate it from the original
# version.
#
# added ConfigParser
import os
import sys
import json
import bottle
import datetime
import pprint

from bottle import hook, route, run, request, abort, response, static_file
from pymongo import MongoClient
from pymongo.errors import WriteError, DuplicateKeyError

import httplib, urllib
import ConfigParser

# Get config
config=ConfigParser.ConfigParser({'app_token' : '', 'user_token' : '', 'enabled' : 'False', 'baseuri' : 'http://usercontent.arednmesh.org/K/5/K5DLQ/', 'host' : '0.0.0.0', 'port' : '8080', 'dbhost' : 'mongodb', 'dbport' : '27017'})
configdata=config.read("sysinfodb.ini")

# Avoid 'noSection' exceptions
if not config.has_section('pushover'):
    config.add_section('pushover')
if not config.has_section('server'):
    config.add_section('server')

# Set config values
po_apptoken=config.get("pushover","app_token")
po_usertoken=config.get("pushover","user_token")
po_enabled=config.get("pushover","enabled")
server_baseuri=config.get("pushover","baseuri")
server_host=config.get("server","host")
server_port=config.getint("server","port")
database_host=config.get("server","dbhost")
database_port=config.getint("server","dbport")

#
# CALL FROM A NODE:
# 1. load CURL
# 2. wget -q -O- http://localnode:8080/cgi-bin/sysinfo.json|curl -H 'Accept: application/json' -X PUT -T - http://10.43.81.87:8080/sysinfo

connection = MongoClient(database_host, database_port)
db = connection.aredn
collection = db.sysinfo

def static_file_cors(*args, **kwargs):
    response = static_file(*args, **kwargs)
    response.set_header('Access-Control-Allow-Origin', '*')
    return response

@route('/sysinfo', method='PUT')
def put_sysinfo():
    entity=json.load(request.body)

    # Add _id key and set to NODE name
    i = find_index(entity['interfaces'],'name','eth0')
    entity['_id']=str(entity['interfaces'][i]['mac']).upper()

    # Add audit information
    entity['audit'] = {};
    entity['audit']['last_updated']=str(datetime.datetime.utcnow())
    entity['audit']['source_ip']= request.environ.get('HTTP_X_FORWARDED_FOR')

    # validate lat/lon values
    if entity['lat']:
        if float(entity['lat']) < -90 or float(entity['lat']) > 90:
            print "ERROR: Invalid LAT: {0}".format(entity['lat'])
            entity['lat']=""
    if entity['lon']:
        if float(entity['lon']) < -180 or float(entity['lon']) > 180:
            print "ERROR: Invalid LON: {0}".format(entity['lon'])
            entity['lon']=""

    try:
        collection.save(entity)

        # Regenerate the KML file ---------------
        get_genmap()

        if entity['lat'] and entity['lon']:
        	# Notify via Pushover
        	pushover(entity)
    except WriteError as ve:
        print str(ve)
        abort(400, str(ve))

# protect with Apache
@route('/sysinfo/:id', method='GET')
def get_sysinfo_node(id):
    entity = collection.find_one({'node':id})
    if not entity:
        abort(404, 'No sysinfo node named %s' % id)
    #entity=scrub_decode_keys(entity)
    return entity

# protect with Apache
@route('/sysinfo/mac/:id', method='GET')
def get_sysinfo_node(id):
    entity = collection.find_one({'_id':id})
    if not entity:
        abort(404, 'No sysinfo node with eth0 mac %s' % id)
    #entity=scrub_decode_keys(entity)
    return entity

# protect with Apache
# regenerate the map.kml
@route('/genmap', method='GET')
def get_genmap():
    try:
        os.system("./mongo_kml.py")
    except Exception, e:
        print str(e)

    response.content_type = 'text/html'
    return 'ok'

# return the complete map.kml
@route('/map.kml', method='GET')
def get_mapkml():
    return static_file_cors('mongo_kml.kml',root='.')

# return the map9.kml
@route('/map9.kml', method='GET')
def get_map9kml():
    return static_file_cors('mongo_kml9.kml',root='.')

# return the map2.kml
@route('/map2.kml', method='GET')
def get_map2kml():
    return static_file_cors('mongo_kml2.kml',root='.')

# return the map3.kml
@route('/map3.kml', method='GET')
def get_map3kml():
    return static_file_cors('mongo_kml3.kml',root='.')

# return the map.kml
@route('/map5.kml', method='GET')
def get_map5kml():
    return static_file_cors('mongo_kml5.kml',root='.')

# return the links.kml
@route('/links.kml', method='GET')
def get_maplinkskml():
    return static_file_cors('mongo_kmllinks.kml',root='.')

# change certain keys with '.N' to '(N)' --- NOT NEEDED ANYMORE
def scrub_encode_keys(j):
    # scrub interface keys
    for i in j['interfaces']:
        if i['name']=='eth0.1':
            i['name']= 'eth0(1)'
        if i['name']=='eth0.2':
            i['name']= 'eth0(2)'
    return j

# change certain keys with '(N)' back to '.N' --- NOT NEEDED ANYMORE
def scrub_decode_keys(j):
    # scrub interface keys
    for i in j['interfaces']:
        if i['name']=='eth0(1)':
            i['name']= 'eth0.1'
        if i['name']=='eth0(2)':
            i['name']= 'eth0.2'
    return j

def find_index(dicts, key, value):
    class Null: pass
    for i, d in enumerate(dicts):
        if d.get(key, Null) == value:
            return i
    else:
        raise ValueError('no dict with the key and value combination found')

def pushover(e):
    return
    conn = httplib.HTTPSConnection("api.pushover.net:443")
    conn.request("POST", "/1/messages.json",
        urllib.urlencode({
            "sound": "none",
            "token": po_apptoken,
            "user": po_usertoken,
            "message": "Sysinfo received: " + e['node'],
            "url_title": "View on Map",
            "url": server_baseuri + "livemap.html?z=10&lat=" + e['lat'] + "&lon=" + e['lon'] ,
        }),
        { "Content-type": "application/x-www-form-urlencoded" })
    conn.getresponse()

run(host=server_host, port=server_port)
