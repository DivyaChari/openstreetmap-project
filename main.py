import csv
import codecs
import xml.etree.cElementTree as ET
from collections import defaultdict
import re
import pprint
import cerberus
import schema

filename = 'sample_map.osm'
lower = re.compile(r'^([a-z]|_)*$')
lower_colon = re.compile(r'^([a-z]|_)*:([a-z]|_)*$')
problemchars = re.compile(r'[=\+/&<>;\'"\?%#$@\,\. \t\r\n]')

"""
Variables to monitor map information
"""
keys = {"lower": 0, "lower_colon": 0, "problemchars": 0, "other": 0}
unique_street = []
unique_city = []
unique_zip_code = []
unique_country = []
unique_city = []

"""
Mapping to clean up street names
"""
street_mapping = { "St": "Street",
            "St,": "Street,",
            "st": "Street",
            "street": "Street",
            "road": "Road",
            "Rd": "Road",
            "Rd,": "Road,",
            "SALAI": "Salai", #This is the Tamil word for road
            "nagar": "Nagar", #This is the Tamil word for colony
            }

"""
Output csv file names
"""
NODES_PATH = "nodes.csv"
NODE_TAGS_PATH = "nodes_tags.csv"
WAYS_PATH = "ways.csv"
WAY_NODES_PATH = "ways_nodes.csv"
WAY_TAGS_PATH = "ways_tags.csv"

"""
Schema and the associated element structure for different tag types
"""
SCHEMA = schema.schema
NODE_FIELDS = ['id', 'lat', 'lon', 'user', 'uid', 'version', 'changeset', 'timestamp']
NODE_TAGS_FIELDS = ['id', 'key', 'value', 'type']
WAY_FIELDS = ['id', 'user', 'uid', 'version', 'changeset', 'timestamp']
WAY_TAGS_FIELDS = ['id', 'key', 'value', 'type']
WAY_NODES_FIELDS = ['id', 'node_id', 'position']

"""
The map file is iteratively parsed to find out what tags are there and how many
Input: name of file to be parsed
"""
def count_tags(filename):
    tag_list={}
    for event, elem in ET.iterparse(filename):
        if elem.tag not in tag_list:
            tag_list[elem.tag] = 1
        else:
            tag_list[elem.tag] += 1
    print(tag_list)

"""
The validity of the tag values are checked and replaced if required
Input: element of type tag
"""
def audit_update_element(element):

    item = element.items()
    key = element.attrib['k']
    global keys
    global unique_street
    global unique_zip_code
    global unique_country
    global unique_city

    """
    The validity of key is checked and appropriate counts are updated
    """
    if lower.match(key):
        keys["lower"] = keys["lower"] + 1
    elif lower_colon.match(key):
        keys["lower_colon"] = keys["lower_colon"] + 1
    elif problemchars.match(key):
        keys["problemchars"] = keys["problemchars"] + 1
    else:
        keys["other"] = keys["other"] + 1

    """
    The validity of street name is checked and replaced from mapping if needed
    """
    if key == "addr:street":
        value = element.attrib['v']
        if any(s in value for s in street_mapping.keys()):
            for label in street_mapping:
                if label in value.split():
                    better_name = value.replace(label, street_mapping[label])
                    print(value, "=>", better_name)
                    element.attrib['v'] = better_name
                    if not(all(s.isalpha() or s.isspace() or s.isdigit() for s in better_name) or (better_name in unique_street)):
                        unique_street.append(better_name)
                
    """
    The validity of zip code is checked and spaces are eliminated if found
    """            
    if key == "addr:postcode":
        value = element.attrib['v']
        if (" " in value):
            print(value, "=>", value.replace(" ", ""))
            value = value.replace(" ", "")
            element.attrib['v'] = value
        if (value[0:3]!='600') or (not value.isdigit()) or (len(value) != 6):
            unique_zip_code.append(value)
            
    """
    The validity of city name is checked and formatting is updated if found
    """            
    if key == "addr:city":
        value = element.attrib['v']
        if (value != 'Chennai') and (value not in unique_city):
            if ('chennai' in value.lower()):
                print(value, "=>", "Chennai")
                element.attrib['v'] = "Chennai"
            else:
                unique_city.append(value)

    """
    The validity of country name is checked and replaced if required
    """                
    if key == "addr:country":
        value = element.attrib['v']
        if value != "IN":
            unique_country.append(value)
            print(value, "=>", "IN")
            element.attrib['v'] = "IN"

    return element

