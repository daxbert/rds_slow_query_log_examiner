# POWERSHELL

. ./config.ps1

if ( "$Env:AWS_ACCESS_KEY_ID" -and "$Env:AWS_SECRET_ACCESS_KEY") {
    echo "AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY defined"
}
else {
    echo "AWS_ACCESS_KEY_ID or AWS_SECRET_ACCESS_KEY undefined"
    if ( "$Env:AWS_DEFAULT_PROFILE" ) {
        echo "AWS_DEFAULT_PROFILE defined [$Env:AWS_DEFAULT_PROFILE]"
        echo "Will attempt to parse keys from credentials file"
        echo "for the profile specified"
        echo "This could be improved..."
        echo ""
	    $Env:AWS_ACCESS_KEY_ID=(Select-String -Path ~/.aws/credentials -Pattern $Env:AWS_DEFAULT_PROFILE -Context 2  | Out-String -stream | Select-String -Pattern "aws_access_key_id" | Out-String -stream).split("=")[2].Trim()
	    $Env:AWS_SECRET_ACCESS_KEY=(Select-String -Path ~/.aws/credentials -Pattern $Env:AWS_DEFAULT_PROFILE -Context 2  | Out-String -stream | Select-String -Pattern "aws_secret_access_key" | Out-String -stream).split("=")[2].Trim()
    }
    else {
        echo "Set both AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY"
        echo "or set AWS_DEFAULT_PROFILE"
        echo ""
        echo "Set-Item -Path Env:AWS_ACCESS_KEY_ID -Value 'AKIA...'"
        echo "Set-Item -Path Env:AWS_SECRET_ACCESS_KEY -Value '#########'"
        echo "OR"
        echo "Set-Item -Path Env:AWS_DEFAULT_PROFILE -Value 'someprofile'"
        echo ""
        exit 1
    }
}

echo ""
echo "Executing docker run command"
echo ""
    docker run -it -p 0.0.0.0:5150:5150 -p 0.0.0.0:5151:5151 -e "AWS_ACCESS_KEY_ID=$Env:AWS_ACCESS_KEY_ID" -e "AWS_SECRET_ACCESS_KEY=$Env:AWS_SECRET_ACCESS_KEY" $Env:DOCKER_NAME $args

