from decimal import Decimal
from qgis import processing
from qgis.processing import alg
from qgis.PyQt.QtCore import QVariant
from qgis.core import (NULL, QgsProject, QgsSpatialIndex, QgsGeometry, QgsVectorFileWriter, QgsDistanceArea, QgsPointXY, QgsField, QgsFields, QgsVectorDataProvider)

#ui input parameters
@alg(name='nos_contato04', label='Nós Contato 0.4', group='GAUS Contato', group_label='GAUS Contato')
@alg.input(type=alg.VECTOR_LAYER, name='nodes', label='SHP com os nós', types=[0])
@alg.input(type=alg.VECTOR_LAYER, name='edges', label='SHP com as linhas de conexão', types=[1])
@alg.input(type=alg.ENUM, name='analysis', label='Tipo de Análise', options=['Topológico','Geométrico'], default = 0)
@alg.input(type=alg.NUMBER, name='radius', label='Raio de Análise (deixar 0.0 para análise global)')
@alg.input(type=alg.FIELD, name='potentialO', label='Origens', parentLayerParameterName = 'nodes')
@alg.input(type=alg.FIELD, name='potentialD', label='Destinos', parentLayerParameterName = 'nodes')
@alg.input(type=alg.FIELD, name='supply', label='Atrito', parentLayerParameterName = 'nodes')
@alg.input(type=alg.VECTOR_LAYER_DEST, name='dest', label='Criar novo shapefile para resultados? [opcional]', optional = True, createByDefault = False)

#ui output definition (does nothing, it is here because qgis requires the declaration of at least one output)
@alg.output(type=alg.NUMBER, name='numoffeat', label='Number of Features Processed')

