from curses.ascii import ACK
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
WAITING_TTN = 1
WAITING_ACK = 2
CONFIGURED = 3

REQUEST_CONFIG = 1
CONCENTRATION = 2
UNIT = 3
BOTH = 4
CONCENTRATION_REC = 5
UNIT_REC = 6
BOTH_REC = 7

UP = 0
DOWN_QUEUED = 1
DOWN_ACK = 2

UPLINK_INTERVAL_DICT = {0:120,1:60,2:45,3:30,4:20,5:15,6:10,7:5}
RECOVERY_INTERVAL_DICT = {0:-1,1:2,2:4,3:8,4:16,5:32,6:64,7:128}

# devices = ["air-quality-station-test2"]
UPLINK_TOPIC_TEMPLATE = "v3/{{username}}/devices/{{device}}/{{topic}}"
UPLINK_TOPICS = ["up","down/queued","down/nack"]

# usernameMqttBroker = "air-quality-grenoble@ttn"
# passwordMqttBroker = "NNSXS.OZZCXODHUEZ6NGUBA4JPSU5JEIRALEU6HCU7ZJQ.QAOYPVCTCFYWIB5BLMEWN5ZN3TXO2WMB5QU6EIQSQ66CPWNHMECQ"
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
# influxdbQueryApi = influxdbClient.query_api()

# QUERY_LAST_SF_TEMPLATE = "from(bucket:\"{{bucket}}\")\n|>range(start:0)\n|>filter(fn: (r) => r._measurement==\"{{device_id}}@{{app_id}}:network-health-sf\" and r._field==\"spreading_factor\")\n|>last()"

previousSpreadingFactor = dict()

devicesStates = dict()

previousMessages = dict()

dateFormat= "%Y-%m-%dT%H:%M:%S.%f"

def formatTimestamp(timestamp):
    formattedTimestamp = datetime.strptime(timestamp,dateFormat)
    formattedTimestamp = int(formattedTimestamp.timestamp()*1000000)
    return formattedTimestamp

def filterInfo(rawPayload):
    arrayPayload = binascii.a2b_base64(rawPayload["uplink_message"]["frm_payload"])
    filteredPayload = {
        "message_id" : arrayPayload[0],
        "device_id" : rawPayload["end_device_ids"]["device_id"],
        "app_id" : rawPayload["end_device_ids"]["application_ids"]["application_id"],
        "timestamp" : formatTimestamp(rawPayload["received_at"][:-4]),
        "type" : rawPayload["uplink_message"]["f_port"],
        "payload" : arrayPayload,
        "raw_payload" : rawPayload["uplink_message"]["frm_payload"],
        "spreading_factor" : rawPayload["uplink_message"]["settings"]["data_rate"]["lora"]["spreading_factor"],
        "is_recovered" : False
    }
    print("Filtered : " + str(filteredPayload))
    return filteredPayload

def readTwoBytes(index,array):
    return (array[index] << 8) + array[index+1]

def parsePayload(message):
    payload = message["payload"]
    data_type = message["type"]
    if(data_type == 1):
        data = {"uplink_interval": payload[0]>>5,
                "data_type": (payload[0] & 0b00011000) >> 3,
                "recovery_interval": payload[0] & 0b00000111
               }
    else:
        data = {"temperature" : 0,
                "humidity" : 0,
                "c_pms_1_0" : 'N/A',
                "c_pms_2_5" : 'N/A',
                "c_pms_10" : 'N/A',
                "q_pms_0_3" : 'N/A',
                "q_pms_0_5" : 'N/A',
                "q_pms_1_0" : 'N/A',
                "q_pms_2_5" : 'N/A',
                "q_pms_5_0" : 'N/A',
                "q_pms_10" : 'N/A'}
        if(data_type == REQUEST_CONFIG):
            data = 'Request'
        else:
            data["temperature"] = payload[1]/2
            data["humidity"] = payload[2]
        if(data_type in [CONCENTRATION,BOTH,CONCENTRATION_REC,BOTH_REC]):
            data["c_pms_1_0"] = readTwoBytes(3,payload)
            data["c_pms_2_5"] = readTwoBytes(5,payload)
            data["c_pms_10"] = readTwoBytes(7,payload)
        if(data_type in[UNIT,BOTH,UNIT_REC,BOTH_REC]):
            shift = 0
            if(data_type in [UNIT_REC,BOTH_REC]):
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

