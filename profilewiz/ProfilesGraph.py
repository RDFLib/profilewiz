from rdflib import Graph, URIRef, BNode, RDF, RDFS, PROF, Literal, DCTERMS, OWL, SKOS
from rdflib.util import guess_format

DEFAULT_NS = [('prof', str(PROF) ), ('dcterms', str(DCTERMS) ), ('skos' , str(SKOS) )]
PROFILE_JSONCONTEXT = "http://www.opengis.net/def/ogc-na/profiles/json_ld_context"
# for now assume prof roles are in PROF namespace - this will change
PROFROLE=PROF

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
            PROFROLE.schema, conformsTo=PROFILE_JSONCONTEXT
        )
        for p, ont in self.getResourcesDict(PROFROLE.vocabulary, conformsTo=OWL).items():
            print("preloading ontology: ", p, " from ", ont)
            self.loadedowl[p] = Graph().parse(ont, format=guess_format(ont))

    def addResource(self,prof,artefact,label, role=PROFROLE.cachedCopy, conformsTo=OWL.Ontology, desc=None, format='text/turtle'):
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

    def getResourcesDict(self, role, fmt=None, conformsTo=None):
        """ Get a dict resources for a given role and content type
        role = URI ref or string URI - must be fully qualified form
        fmt = string - IANA mimetype code eg 'text/html'
        """
        res = {}
        filter = ""
        if fmt:
            filter += " ?r dcterms:format '%s' . " % (fmt, )
        if conformsTo:
            filter += " ?r dcterms:conformsTo <%s> ." % (str(conformsTo),)
        qarts = """SELECT ?p ?c
               WHERE { 
                ?p prof:hasResource ?r .
                ?r prof:hasRole <%s> . 
                %s 
                 ?r prof:hasArtifact ?c . 
                 } """ % (str(role), filter )
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
                return self.getResourcesDict(PROF.cachedCopy,fmt=f)[uri] , f
            except:
                pass

        return None,None

    def getParents(self,uri):
        return self.graph.objects(predicate=PROF.isProfileOf, subject=URIRef(str(uri)))

    def getProfilesOf(self,uri):
        return self.graph.subjects(predicate=PROF.isProfileOf, object=URIRef(str(uri)))

    def getJSONcontextMap(self):
        """ Get map of profiles to jsonld context resources """

        try:
            return self.getResourcesDict(PROF.schema, conformsTo=PROFILE_JSONCONTEXT)
        except:
            pass

        return {}

    def getJSONcontext(self, uri: str):
        """ Get JSON ld context for a profile

        Parameters
        ----------
        uri
        """
        contexts = self.getResourcesDict(PROF.schema, conformsTo=PROFILE_JSONCONTEXT)
        prof = [uri,]
        while prof:
            try:
                return contexts[str(prof[0])]
            except:
                pass
            prof += self.getProfilesOf(prof[0])
            prof = prof[1:]

        return None
