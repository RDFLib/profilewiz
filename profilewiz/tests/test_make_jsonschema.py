import json
from unittest import TestCase

import rdflib
from rdflib import XSD, RDFS, Graph

from Frame import Frame
from make_jsonschema import make_schema


class Test(TestCase):
    def test_make_schema(self):
        sid = "http://example.org/myClass"
        propid = "http://example.org/myProp1"
        g= Graph()
        cases = [
            ( 0,1,XSD.int) ,
            ( 0,None,XSD.int) ,
            ( 1,None,XSD.int) ,
            ( None,None,XSD.int) ,
            (None, 10, XSD.int) ,
            (None, 1, XSD.datetime),
            (None, 1, RDFS.Class),
        ]
        for minc,maxc,r in cases:
            frame = Frame(sid )
            frame.update( propid, maxCard=maxc, minCard=minc, propRange=r)

            schema = make_schema(sid, g, { sid: frame } )
            print (json.dumps(schema,indent=4))
        # self.fail()
