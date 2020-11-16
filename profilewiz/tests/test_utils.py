import unittest
from unittest import TestCase

from rdflib import Graph, Namespace, URIRef

from utils import get_basetype, shortforms, mergeonts, get_attrmap

IMP = Namespace("http://example.org/examples/ont-imported/")
EX = Namespace("http://example.org/examples/ont1/")


class GraphTestCase(unittest.TestCase):
    def setUp(self):
        self.g = Graph().parse(source="../../examples/basic/ex1_input.ttl", format="ttl")
        self.g2 = Graph().parse(source="../../examples/basic/lib/ext.ttl", format="ttl")
        self.closure = self.g + self.g2

    def test_env(self):
        assert (not self.g == None)

    def test_get_basetype(self):
        bt = get_basetype(self.closure, IMP.ScalarClass)
        self.assertIsNotNone(bt, msg="Base class should be XSD string")
        bt = get_basetype(self.closure, EX.LocalClass)
        self.assertIsNone(bt, msg="Base class should be None for complex class")

    def test_shortforms(self):
        t,id = shortforms(IMP.ScalarClass,self.g,False)
        self.assertEqual(t,id, msg="Valid curie forms should match token and id if qname mode is false")
        t, id = shortforms(IMP.ScalarClass, self.g, True)
        self.assertNotEqual(t, id, msg="qname and curie cannot match")
        t, id = shortforms(URIRef('http://frog.com/ribbit'), self.g, False)
        # self.fail()

    def test_mergeonts(self):
        new=Graph()
        new +=self.g
        mergeonts(new,self.g2)
        print( new.serialize(format='ttl'))

class AttributeMapTestCase(unittest.TestCase):
    def test_load(self):
        print ( get_attrmap(filename="../../examples/basic/attribute_map.csv") )
