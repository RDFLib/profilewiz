from rdflib import RDFS, URIRef


class Frame(object):
    """ frame containing details of properties and frames from superClasses"""
    theclass = None
    props = {}
    superClasses = set()

    def __init__(self, theclass, supers=[]):
        self.theclass = str(theclass)
        self.superClasses.update(supers)
        self.props = {}

    def update(self, prop, maxCard=None, minCard=None, hasValue=None, valuesFrom=None, propRange=None):
        details = {}
        if prop in self.props:
            details = self.props[prop]
        if maxCard:
            details['maxCard'] = maxCard
        if minCard:
            details['minCard'] = minCard
        if hasValue:
            details['hasValue'] = hasValue
        if valuesFrom:
            details['valuesFrom'] = valuesFrom
        if propRange:
            details['propRange'] = str(propRange)
        self.props[prop]  = details

    def addSuper(self,superclass):
        self.superClasses.add(superclass)

class Frameset(object):
    """ a set of frames for classes

    A frameset is a dict that allows for cumulative collation of information binding properties to classes,
    taking into account superclasses.
    """
    frameset = {}

    def __init__(self):
        self.frameset = {}

    def framefor(self, theclass, supers=[]):
        try:
            return self.frameset[str(theclass)]
        except:
            return Frame(theclass, supers=supers)

    def storeframe(self, theclass, frame: Frame):
        self.frameset[str(theclass)] = frame

    def buildframe(self, theclass, closure):
        """ build out frames for a class and its superclasses using the supplied closure graph"""
        if str(theclass) in self.frameset:
            return

        curframe = Frame(theclass)
        for p, o in closure.subjects(predicate=RDFS.domain, object=URIRef(theclass)):
            curframe.update(p)
        self.storeframe(theclass, curframe)
        for superclass in closure.objects(predicate=RDFS.subClassOf, subject=URIRef(str(theclass))):
            self.buildframe(superclass, closure)
