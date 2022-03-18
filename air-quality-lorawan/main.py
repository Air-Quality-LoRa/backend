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
import os

DEBUG = True

NOT_CONFIGURED = 0
WAITING_ACK = 1
JUST_CONFIGURED = 2
CONFIGURED = 3

MQTT_PUBLISH_EVENT = 0
MQTT_ACK_EVENT = 1
BOARD_DATA_EVENT = 2
BOARD_RECOVERY_EVENT = 3
USER_CONFIG_EVENT = 4
SERVER_CONFIG_EVENT = 5
BOARD_REQUEST_CONFIG_EVENT = 6
UNKNOWN_EVENT = 7

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
# UPLINK_TOPIC_TEMPLATE = "application/{{username}}/device/{{device}}/event/{{topic}}"
UPLINK_TOPICS = ["up","down/ack"]
# UPLINK_TOPICS = ["up","ack"]
DOWNLINK_TOPIC_TEMPLATE = "v3/{{username}}/devices/{{device}}/down/replace"
# mqtt_username = ""

TTN_MQTT_BROKER_ADDRESS = "eu1.cloud.thethings.network"
# TTN_MQTT_BROKER_ADDRESS = "lns.campusiot.imag.fr"
TTN_MQTT_BROKER_PORT = 1883

influxdbAddress = "influxdb" #os.environ["influxdb_Address"]
influxdbPort = "8086" #os.environ["influxdbPort"]
influxdbUsername = "admin" 
influxdbToken = "__SUPER_SECRET_TOKEN_TO_CHANGE__"
influxdbOrg = "air-quality"
INFLUXDB_BUCKET = "air-quality"

mqttBrokerClient = mqtt.Client()
influxdbClient = influxdb_client.InfluxDBClient("http://"+influxdbAddress+":"+influxdbPort,token=influxdbToken,org=influxdbOrg)
influxdbWriteApi = influxdbClient.write_api(write_options=SYNCHRONOUS)

previousSpreadingFactor = dict()

devicesStates = dict()

previousMessages = dict()

publishTracker = dict()

DATE_FORMAT= "%Y-%m-%dT%H:%M:%S.%f"

def formatTimestamp(timestamp):
    formattedTimestamp = datetime.strptime(timestamp,DATE_FORMAT)
    formattedTimestamp = int(formattedTimestamp.timestamp()*1000000000)
    return formattedTimestamp

def getEndDevice(message):
    return message["end_device_ids"]["device_id"]
    # return message["deviceName"]

def getPort(message):
    return message["uplink_message"]["f_port"]
    # return message["fPort"]

def filterInfo(rawPayload):
    try:
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
    except KeyError:
        filteredPayload = {
            "message_id" : -1,
            "device_id" : rawPayload["end_device_ids"]["device_id"],
            "app_id" : rawPayload["end_device_ids"]["application_ids"]["application_id"],
            "timestamp" : formatTimestamp(rawPayload["received_at"][:-4]),
            "type" : 1,
            "payload" : [],
            "raw_payload" : "",
            "spreading_factor" : int(rawPayload["uplink_message"]["settings"]["data_rate"]["lora"]["spreading_factor"]),
            "is_recovered" : False
        }
    # try:
    #     arrayPayload = binascii.a2b_base64(rawPayload["data"])
    #     filteredPayload = {
    #         "message_id" : arrayPayload[0],
    #         "device_id" : rawPayload["deviceName"],
    #         "app_id" : rawPayload["applicationName"],
    #         "timestamp" : formatTimestamp(rawPayload["rxInfo"]["time"][:-1]),
    #         "type" : int(rawPayload["fPort"]),
    #         "payload" : arrayPayload,
    #         "raw_payload" : rawPayload["data"],
    #         "spreading_factor" : int(rawPayload["txInfo"]["loRaModulationInfo"]["spreadingFactor"]),
    #         "is_recovered" : False
    #     }
    # except KeyError:
    #     filteredPayload = {
    #         "message_id" : -1,
    #         "device_id" : rawPayload["deviceName"],
    #         "app_id" : rawPayload["applicationName"],
    #         "timestamp" : formatTimestamp(rawPayload["rxInfo"]["time"][:-1]),
    #         "type" : 1,
    #         "payload" : [],
    #         "raw_payload" : "",
    #         "spreading_factor" : int(rawPayload["txInfo"]["loRaModulationInfo"]["spreadingFactor"]),
    #         "is_recovered" : False
    #     }
    debug("Uplink : for " + filteredPayload["device_id"] + " -> filtered : " + str(filteredPayload))
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
    debug("Uplink : for " + message["device_id"] + " -> decoded payload " + str(payload))
    return payload    

