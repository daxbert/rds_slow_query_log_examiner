docker-machine ls --filter "Name=default" | grep default > $null
if ( -not $? ) {
	docker-machine create -driver virtualbox default
}
Set-Item -Path Env:DOCKER_CERT_PATH 	-Value "${Env:USERPROFILE}\.docker\machine\machines\default"
Set-Item -Path Env:DOCKER_HOST 		-Value "tcp://192.168.99.100:2376"
Set-Item -Path Env:DOCKER_MACHINE_NAME 	-Value "default"
Set-Item -Path Env:DOCKER_TLS_VERIFY	-Value 1

