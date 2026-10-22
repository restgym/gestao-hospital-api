# Gestão Hospitalar
# Base image: Ubuntu 22.04, Java 8 (headless JRE), mitmproxy and the RESTgym infrastructure (see infrastructure/api/Dockerfile)
FROM restgym/api-base:java8

# MongoDB 6.0, from the repository of MongoDB. Every package is pinned to its version, since the repository serves all of
# them and mongodb-org would install the latest otherwise
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl gnupg \
    && curl -fsSL https://www.mongodb.org/static/pgp/server-6.0.asc | gpg --dearmor -o /usr/share/keyrings/mongodb-server-6.0.gpg \
    && echo "deb [ arch=amd64,arm64 signed-by=/usr/share/keyrings/mongodb-server-6.0.gpg ] https://repo.mongodb.org/apt/ubuntu jammy/mongodb-org/6.0 multiverse" > /etc/apt/sources.list.d/mongodb-org-6.0.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
        mongodb-org=6.0.29 mongodb-org-database=6.0.29 mongodb-org-server=6.0.29 mongodb-org-mongos=6.0.29 \
        mongodb-org-shell=6.0.29 mongodb-org-tools=6.0.29 mongodb-org-database-tools-extra=6.0.29 \
        mongodb-mongosh=2.13.0 mongodb-database-tools=100.19.1 \
    && rm -rf /var/lib/apt/lists/*

# The API: its executable, the classes for code coverage, its specifications and scripts
COPY ./apis/gestao-hospital/ /api/

# The mock of LocationIQ (location-iq-mock/, see its README.md), which the API calls instead of the real service: a
# private certificate authority, a certificate of us1.locationiq.com signed by it, and the authority trusted by Java
RUN cd /api/location-iq-mock \
    && mkdir -p certs \
    && openssl req -x509 -newkey rsa:2048 -nodes -days 36500 -subj "/CN=RESTgym LocationIQ mock CA" \
        -keyout certs/ca.key -out certs/ca.pem \
    && openssl req -newkey rsa:2048 -nodes -subj "/CN=us1.locationiq.com" -keyout certs/server.key -out certs/server.csr \
    && printf 'subjectAltName=DNS:us1.locationiq.com\nextendedKeyUsage=serverAuth\n' > certs/server.ext \
    && openssl x509 -req -in certs/server.csr -CA certs/ca.pem -CAkey certs/ca.key -CAcreateserial -days 36500 \
        -extfile certs/server.ext -out certs/server.pem \
    && keytool -importcert -noprompt -alias restgym-locationiq-mock -file certs/ca.pem \
        -keystore "$(readlink -f "$JAVA_HOME/lib/security/cacerts")" -storepass changeit

# Startup script (in /api): starts the API, the collection of code coverage and the proxy (see infrastructure/api/restgym-api.sh)
ENTRYPOINT ["bash", "/api/entrypoint.sh"]
