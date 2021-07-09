from decimal import Decimal
from qgis import processing
from qgis.processing import alg
from qgis.PyQt.QtCore import QVariant
from qgis.core import (NULL, QgsProject, QgsGeometry, QgsVectorFileWriter, QgsSpatialIndex, QgsDistanceArea, QgsPointXY, QgsField, QgsFields, QgsVectorDataProvider)

#ui input parameters
@alg(name='GAUS_pl11', label='GAUS Points+Lines 1.1', group='GAUS v1.1', group_label='GAUS v1.1')
@alg.input(type=alg.VECTOR_LAYER, name='inpLines', label='Lines', types=[1])
@alg.input(type=alg.VECTOR_LAYER, name='inpPoints', label='Points', types=[0])
@alg.input(type=alg.ENUM, name='analysis', label='Analysis Type', options=['Topological','Geodetic'], default = 0)
@alg.input(type=alg.ENUM, name='metrics', label='Metrics to be Computed', options=['Accessibility','Betweenness','Freeman-Krafta Centrality','Opportunity','Convergence','Polarity','Reach','Connectivity'], allowMultiple=True)
@alg.input(type=alg.NUMBER, name='radius', label='Analysis Radius (0.0 = Global Analysis)')
@alg.input(type=alg.FIELD, name='impedance',label='Impedance of Lines',parentLayerParameterName = 'inpLines',allowMultiple=True,optional = True)
@alg.input(type=alg.FIELD, name='load',label='Load of Points',parentLayerParameterName = 'inpPoints',allowMultiple=True,optional = True)
@alg.input(type=alg.FIELD, name='supply',label='Supply in Points',parentLayerParameterName = 'inpPoints',allowMultiple=True,optional = True)
@alg.input(type=alg.FIELD, name='demand',label='Demand in Points',parentLayerParameterName = 'inpPoints',allowMultiple=True,optional = True)
@alg.input(type=alg.VECTOR_LAYER_DEST, name='dest', label='Create New Shapefiles for Results? [optional]', optional = True, createByDefault = False)
@alg.input(type=alg.NUMBER, name='precision', label='Distance Precision', default=0.00015)

#ui output definition (does nothing, it is here because qgis requires the declaration of at least one output)
@alg.output(type=alg.NUMBER, name='numoffeat', label='Number of Features Processed')