# The callback for when the client receives a CONNACK response from the server.
def on_connect(client, userdata, flags, rc):
    debug("Connected to ttn mqtt")

    # Subscribing in on_connect() means that if we lose the connection and
    # reconnect then subscriptions will be renewed.
    template = Template(UPLINK_TOPIC_TEMPLATE)
    for device in getDeviceIds():
        for topic in UPLINK_TOPICS:
            topicRendered = template.render(username=getMqttCredentials()[0],device=device,topic=topic)
            client.subscribe(topicRendered,0)
            debug("Subscribing to topic : " + topicRendered)
        stateMachine(device,SERVER_CONFIG_EVENT,None)

def formatMsg(message_mqtt:dict):
    formattedMsg = filterInfo(message_mqtt)
    formattedMsg["payload"] = parsePayload(formattedMsg)
    return formattedMsg

def storeRecoveryLoss(nbRecovery:int,nbLoss:int,message:dict):
    p = influxdb_client.Point(message["device_id"] + "@" + message["app_id"]+":network-health-rec-los")
    p = p.field("nb_loss",nbLoss)
    p = p.field("nb_recovery",nbRecovery)
    influxdbWriteApi.write(bucket=INFLUXDB_BUCKET,org=influxdbOrg,record=p)
    
    debug("Storing : for " + message["device_id"] + " -> rec_los " + str(nbRecovery) + " | " + str(nbLoss))
    
def storeSpreadingFactor(message:dict):
    p = influxdb_client.Point(message["device_id"] + "@" + message["app_id"]+":network-health-sf")
    p = p.field("spreading_factor", message["spreading_factor"])
    influxdbWriteApi.write(bucket=INFLUXDB_BUCKET,org=influxdbOrg,record=p)
    
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
    influxdbWriteApi.write(bucket=INFLUXDB_BUCKET,org=influxdbOrg,record=p)
    
    debug("Storing : for " + message["device_id"] + " -> message " + str(message))

def storePreviousMessage(message:dict,config:dict):
    if(config["data_recovery"] == -1):
        return
    
    rawPayload = message["raw_payload"]
    id = int(message["message_id"])
    time = int(message["timestamp"])
    previousMessages[message["device_id"]].insert(0,[id,rawPayload,time])
    if(len(previousMessages[message["device_id"]]) > config["data_recovery"]  +1):
        previousMessages[message["device_id"]].pop()
    
    debug("Update : for " + message["device_id"] +  " -> previousMessage " + str(previousMessages))

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
    xorMsg = binascii.a2b_base64(message["raw_payload"])
    xorServ = []
    for i in range(1,config["data_recovery"]):
        xorServ = xorPayload(xorServ,binascii.a2b_base64(previousMessages[message["device_id"]][i][1]))
    recoveredPayload = xorPayload(xorMsg,xorServ)
    timestamp = 0
    if(missingIndex == 1):
        timestamp = previousMessages[message["device_id"]][2][2]
        timestamp += config["data_interval"]*1000000000*60 #add minute from previous message
    else:
        timestamp = previousMessages[message["device_id"]][missingIndex-1][2]
        timestamp -= config["data_interval"]*1000000000*60 #add minute from previous message
    recoveredMessage = {
        "message_id" : id,
        "device_id" : message["device_id"],
        "app_id" : message["app_id"],
        "timestamp" : timestamp,
        "type" : message["type"]-3,
        "payload" : recoveredPayload,
        "raw_payload" : binascii.b2a_base64(bytearray(recoveredPayload),newline=False).decode("utf-8"),
        "spreading_factor" : message["spreading_factor"],
        "is_recovered" : True, 
    }
    recoveredMessage["payload"] = parsePayload(recoveredMessage)
    
    debug("Recovered message : " + str(recoveredMessage))
    
    return recoveredMessage

