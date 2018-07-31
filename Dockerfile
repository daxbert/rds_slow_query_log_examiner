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
    python36  get-pip.py && \
	pip install awscli urllib3 boto3 Flask && \
    yum install -y http://www.percona.com/downloads/percona-release/redhat/0.1-6/percona-release-0.1-6.noarch.rpm  && \
    yum install -y percona-toolkit && \
    yum install -y https://download.postgresql.org/pub/repos/yum/9.6/redhat/rhel-7-x86_64/pgdg-centos96-9.6-3.noarch.rpm && \
    yum install -y pgbadger && \
    yum clean all; \
    rm -rf /var/log/apt/lists/*; \
    rm /var/log/yum.log; \
    rm -rf /var/cache/yum; \
    rm /tmp/*;  

EXPOSE 5150
ADD ./rootfs /
CMD ["python36", "/apps/rds_slow_query_log_examiner/www/app.py"]
