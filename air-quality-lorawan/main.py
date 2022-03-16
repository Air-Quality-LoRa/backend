import threading
from time import sleep
import paho.mqtt.client as mqtt
import json
import binascii
import influxdb_client
from influxdb_client.client.write_api import SYNCHRONOUS
from datetime import datetime
from http.server import HTTPServer, SimpleHTTPRequestHandler
from jinja2 import Environment, FileSystemLoader, Template, select_autoescape
from config import *

NOT_CONFIGURED = 0
WAITING_ACK = 1
CONFIGURED = 2

REQUEST_CONFIG = 1
CONCENTRATION = 2
UNIT = 3
BOTH = 4
CONCENTRATION_REC = 5
UNIT_REC = 6
BOTH_REC = 7

UP = 0
DOWN_ACK = 1

UPLINK_INTERVAL_DICT = {0:120,1:60,2:45,3:30,4:20,5:15,6:10,7:5}
RECOVERY_INTERVAL_DICT = {0:-1,1:2,2:4,3:8,4:16,5:32,6:64,7:128}
UPLINK_INTERVAL_DICT_REV = {120:0,60:1,45:2,30:3,20:4,15:5,10:6,5:7}
RECOVERY_INTERVAL_DICT_REV = {-1:0,2:1,4:2,8:3,16:4,32:5,64:6,128:7}

UPLINK_TOPIC_TEMPLATE = "v3/{{username}}/devices/{{device}}/{{topic}}"
UPLINK_TOPICS = ["up","down/nack"]
DOWNLINK_TOPIC_TEMPLATE = "v3/{{username}}/devices/{{device}}/down/replace"

TTN_MQTT_BROKER_ADDRESS = "eu1.cloud.thethings.network"
TTN_MQTT_BROKER_PORT = 1883

influxdbAddress = "localhost"
influxdbPort = "8086"
influxdbUsername = "admin"
influxdbToken = "o92Qd_sO34KKh7lj3AczKutxH5aZ8vTGytrud-iKu7FvA4bo-nvOj09g9SRGbFnitFi4XoG8Iri32_0DORhR7Q=="
influxdbOrg = "f43170103778eb07"
INFLUXDB_BUCKET = "air-quality"

mqttBrokerClient = mqtt.Client()
influxdbClient = influxdb_client.InfluxDBClient("http://"+influxdbAddress+":"+influxdbPort,token=influxdbToken,org=influxdbOrg)
influxdbWriteApi = influxdbClient.write_api(write_options=SYNCHRONOUS)

previousSpreadingFactor = dict()

devicesStates = dict()

previousMessages = dict()

dateFormat= "%Y-%m-%dT%H:%M:%S.%f"

def formatTimestamp(timestamp):
    formattedTimestamp = datetime.strptime(timestamp,dateFormat)
    formattedTimestamp = int(formattedTimestamp.timestamp()*1000000)
    return formattedTimestamp

def getEndDevice(message):
    return message["end_device_ids"]["device_id"]

def filterInfo(rawPayload):
    arrayPayload = binascii.a2b_base64(rawPayload["uplink_message"]["frm_payload"])
    filteredPayload = {
        "message_id" : arrayPayload[0],
        "device_id" : rawPayload["end_device_ids"]["device_id"],
        "app_id" : rawPayload["end_device_ids"]["application_ids"]["application_id"],
        "timestamp" : formatTimestamp(rawPayload["received_at"][:-4]),
        "type" : int(rawPayload["uplink_message"]["f_port"]),
        "payload" : arrayPayload,
        "raw_payload" : rawPayload["uplink_message"]["frm_payload"],
        "spreading_factor" : int(rawPayload["uplink_message"]["settings"]["data_rate"]["lora"]["spreading_factor"]),
        "is_recovered" : False
    }
    print("Filtered : " + str(filteredPayload))
    return filteredPayload

def readTwoBytes(index,array):
    return (array[index+1] << 8) + array[index]

