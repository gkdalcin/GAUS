from decimal import Decimal
from qgis import processing
from qgis.processing import alg
from qgis.PyQt.QtCore import QVariant
from qgis.core import (NULL, QgsProject, QgsGeometry, QgsVectorFileWriter, QgsDistanceArea, QgsPointXY, QgsField, QgsFields, QgsVectorDataProvider)

#ui input parameters
@alg(name='GAUS_l11', label='GAUS Lines 1.1', group='GAUS v1.1', group_label='GAUS v1.1')
@alg.input(type=alg.VECTOR_LAYER, name='inpLines', label='Lines', types=[1])
@alg.input(type=alg.ENUM, name='analysis', label='Analysis Type', options=['Topological','Geodetic'], default = 0)
@alg.input(type=alg.ENUM, name='metrics', label='Metrics to be Computed', options=['Accessibility','Betweenness','Freeman-Krafta Centrality','Opportunity','Convergence','Polarity','Reach','Connectivity'], allowMultiple=True)
@alg.input(type=alg.ENUM, name='geomrule', label='Rule for Connecting Lines', options=['Overlapping Vertices','Crossing Lines', 'Overlapping Vertices + Crossing Lines'], default = 0)
@alg.input(type=alg.NUMBER, name='radius', label='Analysis Radius (0.0 = Global Analysis)')
@alg.input(type=alg.FIELD, name='impedance',label='Impedance of Lines',parentLayerParameterName = 'inpLines',allowMultiple=True,optional = True)
@alg.input(type=alg.FIELD, name='load',label='Load of Lines',parentLayerParameterName = 'inpLines',allowMultiple=True,optional = True)
@alg.input(type=alg.FIELD, name='supply',label='Supply in Lines',parentLayerParameterName = 'inpLines',allowMultiple=True,optional = True)
@alg.input(type=alg.FIELD, name='demand',label='Demand in Lines',parentLayerParameterName = 'inpLines',allowMultiple=True,optional = True)
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
    
    #Edges of the network
    class EdgeObj:
        def __init__(self, featCount, feat, loadF, supplyF, demandF, impF, analysisType, metricsL):
            self.id = feat.id()
            self.heapPos = -1 #current position of the edge inside the heap
            self.neighA = [] #list of connected edges
            self.geom = feat.geometry()
            self.length = QgsDistanceArea().measureLength(feat.geometry()) if analysisType == 1 else 1
            
            #configurational metrics
            if 0 in metricsL: self.access = 0
            if 1 in metricsL: self.btw = 0
            if 2 in metricsL: self.cent = 0
            if 3 in metricsL: self.opport = 0
            if 4 in metricsL: self.converg = 0
            if 5 in metricsL: self.polarity = 0
            if 6 in metricsL: self.reach = 0
            
            self.load, self.supply, self.demand, self.imp = 0,0,0,0
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
            if impF == []: self.imp = 1
            else:
                for i in range(len(impF)): 
                    if feat.attribute(impF[i]) != NULL: self.imp += feat.attribute(impF[i])
    
    #verifies if highest id number is lower than number of features
    #in order to avoid potential conflicts with matrices' size
    def verifyFeatCount(inputFeat):
        featCount = inputFeat.featureCount()
        for feat in inputFeat.getFeatures(): featCount = max(featCount, feat.id()+1)
        return featCount
    
    #import input parameters
    inputEdges = instance.parameterAsVectorLayer(parameters, 'inpLines', context) #edges vector layer
    metricsL = instance.parameterAsEnums(parameters, 'metrics', context)
    impField = instance.parameterAsFields(parameters, 'impedance', context) #shp column with impedance values
    loadField = instance.parameterAsFields(parameters, 'load', context) #shp column with potential value
    supplyField = instance.parameterAsFields(parameters, 'supply', context) #shp column with potential value
    demandField = instance.parameterAsFields(parameters, 'demand', context) #shp column with potential value
    analysisType = instance.parameterAsEnum(parameters, 'analysis', context) #indication if analysis is topo or geom
    radius = instance.parameterAsDouble(parameters, 'radius', context) #radius of the analysis
    geomR = instance.parameterAsEnum(parameters, 'geomrule', context) #chosen rule for geometry connection
    outPath = instance.parameterAsOutputLayer(parameters, 'dest', context) #path where results will be saved
    
    #edges initialization
    edgesCount = verifyFeatCount(inputEdges)
    edgesA = [] #array that stores network edges
    for edge in inputEdges.getFeatures():
        if edge.id() % 50 == 0: feedback.pushInfo(f'Initializing Edge {edge.id()}')
        edgesA.append(EdgeObj(edgesCount, edge, loadField, supplyField, demandField, impField, analysisType, metricsL))
        for i in range(len(edgesA)-1):
            if (geomR==0 and edgesA[-1].geom.touches(edgesA[i].geom)) or (geomR==1 and edgesA[-1].geom.crosses(edgesA[i].geom)) or (geomR==2 and (edgesA[-1].geom.crosses(edgesA[i].geom) or edgesA[-1].geom.touches(edgesA[i].geom))):
                    dist = (edgesA[-1].imp*edgesA[-1].length + edgesA[i].imp*edgesA[i].length)/2
                    if dist <= radius or radius == 0.0:
                        edgesA[-1].neighA.append([edgesA[i], dist])
                        edgesA[i].neighA.append([edgesA[-1], dist])

    #compute shortest paths (djikstra algorithm with binary heap as priority queue)
    #step 1: heap cretation
    if metricsL != [7]:
        for source in edgesA:
            if source.id % 50 == 0: feedback.pushInfo(f'Shortest Paths Edge {source.id}')
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
            level = [99999999999999 for i in range(edgesCount)]
            sortedA = []
            numSP = [0 for i in range(edgesCount)]
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
        #step 3 metrics update
            if 1 in metricsL: btwTemp = [0 for i in range(edgesCount)]
            if 2 in metricsL: centTemp = [0 for i in range(edgesCount)]
            if 4 in metricsL or 5 in metricsL: cvgTemp = [0 for i in range(edgesCount)]
            while sortedA != []:
                farest = sortedA[-1]
                cost = costA[farest.id]
                if (radius == 0.0 or cost <= radius): 
                    if 0 in metricsL and farest.id != source.id: source.access += farest.load/cost
                    if 3 in metricsL and source.demand > 0: source.opport += farest.supply/(cost+1)
                    if 6 in metricsL: source.reach += farest.load
                sortedA.pop(len(sortedA)-1)
                pot = farest.load * source.load
                tension = source.supply * farest.demand 
                
                for neigh in pivotA[farest.id]:
                    if numSP[farest.id] > 0 and (radius == 0.0 or cost <= radius):
                        if 1 in metricsL: btwTemp[neigh.id] += (numSP[neigh.id]/numSP[farest.id])*(1 + btwTemp[farest.id])
                        if 2 in metricsL: centTemp[neigh.id] += (numSP[neigh.id]/numSP[farest.id])*((pot/(level[farest.id] + 1)) + centTemp[farest.id])
                        if 4 in metricsL or 5 in metricsL: cvgTemp[neigh.id] += (numSP[neigh.id]/numSP[farest.id])*((tension/(level[farest.id]+1))+cvgTemp[farest.id])
                
                if pivotA[farest.id] == [] and level[farest.id] == 1 and (radius == 0.0 or cost <= radius): 
                    if 2 in metricsL: centTemp[source.id] += (pot/2) + centTemp[farest.id]
                    if 4 in metricsL or 5 in metricsL: cvgTemp[source.id] += (numSP[neigh.id]/numSP[farest.id])*((tension/(level[farest.id]+1))+cvgTemp[farest.id])
                
                if farest.id != source.id and (radius == 0.0 or cost <= radius): 
                    if 1 in metricsL: farest.btw += btwTemp[farest.id]/2
                    if 2 in metricsL: centTemp[farest.id] += pot/(level[farest.id]+1)
                if (4 in metricsL or 5 in metricsL) and (radius == 0.0 or cost <= radius): cvgTemp[farest.id] += tension/(level[farest.id]+1)
                
                if 2 in metricsL: farest.cent += centTemp[farest.id]/2
                if 4 in metricsL and farest.supply > 0: farest.converg += cvgTemp[farest.id]
                if 5 in metricsL: farest.polarity += cvgTemp[farest.id]

    #update table of contents
    strBegin = "T" if analysisType == 0 else "G"
    strMid = "g" if radius == 0.0 else str(int(radius))
    if len(strMid) > 5: strBegin += strMid[0:5]
    else: strBegin += strMid
    
    if 0 in metricsL:
        aux = 0
        while inputEdges.fields().indexFromName(strBegin + "Acc" + str(aux)) != -1 and aux < 9: aux += 1
        inputEdges.dataProvider().addAttributes([QgsField(strBegin + "Acc" + str(aux),QVariant.Double)])
        inputEdges.updateFields()
        accIndex = inputEdges.fields().indexFromName(strBegin + "Acc" + str(aux))
    if 1 in metricsL:
        aux = 0
        while inputEdges.fields().indexFromName(strBegin + "Btw" + str(aux)) != -1 and aux < 9: aux += 1
        inputEdges.dataProvider().addAttributes([QgsField(strBegin + "Btw" + str(aux),QVariant.Double)])
        inputEdges.updateFields()
        btwIndex = inputEdges.fields().indexFromName(strBegin + "Btw" + str(aux))
    if 2 in metricsL:
        aux = 0
        while inputEdges.fields().indexFromName(strBegin + "Cen" + str(aux)) != -1 and aux < 9: aux += 1
        inputEdges.dataProvider().addAttributes([QgsField(strBegin + "Cen" + str(aux),QVariant.Double)])
        inputEdges.updateFields()
        centIndex = inputEdges.fields().indexFromName(strBegin + "Cen" + str(aux))
    if 3 in metricsL:
        aux = 0
        while inputEdges.fields().indexFromName(strBegin + "Opp" + str(aux)) != -1 and aux < 9: aux += 1
        inputEdges.dataProvider().addAttributes([QgsField(strBegin + "Opp" + str(aux),QVariant.Double)])
        inputEdges.updateFields()
        oppIndex = inputEdges.fields().indexFromName(strBegin + "Opp" + str(aux))
    if 4 in metricsL:
        aux = 0
        while inputEdges.fields().indexFromName(strBegin + "Cvg" + str(aux)) != -1 and aux < 9: aux += 1
        inputEdges.dataProvider().addAttributes([QgsField(strBegin + "Cvg" + str(aux),QVariant.Double)])
        inputEdges.updateFields()
        cvgIndex = inputEdges.fields().indexFromName(strBegin + "Cvg" + str(aux))
    if 5 in metricsL:
        aux = 0
        while inputEdges.fields().indexFromName(strBegin + "Pol" + str(aux)) != -1 and aux < 9: aux += 1
        inputEdges.dataProvider().addAttributes([QgsField(strBegin + "Pol" + str(aux),QVariant.Double)])
        inputEdges.updateFields()
        polIndex = inputEdges.fields().indexFromName(strBegin + "Pol" + str(aux))
    if 6 in metricsL:
        aux = 0
        while inputEdges.fields().indexFromName(strBegin + "Rea" + str(aux)) != -1 and aux < 9: aux += 1
        inputEdges.dataProvider().addAttributes([QgsField(strBegin + "Rea" + str(aux),QVariant.Double)])
        inputEdges.updateFields()
        reachIndex = inputEdges.fields().indexFromName(strBegin + "Rea" + str(aux))
    if 7 in metricsL:
        aux = 0
        while inputEdges.fields().indexFromName(strBegin + "Cnc" + str(aux)) != -1 and aux < 9: aux += 1
        inputEdges.dataProvider().addAttributes([QgsField(strBegin + "Cnc" + str(aux),QVariant.Double)])
        inputEdges.updateFields()
        cncIndex = inputEdges.fields().indexFromName(strBegin + "Cnc" + str(aux))
    
    for edge in edgesA:
        metricsD = {}
        if 0 in metricsL: metricsD[accIndex] = edge.access
        if 1 in metricsL: metricsD[btwIndex] = edge.btw
        if 2 in metricsL: metricsD[centIndex] = edge.cent
        if 3 in metricsL: metricsD[oppIndex] = edge.opport
        if 4 in metricsL: metricsD[cvgIndex] = edge.converg
        if 5 in metricsL: metricsD[polIndex] = edge.polarity
        if 6 in metricsL: metricsD[reachIndex] = edge.reach
        if 7 in metricsL: metricsD[cncIndex] = len(edge.neighA)
        inputEdges.dataProvider().changeAttributeValues({edge.id : metricsD})
    
    if outPath != "":
        crs = QgsProject.instance().crs()
        transform_context = QgsProject.instance().transformContext()
        save_options = QgsVectorFileWriter.SaveVectorOptions()
        save_options.driverName = "ESRI Shapefile"
        save_options.fileEncoding = "System"
        writer = QgsVectorFileWriter.writeAsVectorFormat(inputEdges, outPath, "System", crs, "ESRI Shapefile")
        metricsOut = []
        if 0 in metricsL: metricsOut.append(accIndex)
        if 1 in metricsL: metricsOut.append(btwIndex)
        if 2 in metricsL: metricsOut.append(centIndex)
        if 3 in metricsL: metricsOut.append(oppIndex)
        if 4 in metricsL: metricsOut.append(cvgIndex)
        if 5 in metricsL: metricsOut.append(polIndex)
        if 6 in metricsL: metricsOut.append(reachIndex)
        if 7 in metricsL: metricsOut.append(cncIndex)
        inputEdges.dataProvider().deleteAttributes(metricsOut)
        inputEdges.updateFields()

    