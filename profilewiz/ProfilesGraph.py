from rdflib import Graph, URIRef, BNode, RDF, RDFS, PROF, Literal, DCTERMS, OWL, SKOS, Namespace, PROV
from rdflib.util import guess_format

from profilewiz import JSONLD_URI


# for now assume prof roles are in PROF namespace - this will change
PROFROLE = Namespace( str(PROF) + "role/")
# TODO - allow configuration of a default set of profile catalogs to acquire a set of roles and map intention to the chosen roles rather than a default value.

DEFAULT_NS = [('prof', str(PROF)), ('profrole', str(PROFROLE)), ('dcterms', str(DCTERMS)), ('prov', str(PROV)),  ('skos', str(SKOS))]


class ProfilesGraph:
    """ A container for a map of known profiles and supporting resources """

    def __init__(self, uri=None, labels=None, descriptions=None, meta=None):
        if meta is None:
            meta = {}
        if descriptions is None:
            descriptions = {}
        if labels is None:
            labels = {}
        self.graph = Graph()
        self.loadedowl = {}
        self.ldcontexts = {}
        for pre, ns in DEFAULT_NS:
            self.graph.namespace_manager.bind(pre, URIRef(ns))
        if uri:
            preds = {}
            preds.update(labels)
            preds.update(descriptions)
            preds.update(meta)
            self.add_prof(uri, preds)

    def add_prof(self, uri, preds):
        """ Add a profile to the graph with a set of predicate values
        Parameters
        ----------
        uri: string (URI)
        preds : dict of pred,value pairs

        Returns
        -------

        """
        self.graph.add((uri, RDF.type, PROF.Profile))
        for p, v in preds.items():
            if type(v) == str:
                self.graph.add((uri, URIRef(str(p)), Literal(v)))
            elif type(v) in (Literal, URIRef):
                self.graph.add((uri, URIRef(str(p)), v))
            else:
                print("Profile attributes: can only initialize Literal, URIRef and string values")

    def parse(self, source, *args, **kwargs):
        self.graph.parse(source, *args, **kwargs)
        self.ldcontexts = self.getResourcesDict(
            PROFROLE.context, conformsTo=JSONLD_URI
        )
        for p, ont in self.getResourcesDict(PROFROLE.vocabulary, fmt="text/turtle", conformsTo=OWL).items():
            print("preloading ontology: ", p, " from ", ont)
            self.loadedowl[p] = Graph().parse(ont, format=guess_format(ont))

    def addResource(self, prof, artefact, label, role=PROFROLE.cachedCopy, conformsTo=OWL.Ontology, desc=None,
                    fmt='text/turtle'):
        """ add a resource as a Bnode to a profile in a profiles graph"""
        cacheResource = BNode()
        self.graph.add((cacheResource, RDF.type, PROF.ResourceDescriptor))
        self.graph.add((cacheResource, PROF.hasArtifact, Literal(artefact)))
        self.graph.add((cacheResource, PROF.hasRole, role))
        self.graph.add((cacheResource, RDFS.label, Literal(str(label))))
        self.graph.add((cacheResource, DCTERMS.conformsTo, URIRef(str(conformsTo))))
        self.graph.add((cacheResource, DCTERMS['format'], Literal(str(fmt))))
        if desc:
            self.graph.add((cacheResource, RDFS.comment, Literal(desc)))
        self.graph.add((prof, PROF.hasResource, cacheResource))

    def getResourcesDict(self, role, fmt=None, conformsTo=None):
        """ Get a dict resources for a given role and content type
        role = URI ref or string URI - must be fully qualified form
        fmt = string - IANA mimetype code eg 'text/html'
        """
        res = {}
        filter_clause = ""
        if fmt:
            filter_clause += " ?r dcterms:format '%s' . " % (fmt,)
        if conformsTo:
            filter_clause += " ?r dcterms:conformsTo <%s> ." % (str(conformsTo),)
        qarts = """SELECT ?p ?c
               WHERE { 
                ?p prof:hasResource ?r .
                ?r prof:hasRole <%s> . 
                %s 
                 ?r prof:hasArtifact ?c . 
                 } """ % (str(role), filter_clause)
        arts = self.graph.query(qarts)
        for p, c in arts:
            res[str(p)] = str(c)
        return res

    def getLocal(self, uri: str, fmt: str = None) -> (str, str):
        """ Get local cached copy of the vocabulary for this profile

        Parameters
        ----------
        uri
        fmt
        """
        if not fmt:
            formats = ['text/turtle', 'application/rdf+xml']
        else:
            formats = [fmt]
        for f in formats:
            try:
                return self.getResourcesDict(PROF.cachedCopy, fmt=f)[uri], f
            except KeyError:
                pass

        return None, None

    def getParents(self, uri):
        return self.graph.objects(predicate=PROF.isProfileOf, subject=URIRef(str(uri)))

    def getProfilesOf(self, uri):
        return self.graph.subjects(predicate=PROF.isProfileOf, object=URIRef(str(uri)))

    def getJSONcontextMap(self):
        """ Get map of profiles to jsonld context resources """

        try:
            return self.getResourcesDict(PROFROLE.context, conformsTo=JSONLD_URI)
        except:
            pass

        return {}

    def getJSONcontext(self, uri: str):
        """ Get JSON ld context for a profile

        Parameters
        ----------
        uri
        """
        contexts = self.getResourcesDict(PROFROLE.context, conformsTo=JSONLD_URI)
        prof = [uri, ]
        while prof:
            try:
                return contexts[str(prof[0])]
            except:
                pass
            prof += self.getProfilesOf(prof[0])
            prof = prof[1:]

        return None
