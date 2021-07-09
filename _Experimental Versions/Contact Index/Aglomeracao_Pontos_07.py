from qgis import processing
from qgis.processing import alg
from qgis.PyQt.QtCore import QVariant
from qgis.core import (QgsProject, QgsSpatialIndex, QgsDistanceArea, QgsPointXY, QgsField, QgsFields, QgsVectorDataProvider, QgsVectorFileWriter)

#ui input parameters
@alg(name='aglomeracaoPontos07', label='Aglomeração de Pontos 0.7', group='GAUS Contato', group_label='GAUS Contato')
@alg.input(type=alg.VECTOR_LAYER, name='features', label='SHP de pontos', types=[0])
@alg.input(type=alg.NUMBER, name='radiusA', label='Raio de Análise A', default = 400)
@alg.input(type=alg.NUMBER, name='radiusB', label='Raio de Análise B', default = 1000)
@alg.input(type=alg.NUMBER, name='radiusC', label='Raio de Análise C', default = 2500)
@alg.input(type=alg.NUMBER, name='radiusD', label='Raio de Análise D', default = 5000)
@alg.input(type=alg.VECTOR_LAYER_DEST, name='dest', label='Criar novo shapefile para resultados? [opcional]', optional = True, createByDefault = False)

#ui output definition (does nothing, it is here because qgis requires the declaration of at least one output)
@alg.output(type=alg.NUMBER, name='numoffeat', label='Number of Features Processed')

