import influxdb_client
from influxdb_client.client.write_api import SYNCHRONOUS

influxdbAddress = "localhost" #os.environ["influxdb_Address"]
influxdbPort = "8086" #os.environ["influxdbPort"]
influxdbUsername = "admin" 
influxdbToken = "__SUPER_SECRET_TOKEN_TO_CHANGE__"
influxdbOrg = "air-quality"
INFLUXDB_BUCKET = "air-quality"
def connect():
    influxdbClient = influxdb_client.InfluxDBClient("http://"+influxdbAddress+":"+influxdbPort,token=influxdbToken,org=influxdbOrg)
    return  influxdbClient.write_api(write_options=SYNCHRONOUS)

def write(w:influxdb_client.WriteApi,p):
    w.write(bucket=INFLUXDB_BUCKET,org=influxdbOrg,record=p)