def handleRecover(message:dict,config:dict):
    if(config["data_recovery"] == -1):
        debug("Unable to recover : for " + message["device_id"] + " -> reason no recovery mode")
        return

    if(len(previousMessages[message["device_id"]]) < config["data_recovery"]):
        debug("Unable to recover : for " + message["device_id"] + " -> reason not enough messages in memory.")
        return 
    
    recoveryId = message["message_id"]
    nbJumps = 0
    previousNum = recoveryId
    missingId = 0
    missingIndex = 0
    for i in range(1, config["data_recovery"]):
        jump = (previousNum - previousMessages[message["device_id"]][i][0]) % 256 
        if(jump > 1):
            nbJumps += jump-1
            missingId = previousMessages[message["device_id"]][i][0] + 1
            missingIndex = i
        previousNum = previousMessages[message["device_id"]][i][0]
    if(nbJumps != 1):
        debug("Unable to recover : for " + message["device_id"] + " -> reason " + str(nbJumps) + " missing messages")
        return
    recoveredMessage = recoverMessage(message,missingId,missingIndex,config)
    storeMessage(recoveredMessage)
    storeRecoveryLoss(1,0,recoveredMessage)

def stateMachine(device,event,message):
    try:
        state = devicesStates[device]
        if(event == USER_CONFIG_EVENT):
            devicesStates[device] = NOT_CONFIGURED
            configDevice(device)
        elif(event == SERVER_CONFIG_EVENT):
            if(state in [CONFIGURED,JUST_CONFIGURED]):
                debug("Ignore Config : for " + device + " -> state " + str(state))
            elif(state in [NOT_CONFIGURED,WAITING_ACK]):
                devicesStates[device] = NOT_CONFIGURED
                configDevice(device)
        elif(event == MQTT_PUBLISH_EVENT):
            if(state == NOT_CONFIGURED):
                devicesStates[device] = WAITING_ACK
        elif(event == MQTT_ACK_EVENT):
            if(state == WAITING_ACK):
                devicesStates[device] = JUST_CONFIGURED
        elif(event == BOARD_DATA_EVENT):
            handleUplink(formatMsg(message))
            if(state == JUST_CONFIGURED):
                devicesStates[device] = CONFIGURED
        elif(event == BOARD_RECOVERY_EVENT):
            if(state == JUST_CONFIGURED):
                devicesStates[device] = CONFIGURED
                handleUplink(formatMsg(message))
            elif(state == CONFIGURED):
                handleUplink(formatMsg(message))
                pass
            else:
                debug("Ignore Recovery Message : for " + device + " -> state " + str(state))
        elif(event == BOARD_REQUEST_CONFIG_EVENT):
            if(state == WAITING_ACK):
                debug("Ignore Request Config Message : for " + device + " -> state " + str(state))
            elif(state == JUST_CONFIGURED):
                debug("Ignore Request Config Message : for " + device + " -> state " + str(state))
                devicesStates[device] = CONFIGURED
            else:
                devicesStates[device] = NOT_CONFIGURED
                configDevice(device)
        else:
            debug("Unkown Event : for " + device)
        debug("Update : for " + device + " | from state " + str(state) + " with event " + str(event) + " to state " + str(devicesStates[device]))
    except KeyboardInterrupt:
        raise KeyboardInterrupt
    except Exception as e:
        print(e)
        debug("State machine failed : resetting state machine for device")
        devicesStates[device] = NOT_CONFIGURED
        configDevice(device)
# def handleMessage(message,topic):
#     pass
    # if(topic == UP):
    #     message = formatMsg(message)
    #     type = message["type"]
    #     state = devicesStates[message["device_id"]]
    #     if(state == WAITING_ACK or (state == NOT_CONFIGURED and type != REQUEST_CONFIG)):
    #         debug("Ignore Message : for " + message["device_id"] + " -> state " + str(state))
    #         return #ignore message
    #     if(state == JUST_CONFIGURED and type == REQUEST_CONFIG):
    #         devicesStates[message["device_id"]] = CONFIGURED
    #         debug("Update : for " + message["device_id"] + " -> devicesStates " + str(devicesStates))
    #         return
    #     elif(message["type"] == REQUEST_CONFIG):
    #         debug("Uplink : for " + message["device_id"] + " -> message " + str(message))
    #         configDevice(message["device_id"])
    #     else:
    #         handleUplink(message)
    # elif(topic == DOWN_ACK):
    #     device = getEndDevice(message)
    #     if(devicesStates[device] == WAITING_ACK):
    #         devicesStates[device] = JUST_CONFIGURED
    #         debug("Update : for " + device + " -> devicesStates " + str(devicesStates))

