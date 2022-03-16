import json, os

configuration = dict()

def setDeviceConfig(config):
    configuration["device_config"] = config
    saveConfig()

def setDeviceIds(deviceIds:[]):
    configuration["device_ids"] = device_ids
    saveConfig()
    
def setMqttCredentials(username:str, key:str):
    configuration["mqttApiKey"] = key
    configuration["mqttUsername"] = username
    saveConfig()

def getDeviceConfig(config):
    return configuration["device_config"]

def getDeviceIds(deviceIds:[]):
    return configuration["device_ids"]
 
    
def getMqttCredentials():
    return (configuration["mqttUsername"], configuration["mqttApiKey"])


def saveConfig():
    global configuration
    with open('config.json.tmp', 'w') as f:
        f.write(json.dumps(configuration))
    os.replace('config.json.tmp', 'config.json')

def loadConfig():
    global configuration
    with open('config.json', 'r') as f:
        configuration = json.load(f)