"""
The elements in the osm file are parsed, audited, and replaced if required
The result is reshaped in line with a schema for writing to a csv file
Input: element from osm file, schema structure
"""
def shape_element(element, node_attr_fields=NODE_FIELDS, way_attr_fields=WAY_FIELDS,
                  problem_chars=problemchars, default_tag_type='regular'):
    node_attribs = dict().fromkeys(node_attr_fields, None)
    way_attribs = dict().fromkeys(way_attr_fields, None)
    way_nodes = []
    tags = []
    
    if element.tag == 'node':
        for attribute in node_attr_fields:
            for attrib, value in element.attrib.items():
                if attribute == attrib:
                    node_attribs[attribute] = value
                    
    elif element.tag == 'way':
        for attribute in way_attr_fields:
            for attrib, value in element.attrib.items():
                if attribute == attrib:
                    way_attribs[attribute] = value
                
    count = 0
    for secondary in element.iter():
        if secondary.tag == 'tag':
            if problem_chars.match(secondary.attrib['k']) is not None:
                continue
            else:
                secondary = audit_update_element(secondary)
                new = {}
                new['id'] = element.attrib['id']
                if ":" not in secondary.attrib['k']:
                    new['key'] = secondary.attrib['k']
                    new['type'] = default_tag_type
                    new['value'] = secondary.attrib['v']
                else:
                    post_colon = secondary.attrib['k'].index(":") + 1
                    new['key'] = secondary.attrib['k'][post_colon:]
                    new['type'] = secondary.attrib['k'][:post_colon - 1]
                    new['value'] = secondary.attrib['v']
                tags.append(new)
                
        if element.tag == 'way' and secondary.tag == 'nd':
            new = {}
            new['id'] = element.attrib['id']
            new['node_id'] = secondary.attrib['ref']
            new['position'] = count
            count += 1
            way_nodes.append(new)
                
    if element.tag == 'node':
        return {'node': node_attribs, 'node_tags': tags}
    elif element.tag == 'way':
        return {'way': way_attribs, 'way_nodes': way_nodes, 'way_tags': tags}

"""
Obtain next element from the osm file
Input: osm file name
"""
def get_element(osm_file, tags=('node', 'way', 'relation')):
    context = ET.iterparse(osm_file, events=('start', 'end'))
    _, root = next(context)
    for event, elem in context:
        if event == 'end' and elem.tag in tags:
            yield elem
            root.clear()
"""
Extend csv.DictWriter to handle Unicode input
"""
class UnicodeDictWriter(csv.DictWriter, object):
    def writerow(self, row):
        super(UnicodeDictWriter, self).writerow({
            k: v for k, v in row.items()
        })
    def writerows(self, rows):
        for row in rows:
            self.writerow(row)

"""
Process each XML element and write to csv file
"""
def test():

    print("Map structure")
    count_tags(filename)

    print("\nErrors fixed in the audit")
    with codecs.open(NODES_PATH, 'w', encoding='utf8') as nodes_file, \
         codecs.open(NODE_TAGS_PATH, 'w', encoding='utf8') as nodes_tags_file, \
         codecs.open(WAYS_PATH, 'w', encoding='utf8') as ways_file, \
         codecs.open(WAY_NODES_PATH, 'w', encoding='utf8') as way_nodes_file, \
         codecs.open(WAY_TAGS_PATH, 'w', encoding='utf8') as way_tags_file:

        nodes_writer = UnicodeDictWriter(nodes_file, NODE_FIELDS)
        node_tags_writer = UnicodeDictWriter(nodes_tags_file, NODE_TAGS_FIELDS)
        ways_writer = UnicodeDictWriter(ways_file, WAY_FIELDS)
        way_nodes_writer = UnicodeDictWriter(way_nodes_file, WAY_NODES_FIELDS)
        way_tags_writer = UnicodeDictWriter(way_tags_file, WAY_TAGS_FIELDS)

        nodes_writer.writeheader()
        node_tags_writer.writeheader()
        ways_writer.writeheader()
        way_nodes_writer.writeheader()
        way_tags_writer.writeheader()

        for element in get_element(filename, tags=('node', 'way')):
            el = shape_element(element)
            if el:
                if element.tag == 'node':
                    nodes_writer.writerow(el['node'])
                    node_tags_writer.writerows(el['node_tags'])
                elif element.tag == 'way':
                    ways_writer.writerow(el['way'])
                    way_nodes_writer.writerows(el['way_nodes'])
                    way_tags_writer.writerows(el['way_tags'])

        print("\nValidity of keys in the map")            
        pprint.pprint(keys)

        print("\nErrors that could not be fixed in the audit")
        if len(unique_street) != 0:
            print("\nErrors remaining in street name values")
            pprint.pprint(unique_street)
        else:
            print("\nNo errors remaining in street name values")
       
        if len(unique_zip_code) != 0:
            print("\nErrors remaining in zip code values")
            pprint.pprint(unique_zip_code)
        else:
            print("\nNo errors remaining in zip code values")

        if len(unique_country) != 0:
            print("\nErrors remaining in country name values")
            pprint.pprint(unique_country)
        else:
            print("\nNo errors remaining in country name values")
    
        if len(unique_city) != 0:
            print("\nErrors remaining in city name values")
            pprint.pprint(unique_city)
        else:
            print("\nNo errors remaining in city name values")

if __name__ == '__main__':
    test()