def handleUplink(message):
    debug("Uplink : for " + message["device_id"] + " -> message " + str(message))
    
    config = getDeviceConfig()["sf"+str(message["spreading_factor"])]
    
    if(message["spreading_factor"] != previousSpreadingFactor[message["device_id"]]):
        previousMessages[message["device_id"]] = []
        
        debug("Update : for " + message["device_id"] + " -> previousMessages " + str(previousMessages))

    if(len(previousMessages[message["device_id"]])!=0):
        saut = (int(message["message_id"]) - previousMessages[message["device_id"]][0][0])%256
        if(saut > 1):
            storeRecoveryLoss(0,saut-1,message)
    storePreviousMessage(message,config)
    storeSpreadingFactor(message)
    previousSpreadingFactor[message["device_id"]] = message["spreading_factor"]

    debug("Update : for " + message["device_id"] + " -> previousSpreadingFactor " + str(previousSpreadingFactor))


    if(message["type"] in [CONCENTRATION,UNIT,BOTH]):
        storeMessage(message)
    elif(message["type"] in [CONCENTRATION_REC,UNIT_REC,BOTH_REC]):
        handleRecover(message, config)
    return

def topicOf(topic):
    if(topic[-2:] == "up"):
        return UP
    elif(topic[-8:] == "down/ack"):
        return DOWN_ACK

# The callback for when a PUBLISH message is received from the server.
def on_message(client, userdata, msg):
    debug("Message recieved from MQTT :\nTopic : " + str(msg.topic) + "\nMsg : " + str(msg.payload) + "\n\n\n")
    
    topic = topicOf(str(msg.topic))
    messageJson = json.loads(msg.payload.decode("utf-8"))
    device = getEndDevice(messageJson)
    event = UNKNOWN_EVENT
    if(topic == UP):
        try:
            port = getPort(messageJson)
            if(port in [CONCENTRATION,UNIT,BOTH]):
                event = BOARD_DATA_EVENT
            elif(port in [CONCENTRATION_REC,UNIT_REC,BOTH_REC]):
                event = BOARD_RECOVERY_EVENT
        except(KeyError):
            event = BOARD_REQUEST_CONFIG_EVENT
    elif(topic == DOWN_ACK):
        event = MQTT_ACK_EVENT
    stateMachine(device,event,messageJson)



def formDownlinkPayload(config):
    payload = bytearray()
    for x in range(12,6,-1):
        elems = config["sf"+str(x)]
        byte = UPLINK_INTERVAL_DICT_REV[elems["data_interval"]] << 5 
        byte |= elems["data_type"] << 3
        byte |= RECOVERY_INTERVAL_DICT_REV[elems["data_recovery"]]
        payload.append(byte)
    return binascii.b2a_base64(payload, newline=False).decode("utf-8")

def configDevice(device_id):
    debug("Reconfigure : for " + device_id)
    previousMessages[device_id] = []
    payloadbase64 = formDownlinkPayload(getDeviceConfig())
    downlink = {
        "downlinks": [{
        "f_port": 1,
        "frm_payload": payloadbase64,
        "confirmed": True,
        "correlation_ids": [device_id]
    }]}
    # downlink = {
        # "confirmed": True,
        # "fPort": 1,
        # "data": payloadbase64,
    # }
    payloadjson = str(json.dumps(downlink))
    template = Template(DOWNLINK_TOPIC_TEMPLATE)
    topic = template.render(username = getMqttCredentials()[0],device=device_id)
    debug("Publishing : for " + device_id + " -> topic " + topic + " payload " + str(payloadjson))
    messageInfo = mqttBrokerClient.publish(topic, payload=payloadjson, qos=2, retain=False)
    publishTracker[messageInfo.mid] = device_id

def on_publish(client, userdata, mid):
    device_id = publishTracker[mid]
    publishTracker.pop(mid)
    stateMachine(device_id,MQTT_PUBLISH_EVENT,None)

def on_disconnect(client, userdata, rc):
    debug("MQTT disconnected")

def on_connect_fail(client, userdata, rc):
    debug("MQTT connection failed")

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
    mqttBrokerClient.on_publish = on_publish
    mqttBrokerClient.on_disconnect = on_disconnect
    mqttBrokerClient.connect_async(TTN_MQTT_BROKER_ADDRESS, port=TTN_MQTT_BROKER_PORT, keepalive=60, bind_address="")
    mqttBrokerClient.loop_forever(retry_first_connection=True)