# The callback for when the client receives a CONNACK response from the server.
def on_connect(client, userdata, flags, rc):
    print("Connected to ttn mqtt")

    # Subscribing in on_connect() means that if we lose the connection and
    # reconnect then subscriptions will be renewed.
    template = Template(UPLINK_TOPIC_TEMPLATE)
    for device in getDeviceIds:
        for topic in UPLINK_TOPICS:
            client.subscribe(template.render(username=usernameMqttBroker,device=device,topic=topic),2)

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
    p = p.field("temperature", message["payload"]["temperature"])
    p = p.field("humidity", message["payload"]["humidity"])
    p = p.field("c_pms_1_0", message["payload"]["c_pms_1_0"])
    p = p.field("c_pms_2_5", message["payload"]["c_pms_2_5"])
    p = p.field("c_pms_10", message["payload"]["c_pms_10"])
    p = p.field("q_pms_0_3", message["payload"]["q_pms_0_3"])
    p = p.field("q_pms_0_5", message["payload"]["q_pms_0_5"])
    p = p.field("q_pms_1_0", message["payload"]["q_pms_1_0"])
    p = p.field("q_pms_2_5", message["payload"]["q_pms_2_5"])
    p = p.field("q_pms_5_0", message["payload"]["q_pms_5_0"])
    p = p.field("q_pms_10", message["payload"]["q_pms_10"])
    p = p.time(message["timestamp"])
    influxdbWriteApi.write(bucket=INFLUXDB_BUCKET,org=influxdbOrg,record=p)

def storePreviousMessage(message,config):
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
        if(devicesStates[message["device_id"]] != CONFIGURED):
            return #ignore message
        else:
            handleUplink(message)
    elif(topic == DOWN_QUEUED):
        if(devicesStates[message["device_id"]] == WAITING_TTN):
            devicesStates[message["device_id"]] = WAITING_ACK
    elif(topic == DOWN_ACK):
        if(devicesStates[message["device_id"]] == WAITING_ACK):
            devicesStates[message["device_id"]] = CONFIGURED

def handleUplink(message):
    config = getDeviceConfig()["sf"+message["spreading_factor"]]
    
    if(int(message["spreading_factor"]) != int(previousSpreadingFactor[message["device_id"]])):
        previousMessages[message["device_id"]] = []
    if(len(previousMessages[message["device_id"]])!=0):
        saut = (int(message["message_id"]) - previousMessages[message["message_id"]][0][0])%256
        if(saut > 1):
            storeRecoveryLoss(saut-1,0,message)
    storePreviousMessage(message,config)
    storeSpreadingFactor(message)
    previousSpreadingFactor[message["device_id"]] = int(message["spreading_factor"])


    if(message["type"] in [CONCENTRATION,UNIT,BOTH]):
        storeMessage(message)
    elif(message["type"] in [CONCENTRATION_REC,UNIT_REC,BOTH_REC]):
        handleRecover(message, config)
    elif(message["type"] == REQUEST_CONFIG):
        #TODO
        pass
    return

def topicOf(topic):
    if(topic[-2:] == "up"):
        return UP
    elif(topic[-11:] == "down/queued"):
        return DOWN_QUEUED
    elif(topic[-9:]):
        return DOWN_ACK

# The callback for when a PUBLISH message is received from the server.
def on_message(client, userdata, msg):
    print("[DEBUG] Message recieved from MQTT :\nTopic : " + str(msg.topic) + "\nMsg : " + str(msg.payload) + "\n\n\n")
    message = formatMsg(msg.payload)
    topic = topicOf(str(msg.topic))
    handleMessage(message,topic)

def main():
    run()
    # mqttBrokerClient.username_pw_set(usernameMqttBroker,passwordMqttBroker)
    # mqttBrokerClient.on_connect = on_connect
    # mqttBrokerClient.on_message = on_message
    # mqttBrokerClient.connect_async(addressMqttBroker, port=portMqttBroker, keepalive=60, bind_address="")
    # mqttBrokerClient.loop_forever()


env = Environment(
    loader=FileSystemLoader('templates'),
    autoescape=select_autoescape()
)

def handleDeviceConfig(data):
    global config
    config = data

def handleAppConfig(data):
    global usernameMqttBroker
    global passwordMqttBroker
    usernameMqttBroker = data["username"]
    passwordMqttBroker = data["api-key"]
    #Change SQLIT
    #TODO
    #Restart mqtt

def handleAddDevice(data):
    devices = getDeviceIds()
    if(data['end-device'] in devices):
        return False
    else:
        devices.append(data['end-device'])
        setDeviceIds(devices)
        return True
    #Subscribe in mqtt
    #Save in SQLITE
    #TODO

def handleRemoveDevice(data):
    devices = getDeviceIds()
    devices.remove(data['end-device'])
    setDeviceIds(devices)
    #Unsubscribe in mqtt
    #Save in SQLITE
    #TODO

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
            msg = template.render(end_device_list=getDeviceIds,api_key=passwordMqttBroker,username=usernameMqttBroker)
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            self.wfile.write(bytes(msg,"utf-8"))
        else :
            self.path = '/templates/' + self.path[13:]
            print(self.path)
            return SimpleHTTPRequestHandler.do_GET(self)

def run(server_class=HTTPServer, handler_class=DownlinkServer):
    server_address = ('', 1885)
    httpd = server_class(server_address, handler_class)
    httpd.serve_forever()

def init():
    # initConfig
    devices = getDeviceIds()
    for device in devices:
        devicesStates[device] = NOT_CONFIGURED
        previousMessages[device] = []
        previousSpreadingFactor[device] = 0
    pass


main()