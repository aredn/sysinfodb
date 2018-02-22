#!/usr/bin/env python
'''Generate a KML document of a tour based on rotating around locations.
'''
from pykml.factory import nsmap
from pykml.factory import KML_ElementMaker as KML
from pykml.factory import GX_ElementMaker as GX
from pykml.parser import Schema
from lxml import etree
from bson.json_util import dumps
import json, requests, requests.exceptions
import sys, socket

from pymongo import MongoClient
from pymongo.errors import WriteError, DuplicateKeyError


import ConfigParser

# Get config
config=ConfigParser.ConfigParser({'baseuri' : 'http://usercontent.aredn.org/K/5/K5DLQ/', 'dbhost' : 'mongodb', 'dbport' : '27017'})
configdata=config.read("sysinfodb.ini")
if not config.has_section('server'):
    config.add_section('server')
server_baseuri=config.get("server","baseuri")
database_host=config.get("server","dbhost")
database_port=config.getint("server","dbport")

FIRMWARE_CURRENT_VERSION="3.16.1.1"

#----------------
def board_icon(x):
  return {
    '2': 'wifi2',
    '3' : 'wifi3',
    '5' : 'wifi5',
    '9' : 'wifi9',
  }.get(x, 'wifi2')  # default value

#---------------- NO LONGER NEEDED as of develop-160+
def board_model(x):
  return {
    '0xe012': 'NanoStation M2', # nsm2
    'TP-Link CPE210 v1.0' : 'TP-Link CPE210 v1.0',
    'TP-Link CPE510 v1.0' : 'TP-Link CPE510 v1.0',
    '0xe005' : 'NanoStation M5',
    '0xe009' : 'NanoStation Loco M9',
    '0xe012' : 'NanoStation M2',
    '0xe035' : 'NanoStation M3',
    '0xe0a2' : 'NanoStation Loco M2',
    '0xe0a5' : 'NanoStation Loco M5',
    '0xe105' : 'Rocket M5',
    '0xe1b2' : 'Rocket M2',
    '0xe1b5' : 'Rocket M5',
    '0xe1b9' : 'Rocket M9',
    '0xe1c3' : 'Rocket M3',
    '0xe202' : 'Bullet M2 HP',
    '0xe205' : 'Bullet M5',
    '0xe212' : 'airGrid M2',
    '0xe215' : 'airGrid M5',
    '0xe232' : 'NanoBridge M2',
    '0xe239' : 'NanoBridge M9',
    '0xe242' : 'airGrid M2 HP',
    '0xe243' : 'NanoBridge M3',
    '0xe245' : 'airGrid M5 HP',
    '0xe252' : 'airGrid M2 HP',
    '0xe255' : 'airGrid M5 HP',
    '0xe2b5' : 'NanoBridge M5',
    '0xe2c2' : 'NanoBeam M2 International',
    '0xe2d2' : 'Bullet M2 Titanium HP',
    '0xe2d5' : 'Bullet M5 Titanium',
    '0xe302' : 'PicoStation M2',
    '0xe3e5' : 'PowerBeam M5 300',
    '0xe4a2' : 'AirRouter',
    '0xe4b2' : 'AirRouter HP',
    '0xe4e5' : 'PowerBeam M5 400',
    '0xe805' : 'NanoStation M5',
    '0xe815' : 'NanoBeam M5 16',
    '0xe825' : 'NanoBeam M5 19',
    '0xe835' : 'AirGrid M5 XW',
    '0xe855' : 'NanoStation M5 XW',
    '0xe866' : 'NanoStation M2 XW',
    '0xe867' : 'NanoStation Loco M2 XW',
    'Ubiquiti Nanostation M XW' : 'NanoStation M5 XW',
    'Ubiquiti Rocket M XW' : 'Rocket M XW',
    '0xe6b5' : 'Rocket M5 XW', #Rocket M5 XW
    '0xe8a5' : 'NanoStation Loco M5',
    'Ubiquiti Loco M XW' : 'NanoStation Loco M5 XW',
    'unknown': 'unknown',
  }.get(x, 'unknown')  # default value

