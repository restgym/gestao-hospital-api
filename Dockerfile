FROM ubuntu:22.04

ENV API=gestaohospitalar
ENV TOOL=${TOOL:-manual}
ENV RUN=${RUN:-1}
ENV DEBIAN_FRONTEND=noninteractive

RUN mkdir -p /api /infrastructure /results

# Install required packages including MongoDB
RUN apt-get update && \
    apt-get -y upgrade && \
    apt-get -y install \
        openjdk-8-jdk \
        curl \
        wget \
        netcat \
        sqlite3 \
        python3 \
        python3-pip \
        gnupg \
        ca-certificates && \
    pip3 install mitmproxy requests && \
    curl -fsSL https://www.mongodb.org/static/pgp/server-6.0.asc | gpg --dearmor -o /usr/share/keyrings/mongodb-server-6.0.gpg && \
    echo "deb [ arch=amd64,arm64 signed-by=/usr/share/keyrings/mongodb-server-6.0.gpg ] https://repo.mongodb.org/apt/ubuntu jammy/mongodb-org/6.0 multiverse" | tee /etc/apt/sources.list.d/mongodb-org-6.0.list && \
    apt-get update && \
    apt-get -y install mongodb-org && \
    apt-get -y autoremove && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

COPY apis/gestaohospitalar/gestaohospitalar-0.0.1.jar /api/gestaohospitalar.jar
COPY apis/gestaohospitalar/classes/ /api/classes/
COPY apis/gestaohospitalar/database/ /api/database/
COPY apis/gestaohospitalar/specifications/ /api/specifications/
COPY apis/gestaohospitalar/auth.py /api/auth.py
COPY apis/infrastructure/ /infrastructure/

# Expose ports
EXPOSE 9090 12345 8080

COPY apis/gestaohospitalar/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]

CMD ["/bin/bash", "/start.sh"]