def computeMetrics(instance, parameters, context, feedback, inputs):
    """
    This model calculates the chances of occurrence of specific land use in the shortest path connecting pairs of nodes in an urban spatial network.
    """
    
    #Class that stores the metrics for the edges of the network
    class NodeObj:
        def __init__(self, featCount, feat, potOField, potDField, supField):
            self.id = feat.id() #id number, retrieved from the input shp
            self.heapPos = -1 #current position of the edge inside the heap
            self.neighA = [] #list of connected nodes
            self.geom = feat.geometry() #geometry retrieved from the input shp
            self.sp, self.pctSp, self.contact, self.pctPot, self.avDist, self.aglom,self.reach = 0,0,0,0,0,0,0 #output metrics
            
            #potential of the edge, depends on user-defined parameters
            self.potO = feat.attribute(potOField[0])
            if self.potO == NULL: self.potO = 0
            self.potD = feat.attribute(potDField[0])
            if self.potD == NULL: self.potD = 0
            
            #potential of the edge, depends on user-defined parameters
            self.sup = feat.attribute(supField[0])
            if self.sup == NULL: self.sup = 0
    
    #verifies if highest id number is lower than number of features
    #in order to avoid potential conflicts with matrices' size
    def verifyFeatCount(inputFeat):
        featCount = inputFeat.featureCount()
        for feat in inputFeat.getFeatures(): featCount = max(featCount, feat.id()+1)
        return featCount
    
    #import input parameters
    inputNodes = instance.parameterAsVectorLayer(parameters, 'nodes', context) #nodes vector layer
    inputEdges = instance.parameterAsVectorLayer(parameters, 'edges', context) #edges vector layer
    potOField = instance.parameterAsFields(parameters, 'potentialO', context) #shp column with potential value
    potDField = instance.parameterAsFields(parameters, 'potentialD', context) #shp column with potential value
    supField = instance.parameterAsFields(parameters, 'supply', context) #shp column with potential value
    analysisType = instance.parameterAsEnum(parameters, 'analysis', context) #indication if analysis is topo or geom
    radius = instance.parameterAsDouble(parameters, 'radius', context) #radius of the analysis
    geomRule = instance.parameterAsEnum(parameters, 'geomrule', context) #chosen rule for geometry connection
    outPath = instance.parameterAsOutputLayer(parameters, 'dest', context) #path where results will be saved
    
    #nodes initialization
    nodesCount = verifyFeatCount(inputNodes)
    nodesA = [0 for i in range(nodesCount)] #array that stores network nodes
    for node in inputNodes.getFeatures(): 
        nodesA[node.id()] = NodeObj(nodesCount, node, potOField, potDField, supField)
        if node.id() % 50 == 0: feedback.pushInfo("Node {} inicializado".format(node.id()))
    
    #Initialize Edges
    feedback.pushInfo("Initialize Edges")
    nodesSpaceIndex = QgsSpatialIndex(inputNodes.getFeatures())
    
    #topological distances computation
    if analysisType == 1:
        for edge in inputEdges.getFeatures():
            edgesVertices = edge.geometry().asMultiPolyline()
            vert1 = nodesSpaceIndex.nearestNeighbor(edgesVertices[0][0], 1, 0.00015)
            vert2 = nodesSpaceIndex.nearestNeighbor(edgesVertices[0][-1], 1, 0.00015)
            if vert1 != [] and vert2 != []: #if one vertex is empty, the edge does not connect points
                dist = QgsDistanceArea().measureLine(edgesVertices[0][0],edgesVertices[0][-1])
                if dist <= radius or radius == 0.0:
                    nodesA[vert1[0]].neighA.append([nodesA[vert2[0]],dist])
                    nodesA[vert2[0]].neighA.append([nodesA[vert1[0]],dist])

    #geodetic distances computation
    else:
        for edge in inputEdges.getFeatures():
            edgesVertices = edge.geometry().asMultiPolyline()
            vert1 = nodesSpaceIndex.nearestNeighbor(edgesVertices[0][0], 1, 0.00015)
            vert2 = nodesSpaceIndex.nearestNeighbor(edgesVertices[0][-1], 1, 0.00015)
            if vert1 != [] and vert2 != []: #if one vertex is empty, the edge does not connect points
                nodesA[vert1[0]].neighA.append([nodesA[vert2[0]],1])
                nodesA[vert2[0]].neighA.append([nodesA[vert1[0]],1])
    
    #compute shortest paths (djikstra algorithm with binary heap as priority queue)
    #step 1: heap cretation
    totalLoad, totalSp, totalSpOf, totalAvDist, totalAglom = 0,0,0,0,0
    
    for source in nodesA:
        if source.id % 100 == 0: feedback.pushInfo("Caminho Mínimo Edge {}".format(source.id))
        finitePos = 0
        totalLoad += source.sup
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
        
        #step 2 heapsort
        pivotA = [[] for i in range(nodesCount)] #array of pivot edges in shortest paths
        levelFromSource = [99999999999999 for i in range(nodesCount)]
        sortedA = []
        numShortPaths, secondSearch, offerMark = [0 for i in range(nodesCount)], [0 for i in range(nodesCount)], [0 for i in range(nodesCount)]
        numShortPaths[source.id] = 1
        if source.sup > 0: offerMark[source.id] = 1
        for ind in range(len(source.neighA)):
            neighID = source.neighA[ind][0].id
            numShortPaths[neighID] = 1
            levelFromSource[neighID] = 1
            if offerMark[source.id] == 1 or source.neighA[ind][0].sup > 0: offerMark[neighID] = 1
            
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
                    neighID = closest.neighA[ind][0].id
                    prevCost = costA[neighID]
                    if prevCost > cost and (radius == 0.0 or cost <= radius):
                        if source.id == closest.id: feedback.pushInfo("GOL")
                        costA[closest.neighA[ind][0].id], levelFromSource[neighID] = cost, levelFromSource[closest.id] + 1
                        pivotA[neighID] = []
                        pivotA[neighID].append(closest)
                        numShortPaths[neighID] += numShortPaths[closest.id]
                        if closest.neighA[ind][0].sup > 0 or offerMark[closest.id] > 0: offerMark[neighID] = 1
                        
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
                    
                    elif source.id != closest.id and costA[neighID] == cost and (radius == 0.0 or cost <= radius):
                        pivotA[neighID].append(closest)
                        numShortPaths[neighID] += numShortPaths[closest.id]
                        if closest.neighA[ind][0].sup > 0 or offerMark[closest.id] > 0: offerMark[neighID] = 1
            
        #step 3 metrics update
        spTemp = [0 for i in range(nodesCount)]
        while sortedA != []:
            farest = sortedA[-1]
            population = source.potO * farest.potD
            cost = costA[farest.id]
            sortedA.pop(len(sortedA)-1)
            if radius == 0.0 or cost <= radius:
                source.reach += farest.potD
                if farest.id != source.id: source.avDist += farest.potD*costA[farest.id]
            if farest.id != source.id and (radius == 0.0 or cost <= radius): 
                spTemp[farest.id] = (population*numShortPaths[farest.id]) + secondSearch[farest.id]
                farest.sp += spTemp[farest.id]
                if offerMark[farest.id] > 0: totalSpOf += population*numShortPaths[farest.id]
                totalSp += population*numShortPaths[farest.id]
            elif (farest.id == source.id) and (radius == 0.0 or cost <= radius): 
                farest.sp += secondSearch[farest.id]
            for neigh in pivotA[farest.id]:
                if radius == 0.0 or cost <= radius: 
                    secondSearch[neigh.id] += (numShortPaths[neigh.id]/numShortPaths[farest.id])*spTemp[farest.id]
            if pivotA[farest.id] == [] and levelFromSource[farest.id] == 1 and (radius == 0.0 or cost <= radius): 
                secondSearch[source.id] += (numShortPaths[source.id]/numShortPaths[farest.id])*spTemp[farest.id]
    
    totalSpOf = 100*totalSpOf/totalSp
    
    for node in nodesA:
        node.pctPot = 100 * (node.sup / totalLoad)
        node.pctSp = 100 * (node.sp / totalSp)
        node.contact = node.pctPot * node.pctSp
        if node.reach > 1: node.avDist = node.avDist/(node.reach - 1)
        if node.avDist > 0: node.aglom = 1/node.avDist
        totalAvDist += node.avDist
        totalAglom += node.aglom
    
    #updates table of contents
    feedback.pushInfo("Updating Table of Contents")
    if analysisType == 0:
        a,b,c,d,e,f,g,h,i,j = 0,0,0,0,0,0,0,0,0,0
        
        while inputNodes.fields().indexFromName("AvDist" + str(g)) != -1: g += 1
        inputNodes.dataProvider().addAttributes([QgsField("AvDist" + str(g),QVariant.Double)])
        inputNodes.updateFields()
        avDistIndex = inputNodes.fields().indexFromName("AvDist" + str(g))
        
        while inputNodes.fields().indexFromName("%AvDist" + str(h)) != -1: h += 1
        inputNodes.dataProvider().addAttributes([QgsField("%AvDist" + str(h),QVariant.Double)])
        inputNodes.updateFields()
        pavDistIndex = inputNodes.fields().indexFromName("%AvDist" + str(h))
        
        while inputNodes.fields().indexFromName("Aglom" + str(i)) != -1: i += 1
        inputNodes.dataProvider().addAttributes([QgsField("Aglom" + str(i),QVariant.Double)])
        inputNodes.updateFields()
        aglomIndex = inputNodes.fields().indexFromName("Aglom" + str(i))
        
        while inputNodes.fields().indexFromName("%Aglom" + str(j)) != -1: j += 1
        inputNodes.dataProvider().addAttributes([QgsField("%Aglom" + str(j),QVariant.Double)])
        inputNodes.updateFields()
        paglomIndex = inputNodes.fields().indexFromName("%Aglom" + str(j))
        
        while inputNodes.fields().indexFromName("CamMin" + str(a)) != -1: a += 1
        inputNodes.dataProvider().addAttributes([QgsField("CamMin" + str(a),QVariant.Double)])
        inputNodes.updateFields()
        spIndex = inputNodes.fields().indexFromName("CamMin" + str(a))
        
        while inputNodes.fields().indexFromName("%CamMin" + str(b)) != -1: b += 1
        inputNodes.dataProvider().addAttributes([QgsField("%CamMin" + str(b),QVariant.Double)])
        inputNodes.updateFields()
        pctspIndex = inputNodes.fields().indexFromName("%CamMin" + str(b))
        
        while inputNodes.fields().indexFromName("%Load" + str(c)) != -1: c += 1
        inputNodes.dataProvider().addAttributes([QgsField("%Load" + str(c),QVariant.Double)])
        inputNodes.updateFields()
        pctLoadIndex = inputNodes.fields().indexFromName("%Load" + str(c))
        
        while inputNodes.fields().indexFromName("Contact" + str(d)) != -1: d += 1
        inputNodes.dataProvider().addAttributes([QgsField("Contact" + str(d),QVariant.Double)])
        inputNodes.updateFields()
        contactIndex = inputNodes.fields().indexFromName("Contact" + str(d))
        
        while inputNodes.fields().indexFromName("SomaCam" + str(e)) != -1: e += 1
        inputNodes.dataProvider().addAttributes([QgsField("SomaCam" + str(e),QVariant.Double)])
        inputNodes.updateFields()
        totalSpIndex = inputNodes.fields().indexFromName("SomaCam" + str(e))
        
        while inputNodes.fields().indexFromName("%CamOf" + str(f)) != -1: f += 1
        inputNodes.dataProvider().addAttributes([QgsField("%CamOf" + str(f),QVariant.Double)])
        inputNodes.updateFields()
        camOfIndex = inputNodes.fields().indexFromName("%CamOf" + str(f))

    else:
        a,b,c,d,e,f,g,h,i,j = 0,0,0,0,0,0,0,0,0,0
        while inputNodes.fields().indexFromName("AvDist" + str(g)) != -1: g += 1
        inputNodes.dataProvider().addAttributes([QgsField("AvDist" + str(g),QVariant.Double)])
        inputNodes.updateFields()
        avDistIndex = inputNodes.fields().indexFromName("AvDist" + str(g))
        
        while inputNodes.fields().indexFromName("%AvDist" + str(h)) != -1: h += 1
        inputNodes.dataProvider().addAttributes([QgsField("%AvDist" + str(h),QVariant.Double)])
        inputNodes.updateFields()
        pavDistIndex = inputNodes.fields().indexFromName("%AvDist" + str(h))
        
        while inputNodes.fields().indexFromName("Aglom" + str(i)) != -1: i += 1
        inputNodes.dataProvider().addAttributes([QgsField("Aglom" + str(i),QVariant.Double)])
        inputNodes.updateFields()
        aglomIndex = inputNodes.fields().indexFromName("Aglom" + str(i))
        
        while inputNodes.fields().indexFromName("%Aglom" + str(j)) != -1: j += 1
        inputNodes.dataProvider().addAttributes([QgsField("%Aglom" + str(j),QVariant.Double)])
        inputNodes.updateFields()
        paglomIndex = inputNodes.fields().indexFromName("%Aglom" + str(j))
        
        while inputNodes.fields().indexFromName("CamMin" + str(a)) != -1: a += 1
        inputNodes.dataProvider().addAttributes([QgsField("CamMin" + str(a),QVariant.Double)])
        inputNodes.updateFields()
        spIndex = inputNodes.fields().indexFromName("CamMin" + str(a))
        
        while inputNodes.fields().indexFromName("%CamMin" + str(b)) != -1: b += 1
        inputNodes.dataProvider().addAttributes([QgsField("%CamMin" + str(b),QVariant.Double)])
        inputNodes.updateFields()
        pctspIndex = inputNodes.fields().indexFromName("%CamMin" + str(b))
        
        while inputNodes.fields().indexFromName("%Load" + str(c)) != -1: c += 1
        inputNodes.dataProvider().addAttributes([QgsField("%Load" + str(c),QVariant.Double)])
        inputNodes.updateFields()
        pctLoadIndex = inputNodes.fields().indexFromName("%Load" + str(c))
        
        while inputNodes.fields().indexFromName("Contact" + str(d)) != -1: d += 1
        inputNodes.dataProvider().addAttributes([QgsField("Contact" + str(d),QVariant.Double)])
        inputNodes.updateFields()
        contactIndex = inputNodes.fields().indexFromName("Contact" + str(d))
        
        while inputNodes.fields().indexFromName("SomaCam" + str(e)) != -1: e += 1
        inputNodes.dataProvider().addAttributes([QgsField("SomaCam" + str(e),QVariant.Double)])
        inputNodes.updateFields()
        totalSpIndex = inputNodes.fields().indexFromName("SomaCam" + str(e))
        
        while inputNodes.fields().indexFromName("%CamOf" + str(f)) != -1: f += 1
        inputNodes.dataProvider().addAttributes([QgsField("%CamOf" + str(f),QVariant.Double)])
        inputNodes.updateFields()
        camOfIndex = inputNodes.fields().indexFromName("%CamOf" + str(f))
    
    for node in nodesA: 
        inputNodes.dataProvider().changeAttributeValues({node.id : {
            avDistIndex: node.avDist, 
            pavDistIndex: 100*node.avDist/totalAvDist,
            aglomIndex: node.aglom,
            paglomIndex: 100*node.aglom/totalAglom,
            spIndex : node.sp, 
            pctspIndex : node.pctSp, 
            pctLoadIndex : node.pctPot, 
            contactIndex : node.contact, 
            totalSpIndex : totalSp, 
            camOfIndex : totalSpOf}})
    
    if outPath != "":
        crs = QgsProject.instance().crs()
        transform_context = QgsProject.instance().transformContext()
        save_options = QgsVectorFileWriter.SaveVectorOptions()
        save_options.driverName = "ESRI Shapefile"
        save_options.fileEncoding = "System"
        writer = QgsVectorFileWriter.writeAsVectorFormat(inputNodes, outPath, "System", crs, "ESRI Shapefile")
        inputNodes.dataProvider().deleteAttributes([
            avDistIndex, 
            pavDistIndex,
            aglomIndex,
            paglomIndex,
            spIndex, 
            pctspIndex, 
            pctLoadIndex, 
            contactIndex, 
            totalSpIndex, 
            camOfIndex])
        inputNodes.updateFields()


