from http.server import HTTPServer, SimpleHTTPRequestHandler
import main
import json
from jinja2 import Environment, FileSystemLoader, select_autoescape

env = Environment(
    loader=FileSystemLoader('templates'),
    autoescape=select_autoescape()
)

class DownlinkServer(SimpleHTTPRequestHandler):
    def do_POST(self):
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length)
        pd = post_data.decode("utf-8")
        data = json.loads(pd)
        main.debug("HTTP POST Request : adress " + self.path)
        main.debug("content : " + str(data))
        if(self.path == "/api-backend/config_device"):
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            main.handleDeviceConfig(data)
        elif(self.path == "/api-backend/config_app"):
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            main.handleAppConfig(data)
        elif(self.path == "/api-backend/add_device"):
            if(main.handleAddDevice(data)):
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
            main.handleRemoveDevice(data)
        else:
            self.send_error(404)
            self.send_header("Content-type", "text/html")
            self.end_headers()
    def do_GET(self):

        main.debug("HTTP GET Request : adress " + self.path)

        if(self.path[13:] == "enddevicePage.html"):
            template = env.get_template(self.path[13:])
            credentials = main.getMqttCredentials()
            msg = template.render(end_device_list=main.getDeviceIds(),appid=main.getAppId(),pwd=credentials[1],username=credentials[0])
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            self.wfile.write(bytes(msg,"utf-8"))
        elif(self.path[13:] == "configpage.html"):
            template = env.get_template(self.path[13:])
            config = main.getDeviceConfig()
            msg = template.render(config=config,sf=main.previousSpreadingFactor)
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