#----------------
def styleIdExists(d, v):
  rc = False
  for s in d.Document.getchildren():
    if s.tag == '{' + s.nsmap.get(None) + '}Style':
      if s.attrib['id'] == v:
        rc = True
  return rc

#----------------
def createStyle(nstyle,iconurl):
  	return KML.Style(
    KML.LabelStyle(
      KML.scale(0),
    ),
    KML.IconStyle(
      KML.scale(1.0),
      KML.Icon(
          KML.href(iconurl)
      ),
    ),
    id=nstyle,
  )

def createLineStyle(nstyle):
  if nstyle.endswith('9'):
    color='FFFF78F0'
  elif nstyle.endswith('2'):
    color='FF78323C'
  elif nstyle.endswith('3'):
    color='FFF00014'
  elif nstyle.endswith('5'):
    color='FF0078F0'
  elif nstyle.endswith('t'):
    color='FF7800F0'

  return KML.Style(
    KML.LabelStyle(
      KML.scale(1),
    ),
    KML.LineStyle(
      KML.color(color),
      KML.width('3'),
    ),
    id=str(nstyle),
  )

def createKML(docid,iconurl):
  return KML.kml(
    KML.Document(
      KML.Style(
        KML.IconStyle(
          KML.scale(1.0),
          KML.Icon(
              KML.href(iconurl)
          ),
        ),
        id=docid,
      )
    )
  )

def createFolder(fname, fid):
  return KML.Folder(
    KML.name(fname),
    id=fid,
  )

def createPlacemark(node,nstyle,warn):
  firmware_version=""
  if warn==True:
    firmware_version="<font style='color:rgb(255,0,0)'>" + node['firmware_version'] + "</font>"
  else:
    firmware_version=node['firmware_version']

  desc="<a href=\"http://{name}.local.mesh:8080\">Node Console</a><br />Desc: {desc}<br/>FW ver: {firmware_ver}<br />Ch: {channel}<br />SSID: {ssid}<br />Tunnel installed: {hastunnel}<br />MAC: {mac}<br />Last updated: {lastmod}".format(
    name=node['name'],
    desc=node['desc'],
    firmware_ver=firmware_version,
    channel=node['channel'],
    ssid=node['ssid'],
    hastunnel=node['tunnel_installed'],
    mac=node['_id'],
    lastmod=node['audit']['last_updated'],
  )

  pm=KML.Placemark(
	KML.name(node['name']),
	KML.description(desc),
	KML.styleUrl('#' + nstyle),
	KML.Point(
	  KML.coordinates("{lon},{lat},{alt}".format(
	        lon=node['lon'],
	        lat=node['lat'],
	        alt=0,
	      )
	  )
	),
	id=node['name'].replace(' ','_')
	)
  return pm

def createLine(lineid, node1,node2,nstyle):
  return KML.Placemark(
    KML.name(lineid),
    KML.styleUrl('#' + str(nstyle)),
    KML.LineString(
      KML.tessellate('1'),
      KML.altitudeMode('clampToGround'),
      KML.coordinates("{lon},{lat},100,{lon2},{lat2},100".format(
        lon=node1['lon'],
        lat=node1['lat'],
        lon2=node2['lon'],
        lat2=node2['lat'],
        )
      )
    ),
    id=lineid
  )

def getBandCh(ch):
  band=2  # default
  ich=int(ch)
  if ich >= -2 and ich <= 6:
    band=2
  elif ich >= 3380 and ich <= 3495:
    band=3
  elif ich >= 133 and ich <= 184:
    band=5
  return band

