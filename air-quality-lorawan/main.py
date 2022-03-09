import paho.mqtt.client as mqtt
from threading import Timer
import json
import base64
import influxdb_client

uplinkTopic = "v3/air-quality-grenoble@ttn/devices/air-quality-station-test2/up"
usernameMqttBroker = "air-quality-grenoble@ttn"
passwordMqttBroker = "NNSXS.OZZCXODHUEZ6NGUBA4JPSU5JEIRALEU6HCU7ZJQ.QAOYPVCTCFYWIB5BLMEWN5ZN3TXO2WMB5QU6EIQSQ66CPWNHMECQ"
addressMqttBroker = "eu1.cloud.thethings.network"
portMqttBroker = 1883

influxdbAddress = "localhost"
influxdbPort = "8086"
influxdbUsername = "admin"
influxdbToken = "o92Qd_sO34KKh7lj3AczKutxH5aZ8vTGytrud-iKu7FvA4bo-nvOj09g9SRGbFnitFi4XoG8Iri32_0DORhR7Q=="
influxdbOrg = "f43170103778eb07"
influxdbBucket = "air-quality"

mqttBrokerClient = mqtt.Client()
influxdbClient = influxdb_client.InfluxDBClient("http://"+influxdbAddress+":"+influxdbPort,token=influxdbToken,org=influxdbOrg)

# The callback for when the client receives a CONNACK response from the server.
def on_connect(client, userdata, flags, rc):
    print("Connected to ttn mqtt")

    # Subscribing in on_connect() means that if we lose the connection and
    # reconnect then subscriptions will be renewed.
    client.subscribe(uplinkTopic,2)

# The callback for when a PUBLISH message is received from the server.
def on_message(client, userdata, msg):
    print(msg.topic+" "+str(msg.payload))
    payload = json.loads(msg.payload)
    dataObject = dict("")
    dataObject["device_id"] = payload["end_device_ids"]["device_id"]
    dataObject["app_id"] = payload["end_device_ids"]["application_ids"]["application_id"]
    dataObject["timestamp"] = payload["received_at"]
    dataObject["payload"] = payload["uplink_message"]["frm_payload"]
    json_influx = [{
        "measurment":"fine-particle",
        "time":payload["received_at"],
        "fields": {
            "Salut": 0
        }

    }]
    influxdbClient.write_points(json_influx)

def main():

    mqttBrokerClient.username_pw_set(usernameMqttBroker,passwordMqttBroker)
    mqttBrokerClient.on_connect = on_connect
    mqttBrokerClient.on_message = on_message
    mqttBrokerClient.connect_async(addressMqttBroker, port=portMqttBroker, keepalive=60, bind_address="")
    mqttBrokerClient.loop_forever()

main()
