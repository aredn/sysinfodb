# 
# aredn/sysinfodb
#

FROM ubuntu:latest
MAINTAINER dman776@gmail.com
ENV IMAGE=aredn/sysinfodb \
    AREDNUSER=aredn \
    AREDNDIR=/opt/aredn

EXPOSE 8080
RUN apt-get update && apt-get install -y \
    tar \
    git \
    curl \
    nano \
    wget \
    dialog \
    net-tools \
    build-essential \
    htop \
    vim-tiny \
    python \
    python-dev \
    python-distribute \
    python-pip

RUN pip install --upgrade pip
RUN pip install \
    bottle \
    pymongo \
    pykml \
    requests

RUN useradd -m ${AREDNUSER}

RUN mkdir -p ${AREDNDIR} \
    && chown ${AREDNUSER}:${AREDNUSER} ${AREDNDIR}

USER ${AREDNUSER}
WORKDIR ${AREDNDIR}

# COPY livemap.html ${AREDNDIR}
COPY mongo_kml.py ${AREDNDIR}
COPY sysinfodb.py ${AREDNDIR}
COPY start.sh ${AREDNDIR}
# CMD ${AREDNDIR}/sysinfodb.py
CMD ${AREDNDIR}/start.sh