def getBand(bid):
  #print "BOARD_ID=" + bid
  band=2  # default
  if bid=='0xe035':
    band=3
  elif bid=='0xe866': # NSLM2XW
    band=2
  elif bid=='0xe867': # NSM2XW
    band=2
  elif bid=='Ubiquiti Nanostation M XW':
    band=5
  elif bid=='Ubiquiti Rocket M XW':
    band=5
  elif bid=='Ubiquiti Loco M XW':
    band=5
  elif bid=='TP-Link CPE210 v1.0':
    band=2
  elif bid=='TP-Link CPE510 v1.0':
    band=5
  elif bid=='unknown':
    band=2
  else:
    #try:
    band=int(bid[len(bid)-1])
    #except ValueError, e:
    #  band=2
    #  pass
  return band

def getNodeIPs(node):
  ips=[]
  try:
    for i in node['interfaces']:
      if i['name'] not in ['eth0.1','eth1','wlan0-1']:
        ips.append(i['ip'])
  except Exception, e:
    pass
  return json.dumps(ips)  # because we don't want unicode

def getLinks(node):
  rc=[]
  nodeIPs=getNodeIPs(node)
  #if "172." in nodeIPs:
    #print "My IP's: " + str(nodeIPs)

  try:
    for l in node['olsr']['topology']:
      if l['destinationIP'] in nodeIPs:
        rc.append(str(l['lastHopIP']))
      #if l['lastHopIP'] in nodeIPs:
      #  rc.append(l['destinationIP'])
  except KeyError, e:
      pass
  return rc

def getNodeByIp(ip):
  node=[]
  try:
    #node=collection.find({'interfaces.ip': { '$eq': ip}},{'node':'true','lat':'true','lon':'true'})
    node=collection.find({ '$and': [{'interfaces.ip': { '$eq': ip}},{'lat': {'$ne': ''}},{'lon': {'$ne': ''}}]},{'node':'true','lat':'true','lon':'true'})
  except KeyError, e:
    pass
  except Exception, e:
    print "(getNodeByIp: " + e + ")"

  if node.count()>0:
    return json.loads(dumps(node[0]))
  else:
    return {}

def getNode(nodename):
  node=[]
  try:
    node=collection.find_one({ "node": { "$eq": nodename}})
  except KeyError, e:
    pass
  except Exception, e:
    print "(getNode: " + e + ")"
  return node

def writeFile(doc,suff,folder):
  doc.Document.append(folder)
  ofile = file(__file__.rstrip('.py') + suff +'.kml','w')
  ofile.write(etree.tostring(doc, pretty_print=True))
  try:
    assert(Schema("kml22gx.xsd").validate(doc))  
  except AssertionError, e:
    print "AssertionError on " + suff + " file"
    pass
  return True

def checkForWarnings(node):
	warn=False
  # check for non-current firmware versions
	if node['firmware_version']!=FIRMWARE_CURRENT_VERSION:
		warn=True
	return warn
#----------------

#icon_src='http://www.aredn.org/sites/default/files/ubnt_icons/'
icon_src=server_baseuri

# define a variable for the Google Extensions namespace URL string
gxns = '{' + nsmap['gx'] + '}'

warnbgcolor="3214E7FF"

node_list=[]
d={}
links=[]
warn=False

# start with a base KML doc
k_doc = createKML('default',icon_src + 'wifi.png')
k_doc9 = createKML('default',icon_src + 'wifi.png')
k_doc2 = createKML('default',icon_src + 'wifi.png')
k_doc3 = createKML('default',icon_src + 'wifi.png')
k_doc5 = createKML('default',icon_src + 'wifi.png')
k_doclinks = createKML('default',icon_src + 'wifi.png')

links_folder=createFolder('Links', 'links')
links_band9_folder=createFolder('900Mhz', 'lf900Mhz')
links_band2_folder=createFolder('2Ghz', 'lf2Ghz')
links_band3_folder=createFolder('3Ghz', 'lf3Ghz')
links_band5_folder=createFolder('5Ghz', 'lf5Ghz')

bands_folder=createFolder('Bands', 'bands')
band9_folder=createFolder('900Mhz', 'f900Mhz')
band2_folder=createFolder('2Ghz', 'f2Ghz')
band3_folder=createFolder('3Ghz', 'f3Ghz')
band5_folder=createFolder('5Ghz', 'f5Ghz')

