# syntax=docker/dockerfile:1

FROM python:3.8

WORKDIR /app

RUN pip3 install paho-mqtt influxdb-client

CMD ["python3","/app/main.py"]