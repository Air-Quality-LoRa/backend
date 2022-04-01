import influxdb_client
from influxdb_client.client.write_api import SYNCHRONOUS
import os
from main import *

INFLUXDB_ADRESS = os.environ["INFLUXDB_ADDRESS"]
INFLUXDB_PORT = os.environ["INFLUXDB_PORT"]
INFLUXDB_USERNAME = os.environ["INFLUXDB_USERNAME"]
INFLUXDB_TOKEN = os.environ["INFLUXDB_TOKEN"]
INFLUXDB_ORG = os.environ["INFLUXDB_ORG"]
INFLUXDB_BUCKET = os.environ["INFLUXDB_BUCKET"]

influxdbClient = influxdb_client.InfluxDBClient("http://"+INFLUXDB_ADRESS+":"+INFLUXDB_PORT,token=INFLUXDB_TOKEN,org=INFLUXDB_ORG)
influxdbWriteApi = influxdbClient.write_api(write_options=SYNCHRONOUS)

def storeRecoveryLoss(nbRecovery:int,nbLoss:int,message:dict):
    p = influxdb_client.Point(message["device_id"] + "@" + message["app_id"]+":network-health-rec-los")
    p = p.field("nb_loss",nbLoss)
    p = p.field("nb_recovery",nbRecovery)
    influxdbWriteApi.write(bucket=INFLUXDB_BUCKET,org=INFLUXDB_ORG,record=p)
    
    debug("Storing : for " + message["device_id"] + " -> rec_los " + str(nbRecovery) + " | " + str(nbLoss))
    
def storeSpreadingFactor(message:dict):
    p = influxdb_client.Point(message["device_id"] + "@" + message["app_id"]+":network-health-sf")
    p = p.field("spreading_factor", message["spreading_factor"])
    influxdbWriteApi.write(bucket=INFLUXDB_BUCKET,org=INFLUXDB_ORG,record=p)
    
    debug("Storing : for " + message["device_id"] + " -> sf " + str(message["spreading_factor"]))

def storeMessage(message:dict):
    p = influxdb_client.Point(message["device_id"] + "@" + message["app_id"])
    if(message["is_recovered"]):
        p = p.tag("recovery","true")
    else:
        p = p.tag("recovery","false")
    
    for data in message["payload"].keys():
        p = p.field(data, message["payload"][data])

    p = p.time(int(message["timestamp"]))
    influxdbWriteApi.write(bucket=INFLUXDB_BUCKET,org=INFLUXDB_ORG,record=p)
    
    debug("Storing : for " + message["device_id"] + " -> message " + str(message))