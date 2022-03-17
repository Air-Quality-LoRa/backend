# The Server configuration for the air quality project

Deployment is done with `docker` and `docker-compose`. Please install them before following instructions. You can find documentation to install it [here](https://docs.docker.com/engine/install/debian/).

## Deployment 

### Secure the python backend

Install `apache2-utils` to generate a `.htpasswd` file.

Run 
```
htpasswd -c configuration/nginx/.htpasswd USERNAME
``` 
and then interactively type a password.


### Change the credentials
Change the information in the `.env` file.


### Start the server
Start everything with 
```
docker-compose up --build -d
```

## Persistant data
The persistant data is located in two folders:
- `configuration`
- `influx-data`
When you transfer the server, transfer these two folders to the new server.

## Update the server
```
git pull
docker-compose pull
docker-compose up --force-recreate --build -d
docker image prune -f #optional, to free space
```