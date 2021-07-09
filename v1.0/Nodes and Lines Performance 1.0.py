from qgis import processing
from qgis.processing import alg
from qgis.PyQt.QtCore import QVariant
from qgis.core import (QgsProject,
                       QgsSpatialIndex,
                       QgsDistanceArea,
                       QgsPointXY,
                       QgsField,
                       QgsFields,
                       QgsVectorDataProvider,
                       QgsVectorFileWriter,
                       NULL)

@alg(name='Nodes Performance 1.0', label='Nodes Performance 1.0', group='GAUS v1.0', group_label='GAUS v1.0')
@alg.input(type=alg.VECTOR_LAYER, name='nodes', label='Nodes', types=[0])
@alg.input(type=alg.VECTOR_LAYER, name='edges', label='Lines', types=[1])
@alg.input(type=alg.ENUM, name='analysis', label='Analysis', options=['Topological Distance','Geodetic Distance'], default = 0)
@alg.input(type=alg.NUMBER, name='radius', label='Analysis Radius (0.0 for Global Analysis)')
@alg.input(type=alg.FIELD, name='supply', label='Supply', parentLayerParameterName = 'nodes', optional = True)
@alg.input(type=alg.FIELD, name='demand', label='Demand', parentLayerParameterName = 'nodes', optional = True)
@alg.input(type=alg.FIELD, name='impedance', label='Impedance', parentLayerParameterName = 'edges', optional = True)
@alg.input(type=alg.VECTOR_LAYER_DEST, name='dest', label='Create New Shapefile for Results? [optional]', optional = True, createByDefault = False)

@alg.output(type=alg.NUMBER, name='numoffeat', label='Number of Features Processed')

