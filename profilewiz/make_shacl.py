import requests
import json


def make_shacl(ontid, ont, imported={}, subs={}):
    """ make a JSON Context from objects (in a given namespace)- using imports if relevant"""
    service = "https://astrea.linkeddata.es/api/shacl/document"
    headers = {'Content-Type': 'application/json', 'Accept': 'text/turtle'}
    request = { "ontology": ont.serialize(format="turtle").decode('utf-8') ,
        "serialisation": "TURTLE" }
    print( 'Accessing SHACL generator service')
    shacl = requests.post(service,data=json.dumps(request), headers=headers)
    res=shacl.text
    for str,sub in subs.items():
        res.replace(str,sub)
    return shacl.text