def parsePayload(message):
    payload = message["payload"]
    data_type = message["type"]
    data = dict()
    if(data_type == REQUEST_CONFIG):
        data = 'Request Config'
    else:
        data["temperature"] = payload[1]/2 - 20
        data["humidity"] = payload[2]
        if(data_type in [CONCENTRATION,BOTH,CONCENTRATION_REC,BOTH_REC]):
            data["c_pms_1_0"] = readTwoBytes(3,payload)
            data["c_pms_2_5"] = readTwoBytes(5,payload)
            data["c_pms_10"] = readTwoBytes(7,payload)
        if(data_type in[UNIT,BOTH,UNIT_REC,BOTH_REC]):
            shift = 0
            if(data_type in [BOTH,BOTH_REC]):
                shift = 6
            data["q_pms_0_3"] = readTwoBytes(3+shift,payload)
            data["q_pms_0_5"] = readTwoBytes(5+shift,payload)
            data["q_pms_1_0"] = readTwoBytes(7+shift,payload)
            data["q_pms_2_5"] = readTwoBytes(9+shift,payload)
            data["q_pms_5_0"] = readTwoBytes(11+shift,payload)
            data["q_pms_10"] = readTwoBytes(13+shift,payload)
    
    payload = data
    print("Payload décodée : " + str(payload))
    return payload    

def configAllDevices():
    devices = getDeviceIds()
    for device in devices:
        if(devicesStates[device] != CONFIGURED):
            configDevice(device)

# The callback for when the client receives a CONNACK response from the server.
def on_connect(client, userdata, flags, rc):
    print("Connected to ttn mqtt")

    # Subscribing in on_connect() means that if we lose the connection and
    # reconnect then subscriptions will be renewed.
    template = Template(UPLINK_TOPIC_TEMPLATE)
    for device in getDeviceIds():
        for topic in UPLINK_TOPICS:
            client.subscribe(template.render(username=getMqttCredentials()[0],device=device,topic=topic),0)
    configAllDevices()

def formatMsg(msg):
    formattedMsg = json.loads(msg.payload)
    formattedMsg = filterInfo(formattedMsg)
    formattedMsg["payload"] = parsePayload(formattedMsg)
    return formattedMsg

def storeRecoveryLoss(nbRecovery,nbLoss,message):
    p = influxdb_client.Point(message["device_id"] + "@" + message["app_id"]+":network-health-rec-los")
    p = p.field("nb_loss",nbLoss)
    p = p.field("nb_recovery",nbRecovery)
    influxdbWriteApi.write(bucker=INFLUXDB_BUCKET,org=influxdbOrg,record=p)
    
def storeSpreadingFactor(message):
    p = influxdb_client.Point(message["device_id"] + "@" + message["app_id"]+":network-health-sf")
    p = p.field("spreading_factor", message["spreading_factor"])
    influxdbWriteApi.write(bucker=INFLUXDB_BUCKET,org=influxdbOrg,record=p)

def storeMessage(message):
    p = influxdb_client.Point(message["device_id"] + "@" + message["app_id"])
    if(message["is_recovered"]):
        p = p.tag("recovery","true")
    else:
        p = p.tag("recovery","false")
    
    for data in message["payload"].keys():
        p = p.field(data, message["payload"][data])

    p = p.time(message["timestamp"])
    influxdbWriteApi.write(bucket=INFLUXDB_BUCKET,org=influxdbOrg,record=p)

def storePreviousMessage(message,config):
    if(config["recovery_interval"] == -1):
        return
    
    rawPayload = message["raw_payload"]
    id = int(message["message_id"])
    time = int(message["timestamp"])
    previousMessages[message["device_id"]].insert(0,[id,rawPayload,time])
    if(len(previousMessages[message["device_id"]]) > config["recovery_interval"]  +1):
        previousMessages[message["device_id"]].pop()

def xorPayload(a,b):
    if(a==[]):
        return b
    elif(b==[]):
        return a
    n = len(a)
    xor = []
    for i in range(n):
        xor.append(a[i]^b[i])
    return xor

def recoverMessage(message,id,missingIndex,config):
    xorMsg = message["raw_payload"]
    xorServ = []
    for i in range(1,config["recovery_interval"]):
        xor = xorPayload(xor,previousMessages[message["device_id"]][i][1])
    recoveredPayload = xorPayload(xorMsg,xorServ)
    timestamp = 0
    if(missingIndex == 1):
        timestamp = previousMessages[2][2]
        timestamp += config["data_interval"]*1000000*60 #add minute from previous message
    else:
        timestamp = previousMessages[missingIndex-1][2]
        timestamp -= config["data_interval"]*1000000*60 #add minute from previous message
    recoveredMessage = {
        "message_id" : id,
        "device_id" : message["device_id"],
        "app_id" : message["app_id"],
        "timestamp" : timestamp,
        "type" : message["type"]-3,
        "payload" : recoveredPayload,
        "raw_payload" : binascii.b2a_base64(bytearray(recoveredPayload)),
        "spreading_factor" : message["spreading_factor"],
        "is_recovered" : True, 
    }
    recoveredMessage["payload"] = parsePayload(recoveredMessage)
    return recoveredMessage

