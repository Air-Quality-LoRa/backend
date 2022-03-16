import configparser
import threading

device_config = {  "sf7": {
                "data_type": 1,
                "data_interval": 5,
                "data_recovery" : 2
            },
            "sf8": {
                "data_type": 1,
                "data_interval": 10,
                "data_recovery" : 2
            },
            "sf9": {
                "data_type": 1,
                "data_interval": 15,
                "data_recovery" : 2
            },
            "sf10": {
                "data_type": 1,
                "data_interval": 30,
                "data_recovery" : 2
            },
            "sf11": {
                "data_type": 1,
                "data_interval": 60,
                "data_recovery" : 2
            },
            "sf12": {
                "data_type": 1,
                "data_interval": 120,
                "data_recovery" : 2
            },
}

mqttUsername = ""
mqttApiKey = ""

device_ids = []

configParser = configparser.ConfigParser()

mutex = threading.Lock()

def setDeviceConfig(config):
    global device_config
    device_config = config
    saveConfig()

def saveConfig():
    global mutex
    mutex.acquire()
    mqtt = configParser['MQTT']
    mqtt['username'] = mqttUsername
    mqtt['apikey'] = mqttApiKey
    devices = configParser['DEVICES']
    devices['list'] = str(device_ids)
    devices['config'] = device_config
    

    mutex.release()

    