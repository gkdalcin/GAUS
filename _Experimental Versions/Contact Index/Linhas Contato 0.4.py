from decimal import Decimal
from qgis import processing
from qgis.processing import alg
from qgis.PyQt.QtCore import QVariant
from qgis.core import (QgsProject, QgsGeometry, QgsVectorFileWriter, QgsDistanceArea, QgsPointXY, QgsField, QgsFields, QgsVectorDataProvider)

#ui input parameters
@alg(name='linhas_contato04', label='Linhas Contato 0.4', group='GAUS Contato', group_label='GAUS Contato')
@alg.input(type=alg.VECTOR_LAYER, name='edges', label='SHP com os trechos', types=[1])
@alg.input(type=alg.ENUM, name='analysis', label='Tipo de Análise', options=['Topológico','Geométrico'], default = 0)
@alg.input(type=alg.NUMBER, name='radius', label='Raio de Análise (deixar 0.0 para análise global)')
@alg.input(type=alg.ENUM, name='geomrule', label='Regra de Conexão das Linhas', options=['Vértices Coincidentes','Linhas Que Se Cruzam', 'Ambos'], default = 0)
@alg.input(type=alg.FIELD, name='potentialO', label='Origens', parentLayerParameterName = 'edges')
@alg.input(type=alg.FIELD, name='potentialD', label='Destinos', parentLayerParameterName = 'edges')
@alg.input(type=alg.FIELD, name='supply', label='Atrito', parentLayerParameterName = 'edges')
@alg.input(type=alg.VECTOR_LAYER_DEST, name='dest', label='Criar novo shapefile para resultados? [opcional]', optional = True, createByDefault = False)

#ui output definition (does nothing, it is here because qgis requires the declaration of at least one output)
@alg.output(type=alg.NUMBER, name='numoffeat', label='Number of Features Processed')