def computeMetrics(instance, parameters, context, feedback, inputs):
    """
    Calcula a distância média de um ponto para outros pontos dentro de um determinado raio.
    """
    
    #Class that stores the metrics for the nodes of the network
    class FeatObj:
        def __init__(self, featCount, feat):
            self.id = feat.id() #id number, retrieved from the input shp
            self.geom = feat.geometry() #geometry retrieved from the input shp
            self.avDist, self.aglom, self.pointsWithin = 0,0,0 #output metrics
            self.avDistA, self.aglomA, self.pointsWithinA = 0,0,0 #output metrics
            self.avDistB, self.aglomB, self.pointsWithinB = 0,0,0 #output metrics
            self.avDistC, self.aglomC, self.pointsWithinC = 0,0,0 #output metrics
            self.avDistD, self.aglomD, self.pointsWithinD = 0,0,0 #output metrics

    #verifies if highest id number is lower than number of features
    #in order to avoid potential conflicts with matrices' size
    def verifyFeatCount(inputFeat):
        featCount = inputFeat.featureCount()
        for feat in inputFeat.getFeatures(): featCount = max(featCount, feat.id()+1)
        return featCount
    
    #import input parameters
    inputFeat = instance.parameterAsVectorLayer(parameters, 'features', context) #nodes vector layer
    radiusA = int(instance.parameterAsDouble(parameters, 'radiusA', context))
    radiusB = int(instance.parameterAsDouble(parameters, 'radiusB', context))
    radiusC = int(instance.parameterAsDouble(parameters, 'radiusC', context))
    radiusD = int(instance.parameterAsDouble(parameters, 'radiusD', context)) 
    outPath = instance.parameterAsOutputLayer(parameters, 'dest', context) #path where results will be saved
    
    #features initialization
    featCount = verifyFeatCount(inputFeat)
    featA = [0 for i in range(featCount)]
    for feat in inputFeat.getFeatures(): 
        featA[feat.id()] = FeatObj(featCount, feat)
        if feat.id() % 100 == 0: feedback.pushInfo("Ponto {} inicializado".format(feat.id()))

    #computes aglommeration index
    ind, totalAglom, totalAvDist = 0,0,0
    totalAglomA, totalAvDistA = 0,0
    totalAglomB, totalAvDistB = 0,0
    totalAglomC, totalAvDistC = 0,0
    totalAglomD, totalAvDistD = 0,0
    
    for feat in featA:
        feedback.pushInfo("Computando Aglomeração Ponto {}".format(feat.id))
        for i in range(ind + 1, featCount):
            dist = feat.geom.distance(featA[i].geom)
            
            feat.avDist += dist
            featA[i].avDist += dist
            feat.pointsWithin += 1
            featA[i].pointsWithin += 1
            if (dist <= radiusA):
                feat.avDistA += dist
                featA[i].avDistA += dist
                feat.pointsWithinA += 1
                featA[i].pointsWithinA += 1
            if (dist <= radiusB):
                feat.avDistB += dist
                featA[i].avDistB += dist
                feat.pointsWithinB += 1
                featA[i].pointsWithinB += 1
            if (dist <= radiusC):
                feat.avDistC += dist
                featA[i].avDistC += dist
                feat.pointsWithinC += 1
                featA[i].pointsWithinC += 1
            if (dist <= radiusD):
                feat.avDistD += dist
                featA[i].avDistD += dist
                feat.pointsWithinD += 1
                featA[i].pointsWithinD += 1
            
        if feat.pointsWithin > 0 and feat.avDist > 0: 
            feat.avDist = feat.avDist/feat.pointsWithin
            feat.aglom = 1/feat.avDist
            totalAglom += feat.aglom
            totalAvDist += feat.avDist
        if feat.pointsWithinA > 0 and feat.avDistA > 0: 
            feat.avDistA = feat.avDistA/feat.pointsWithinA
            feat.aglomA = 1/feat.avDistA
            totalAglomA += feat.aglomA
            totalAvDistA += feat.avDistA
        if feat.pointsWithinB > 0 and feat.avDistB > 0: 
            feat.avDistB = feat.avDistB/feat.pointsWithinB
            feat.aglomB = 1/feat.avDistB
            totalAglomB += feat.aglomB
            totalAvDistB += feat.avDistB
        if feat.pointsWithinC > 0 and feat.avDistC > 0: 
            feat.avDistC = feat.avDistC/feat.pointsWithinC
            feat.aglomC = 1/feat.avDistC
            totalAglomC += feat.aglomC
            totalAvDistC += feat.avDistC
        if feat.pointsWithinD > 0 and feat.avDistD > 0: 
            feat.avDistD = feat.avDistD/feat.pointsWithinD
            feat.aglomD = 1/feat.avDistD
            totalAglomD += feat.aglomD
            totalAvDistD += feat.avDistD
        ind += 1
    
    #updates acessibility and centrality in table of contents
    feedback.pushInfo("Updating Table of Contents")
    a,b,c,d = 0,0,0,0
    while inputFeat.fields().indexFromName("ADGlob" + str(a)) != -1: a += 1
    inputFeat.dataProvider().addAttributes([QgsField("ADGlob" + str(a),QVariant.Double)])
    inputFeat.updateFields()
    avdistIndex = inputFeat.fields().indexFromName("ADGlob" + str(a))
    while inputFeat.fields().indexFromName("%ADGlob" + str(b)) != -1: b += 1
    inputFeat.dataProvider().addAttributes([QgsField("%ADGlob" + str(b),QVariant.Double)])
    inputFeat.updateFields()
    avdistNIndex = inputFeat.fields().indexFromName("%ADGlob" + str(b))
    while inputFeat.fields().indexFromName("AgGlob" + str(c)) != -1: c += 1
    inputFeat.dataProvider().addAttributes([QgsField("AgGlob" + str(c),QVariant.Double)])
    inputFeat.updateFields()
    aglomIndex = inputFeat.fields().indexFromName("AgGlob" + str(c))
    while inputFeat.fields().indexFromName("%AgGlob" + str(d)) != -1: d += 1
    inputFeat.dataProvider().addAttributes([QgsField("%AgGlob" + str(d),QVariant.Double)])
    inputFeat.updateFields()
    aglomNIndex = inputFeat.fields().indexFromName("%AgGlob" + str(d))
    
    a,b,c,d,e = 0,0,0,0,0
    while inputFeat.fields().indexFromName("AD" + str(radiusA) + "_" + str(a)) != -1: a += 1
    inputFeat.dataProvider().addAttributes([QgsField("AD" + str(radiusA) + "_" + str(a),QVariant.Double)])
    inputFeat.updateFields()
    avdistIndexA = inputFeat.fields().indexFromName("AD" + str(radiusA) + "_" + str(a))
    while inputFeat.fields().indexFromName("%AD" + str(radiusA) + "_" + str(b)) != -1: b += 1
    inputFeat.dataProvider().addAttributes([QgsField("%AD" + str(radiusA) + "_" + str(b),QVariant.Double)])
    inputFeat.updateFields()
    avdistNIndexA = inputFeat.fields().indexFromName("%AD" + str(radiusA) + "_" + str(b))
    while inputFeat.fields().indexFromName("Ag" + str(radiusA) + "_" + str(c)) != -1: c += 1
    inputFeat.dataProvider().addAttributes([QgsField("Ag" + str(radiusA) + "_" + str(c),QVariant.Double)])
    inputFeat.updateFields()
    aglomIndexA = inputFeat.fields().indexFromName("Ag" + str(radiusA) + "_" + str(c))
    while inputFeat.fields().indexFromName("%Ag" + str(radiusA) + "_" + str(d)) != -1: d += 1
    inputFeat.dataProvider().addAttributes([QgsField("%Ag" + str(radiusA) + "_" + str(d),QVariant.Double)])
    inputFeat.updateFields()
    aglomNIndexA = inputFeat.fields().indexFromName("%Ag" + str(radiusA) + "_" + str(d))
    while inputFeat.fields().indexFromName("%PW" + str(radiusA) + "_" + str(e)) != -1: e += 1
    inputFeat.dataProvider().addAttributes([QgsField("%PW" + str(radiusA) + "_" + str(e),QVariant.Double)])
    inputFeat.updateFields()
    PWIndexA = inputFeat.fields().indexFromName("%PW" + str(radiusA) + "_" + str(e))
    
    a,b,c,d,e = 0,0,0,0,0
    while inputFeat.fields().indexFromName("AD" + str(radiusB) + "_" + str(a)) != -1: a += 1
    inputFeat.dataProvider().addAttributes([QgsField("AD" + str(radiusB) + "_" + str(a),QVariant.Double)])
    inputFeat.updateFields()
    avdistIndexB = inputFeat.fields().indexFromName("AD" + str(radiusB) + "_" + str(a))
    while inputFeat.fields().indexFromName("%AD" + str(radiusB) + "_" + str(b)) != -1: b += 1
    inputFeat.dataProvider().addAttributes([QgsField("%AD" + str(radiusB) + "_" + str(b),QVariant.Double)])
    inputFeat.updateFields()
    avdistNIndexB = inputFeat.fields().indexFromName("%AD" + str(radiusB) + "_" + str(b))
    while inputFeat.fields().indexFromName("Ag" + str(radiusB) + "_" + str(c)) != -1: c += 1
    inputFeat.dataProvider().addAttributes([QgsField("Ag" + str(radiusB) + "_" + str(c),QVariant.Double)])
    inputFeat.updateFields()
    aglomIndexB = inputFeat.fields().indexFromName("Ag" + str(radiusB) + "_" + str(c))
    while inputFeat.fields().indexFromName("%Ag" + str(radiusB) + "_" + str(d)) != -1: d += 1
    inputFeat.dataProvider().addAttributes([QgsField("%Ag" + str(radiusB) + "_" + str(d),QVariant.Double)])
    inputFeat.updateFields()
    aglomNIndexB = inputFeat.fields().indexFromName("%Ag" + str(radiusB) + "_" + str(d))
    while inputFeat.fields().indexFromName("%PW" + str(radiusB) + "_" + str(e)) != -1: e += 1
    inputFeat.dataProvider().addAttributes([QgsField("%PW" + str(radiusB) + "_" + str(e),QVariant.Double)])
    inputFeat.updateFields()
    PWIndexB = inputFeat.fields().indexFromName("%PW" + str(radiusB) + "_" + str(e))
    
    a,b,c,d,e = 0,0,0,0,0
    while inputFeat.fields().indexFromName("AD" + str(radiusC) + "_" + str(a)) != -1: a += 1
    inputFeat.dataProvider().addAttributes([QgsField("AD" + str(radiusC) + "_" + str(a),QVariant.Double)])
    inputFeat.updateFields()
    avdistIndexC = inputFeat.fields().indexFromName("AD" + str(radiusC) + "_" + str(a))
    while inputFeat.fields().indexFromName("%AD" + str(radiusC) + "_" + str(b)) != -1: b += 1
    inputFeat.dataProvider().addAttributes([QgsField("%AD" + str(radiusC) + "_" + str(b),QVariant.Double)])
    inputFeat.updateFields()
    avdistNIndexC = inputFeat.fields().indexFromName("%AD" + str(radiusC) + "_" + str(b))
    while inputFeat.fields().indexFromName("Ag" + str(radiusC) + "_" + str(c)) != -1: c += 1
    inputFeat.dataProvider().addAttributes([QgsField("Ag" + str(radiusC) + "_" + str(c),QVariant.Double)])
    inputFeat.updateFields()
    aglomIndexC = inputFeat.fields().indexFromName("Ag" + str(radiusC) + "_" + str(c))
    while inputFeat.fields().indexFromName("%Ag" + str(radiusC) + "_" + str(d)) != -1: d += 1
    inputFeat.dataProvider().addAttributes([QgsField("%Ag" + str(radiusC) + "_" + str(d),QVariant.Double)])
    inputFeat.updateFields()
    aglomNIndexC = inputFeat.fields().indexFromName("%Ag" + str(radiusC) + "_" + str(d))
    while inputFeat.fields().indexFromName("%PW" + str(radiusC) + "_" + str(e)) != -1: e += 1
    inputFeat.dataProvider().addAttributes([QgsField("%PW" + str(radiusC) + "_" + str(e),QVariant.Double)])
    inputFeat.updateFields()
    PWIndexC = inputFeat.fields().indexFromName("%PW" + str(radiusC) + "_" + str(e))
    
    a,b,c,d = 0,0,0,0
    while inputFeat.fields().indexFromName("AD" + str(radiusD) + "_" + str(a)) != -1: a += 1
    inputFeat.dataProvider().addAttributes([QgsField("AD" + str(radiusD) + "_" + str(a),QVariant.Double)])
    inputFeat.updateFields()
    avdistIndexD = inputFeat.fields().indexFromName("AD" + str(radiusD) + "_" + str(a))
    while inputFeat.fields().indexFromName("%AD" + str(radiusD) + "_" + str(b)) != -1: b += 1
    inputFeat.dataProvider().addAttributes([QgsField("%AD" + str(radiusD) + "_" + str(b),QVariant.Double)])
    inputFeat.updateFields()
    avdistNIndexD = inputFeat.fields().indexFromName("%AD" + str(radiusD) + "_" + str(b))
    while inputFeat.fields().indexFromName("Ag" + str(radiusD) + "_" + str(c)) != -1: c += 1
    inputFeat.dataProvider().addAttributes([QgsField("Ag" + str(radiusD) + "_" + str(c),QVariant.Double)])
    inputFeat.updateFields()
    aglomIndexD = inputFeat.fields().indexFromName("Ag" + str(radiusD) + "_" + str(c))
    while inputFeat.fields().indexFromName("%Ag" + str(radiusD) + "_" + str(d)) != -1: d += 1
    inputFeat.dataProvider().addAttributes([QgsField("%Ag" + str(radiusD) + "_" + str(d),QVariant.Double)])
    inputFeat.updateFields()
    aglomNIndexD = inputFeat.fields().indexFromName("%Ag" + str(radiusD) + "_" + str(d))
    while inputFeat.fields().indexFromName("%PW" + str(radiusD) + "_" + str(e)) != -1: e += 1
    inputFeat.dataProvider().addAttributes([QgsField("%PW" + str(radiusD) + "_" + str(e),QVariant.Double)])
    inputFeat.updateFields()
    PWIndexD = inputFeat.fields().indexFromName("%PW" + str(radiusD) + "_" + str(e))
    
    for feat in featA: 
        inputFeat.dataProvider().changeAttributeValues({feat.id : {avdistIndex : feat.avDist, avdistNIndex : 100*feat.avDist/totalAvDist, aglomIndex : feat.aglom, aglomNIndex : 100*feat.aglom/totalAglom}})
        inputFeat.dataProvider().changeAttributeValues({feat.id : {avdistIndexA : feat.avDistA, avdistNIndexA : 100*feat.avDistA/totalAvDistA, aglomIndexA : feat.aglomA, aglomNIndexA : 100*feat.aglomA/totalAglomA, PWIndexA : 100*feat.pointsWithinA/(featCount - 1)}})
        inputFeat.dataProvider().changeAttributeValues({feat.id : {avdistIndexB : feat.avDistB, avdistNIndexB : 100*feat.avDistB/totalAvDistB, aglomIndexB : feat.aglomB, aglomNIndexB : 100*feat.aglomB/totalAglomB, PWIndexB : 100*feat.pointsWithinB/(featCount - 1)}})
        inputFeat.dataProvider().changeAttributeValues({feat.id : {avdistIndexC : feat.avDistC, avdistNIndexC : 100*feat.avDistC/totalAvDistC, aglomIndexC : feat.aglomC, aglomNIndexC : 100*feat.aglomC/totalAglomC, PWIndexC : 100*feat.pointsWithinC/(featCount - 1)}})
        inputFeat.dataProvider().changeAttributeValues({feat.id : {avdistIndexD : feat.avDistD, avdistNIndexD : 100*feat.avDistD/totalAvDistD, aglomIndexD : feat.aglomD, aglomNIndexD : 100*feat.aglomD/totalAglomD, PWIndexD : 100*feat.pointsWithinD/(featCount - 1)}})
    
    if outPath != "":
        crs = QgsProject.instance().crs()
        transform_context = QgsProject.instance().transformContext()
        save_options = QgsVectorFileWriter.SaveVectorOptions()
        save_options.driverName = "ESRI Shapefile"
        save_options.fileEncoding = "System"
        writer = QgsVectorFileWriter.writeAsVectorFormat(inputFeat, outPath, "System", crs, "ESRI Shapefile")
        inputFeat.dataProvider().deleteAttributes([avdistIndex, avdistNIndex, aglomIndex, aglomNIndex])
        inputFeat.dataProvider().deleteAttributes([avdistIndexA, avdistNIndexA, aglomIndexA, aglomNIndexA, PWIndexA])
        inputFeat.dataProvider().deleteAttributes([avdistIndexB, avdistNIndexB, aglomIndexB, aglomNIndexB, PWIndexB])
        inputFeat.dataProvider().deleteAttributes([avdistIndexC, avdistNIndexC, aglomIndexC, aglomNIndexC, PWIndexC])
        inputFeat.dataProvider().deleteAttributes([avdistIndexD, avdistNIndexD, aglomIndexD, aglomNIndexD, PWIndexD])
        inputFeat.updateFields()