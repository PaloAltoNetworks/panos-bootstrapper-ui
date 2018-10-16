# PanOS Bootstrapper UI

This project will quickly spin up the PanOS bootstrapper service and a simple UI to consume the bootstrapper API. Using
this tool, an architect or designer can create and manage the templates necessary to configure a Palo Alto Networks
device upon first boot. A fully customized UI can then use those templates to allow an operator to input only those 
variables necessary to compile those templates into a bootstrap package. 

For details about the bootstrapping process, refer to the official 
[documentation](https://www.paloaltonetworks.com/documentation/71/pan-os/newfeaturesguide/management-features/bootstrapping-firewalls-for-rapid-deployment.html).

### Installation

1. Install docker and docker-compose

2. clone or download this repository

```bash
git clone https://github.com/PaloAltoNetworks/panos-bootstrapper-ui.git

```

3. Execute the docker-compose up command

```bash
cd panos-bootstrapper-ui
docker-compose up
```

4. Browse to http://localhost:8088

### Upgrading to the latest version

Upgrading to the latest version should be quick and easy:

```bash
cd panos-bootstrapper-ui
git pull
docker-compose up --force-recreate
```



### Examples 

Examples can be found in the project documentation on here: https://panos-bootstrapper.readthedocs.io/en/latest/ 


### Troubleshooting

If you have issues pulling the images, try to log in to the docker CLI
tool using:

```bash
docker login
```

Verify basic docker functionality with:

```bash
docker run hello-world
```

You can also force the recreation of all the service using these commands:

```bash
cd panos-bootstrapper-ui
git pull
docker-compose up --force-recreate
```

If you are not using `git` then download the `zip` archive again 
and issue the following:

```bash
docker-compose up --force-recreate
```

If you are still having problems, you can try these steps as a last resort

```bash
# Delete every Docker containers
# Must be run first because images are attached to containers
docker rm -f $(docker ps -a -q)

# Delete every Docker image
docker rmi -f $(docker images -q)
```

To completely start over with docker and remove all cached content and recreate the database, try this:

```bash
# enter the bootstrapper-ui directory
cd panos-bootstrapper-ui
# ensure all containers and networks are removed
docker-compose down
# push directory into /var/lib
pushd /var/lib
# stop docker service
sudo service docker stop
# nuke the docker directory (not for the faint of heart)
sudo mv docker docker.nuke
# restart docker
sudo service docker start
# jump back to our bootstrapper-ui dir
popd
# bring up the containers as normal by recreateing all layers, inages, and containers
docker-compose up
```