def handleRecover(message,config):
    if(config["recovery_interval"] == -1):
        return

    if(len(previousMessages[message["device_id"]]) != config["recovery_interval"]+1):
        return 
    
    recoveryId = message["message_id"]
    nbJumps = 0
    previousNum = recoveryId
    missingId = 0
    missingIndex = 0
    for i in range(1, config["recovery_interval"]+1):
        jump = (previousNum - previousMessages[i][0]) % 256 
        if(jump > 1):
            nbJumps += jump
            missingId = previousMessages[message["device_id"]][i][0] + 1
            missingIndex = i
        previousNum = previousMessages[message["device_id"]][i][0]
    if(nbJumps != 1):
        print("Unable to recover : " + nbJumps + "missing messages")
        return
    recoveredMessage = recoverMessage(message,missingId,missingIndex,config)
    storeMessage(recoveredMessage)
    storeRecoveryLoss(0,1,recoveredMessage)

def handleMessage(message,topic):
    if(topic == UP):
        message = formatMsg(message)
        if(devicesStates[message["device_id"]] != CONFIGURED):
            return #ignore message
        else:
            handleUplink(message)
    elif(topic == DOWN_ACK):
        device = getEndDevice(message)
        if(devicesStates[device] == WAITING_ACK):
            devicesStates[device] == CONFIGURED

def handleUplink(message):
    config = getDeviceConfig()["sf"+str(message["spreading_factor"])]
    
    if(message["spreading_factor"] != previousSpreadingFactor[message["device_id"]]):
        previousMessages[message["device_id"]] = []
    if(len(previousMessages[message["device_id"]])!=0):
        saut = (int(message["message_id"]) - previousMessages[message["message_id"]][0][0])%256
        if(saut > 1):
            storeRecoveryLoss(saut-1,0,message)
    storePreviousMessage(message,config)
    storeSpreadingFactor(message)
    previousSpreadingFactor[message["device_id"]] = message["spreading_factor"]


    if(message["type"] in [CONCENTRATION,UNIT,BOTH]):
        storeMessage(message)
    elif(message["type"] in [CONCENTRATION_REC,UNIT_REC,BOTH_REC]):
        handleRecover(message, config)
    elif(message["type"] == REQUEST_CONFIG):
        configDevice[message["device_id"]]
    return

def topicOf(topic):
    if(topic[-2:] == "up"):
        return UP
    elif(topic[-9:] == "down/nack"):
        return DOWN_ACK

# The callback for when a PUBLISH message is received from the server.
def on_message(client, userdata, msg):
    print("[DEBUG] Message recieved from MQTT :\nTopic : " + str(msg.topic) + "\nMsg : " + str(msg.payload) + "\n\n\n")
    topic = topicOf(str(msg.topic))
    handleMessage(msg.payload,topic)

def formDownlinkPayload(config):
    payload = bytearray()
    for x in range(12,6,-1):
        elems = config["sf"+str(x)]
        byte = UPLINK_INTERVAL_DICT_REV[elems["data_interval"]] << 5 
        byte |= elems["data_type"] << 3
        byte |= RECOVERY_INTERVAL_DICT_REV[elems["recovery_interval"]]
        payload.append(byte)
    return binascii.b2a_base64(payload)

def configDevice(device_id):
    devicesStates[device_id] = NOT_CONFIGURED
    previousMessages[device_id] = []
    payload = formDownlinkPayload(getDeviceConfig())
    downlink = {
        "downlinks": [{
        "f_port": 1,
        "frm_payload": payload,
        "confirmed": True,
        "correlation_ids": [device_id]
    }]}
    payload = json.dumps(downlink)
    template = Template(DOWNLINK_TOPIC_TEMPLATE)
    topic = template.render(username = getMqttCredentials()[0],device=device_id)
    mqttBrokerClient.publish(topic, payload=payload, qos=2, retain=False).wait_for_publish()
    devicesStates[device_id] = WAITING_ACK

