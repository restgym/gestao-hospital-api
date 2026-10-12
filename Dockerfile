# Gestão Hospitalar
# Base image: Ubuntu 22.04, Java 8 (headless JRE), mitmproxy and the RESTgym infrastructure (see infrastructure/api/Dockerfile)
FROM restgym/api-base:java8

# MongoDB 6.0 (initialized by entrypoint.sh with database/init-mongo.js), from the repository of MongoDB
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl gnupg \
    && curl -fsSL https://www.mongodb.org/static/pgp/server-6.0.asc | gpg --dearmor -o /usr/share/keyrings/mongodb-server-6.0.gpg \
    && echo "deb [ arch=amd64,arm64 signed-by=/usr/share/keyrings/mongodb-server-6.0.gpg ] https://repo.mongodb.org/apt/ubuntu jammy/mongodb-org/6.0 multiverse" > /etc/apt/sources.list.d/mongodb-org-6.0.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends mongodb-org \
    && rm -rf /var/lib/apt/lists/*

# The API: its executable, the classes for code coverage, its specifications and scripts
COPY ./apis/gestao-hospital/ /api/

# Startup script (in /api): starts the API, the collection of code coverage and the proxy (see infrastructure/api/restgym-api.sh)
ENTRYPOINT ["bash", "/api/entrypoint.sh"]
