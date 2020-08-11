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