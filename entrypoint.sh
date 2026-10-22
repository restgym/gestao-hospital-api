#!/usr/bin/env bash
# Starts Gestão Hospitalar in RESTgym: see /infrastructure/api/restgym-api.sh

source /infrastructure/api/restgym-api.sh

# MongoDB, empty at each start: the API inserts its own sample data when it starts (Instantiation, in its code)
mkdir -p /data/db
mongod --fork --logpath /var/log/mongodb.log --dbpath /data/db || restgym_fail "MongoDB did not start."
restgym_wait_for_port MongoDB 27017

# The mock of LocationIQ (see location-iq-mock/README.md): us1.locationiq.com, which the API calls to geocode the address
# of a new hospital, resolves to the container, where the mock answers on port 443 (HTTPS)
echo "127.0.0.1 us1.locationiq.com" >> /etc/hosts || restgym_fail "Cannot redirect us1.locationiq.com to the LocationIQ mock."
restgym_start_service "the LocationIQ mock" python3 /api/location-iq-mock/locationiq_mock.py --port 443 \
    --cert /api/location-iq-mock/certs/server.pem --key /api/location-iq-mock/certs/server.key \
    --log "$RESTGYM_RESULTS/logs/location-iq-mock.log"
restgym_wait_for_port "the LocationIQ mock" 443

restgym_run_api 8080 \
    java -javaagent:/infrastructure/jacoco/org.jacoco.agent-0.8.12-runtime.jar=includes=*,output=tcpserver,port=12345,address=* \
        -Dfile.encoding=UTF-8 \
        -Dserver.port=8080 \
        -Dspring.data.mongodb.host=localhost \
        -Dspring.data.mongodb.port=27017 \
        -Dspring.data.mongodb.database=HospitalDB \
        -jar /api/gestaohospitalar-0.0.1.jar
