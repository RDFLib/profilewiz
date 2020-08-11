from rdflib import Graph, URIRef, BNode, RDF, RDFS, PROF, Literal, DCTERMS, OWL, SKOS
from rdflib.util import guess_format

DEFAULT_NS = [('prof', str(PROF) ), ('dcterms', str(DCTERMS) ), ('skos' , str(SKOS) )]


class ProfilesGraph:
    """ A container for a map of known profiles and supporting resources """

    def __init__(self,id=None,labels={},descriptions={},meta={}):
        self.graph = Graph()
        self.loadedowl = {}
        self.ldcontexts = {}
        for pre,ns in DEFAULT_NS :
            self.graph.namespace_manager.bind(pre,URIRef(ns))
        if id:
            self.graph.add(( id, RDF.type, PROF.Profile ))
            preds = {}
            preds.update(labels)
            preds.update(descriptions)
            preds.update(meta)
            for p,v in preds.items() :
                if type(v) == str:
                    self.graph.add((id,URIRef(str(p)), Literal(v) ))
                elif type(v) == Literal:
                    self.graph.add((id,URIRef(str(p)), v))
                else:
                     print ("Profile attributes: can only initialize Literal and string values")

    def parse(self, source, *args, **kwargs):
        self.graph.parse(source, *args, **kwargs)
        self.ldcontexts = self.getResourcesDict(
            "prof:schema", "<https://www.w3.org/TR/json-ld/>"
        )
        for p, ont in self.getResourcesDict("prof:vocabulary", "owl:").items():
            print("preloading ontology: ", p, " from ", ont)
            self.loadedowl[p] = Graph().parse(ont, format=guess_format(ont))

    def addResource(self,prof,artefact,label, role=PROF.cachedCopy, conformsTo=OWL.Ontology, desc=None, format='text/turtle'):
        """ add a resource as a Bnode to a profile in a profiles graph"""
        cacheResource = BNode()
        self.graph.add((cacheResource, RDF.type, PROF.ResourceDescriptor))
        self.graph.add((cacheResource, PROF.hasArtifact, Literal(artefact)))
        self.graph.add((cacheResource, PROF.hasRole, role))
        self.graph.add((cacheResource, RDFS.label, Literal(str(label))))
        self.graph.add((cacheResource, DCTERMS.conformsTo, URIRef(str(conformsTo))))
        self.graph.add((cacheResource, DCTERMS['format'], Literal(str(format))))
        if desc:
            self.graph.add((cacheResource, RDFS.comment, Literal(desc)))
        self.graph.add((prof, PROF.hasResource, cacheResource))

    def getResourcesDict(self, role, fmt):
        """ Get a dict resources for a given role and content type

        role = string URI - may use prof:X form
        fmt = string URI - may use prof:
        """
        res = {}
        qarts = """SELECT ?p ?c
               WHERE { 
                ?p prof:hasResource ?r .
                ?r prof:hasRole <%s> . 
                ?r dcterms:format '%s' .
                 ?r prof:hasArtifact ?c . 
                 } """ % (
            str(role),
            str(fmt),
        )
        arts = self.graph.query(qarts)
        for p, c in arts:
            res[str(p)] = str(c)
        return res

    def getLocal(self, uri: str, format: str = None) -> (str,str):
        """ Get local cached copy of the vocabulary for this profile

        Parameters
        ----------
        uri
        format
        """
        if not format:
            formats = ['text/turtle','application/rdf+xml']
        else:
            formats = [format]
        for f in formats:
            try:
                return self.getResourcesDict(PROF.cachedCopy,f)[uri] , f
            except:
                pass

        return None,None
