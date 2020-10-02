from unittest import TestCase

from rdflib import SDO

from profilewiz import ProfilesGraph


class TestProfilesGraph(TestCase):
    def setUp(self):
        self.g = ProfilesGraph()
        self.g.parse(source="../../examples/profile_cat.ttl", format="ttl")

    def test_get_prof_for(self):
       prof = self.g.get_prof_for( SDO )