def on_disconnect(client, userdata, rc):
    print("disconnected")

def on_connect_fail(client, userdata, rc):
    print("fail")

def main():
    init()
    httpServerWorker = threading.Thread(target=runHttpServer)
    httpServerWorker.start()
    credentials = getMqttCredentials()
    mqttBrokerClient.reconnect_delay_set(min_delay=10,max_delay=21600)
    mqttBrokerClient.username_pw_set(credentials[0],credentials[1])
    mqttBrokerClient.on_connect = on_connect
    mqttBrokerClient.on_connect_fail = on_connect_fail
    mqttBrokerClient.on_message = on_message
    mqttBrokerClient.on_disconnect = on_disconnect
    mqttBrokerClient.connect_async(TTN_MQTT_BROKER_ADDRESS, port=TTN_MQTT_BROKER_PORT, keepalive=60, bind_address="")
    mqttBrokerClient.loop_forever(retry_first_connection=True)


env = Environment(
    loader=FileSystemLoader('templates'),
    autoescape=select_autoescape()
)

def handleDeviceConfig(data):
    for i in range(7,13):
        if(data["sf"+str(i)]["recovery_interval"] == 1000):
            data["sf"+str(i)]["recovery_interval"] = -1
    setDeviceConfig(data)
    configAllDevices()

def handleAppConfig(data):
    setMqttCredentials(data["username"],data["api-key"])
    mqttBrokerClient.reconnect()

def handleAddDevice(data):
    devices = getDeviceIds()
    device = data['end-device']
    if(device in devices):
        return False
    else:
        devices.append(device)
        setDeviceIds(devices)
        template = Template(UPLINK_TOPIC_TEMPLATE)
        for topic in UPLINK_TOPICS:
            mqttBrokerClient.subscribe(template.render(username=getMqttCredentials()[0],device=device,topic=topic),0)
        configDevice(device)
        return True

def handleRemoveDevice(data):
    devices = getDeviceIds()
    device = data['end-device']
    devices.remove(device)
    setDeviceIds(devices)
    template = Template(UPLINK_TOPIC_TEMPLATE)
    for topic in UPLINK_TOPICS:
        mqttBrokerClient.unsubscribe(template.render(username=getMqttCredentials()[0],device=device,topic=topic),0)
    previousMessages.pop(device)
    devicesStates.pop(device)

class DownlinkServer(SimpleHTTPRequestHandler):
    def do_POST(self):
        content_length = int(self.headers['Content-Length']) # <--- Gets the size of data
        post_data = self.rfile.read(content_length) # <--- Gets the data itself
        pd = post_data.decode("utf-8")   # <-------- ADD this line
        data = json.loads(pd)
        if(self.path == "/api-backend/config_device"):
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            handleDeviceConfig(data)
        elif(self.path == "/api-backend/config_app"):
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            handleAppConfig(data)
        elif(self.path == "/api-backend/add_device"):
            if(handleAddDevice(data)):
                self.send_response(200)
                self.send_header("Content-type", "text/html")
                self.end_headers()
            else:
                self.send_error(400)
                self.send_header("Content-type", "text/html")
                self.end_headers()
        elif(self.path == "/api-backend/remove_device"):
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            handleRemoveDevice(data)
        else:
            self.send_error(404)
            self.send_header("Content-type", "text/html")
            self.end_headers()
    def do_GET(self):
        if(self.path[13:] == "enddevicePage.html"):
            template = env.get_template(self.path[13:])
            credentials = getMqttCredentials()
            msg = template.render(end_device_list=getDeviceIds(),api_key=credentials[1],username=credentials[0])
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            self.wfile.write(bytes(msg,"utf-8"))
        else :
            self.path = '/templates/' + self.path[13:]
            print(self.path)
            return SimpleHTTPRequestHandler.do_GET(self)

def runHttpServer(server_class=HTTPServer, handler_class=DownlinkServer):
    server_address = ('', 1885)
    httpd = server_class(server_address, handler_class)
    httpd.serve_forever()

def init():
    loadConfig()
    devices = getDeviceIds()
    for device in devices:
        devicesStates[device] = NOT_CONFIGURED
        previousMessages[device] = []
        previousSpreadingFactor[device] = 0


main()