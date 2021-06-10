from decimal import Decimal
from qgis import processing
from qgis.processing import alg
from qgis.PyQt.QtCore import QVariant
from qgis.core import (NULL, QgsProject, QgsGeometry, QgsVectorFileWriter, QgsDistanceArea, QgsPointXY, QgsField, QgsFields, QgsVectorDataProvider)

#ui input parameters
@alg(name='Lines Centrality 1.0', label='Lines Centrality 1.0', group='GAUS v1.0', group_label='GAUS v1.0')
@alg.input(type=alg.VECTOR_LAYER, name='edges', label='Lines', types=[1])
@alg.input(type=alg.ENUM, name='analysis', label='Analysis', options=['Topological Distance','Geodetic Distance'], default = 0)
@alg.input(type=alg.NUMBER, name='radius', label='Analysis Radius (0.0 for Global Analysis)')
@alg.input(type=alg.ENUM, name='geomrule', label='Rule for Connecting the Lines', options=['Overlapping Vertices','Crossing Lines', 'Both above'], default = 0)
@alg.input(type=alg.FIELD, name='potential', label='Load', parentLayerParameterName = 'edges', optional = True)
@alg.input(type=alg.FIELD, name='impedance', label='Impedance', parentLayerParameterName = 'edges', optional = True)
@alg.input(type=alg.VECTOR_LAYER_DEST, name='dest', label='Create New Shapefiles for Results? [optional]', optional = True, createByDefault = False)

#ui output definition (does nothing, it is here because qgis requires the declaration of at least one output)
@alg.output(type=alg.NUMBER, name='numoffeat', label='Number of Features Processed')

