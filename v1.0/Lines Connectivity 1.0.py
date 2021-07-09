from decimal import Decimal
from qgis import processing
from qgis.processing import alg
from qgis.PyQt.QtCore import QVariant
from qgis.core import (QgsProject, QgsGeometry, QgsVectorFileWriter, QgsDistanceArea, QgsPointXY, QgsField, QgsFields, QgsVectorDataProvider)

#ui input parameters
@alg(name='Lines Connectivity 1.0', label='Lines Connectivity 1.0', group='GAUS v1.0', group_label='GAUS v1.0')
@alg.input(type=alg.VECTOR_LAYER, name='edges', label='Lines', types=[1])
@alg.input(type=alg.ENUM, name='geomrule', label='Rule for Connecting the Lines', options=['Overlapping Vertices','Crossing Lines', 'Both Above'], default = 0)
@alg.input(type=alg.VECTOR_LAYER_DEST, name='dest', label='Create New Shapefile for Results? [optional]', optional = True, createByDefault = False)

#ui output definition (does nothing, it is here because qgis requires the declaration of at least one output)
@alg.output(type=alg.NUMBER, name='numoffeat', label='Number of Features Processed')

def computeMetrics(instance, parameters, context, feedback, inputs):
    """
    Computes the connectivity of the lines of a network.
    
    Fields Description:
    Lines: shapefile containing the geometry of the lines of the network.
    Rule for Connecting the Lines: definition of how the connection between lines will be computed.
    Create New Shapefile for Results?: if this field is left blank, the results will be inserted in the existing nodes shapefile. Otherwise, a copy of the existing shapefile will be created containing the results.
    """
    
    #Class that stores the metrics for the edges of the network
    class EdgeObj:
        def __init__(self, featCount, feat):
            self.id = feat.id() #id number, retrieved from the input shp
            self.heapPos = -1 #current position of the edge inside the heap
            self.neighA = [] #list of connected edges
            self.geom = feat.geometry() #geometry retrieved from the input shp
            self.reach = 0 #output metrics
    
    #verifies if highest id number is lower than number of features
    #in order to avoid potential conflicts with matrices' size
    def verifyFeatCount(inputFeat):
        featCount = inputFeat.featureCount()
        for feat in inputFeat.getFeatures(): featCount = max(featCount, feat.id()+1)
        return featCount
    
    
    #import input parameters
    inputEdges = instance.parameterAsVectorLayer(parameters, 'edges', context) #edges vector layer
    geomRule = instance.parameterAsEnum(parameters, 'geomrule', context) #chosen rule for geometry connection
    outPath = instance.parameterAsOutputLayer(parameters, 'dest', context) #path where results will be saved
    
    
    #edges initialization
    edgesCount = verifyFeatCount(inputEdges)
    edgesA = [] #array that stores network edges
    for edge in inputEdges.getFeatures():
        if edge.id() % 50 == 0: feedback.pushInfo("Edge {} inicializada".format(edge.id()))
        edgesA.append(EdgeObj(edgesCount, edge))
        for i in range(len(edgesA)-1):
            if (geomRule == 0 and edgesA[-1].geom.touches(edgesA[i].geom)) or (geomRule == 1 and edgesA[-1].geom.crosses(edgesA[i].geom)) or (geomRule == 2 and (edgesA[-1].geom.crosses(edgesA[i].geom) or edgesA[-1].geom.touches(edgesA[i].geom))):
                edgesA[-1].neighA.append([edgesA[i], 1])
                edgesA[i].neighA.append([edgesA[-1], 1])
    
    
    #compute shortest paths (djikstra algorithm with binary heap as priority queue)
    #step 1: heap cretation
    for indy in range(1):
        source = edgesA[0]
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
            sortedA.append(closest)
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
                    if prevCost > cost:
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

                    elif source.id != closest.id and costA[closest.neighA[ind][0].id] == cost:
                        pivotA[closest.neighA[ind][0].id].append(closest)
                        numShortPaths[closest.neighA[ind][0].id] += numShortPaths[closest.id]
    #step 3 centrality values update
    for source in edgesA:
        if numShortPaths[source.id] > 0: source.reach = 1
    
    #updates table of contents
    feedback.pushInfo("Updating Table of Contents")
    a,b,c,d,e = 0,0,0,0,0
    while inputEdges.fields().indexFromName("Conect" + str(a)) != -1: a += 1
    inputEdges.dataProvider().addAttributes([QgsField("Conect" + str(a),QVariant.Double)])
    inputEdges.updateFields()
    connIndex = inputEdges.fields().indexFromName("Conect" + str(a))

    while inputEdges.fields().indexFromName("Reach" + str(c)) != -1: c += 1
    inputEdges.dataProvider().addAttributes([QgsField("Reach" + str(c),QVariant.Double)])
    inputEdges.updateFields()
    reachIndex = inputEdges.fields().indexFromName("Reach" + str(c))
    
    for edge in edgesA: inputEdges.dataProvider().changeAttributeValues({edge.id : {connIndex : len(edge.neighA), reachIndex : edge.reach}})
    
    if outPath != "":
        crs = QgsProject.instance().crs()
        transform_context = QgsProject.instance().transformContext()
        save_options = QgsVectorFileWriter.SaveVectorOptions()
        save_options.driverName = "ESRI Shapefile"
        save_options.fileEncoding = "System"
        writer = QgsVectorFileWriter.writeAsVectorFormat(inputEdges, outPath, "System", crs, "ESRI Shapefile")
        inputEdges.dataProvider().deleteAttributes([connIndex, reachIndex])
        inputEdges.updateFields()


