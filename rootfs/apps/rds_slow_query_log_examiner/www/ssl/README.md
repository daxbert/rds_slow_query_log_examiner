<h1>SSL Tips:</h1>

* Make sure localhost is in your hosts file

* Add the following entry to your hosts file:

```hosts
localhost 127.0.0.1
docker  192.168.99.100
```

* Add the "insecure" self-signed cert to your trusted root certificates
in your browser

<h1>Roll your own...</h1>

In this directory we have all the files for SSL support.

You may wish to import the SSL cert into your browser
so that your browser will "trust" this cert.

As this cert and key are now "public" you may
wish to build your own.


Should you desire to 
make your own SSL cert, here's
what was done.

Just do this...

```
docker run -it centos bash
yum install -y openssl
```




Within the container create openssl.cnf:
```buildoutcfg
[req]
distinguished_name = req_name
req_extenstions = v3_req
prompt = no
[req_name]
C = US
ST = California
L = Santa Clara
O = MyCompany
OU = MyOrg
CN = localhost
[v3_req]
keyUsage = keyEncipherment, dataEncipherment
extendedKeyUsage = serverAuth
[SAN]
subjectAltName=DNS:localhost,IP:127.0.0.1,DNS:docker,IP:192.168.99.100```

Within the container
<p>
Run this command to create key & cert:

```shell
# openssl req \
-newkey rsa:4096 \
-x509 \
-nodes \
-keyout key.pem \
-new \
-out server.pem \
-reqexts SAN \
-extensions SAN \
-config ./openssl.cnf \
-sha256 \
-days 65535
```

Then copy/paste the file contents into this directory.
