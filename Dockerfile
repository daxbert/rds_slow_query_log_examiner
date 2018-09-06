FROM centos
MAINTAINER dax@chegg.com

ENV LANG en_US.UTF-8  
ENV LANGUAGE en_US:en  
ENV LC_CTYPE en_US.UTF-8
ENV TZ=America/Los_Angeles

RUN \
    yum install -y epel-release wget && \
    yum install -y python36 && \
    cd /tmp && \
    wget https://bootstrap.pypa.io/get-pip.py  && \
    python36 get-pip.py && \
	pip install pyopenssl awscli boto3 Flask && \
    yum clean all; \
    rm -rf /var/log/apt/lists/*; \
    rm /var/log/yum.log; \
    rm -rf /var/cache/yum; \
    rm /tmp/*;  

# EXPOSE HTTPS on 5151
EXPOSE 5151

ADD ./rootfs /
CMD ["sh", "-c", "cd /apps; export FLASK_APP=rds_slow_query_log_examiner; flask run -h 0.0.0.0 -p 5151 --cert rds_slow_query_log_examiner/ssl/server.pem --key rds_slow_query_log_examiner/ssl/key.pem"]