def computeMetrics(instance, parameters, context, feedback, inputs):
    """
    Computes configurational metrics for a network composed of points whose connections are indicated by lines.
    
    Fields Description:
    Points: vector layer of the network's nodes.
    Lines: vector layer of the network's lines.
    Analysis: in topological analysis, the distance between connected nodes is equal to 1. In geodetic analysis, the geodetic distance between them is considered.
    Metrics to be calculated: the selected metrics will be the ones whose result will be displayed in the attributes table.
    Analysis Radius: only the pairs of nodes whose distance is within the defined radius will be considered for the analysis. Zero means that all pairs of nodes are considered.
    Impedance: field of the lines vector layer containing the impedance of each line.
    Load: field of the points vector layer containing the load of each node.
    Supply: field of the points vector layer containing the supply of each node.
    Demand: field of the points vector layer containing the demand of each node.
    Distance Precision: maximum distance between point and line vertex that will be considered as a connection between them.
    Create New Shapefile for Results?: if it is left blank, the results will be inserted in the existing nodes vector layer. Otherwise, a copy of the vector layer will be created containing the results.
    """

    #Nodes of the network
    class NodeObj:
        def __init__(self, featCount, feat, loadF, supplyF, demandF, metricsL):
            self.id = feat.id()
            self.heapPos = -1 #current position of the node inside the heap
            self.neighA = []  #list of connected nodes
            
            #configurational metrics
            if 0 in metricsL: self.access = 0
            if 1 in metricsL: self.btw = 0
            if 2 in metricsL: self.cent = 0
            if 3 in metricsL: self.opport = 0
            if 4 in metricsL: self.converg = 0
            if 5 in metricsL: self.polarity = 0
            if 6 in metricsL: self.reach = 0
            
            #calculation weightings
            self.load, self.supply, self.demand = 0,0,0
            if loadF == []: self.load = 1
            else:
                for i in range(len(loadF)): 
                    if feat.attribute(loadF[i]) != NULL: self.load += feat.attribute(loadF[i])
            if supplyF == []: self.supply = 1
            else:
                for i in range(len(supplyF)): 
                    if feat.attribute(supplyF[i]) != NULL: self.supply += feat.attribute(supplyF[i])
            if demandF == []: self.demand = 1
            else:
                for i in range(len(demandF)): 
                    if feat.attribute(demandF[i]) != NULL: self.demand += feat.attribute(demandF[i])
    
    #verifies if highest id number is lower than number of features
    #in order to avoid potential conflicts with matrices' size
    def verifyFeatCount(inputFeat):
        featCount = inputFeat.featureCount()
        for feat in inputFeat.getFeatures(): featCount = max(featCount, feat.id()+1)
        return featCount
    
    def defineDistance(edge,analysisType,impField,edgeA,edgeB):
        if impField == []: imp = 1
        else:
            imp = 0
            for i in range(len(impField)): 
                if edge.attribute(impField[i]) != NULL: imp += edge.attribute(impField[i])
            
        dist = imp if analysisType == 0 else imp*QgsDistanceArea().measureLine(edgeA,edgeB)
        return dist
    
    #import user input parameters
    inputNodes = instance.parameterAsVectorLayer(parameters, 'inpPoints', context)
    inputEdges = instance.parameterAsVectorLayer(parameters, 'inpLines', context)
    metricsL = instance.parameterAsEnums(parameters, 'metrics', context)
    impField = instance.parameterAsFields(parameters, 'impedance', context)
    loadField = instance.parameterAsFields(parameters, 'load', context)
    supplyField = instance.parameterAsFields(parameters, 'supply', context)
    demandField = instance.parameterAsFields(parameters, 'demand', context)
    analysisType = instance.parameterAsEnum(parameters, 'analysis', context)
    radius = instance.parameterAsDouble(parameters, 'radius', context)
    outPath = instance.parameterAsOutputLayer(parameters, 'dest', context)
    prec = instance.parameterAsDouble(parameters, 'precision', context)
    
    #nodes initialization
    nodesCount = verifyFeatCount(inputNodes)
    nodesA = [0 for i in range(nodesCount)] #array that stores network nodes
    for node in inputNodes.getFeatures(): 
        nodesA[node.id()] = NodeObj(nodesCount, node, loadField, supplyField, demandField,metricsL)
        if node.id() % 100 == 0: feedback.pushInfo(f'Initializing Node {node.id()}')
    
    #Initialize Edges
    feedback.pushInfo("Initialize Edges")
    nodesSpaceIndex = QgsSpatialIndex(inputNodes.getFeatures())
    for edge in inputEdges.getFeatures():
        edgesVertices = edge.geometry().asMultiPolyline()
        vert1 = nodesSpaceIndex.nearestNeighbor(edgesVertices[0][0], 1, prec)
        vert2 = nodesSpaceIndex.nearestNeighbor(edgesVertices[0][-1], 1, prec)
        if vert1 != [] and vert2 != []:
            dist = defineDistance(edge,analysisType,impField,edgesVertices[0][0],edgesVertices[0][-1])
            if dist <= radius or radius == 0.0:
                nodesA[vert1[0]].neighA.append([nodesA[vert2[0]],dist])
                nodesA[vert2[0]].neighA.append([nodesA[vert1[0]],dist])
    
    #Compute Shortest Paths (Djikstra Algorithm with Binary Heap as Priority Queue)
    #1-Heap cretation
    if metricsL != [7]:
        for source in nodesA:
            if source.id % 50 == 0: feedback.pushInfo(f'Shortest Path {source.id}')
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
            level = [0 for i in range(nodesCount)]
            numSP = [0 for i in range(nodesCount)]
            sortedA = [] 
            numSP[source.id], level[source.id] = 1,0
            for ind in range(len(source.neighA)): 
                numSP[source.neighA[ind][0].id] = 1 
                level[source.neighA[ind][0].id] = 1
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
                            costA[closest.neighA[ind][0].id], level[closest.neighA[ind][0].id] = cost, level[closest.id] + 1
                            pivotA[closest.neighA[ind][0].id] = []
                            pivotA[closest.neighA[ind][0].id].append(closest)
                            numSP[closest.neighA[ind][0].id] += numSP[closest.id]
                        
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
                            numSP[closest.neighA[ind][0].id] += numSP[closest.id]
                
            #3-Metrics update
            if 1 in metricsL: btwTemp = [0 for i in range(nodesCount)] 
            if 2 in metricsL: fkcTemp = [0 for i in range(nodesCount)]
            if 4 in metricsL or 5 in metricsL: cvgTemp = [0 for i in range(nodesCount)]
            while sortedA != []:
                farest = sortedA[-1]
                cost = costA[farest.id]
                if radius == 0.0 or cost <= radius: 
                    if 0 in metricsL and farest.id != source.id: source.access += farest.load/costA[farest.id]
                    if 3 in metricsL and source.demand > 0: source.opport += farest.supply/(costA[farest.id]+1)
                    if 6 in metricsL: source.reach += farest.load
                sortedA.pop(len(sortedA)-1)
                pot = farest.load * source.load
                tension = source.supply*farest.demand
                
                for neigh in pivotA[farest.id]:
                    if radius == 0.0 or cost <= radius:
                        if 1 in metricsL: btwTemp[neigh.id] += (numSP[neigh.id]/numSP[farest.id])*(1 + btwTemp[farest.id])
                        if 2 in metricsL: fkcTemp[neigh.id] += (numSP[neigh.id]/numSP[farest.id])*((pot/(level[farest.id]+1))+fkcTemp[farest.id])
                        if 4 in metricsL or 5 in metricsL: cvgTemp[neigh.id] += (numSP[neigh.id]/numSP[farest.id])*((tension/(level[farest.id]+1))+cvgTemp[farest.id])
                
                if pivotA[farest.id] == [] and level[farest.id] == 1 and (radius == 0.0 or cost <= radius): 
                    if 2 in metricsL: fkcTemp[source.id] += (pot/2)+fkcTemp[farest.id]
                    if 4 in metricsL or 5 in metricsL: cvgTemp[source.id] += (numSP[neigh.id]/numSP[farest.id])*((tension/(level[farest.id]+1))+cvgTemp[farest.id])
                
                if farest.id != source.id and (radius == 0.0 or cost <= radius): 
                    if 1 in metricsL: farest.btw += btwTemp[farest.id]/2
                    if 2 in metricsL: fkcTemp[farest.id] += pot/(level[farest.id]+1)
                if (4 in metricsL or 5 in metricsL) and (radius == 0.0 or cost <= radius): cvgTemp[farest.id] += tension/(level[farest.id]+1)
                
                if 2 in metricsL: farest.cent += fkcTemp[farest.id]/2
                if 4 in metricsL and farest.supply > 0: farest.converg += cvgTemp[farest.id]
                if 5 in metricsL: farest.polarity += cvgTemp[farest.id]
    
    #update table of contents
    strBegin = "T" if analysisType == 0 else "G"
    strMid = "g" if radius == 0.0 else str(int(radius))
    if len(strMid) > 5: strBegin += strMid[0:5]
    else: strBegin += strMid
    
    if 0 in metricsL:
        aux = 0
        while inputNodes.fields().indexFromName(strBegin + "Acc" + str(aux)) != -1: aux += 1
        inputNodes.dataProvider().addAttributes([QgsField(strBegin + "Acc" + str(aux),QVariant.Double)])
        inputNodes.updateFields()
        accIndex = inputNodes.fields().indexFromName(strBegin + "Acc" + str(aux))
    if 1 in metricsL:
        aux = 0
        while inputNodes.fields().indexFromName(strBegin + "Btw" + str(aux)) != -1: aux += 1
        inputNodes.dataProvider().addAttributes([QgsField(strBegin + "Btw" + str(aux),QVariant.Double)])
        inputNodes.updateFields()
        btwIndex = inputNodes.fields().indexFromName(strBegin + "Btw" + str(aux))
    if 2 in metricsL:
        aux = 0
        while inputNodes.fields().indexFromName(strBegin + "Cen" + str(aux)) != -1: aux += 1
        inputNodes.dataProvider().addAttributes([QgsField(strBegin + "Cen" + str(aux),QVariant.Double)])
        inputNodes.updateFields()
        centIndex = inputNodes.fields().indexFromName(strBegin + "Cen" + str(aux))
    if 3 in metricsL:
        aux = 0
        while inputNodes.fields().indexFromName(strBegin + "Opp" + str(aux)) != -1: aux += 1
        inputNodes.dataProvider().addAttributes([QgsField(strBegin + "Opp" + str(aux),QVariant.Double)])
        inputNodes.updateFields()
        oppIndex = inputNodes.fields().indexFromName(strBegin + "Opp" + str(aux))
    if 4 in metricsL:
        aux = 0
        while inputNodes.fields().indexFromName(strBegin + "Cvg" + str(aux)) != -1: aux += 1
        inputNodes.dataProvider().addAttributes([QgsField(strBegin + "Cvg" + str(aux),QVariant.Double)])
        inputNodes.updateFields()
        cvgIndex = inputNodes.fields().indexFromName(strBegin + "Cvg" + str(aux))
    if 5 in metricsL:
        aux = 0
        while inputNodes.fields().indexFromName(strBegin + "Pol" + str(aux)) != -1: aux += 1
        inputNodes.dataProvider().addAttributes([QgsField(strBegin + "Pol" + str(aux),QVariant.Double)])
        inputNodes.updateFields()
        polIndex = inputNodes.fields().indexFromName(strBegin + "Pol" + str(aux))
    if 6 in metricsL:
        aux = 0
        while inputNodes.fields().indexFromName(strBegin + "Rea" + str(aux)) != -1: aux += 1
        inputNodes.dataProvider().addAttributes([QgsField(strBegin + "Rea" + str(aux),QVariant.Double)])
        inputNodes.updateFields()
        reachIndex = inputNodes.fields().indexFromName(strBegin + "Rea" + str(aux))
    if 7 in metricsL:
        aux = 0
        while inputNodes.fields().indexFromName(strBegin + "Cnc" + str(aux)) != -1: aux += 1
        inputNodes.dataProvider().addAttributes([QgsField(strBegin + "Cnc" + str(aux),QVariant.Double)])
        inputNodes.updateFields()
        cncIndex = inputNodes.fields().indexFromName(strBegin + "Cnc" + str(aux))
    
    for node in nodesA:
        metricsD = {}
        if 0 in metricsL: metricsD[accIndex] = node.access
        if 1 in metricsL: metricsD[btwIndex] = node.btw
        if 2 in metricsL: metricsD[centIndex] = node.cent
        if 3 in metricsL: metricsD[oppIndex] = node.opport
        if 4 in metricsL: metricsD[cvgIndex] = node.converg
        if 5 in metricsL: metricsD[polIndex] = node.polarity
        if 6 in metricsL: metricsD[reachIndex] = node.reach
        if 7 in metricsL: metricsD[cncIndex] = len(node.neighA)
        inputNodes.dataProvider().changeAttributeValues({node.id : metricsD})
    
    if outPath != "":
        crs = QgsProject.instance().crs()
        transform_context = QgsProject.instance().transformContext()
        save_options = QgsVectorFileWriter.SaveVectorOptions()
        save_options.driverName = "ESRI Shapefile"
        save_options.fileEncoding = "System"
        writer = QgsVectorFileWriter.writeAsVectorFormat(inputNodes, outPath, "System", crs, "ESRI Shapefile")
        metricsOut = []
        if 0 in metricsL: metricsOut.append(accIndex)
        if 1 in metricsL: metricsOut.append(btwIndex)
        if 2 in metricsL: metricsOut.append(centIndex)
        if 3 in metricsL: metricsOut.append(oppIndex)
        if 4 in metricsL: metricsOut.append(cvgIndex)
        if 5 in metricsL: metricsOut.append(polIndex)
        if 6 in metricsL: metricsOut.append(reachIndex)
        if 7 in metricsL: metricsOut.append(cncIndex)
        inputNodes.dataProvider().deleteAttributes(metricsOut)
        inputNodes.updateFields()

    
    
    
    
    
    