def computeMetrics(instance, parameters, context, feedback, inputs):
    """
    Computes performace metrics (spatial opportunity, spatial convergence and polarity) for the nodes of a network using lines as indicative of the connections between nodes.
    
    Fields Description:
    Nodes: shapefile containing the geometry of the nodes (points) of the network.
    Lines: shapefile containing the geometry of the lines, which indicate the existing connections between nodes.
    Analysis: how the distance between nodes is computed. In the topological analysis, the distance between each pair of connected nodes is equal to 1. In the geometric analysis, the distance is equal to the geodetic distance between them.
    Analysis Radius: Zero means that all nodes will be considered for the computation of the metrics for all other nodes. A value higher than zero means that only the nodes within the defined radius will be considered for the computation of the metrics of each node.
    Supply: field of the selected node shapefile containing the supply value each node.
    Demand: field of the selected node shapefile containing the demand value each node.
    Impedance: field of the selected line shapefile containing the impedance value of each line.
    Create New Shapefile for Results?: if this field is left blank, the results will be inserted in the existing nodes shapefile. Otherwise, a copy of the existing shapefile will be created containing the results.
    """
    class NodeObj:
        def __init__(self, featCount, feat, supplyField, demandField):
            self.id = feat.id()
            self.heapPos = -1
            self.neighA = []
            self.opportunity, self.convergence, self.polarity = 0,0,0
            
            if supplyField != []: 
                self.supply = feat.attribute(supplyField[0])
                if self.supply == NULL: self.supply = 0
            else: self.supply = 1
            
            if demandField != []: 
                self.demand = feat.attribute(demandField[0])
                if self.demand == NULL: self.demand = 0
            else: self.demand = 1
    
    def verifyFeatCount(inputFeat):
        featCount = inputFeat.featureCount()
        for feat in inputFeat.getFeatures():
            featCount = max(featCount, feat.id()+1)
        return featCount
    
    #import from vector layers the geometry and data of network's nodes and edges
    inputNodes = instance.parameterAsVectorLayer(parameters, 'nodes', context)
    inputEdges = instance.parameterAsVectorLayer(parameters, 'edges', context)
    supplyField = instance.parameterAsFields(parameters, 'supply', context)
    demandField = instance.parameterAsFields(parameters, 'demand', context)
    analysisType = instance.parameterAsEnum(parameters, 'analysis', context)
    impField = instance.parameterAsFields(parameters, 'impedance', context)
    radius = instance.parameterAsDouble(parameters, 'radius', context)
    outPath = instance.parameterAsOutputLayer(parameters, 'dest', context) #path where results will be saved
    
  #nodes initialization
    nodesCount = verifyFeatCount(inputNodes)
    nodesA = [0 for i in range(nodesCount)] #array that stores network nodes
    for node in inputNodes.getFeatures(): 
        nodesA[node.id()] = NodeObj(nodesCount, node, supplyField, demandField)
        if node.id() % 50 == 0: feedback.pushInfo("Node {} inicializado".format(node.id()))
    
    #Initialize Edges
    feedback.pushInfo("Initialize Edges")
    nodesSpaceIndex = QgsSpatialIndex(inputNodes.getFeatures())
    
    if analysisType == 1 and impField != []:
        for edge in inputEdges.getFeatures():
            edgesVertices = edge.geometry().asMultiPolyline()
            vert1 = nodesSpaceIndex.nearestNeighbor(edgesVertices[0][0], 1, 0.00015)
            vert2 = nodesSpaceIndex.nearestNeighbor(edgesVertices[0][-1], 1, 0.00015)
            if vert1 != [] and vert2 != []: #if one vertex is empty, the edge does not connect points
                dist = QgsDistanceArea().measureLine(edgesVertices[0][0],edgesVertices[0][-1])
                imp = edge.attribute(impField[0])
                if self.imp == NULL: self.imp = 0
                if dist*imp <= radius or radius == 0.0:
                    nodesA[vert1[0]].neighA.append([nodesA[vert2[0]], dist*imp])
                    nodesA[vert2[0]].neighA.append([nodesA[vert1[0]], dist*imp])
                
    elif analysisType == 1:
        for edge in inputEdges.getFeatures():
            edgesVertices = edge.geometry().asMultiPolyline()
            vert1 = nodesSpaceIndex.nearestNeighbor(edgesVertices[0][0], 1, 0.00015)
            vert2 = nodesSpaceIndex.nearestNeighbor(edgesVertices[0][-1], 1, 0.00015)
            if vert1 != [] and vert2 != []: #if one vertex is empty, the edge does not connect points
                dist = QgsDistanceArea().measureLine(edgesVertices[0][0],edgesVertices[0][-1])
                if dist <= radius or radius == 0.0:
                    nodesA[vert1[0]].neighA.append([nodesA[vert2[0]],dist])
                    nodesA[vert2[0]].neighA.append([nodesA[vert1[0]],dist])
                
    elif analysisType == 0 and impField != []:
        for edge in inputEdges.getFeatures():
            edgesVertices = edge.geometry().asMultiPolyline()
            vert1 = nodesSpaceIndex.nearestNeighbor(edgesVertices[0][0], 1, 0.00015)
            vert2 = nodesSpaceIndex.nearestNeighbor(edgesVertices[0][-1], 1, 0.00015)
            if vert1 != [] and vert2 != []: #if one vertex is empty, the edge does not connect points
                imp = edge.attribute(impField[0])
                if self.imp == NULL: self.imp = 0
                if imp <= radius or radius == 0.0:
                    nodesA[vert1[0]].neighA.append([nodesA[vert2[0]], imp])
                    nodesA[vert2[0]].neighA.append([nodesA[vert1[0]], imp])
                
    else:
        for edge in inputEdges.getFeatures():
            edgesVertices = edge.geometry().asMultiPolyline()
            vert1 = nodesSpaceIndex.nearestNeighbor(edgesVertices[0][0], 1, 0.00015)
            vert2 = nodesSpaceIndex.nearestNeighbor(edgesVertices[0][-1], 1, 0.00015)
            if vert1 != [] and vert2 != []: #if one vertex is empty, the edge does not connect points
                nodesA[vert1[0]].neighA.append([nodesA[vert2[0]],1])
                nodesA[vert2[0]].neighA.append([nodesA[vert1[0]],1])
    
    #Compute Shortest Paths (Djikstra Algorithm with Binary Heap as Priority Queue)
    #1-Heap cretation
    for source in nodesA:
        if source.id % 50 == 0: feedback.pushInfo("Caminho Mínimo Edge {}".format(source.id))
        finitePos = 0
        costA = [99999999999999 for i in range(nodesCount)]
        costA[source.id] = 0 #distance from the source edge to itself is zero
        for ind in range(len(source.neighA)): costA[source.neighA[ind][0].id] = source.neighA[ind][1]
        heap = [nodesA[0] for i in range(len(source.neighA) + 1)]
        for destin in nodesA:
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
    #2-Heap sorting
        pivotA = [[] for i in range(nodesCount)]
        levelFromSource = [0 for i in range(nodesCount)]
        numShortPaths = [0 for i in range(nodesCount)]
        sortedA = [] 
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

        #3-Centrality values update
        convTemp = [0 for i in range(nodesCount)]
        while sortedA != []:
            farest = sortedA[-1]
            cost = costA[farest.id]
            if source.demand > 0 and (radius == 0.0 or cost <= radius): source.opportunity += farest.supply/(costA[farest.id]+1)
            sortedA.pop(len(sortedA)-1)
            for neigh in pivotA[farest.id]:
                if radius == 0.0 or cost <= radius: convTemp[neigh.id] += (numShortPaths[neigh.id]/numShortPaths[farest.id])*((source.supply*farest.demand/(levelFromSource[farest.id]+1))+convTemp[farest.id])
            if pivotA[farest.id] == [] and levelFromSource[farest.id] == 1 and (radius == 0.0 or cost <= radius): convTemp[source.id] += (numShortPaths[neigh.id]/numShortPaths[farest.id])*((source.supply*farest.demand/(levelFromSource[farest.id]+1))+convTemp[farest.id])
            if radius == 0.0 or cost <= radius: convTemp[farest.id] += source.supply*farest.demand/(levelFromSource[farest.id]+1)
            if farest.supply > 0: farest.convergence += convTemp[farest.id]
            farest.polarity += convTemp[farest.id]
    
    #updates acessibility and centrality in table of contents
    if analysisType == 0:
        a,b,c = 0,0,0
        while inputNodes.fields().indexFromName("TOpport" + str(a)) != -1: a += 1
        inputNodes.dataProvider().addAttributes([QgsField("TOpport" + str(a),QVariant.Double)])
        inputNodes.updateFields()
        opportIndex = inputNodes.fields().indexFromName("TOpport" + str(a))
        
        while inputNodes.fields().indexFromName("TConv" + str(b)) != -1: b += 1
        inputNodes.dataProvider().addAttributes([QgsField("TConv" + str(b),QVariant.Double)])
        inputNodes.updateFields()
        convergIndex = inputNodes.fields().indexFromName("TConv" + str(b))
        
        while inputNodes.fields().indexFromName("TPolar" + str(c)) != -1: c += 1
        inputNodes.dataProvider().addAttributes([QgsField("TPolar" + str(c),QVariant.Double)])
        inputNodes.updateFields()
        polarIndex = inputNodes.fields().indexFromName("TPolar" + str(c))
        
    else:
        a,b,c = 0,0,0
        while inputNodes.fields().indexFromName("GOpport" + str(a)) != -1: a += 1
        inputNodes.dataProvider().addAttributes([QgsField("GOpport" + str(a),QVariant.Double)])
        inputNodes.updateFields()
        opportIndex = inputNodes.fields().indexFromName("GOpport" + str(a))
        
        while inputNodes.fields().indexFromName("GConv" + str(b)) != -1: b += 1
        inputNodes.dataProvider().addAttributes([QgsField("GConv" + str(b),QVariant.Double)])
        inputNodes.updateFields()
        convergIndex = inputNodes.fields().indexFromName("GConv" + str(b))
        
        while inputNodes.fields().indexFromName("GPolar" + str(c)) != -1: c += 1
        inputNodes.dataProvider().addAttributes([QgsField("GPolar" + str(c),QVariant.Double)])
        inputNodes.updateFields()
        polarIndex = inputNodes.fields().indexFromName("GPolar" + str(c))
    for node in nodesA: inputNodes.dataProvider().changeAttributeValues({node.id : {opportIndex : node.opportunity, convergIndex : node.convergence, polarIndex : node.polarity}})
    
    if outPath != "":
        crs = QgsProject.instance().crs()
        transform_context = QgsProject.instance().transformContext()
        save_options = QgsVectorFileWriter.SaveVectorOptions()
        save_options.driverName = "ESRI Shapefile"
        save_options.fileEncoding = "System"
        writer = QgsVectorFileWriter.writeAsVectorFormat(inputNodes, outPath, "System", crs, "ESRI Shapefile")
        inputNodes.dataProvider().deleteAttributes([opportIndex, convergIndex, polarIndex])
        inputNodes.updateFields()