env = Environment(
    loader=FileSystemLoader('templates'),
    autoescape=select_autoescape()
)

def handleDeviceConfig(data):
    for i in range(7,13):
        if(data["sf"+str(i)]["data_recovery"] == 1000):
            data["sf"+str(i)]["data_recovery"] = -1
    setDeviceConfig(data)
    debug("Update : config " + str(data))
    devices = getDeviceIds()
    for device in devices:
        stateMachine(device,USER_CONFIG_EVENT,None)

def handleAppConfig(data):
    setMqttCredentials(data["username"],data["api-key"])
    mqttBrokerClient.username_pw_set(data["username"],data["api-key"])
    mqttBrokerClient.reconnect()

def handleAddDevice(data):
    devices = getDeviceIds()
    device = data['end-device']
    if(device in devices):
        debug("Unable to add end device : " + data["end-device"])
        return False
    else:
        devices.append(device)
        setDeviceIds(devices)
        debug("Update : devices ids " + str(devices))
        previousMessages[device] = []
        debug("Update : for " + device + " -> previousMessages " + str(previousMessages))
        devicesStates[device] = NOT_CONFIGURED
        debug("Update : for " + device + " -> devicesStates " + str(devicesStates))
        previousSpreadingFactor[device] = 0
        debug("Update : for " + device + " -> previousSpreadingFactor " + str(previousSpreadingFactor))
        
        template = Template(UPLINK_TOPIC_TEMPLATE)
        for topic in UPLINK_TOPICS:
            topicRendered = template.render(username=getMqttCredentials()[0],device=device,topic=topic)
            mqttBrokerClient.subscribe(topicRendered,0)
            debug("Subscribing to topic : " + topicRendered)
        stateMachine(device,USER_CONFIG_EVENT,None)
        return True

def handleRemoveDevice(data):
    devices = getDeviceIds()
    device = data['end-device']
    devices.remove(device)
    setDeviceIds(devices)

    debug("Update : devices ids " + str(devices))
    template = Template(UPLINK_TOPIC_TEMPLATE)
    for topic in UPLINK_TOPICS:
        topicRendered = template.render(username=getMqttCredentials()[0],device=device,topic=topic)
        mqttBrokerClient.unsubscribe(topicRendered,0)
        debug("Unsubscribing from topic : " + topicRendered)
    previousMessages.pop(device)
    debug("Update : previousMessages " + str(previousMessages))
    devicesStates.pop(device)
    debug("Update : devicesStates " + str(devicesStates))
    previousSpreadingFactor.pop(device)
    debug("Update : previousSpreadingFactor " + str(previousSpreadingFactor))

class DownlinkServer(SimpleHTTPRequestHandler):
    def do_POST(self):
        content_length = int(self.headers['Content-Length']) # <--- Gets the size of data
        post_data = self.rfile.read(content_length) # <--- Gets the data itself
        pd = post_data.decode("utf-8")   # <-------- ADD this line
        data = json.loads(pd)
        debug("HTTP POST Request : adress " + self.path)
        debug("content : " + str(data))
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

        debug("HTTP GET Request : adress " + self.path)

        if(self.path[13:] == "enddevicePage.html"):
            template = env.get_template(self.path[13:])
            credentials = getMqttCredentials()
            msg = template.render(end_device_list=getDeviceIds(),api_key=credentials[1],username=credentials[0])
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            self.wfile.write(bytes(msg,"utf-8"))
        elif(self.path[13:] == "configpage.html"):
            template = env.get_template(self.path[13:])
            config = getDeviceConfig()
            msg = template.render(config=config,sf=previousSpreadingFactor)
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            self.wfile.write(bytes(msg,"utf-8"))
        else :
            self.path = '/root/' + self.path[13:]
            return SimpleHTTPRequestHandler.do_GET(self)

def runHttpServer(server_class=HTTPServer, handler_class=DownlinkServer):
    server_address = ('', 1885)
    httpd = server_class(server_address, handler_class)
    httpd.serve_forever()

def init():
    debug("Initializing.")
    loadConfig()
    devices = getDeviceIds()
    for device in devices:
        devicesStates[device] = NOT_CONFIGURED
        previousMessages[device] = []
        previousSpreadingFactor[device] = 0

def debug(x):
    if(DEBUG):
        print("[DEBUG] " + str(x))

main()