def computeMetrics(instance, parameters, context, feedback, inputs):
    """
    This model calculates the chances of occurrence of specific land use in the shortest path connecting pairs of nodes in an urban spatial network.
    """
    
    #Class that stores the metrics for the edges of the network
    class EdgeObj:
        def __init__(self, featCount, feat, potOField, potDField, supField):
            self.id = feat.id() #id number, retrieved from the input shp
            self.heapPos = -1 #current position of the edge inside the heap
            self.neighA = [] #list of connected edges
            self.geom = feat.geometry() #geometry retrieved from the input shp
            self.length = QgsDistanceArea().measureLength(feat.geometry())
            self.sp, self.pctSp, self.contact, self.pctPot, self.avDist, self.aglom,self.reach = 0,0,0,0,0,0,0 #output metrics
            
            #potential of the edge, depends on user-defined parameters
            self.potO = feat.attribute(potOField[0])
            self.potD = feat.attribute(potDField[0])
            
            #potential of the edge, depends on user-defined parameters
            self.sup = feat.attribute(supField[0])
    
    #verifies if highest id number is lower than number of features
    #in order to avoid potential conflicts with matrices' size
    def verifyFeatCount(inputFeat):
        featCount = inputFeat.featureCount()
        for feat in inputFeat.getFeatures(): featCount = max(featCount, feat.id()+1)
        return featCount
    
    #import input parameters
    inputEdges = instance.parameterAsVectorLayer(parameters, 'edges', context) #edges vector layer
    potOField = instance.parameterAsFields(parameters, 'potentialO', context) #shp column with potential value
    potDField = instance.parameterAsFields(parameters, 'potentialD', context) #shp column with potential value
    supField = instance.parameterAsFields(parameters, 'supply', context) #shp column with potential value
    analysisType = instance.parameterAsEnum(parameters, 'analysis', context) #indication if analysis is topo or geom
    radius = instance.parameterAsDouble(parameters, 'radius', context) #radius of the analysis
    geomRule = instance.parameterAsEnum(parameters, 'geomrule', context) #chosen rule for geometry connection
    outPath = instance.parameterAsOutputLayer(parameters, 'dest', context) #path where results will be saved
    
    #edges initialization
    edgesCount = verifyFeatCount(inputEdges)
    edgesA = [] #array that stores network edges
    if geomRule == 0:
        for edge in inputEdges.getFeatures():
            if edge.id() % 100 == 0: feedback.pushInfo("Edge {} inicializada".format(edge.id()))
            edgesA.append(EdgeObj(edgesCount, edge, potOField, potDField, supField))
            for i in range(len(edgesA)-1):
            #edges are connected according to input parameter
                if edgesA[-1].geom.touches(edgesA[i].geom):
                    #if analysis is geometrical, distance is geometrical
                    if analysisType == 1: 
                        dist = (edgesA[-1].length + edgesA[i].length)/2
                        if dist <= radius or radius ==  0.0:
                            edgesA[-1].neighA.append([edgesA[i], dist])
                            edgesA[i].neighA.append([edgesA[-1], dist])
                            if edgesA[-1].neighA[-1][1] != edgesA[i].neighA[-1][1]: feedback.pushInfo("deu ruim")
                    #if analysis is topographical, distance is topographical
                    else: 
                        edgesA[-1].neighA.append([edgesA[i], 1])
                        edgesA[i].neighA.append([edgesA[-1], 1])
    elif geomRule == 1:
        for edge in inputEdges.getFeatures():
            if edge.id() % 100 == 0: feedback.pushInfo("Edge {} inicializada".format(edge.id()))
            edgesA.append(EdgeObj(edgesCount, edge, potOField, potDField, supField))
            for i in range(len(edgesA)-1):
            #edges are connected according to input parameter
                if edgesA[-1].geom.crosses(edgesA[i].geom):
                    #if analysis is geometrical, distance is geometrical
                    if analysisType == 1: 
                        dist = (edgesA[-1].length + edgesA[i].length)/2
                        if dist <= radius or radius ==  0.0:
                            edgesA[-1].neighA.append([edgesA[i], dist])
                            edgesA[i].neighA.append([edgesA[-1], dist])
                    #if analysis is topographical, distance is topographical
                    else: 
                        edgesA[-1].neighA.append([edgesA[i], 1])
                        edgesA[i].neighA.append([edgesA[-1], 1])
    elif geomRule == 2:
        for edge in inputEdges.getFeatures():
            if edge.id() % 100 == 0: feedback.pushInfo("Edge {} inicializada".format(edge.id()))
            edgesA.append(EdgeObj(edgesCount, edge, potOField, potDField, supField))
            for i in range(len(edgesA)-1):
            #edges are connected according to input parameter
                if edgesA[-1].geom.crosses(edgesA[i].geom) or edgesA[-1].geom.touches(edgesA[i].geom):
                    #if analysis is geometrical, distance is geometrical
                    if analysisType == 1: 
                        dist = (edgesA[-1].length + edgesA[i].length)/2
                        if dist <= radius or radius ==  0.0:
                            edgesA[-1].neighA.append([edgesA[i], dist])
                            edgesA[i].neighA.append([edgesA[-1], dist])
                    #if analysis is topographical, distance is topographical
                    else: 
                        edgesA[-1].neighA.append([edgesA[i], 1])
                        edgesA[i].neighA.append([edgesA[-1], 1])
    
    #compute shortest paths (djikstra algorithm with binary heap as priority queue)
    #step 1: heap cretation
    totalLoad, totalSp, totalSpOf, totalAvDist, totalAglom = 0,0,0,0,0
    
    for source in edgesA:
        if source.id % 100 == 0: feedback.pushInfo("Caminho Mínimo Edge {}".format(source.id))
        finitePos = 0
        totalLoad += source.sup
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
        numShortPaths, secondSearch, offerMark = [0 for i in range(edgesCount)], [0 for i in range(edgesCount)], [0 for i in range(edgesCount)]
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
            
        #step 3 centrality values update
        spTemp = [0 for i in range(edgesCount)]
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
    
    for edge in edgesA:
        edge.pctPot = 100 * (edge.sup / totalLoad)
        edge.pctSp = 100 * (edge.sp / totalSp)
        edge.contact = edge.pctPot * edge.pctSp
        if edge.reach > 1: edge.avDist = edge.avDist/(edge.reach - 1)
        if edge.avDist > 0: edge.aglom = 1/edge.avDist
        totalAvDist += edge.avDist
        totalAglom += edge.aglom
    
    #updates table of contents
    feedback.pushInfo("Updating Table of Contents")
    if analysisType == 0:
        a,b,c,d,e,f,g,h,i,j = 0,0,0,0,0,0,0,0,0,0
        
        while inputEdges.fields().indexFromName("AvDist" + str(g)) != -1: g += 1
        inputEdges.dataProvider().addAttributes([QgsField("AvDist" + str(g),QVariant.Double)])
        inputEdges.updateFields()
        avDistIndex = inputEdges.fields().indexFromName("AvDist" + str(g))
        
        while inputEdges.fields().indexFromName("%AvDist" + str(h)) != -1: h += 1
        inputEdges.dataProvider().addAttributes([QgsField("%AvDist" + str(h),QVariant.Double)])
        inputEdges.updateFields()
        pavDistIndex = inputEdges.fields().indexFromName("%AvDist" + str(h))
        
        while inputEdges.fields().indexFromName("Aglom" + str(i)) != -1: i += 1
        inputEdges.dataProvider().addAttributes([QgsField("Aglom" + str(i),QVariant.Double)])
        inputEdges.updateFields()
        aglomIndex = inputEdges.fields().indexFromName("Aglom" + str(i))
        
        while inputEdges.fields().indexFromName("%Aglom" + str(j)) != -1: j += 1
        inputEdges.dataProvider().addAttributes([QgsField("%Aglom" + str(j),QVariant.Double)])
        inputEdges.updateFields()
        paglomIndex = inputEdges.fields().indexFromName("%Aglom" + str(j))
        
        while inputEdges.fields().indexFromName("CamMin" + str(a)) != -1: a += 1
        inputEdges.dataProvider().addAttributes([QgsField("CamMin" + str(a),QVariant.Double)])
        inputEdges.updateFields()
        spIndex = inputEdges.fields().indexFromName("CamMin" + str(a))
        
        while inputEdges.fields().indexFromName("%CamMin" + str(b)) != -1: b += 1
        inputEdges.dataProvider().addAttributes([QgsField("%CamMin" + str(b),QVariant.Double)])
        inputEdges.updateFields()
        pctspIndex = inputEdges.fields().indexFromName("%CamMin" + str(b))
        
        while inputEdges.fields().indexFromName("%Load" + str(c)) != -1: c += 1
        inputEdges.dataProvider().addAttributes([QgsField("%Load" + str(c),QVariant.Double)])
        inputEdges.updateFields()
        pctLoadIndex = inputEdges.fields().indexFromName("%Load" + str(c))
        
        while inputEdges.fields().indexFromName("Contact" + str(d)) != -1: d += 1
        inputEdges.dataProvider().addAttributes([QgsField("Contact" + str(d),QVariant.Double)])
        inputEdges.updateFields()
        contactIndex = inputEdges.fields().indexFromName("Contact" + str(d))
        
        while inputEdges.fields().indexFromName("SomaCam" + str(e)) != -1: e += 1
        inputEdges.dataProvider().addAttributes([QgsField("SomaCam" + str(e),QVariant.Double)])
        inputEdges.updateFields()
        totalSpIndex = inputEdges.fields().indexFromName("SomaCam" + str(e))
        
        while inputEdges.fields().indexFromName("%CamOf" + str(f)) != -1: f += 1
        inputEdges.dataProvider().addAttributes([QgsField("%CamOf" + str(f),QVariant.Double)])
        inputEdges.updateFields()
        camOfIndex = inputEdges.fields().indexFromName("%CamOf" + str(f))

    else:
        a,b,c,d,e,f,g,h,i,j = 0,0,0,0,0,0,0,0,0,0
        while inputEdges.fields().indexFromName("AvDist" + str(g)) != -1: g += 1
        inputEdges.dataProvider().addAttributes([QgsField("AvDist" + str(g),QVariant.Double)])
        inputEdges.updateFields()
        avDistIndex = inputEdges.fields().indexFromName("AvDist" + str(g))
        
        while inputEdges.fields().indexFromName("%AvDist" + str(h)) != -1: h += 1
        inputEdges.dataProvider().addAttributes([QgsField("%AvDist" + str(h),QVariant.Double)])
        inputEdges.updateFields()
        pavDistIndex = inputEdges.fields().indexFromName("%AvDist" + str(h))
        
        while inputEdges.fields().indexFromName("Aglom" + str(i)) != -1: i += 1
        inputEdges.dataProvider().addAttributes([QgsField("Aglom" + str(i),QVariant.Double)])
        inputEdges.updateFields()
        aglomIndex = inputEdges.fields().indexFromName("Aglom" + str(i))
        
        while inputEdges.fields().indexFromName("%Aglom" + str(j)) != -1: j += 1
        inputEdges.dataProvider().addAttributes([QgsField("%Aglom" + str(j),QVariant.Double)])
        inputEdges.updateFields()
        paglomIndex = inputEdges.fields().indexFromName("%Aglom" + str(j))
        
        while inputEdges.fields().indexFromName("CamMin" + str(a)) != -1: a += 1
        inputEdges.dataProvider().addAttributes([QgsField("CamMin" + str(a),QVariant.Double)])
        inputEdges.updateFields()
        spIndex = inputEdges.fields().indexFromName("CamMin" + str(a))
        
        while inputEdges.fields().indexFromName("%CamMin" + str(b)) != -1: b += 1
        inputEdges.dataProvider().addAttributes([QgsField("%CamMin" + str(b),QVariant.Double)])
        inputEdges.updateFields()
        pctspIndex = inputEdges.fields().indexFromName("%CamMin" + str(b))
        
        while inputEdges.fields().indexFromName("%Load" + str(c)) != -1: c += 1
        inputEdges.dataProvider().addAttributes([QgsField("%Load" + str(c),QVariant.Double)])
        inputEdges.updateFields()
        pctLoadIndex = inputEdges.fields().indexFromName("%Load" + str(c))
        
        while inputEdges.fields().indexFromName("Contact" + str(d)) != -1: d += 1
        inputEdges.dataProvider().addAttributes([QgsField("Contact" + str(d),QVariant.Double)])
        inputEdges.updateFields()
        contactIndex = inputEdges.fields().indexFromName("Contact" + str(d))
        
        while inputEdges.fields().indexFromName("SomaCam" + str(e)) != -1: e += 1
        inputEdges.dataProvider().addAttributes([QgsField("SomaCam" + str(e),QVariant.Double)])
        inputEdges.updateFields()
        totalSpIndex = inputEdges.fields().indexFromName("SomaCam" + str(e))
        
        while inputEdges.fields().indexFromName("%CamOf" + str(f)) != -1: f += 1
        inputEdges.dataProvider().addAttributes([QgsField("%CamOf" + str(f),QVariant.Double)])
        inputEdges.updateFields()
        camOfIndex = inputEdges.fields().indexFromName("%CamOf" + str(f))
    
    for edge in edgesA: 
        inputEdges.dataProvider().changeAttributeValues({edge.id : {
            avDistIndex: edge.avDist, 
            pavDistIndex: 100*edge.avDist/totalAvDist,
            aglomIndex: edge.aglom,
            paglomIndex: 100*edge.aglom/totalAglom,
            spIndex : edge.sp, 
            pctspIndex : edge.pctSp, 
            pctLoadIndex : edge.pctPot, 
            contactIndex : edge.contact, 
            totalSpIndex : totalSp, 
            camOfIndex : totalSpOf}})
    
    if outPath != "":
        crs = QgsProject.instance().crs()
        transform_context = QgsProject.instance().transformContext()
        save_options = QgsVectorFileWriter.SaveVectorOptions()
        save_options.driverName = "ESRI Shapefile"
        save_options.fileEncoding = "System"
        writer = QgsVectorFileWriter.writeAsVectorFormat(inputEdges, outPath, "System", crs, "ESRI Shapefile")
        inputEdges.dataProvider().deleteAttributes([
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
        inputEdges.updateFields()