# Get a list of all hosts
# MONGO QUERY HERE
connection = MongoClient(database_host, database_port)
db = connection.aredn
collection = db.sysinfo
j=collection.find( { "$and": [ { "lat": { "$ne": "" } }, { "lon": { "$ne": "" } } ] } )

# --- Iterate over the results to build the placemarks ---
for node in j:
  try:
    #print "Processing " + node['node']
    node['name']=str(node["node"])

    if "develop-16" in str(node['firmware_version']):
      node['desc']=str(node["model"])  # from develop-160+, the model will be accurate that is passed to mongo
    else:
      node['desc']=board_model(str(node["board_id"]))

    b=getBand(node['board_id'])

    # get the style
    nstyle=board_icon(str(b))
    kml_style=createStyle(nstyle, icon_src + nstyle + '.png')

    if not styleIdExists(k_doc, nstyle):
      k_doc.Document.insert(0,kml_style);
    if not styleIdExists(k_doc9, nstyle):
      k_doc9.Document.insert(0,kml_style);
    if not styleIdExists(k_doc2, nstyle):
      k_doc2.Document.insert(0,kml_style);
    if not styleIdExists(k_doc3, nstyle):
      k_doc3.Document.insert(0,kml_style);
    if not styleIdExists(k_doc5, nstyle):
      k_doc5.Document.insert(0,kml_style);
    if not styleIdExists(k_doclinks, nstyle):
      k_doclinks.Document.insert(0,kml_style);

    # ie. if old firmware, set WARN flag
    warn = checkForWarnings(node)

    # add a placemark for the node
    pm=createPlacemark(node, nstyle, warn)
    # print str(node['board_id'])

    if b==9:
      band9_folder.append(pm)
    elif b==2:
      band2_folder.append(pm)
    elif b==3:
      band3_folder.append(pm)
    elif b==5:
      band5_folder.append(pm)

    # get neighbor links for this node
    #
    ls=getLinks(node) # returns list of IP's of neighbors

    for l in ls:
      stylename="line" + str(b)
      n2=getNodeByIp(l)

      if bool(n2):  # we have a valid dictionary object
        #if "172.31." in l:  # it's a tunnel
        #  stylename=stylename + "t"

        # DISABLED for soft launch
        #if not styleIdExists(k_doc, stylename):
        #  k_doc.Document.insert(0,createLineStyle(stylename))
        if not styleIdExists(k_doclinks, stylename):
          k_doclinks.Document.insert(0,createLineStyle(stylename))


        lineid=str(node['node']) + "-to-" + str(n2['node'])
        line=createLine(lineid, node, n2, stylename)

        if b==9:
          links_band9_folder.append(line)
        elif b==2:
          links_band2_folder.append(line)
        elif b==3:
          links_band3_folder.append(line)
        elif b==5:
          links_band5_folder.append(line)
  except KeyError, e:
    print "KeyError: " + str(e)
    pass
  except KeyboardInterrupt:
    break
  except Exception, e:
    print "(" + str(e) + ")"
    print 'Error on line ' + str(sys.exc_info()[-1].tb_lineno)


# add bandX folders to bands folder
bands_folder.append(band9_folder)
bands_folder.append(band2_folder)
bands_folder.append(band3_folder)
bands_folder.append(band5_folder)


# add links band folders to links folder
links_folder.append(links_band9_folder)
links_folder.append(links_band2_folder)
links_folder.append(links_band3_folder)
links_folder.append(links_band5_folder)

# add links to the main bands file -- DISABLED TO DO A SOFT-RELEASE.  Must download the links.kml file
# bands_folder.append(links_folder)

# All nodes file
writeFile(k_doc,"",bands_folder)

# 900 file
writeFile(k_doc9,"9",band9_folder)

# 2G file
writeFile(k_doc2,"2",band2_folder)

# 3G file
writeFile(k_doc3,"3",band3_folder)

# 5G file
writeFile(k_doc5,"5",band5_folder)

# Links file
writeFile(k_doclinks,"links",links_folder)

