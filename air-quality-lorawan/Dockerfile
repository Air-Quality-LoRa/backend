# syntax=docker/dockerfile:1

FROM python:3.8

WORKDIR /app

# COPY ./ /app/

RUN pip3 install paho-mqtt influxdb-client jinja2

CMD ["python3","-u","/app/main.py"]