import unittest
from unittest import TestCase

from rdflib import Graph, Namespace, URIRef

from utils import get_basetype

IMP = Namespace("http://example.org/examples/ont-imported/")
EX = Namespace("http://example.org/examples/ont1/")

class GraphTestCase(unittest.TestCase):
    def setUp(self):
        self.g = Graph().parse(source="../../examples/ex1_input.ttl", format="ttl")
        g2 = Graph().parse(source="../../examples/lib/ext.ttl", format="ttl")
        self.closure = self.g + g2

    def test_env(self):
        assert (not self.g == None)

    def test_get_basetype(self):
        bt = get_basetype(self.closure, IMP.ScalarClass)
        self.assertIsNotNone( bt , msg="Base class should be XSD string" )
        bt = get_basetype(self.closure, EX.LocalClass)
        self.assertIsNone( bt , msg="Base class should be None for complex class" )
