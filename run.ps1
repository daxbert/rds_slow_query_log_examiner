# POWERSHELL

. ./config.ps1

echo ""
echo "Executing docker run command"
echo ""
    docker run -it -p 0.0.0.0:5150:5150 -p 0.0.0.0:5151:5151 $Env:DOCKER_NAME $args