def computeMetrics(instance, parameters, context, feedback, inputs):
    """
     Computes accessibility and centrality for the lines of a network.
    
    Fields Description:
    Lines: shapefile containing the geometry of the lines which compose the network.
    Analysis: how the distance between lines is computed. In the topological analysis, the distance between each pair of connected lines is equal to 1. In the geometric analysis, the distance is equal to the geodetic distance between them.
    Analysis Radius: Zero means that all lines will be considered for the computation of the metrics for all other lines. A value higher than zero means that only the lines within the defined radius will be considered for the computation of the metrics of each line.
    Rule for Connecting the Lines: definition of how the connection between lines will be computed.
    Load: field of the selected line shapefile containing the value of the load of each line.
    Impedance: field of the selected line shapefile containing the value of the impedance of each line.
    Create New Shapefile for Results?: if this field is left blank, the results will be inserted in the existing nodes shapefile. Otherwise, a copy of the existing shapefile will be created containing the results.
    """
    
    #Class that stores the metrics for the edges of the network
    class EdgeObj:
        def __init__(self, featCount, feat, potField, impField, analysisType):
            self.id = feat.id() #id number, retrieved from the input shp
            self.heapPos = -1 #current position of the edge inside the heap
            self.neighA = [] #list of connected edges
            self.geom = feat.geometry() #geometry retrieved from the input shp
            self.centFKC, self.access, self.btw, self.reach = 0,0,0,0 #output metrics
            
            if analysisType == 1: self.length = QgsDistanceArea().measureLength(feat.geometry())
            else: self.length = 1
            
            #potential of the edge, depends on user-defined parameters
            if potField != []: 
                self.pot = feat.attribute(potField[0])
                if self.pot == NULL: self.pot = 0
            else: self.pot = 1
            
            #impedance of the edge, depends on user-defined parameters
            if impField != []: 
                self.imp = feat.attribute(impField[0])
                if self.imp == NULL: self.imp = 0
    
    #verifies if highest id number is lower than number of features
    #in order to avoid potential conflicts with matrices' size
    def verifyFeatCount(inputFeat):
        featCount = inputFeat.featureCount()
        for feat in inputFeat.getFeatures(): featCount = max(featCount, feat.id()+1)
        return featCount
    
    
    #import input parameters
    inputEdges = instance.parameterAsVectorLayer(parameters, 'edges', context) #edges vector layer
    impField = instance.parameterAsFields(parameters, 'impedance', context) #shp column with impedance values
    potField = instance.parameterAsFields(parameters, 'potential', context) #shp column with potential value
    analysisType = instance.parameterAsEnum(parameters, 'analysis', context) #indication if analysis is topo or geom
    radius = instance.parameterAsDouble(parameters, 'radius', context) #radius of the analysis
    geomRule = instance.parameterAsEnum(parameters, 'geomrule', context) #chosen rule for geometry connection
    outPath = instance.parameterAsOutputLayer(parameters, 'dest', context) #path where results will be saved
    
    
    #edges initialization
    edgesCount = verifyFeatCount(inputEdges)
    edgesA = [] #array that stores network edges
    if impField != []:
        for edge in inputEdges.getFeatures():
            if edge.id() % 50 == 0: feedback.pushInfo("Edge {} inicializada".format(edge.id()))
            edgesA.append(EdgeObj(edgesCount, edge, potField, impField, analysisType))
            for i in range(len(edgesA)-1):
                if (geomRule == 0 and edgesA[-1].geom.touches(edgesA[i].geom)) or (geomRule == 1 and edgesA[-1].geom.crosses(edgesA[i].geom)) or (geomRule == 2 and (edgesA[-1].geom.crosses(edgesA[i].geom) or edgesA[-1].geom.touches(edgesA[i].geom))):
                    dist = (edgesA[-1].imp*edgesA[-1].length + edgesA[i].imp*edgesA[i].length)/2
                    if dist <= radius or radius == 0.0:
                        edgesA[-1].neighA.append([edgesA[i], dist])
                        edgesA[i].neighA.append([edgesA[-1], dist])
    else:
        for edge in inputEdges.getFeatures():
            if edge.id() % 50 == 0: feedback.pushInfo("Edge {} inicializada".format(edge.id()))
            edgesA.append(EdgeObj(edgesCount, edge, potField, impField, analysisType))
            for i in range(len(edgesA)-1):
                if (geomRule == 0 and edgesA[-1].geom.touches(edgesA[i].geom)) or (geomRule == 1 and edgesA[-1].geom.crosses(edgesA[i].geom)) or (geomRule == 2 and (edgesA[-1].geom.crosses(edgesA[i].geom) or edgesA[-1].geom.touches(edgesA[i].geom))):
                    dist = (edgesA[-1].length + edgesA[i].length)/2
                    if dist <= radius or radius == 0.0:
                        edgesA[-1].neighA.append([edgesA[i], dist])
                        edgesA[i].neighA.append([edgesA[-1], dist])
    
    
    #compute shortest paths (djikstra algorithm with binary heap as priority queue)
    #step 1: heap cretation
    for source in edgesA:
        if source.id % 50 == 0: feedback.pushInfo("Caminho Mínimo Edge {}".format(source.id))
        finitePos = 0
        costA = [99999999999999 for i in range(edgesCount)]
        costA[source.id] = 0 #distance from the source edge to itself is zero
        for ind in range(len(source.neighA)): costA[source.neighA[ind][0].id] = source.neighA[ind][1]
        heap = [edgesA[0] for i in range(len(source.neighA) + 1)]
        for destin in edgesA:
            if costA[destin.id] == 99999999999999:
                heap.append(destin)
                destin.heapPos = len(heap) - 1
            else:
                heap[finitePos] = destin
                destin.heapPos = finitePos
                n = finitePos
                finitePos += 1
                parent = int((n-1)/2)
                while n !=0 and costA[heap[n].id] < costA[heap[parent].id]:
                    heap[n].heapPos, heap[parent].heapPos = parent, n
                    heap[n], heap[parent] = heap[parent], heap[n]
                    n = parent
                    parent = int((n-1)/2)
    #step 2 heapsort
        pivotA = [[] for i in range(edgesCount)] #array of pivot edges in shortest paths
        levelFromSource = [99999999999999 for i in range(edgesCount)]
        sortedA = []
        numShortPaths = [0 for i in range(edgesCount)]
        numShortPaths[source.id], levelFromSource[source.id] = 1,0
        for ind in range(len(source.neighA)):
            numShortPaths[source.neighA[ind][0].id] = 1
            levelFromSource[source.neighA[ind][0].id] = 1
        while heap != []:
            closest = heap[0]
            if costA[closest.id] <= radius or radius == 0.0: sortedA.append(closest)
            if finitePos > 0:
                heap[0].heapPos, heap[finitePos-1].heapPos = finitePos-1, 0
                heap[0], heap[finitePos-1] = heap[finitePos-1], heap[0]
                heap[finitePos-1].heapPos, heap[-1].heapPos = len(heap)-1, finitePos-1
                heap[finitePos-1], heap[-1] = heap[-1], heap[finitePos-1]
                finitePos -= 1
            heap.pop(len(heap)-1)
            
            n = 0
            lh = finitePos
            posChild1, posChild2 = n*2+1, n*2+2
            if posChild2 <= lh-1:
                costChild1, costChild2 = costA[heap[n*2+1].id], costA[heap[n*2+2].id]
                if any(x < costA[heap[n].id] for x in [costChild1,costChild2]):
                    if costChild1 <= costChild2: sc = posChild1
                    else: sc = posChild2
                else: sc = -1
            elif posChild2 == lh:
                if costA[heap[n*2+1].id] < costA[heap[n].id]: sc = posChild1
                else: sc = -1
            else: sc = -1
                
            while sc >= 0:
                heap[n].heapPos, heap[sc].heapPos = sc, n
                heap[n], heap[sc] = heap[sc], heap[n]
                n = sc
                lh = len(heap)
                posChild1, posChild2 = n*2+1, n*2+2
                if posChild2 <= lh-1:
                    costChild1, costChild2 = costA[heap[n*2+1].id], costA[heap[n*2+2].id]
                    if any(x < costA[heap[n].id] for x in [costChild1,costChild2]):
                        if costChild1 <= costChild2: sc = posChild1
                        else: sc = posChild2
                    else: sc = -1
                elif posChild2 == lh:
                    if costA[heap[n*2+1].id] < costA[heap[n].id]: sc = posChild1
                    else: sc = -1
                else: sc = -1
                
            for ind in range(len(closest.neighA)):
                if closest.neighA[ind][0].heapPos < len(heap):
                    cost = costA[closest.id] + closest.neighA[ind][1]
                    prevCost = costA[closest.neighA[ind][0].id]
                    if prevCost > cost and (radius == 0.0 or cost <= radius):
                        costA[closest.neighA[ind][0].id], levelFromSource[closest.neighA[ind][0].id] = cost, levelFromSource[closest.id] + 1
                        pivotA[closest.neighA[ind][0].id] = []
                        pivotA[closest.neighA[ind][0].id].append(closest)
                        numShortPaths[closest.neighA[ind][0].id] += numShortPaths[closest.id]
                        
                        n = closest.neighA[ind][0].heapPos
                        if prevCost == 99999999999999: 
                            heap[finitePos].heapPos, closest.neighA[ind][0].heapPos = n, finitePos
                            heap[n], heap[finitePos] = heap[finitePos], closest.neighA[ind][0]
                            n = finitePos
                            finitePos += 1
                        parent = int((n-1)/2)
                        while n !=0 and costA[heap[n].id] < costA[heap[parent].id]:
                            heap[n].heapPos, heap[parent].heapPos = parent, n
                            heap[n], heap[parent] = heap[parent], heap[n]
                            n = parent
                            parent = int((n-1)/2)

                    elif source.id != closest.id and costA[closest.neighA[ind][0].id] == cost and (radius == 0.0 or cost <= radius):
                        pivotA[closest.neighA[ind][0].id].append(closest)
                        numShortPaths[closest.neighA[ind][0].id] += numShortPaths[closest.id]
        #step 3 centrality values update
        btwTemp, fkcTemp = [0 for i in range(edgesCount)],[0 for i in range(edgesCount)]
        while sortedA != []:
            farest = sortedA[-1]
            cost = costA[farest.id]
            if (radius == 0.0 or cost <= radius): 
                source.reach += farest.pot
                if farest.id != source.id: 
                    source.access += farest.pot/costA[farest.id]
            sortedA.pop(len(sortedA)-1)
            potential = farest.pot * source.pot
            for neigh in pivotA[farest.id]:
                if numShortPaths[farest.id] > 0 and (radius == 0.0 or cost <= radius):
                    btwTemp[neigh.id] += (numShortPaths[neigh.id]/numShortPaths[farest.id])*(1 + btwTemp[farest.id])
                    fkcTemp[neigh.id] += (numShortPaths[neigh.id]/numShortPaths[farest.id])*((potential/(levelFromSource[farest.id]+1))+fkcTemp[farest.id])
            if pivotA[farest.id] == [] and levelFromSource[farest.id] == 1 and (radius == 0.0 or cost <= radius): 
                fkcTemp[source.id] += (potential/2)+fkcTemp[farest.id]
            if farest.id != source.id and (radius == 0.0 or cost <= radius): fkcTemp[farest.id] += potential/(levelFromSource[farest.id]+1)
            if farest.id != source.id: farest.btw += btwTemp[farest.id]/2
            farest.centFKC += fkcTemp[farest.id]/2
    
    #updates table of contents
    feedback.pushInfo("Updating Table of Contents")
    if analysisType == 0:
        a,b,c,d,e = 0,0,0,0,0
        while inputEdges.fields().indexFromName("TAccess" + str(a)) != -1: a += 1
        inputEdges.dataProvider().addAttributes([QgsField("TAccess" + str(a),QVariant.Double)])
        inputEdges.updateFields()
        accessIndex = inputEdges.fields().indexFromName("TAccess" + str(a))
        
        while inputEdges.fields().indexFromName("TCentFK" + str(c)) != -1: c += 1
        inputEdges.dataProvider().addAttributes([QgsField("TCentFK" + str(c),QVariant.Double)])
        inputEdges.updateFields()
        fkcIndex = inputEdges.fields().indexFromName("TCentFK" + str(c))
        
        while inputEdges.fields().indexFromName("TCentBTW" + str(d)) != -1: d += 1
        inputEdges.dataProvider().addAttributes([QgsField("TCentBTW" + str(d),QVariant.Double)])
        inputEdges.updateFields()
        btwIndex = inputEdges.fields().indexFromName("TCentBTW" + str(d))
        
        while inputEdges.fields().indexFromName("TReach" + str(e)) != -1: e += 1
        inputEdges.dataProvider().addAttributes([QgsField("TReach" + str(e),QVariant.Double)])
        inputEdges.updateFields()
        reachIndex = inputEdges.fields().indexFromName("TReach" + str(e))
        
    else:
        a,b,c,d,e = 0,0,0,0,0
        while inputEdges.fields().indexFromName("GAccess" + str(a)) != -1: a += 1
        inputEdges.dataProvider().addAttributes([QgsField("GAccess" + str(a),QVariant.Double)])
        inputEdges.updateFields()
        accessIndex = inputEdges.fields().indexFromName("GAccess" + str(a))
        
        while inputEdges.fields().indexFromName("GCentFK" + str(c)) != -1: c += 1
        inputEdges.dataProvider().addAttributes([QgsField("GCentFK" + str(c),QVariant.Double)])
        inputEdges.updateFields()
        fkcIndex = inputEdges.fields().indexFromName("GCentFK" + str(c))
        
        while inputEdges.fields().indexFromName("GCentBTW" + str(d)) != -1: d += 1
        inputEdges.dataProvider().addAttributes([QgsField("GCentBTW" + str(d),QVariant.Double)])
        inputEdges.updateFields()
        btwIndex = inputEdges.fields().indexFromName("GCentBTW" + str(d))
        
        while inputEdges.fields().indexFromName("GReach" + str(e)) != -1: e += 1
        inputEdges.dataProvider().addAttributes([QgsField("GReach" + str(e),QVariant.Double)])
        inputEdges.updateFields()
        reachIndex = inputEdges.fields().indexFromName("GReach" + str(e))
    
    for edge in edgesA: inputEdges.dataProvider().changeAttributeValues({edge.id : {fkcIndex : edge.centFKC, accessIndex : edge.access, btwIndex : edge.btw, reachIndex : edge.reach}})
    
    if outPath != "":
        crs = QgsProject.instance().crs()
        transform_context = QgsProject.instance().transformContext()
        save_options = QgsVectorFileWriter.SaveVectorOptions()
        save_options.driverName = "ESRI Shapefile"
        save_options.fileEncoding = "System"
        writer = QgsVectorFileWriter.writeAsVectorFormat(inputEdges, outPath, "System", crs, "ESRI Shapefile")
        inputEdges.dataProvider().deleteAttributes([accessIndex, fkcIndex, btwIndex, reachIndex])
        inputEdges.updateFields()


