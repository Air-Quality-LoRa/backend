# The Server configuration for the air quality project

Deployment is done with `docker` and `docker-compose`. Please install them before following instructions. You can find documentation to install it [here](https://docs.docker.com/engine/install/debian/).

## Deployment 

### Secure the python backend

Install `apache2-utils` to generate a `.htpasswd` file.

Run 
```
htpasswd -c configuration/nginx/.htpasswd admin
``` 
and then interactively type a password.

This pasword will be asked on the configuration pages. 

### Change the credentials
Change the information in the `.env` file as you like

### Create the persistent folders and files
```
mkdir -p data/{grafana,influxdb}
touch data/grafana/grafana.db
```

### Start the server
Start everything with 
```
docker-compose up --build -d
```

## Update the server
```
git pull
docker-compose pull
docker-compose up --force-recreate --build -d
docker image prune -f #optional, to free space
```

# Persistant data
The persistant data is located in two folders:
- `configuration`
- `data`
When you transfer the server, transfer these two folders to the new machine to keep all the data.
