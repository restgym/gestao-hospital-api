#!/usr/bin/env bash
# Starts Gestão Hospitalar in RESTgym: see /infrastructure/api/restgym-api.sh

source /infrastructure/api/restgym-api.sh

# MongoDB, initialized with the data of the API at each start
mkdir -p /data/db
mongod --fork --logpath /var/log/mongodb.log --dbpath /data/db || restgym_fail "MongoDB did not start."
restgym_wait_for_port MongoDB 27017
if [ -f /api/database/init-mongo.js ]; then
    mongosh HospitalDB /api/database/init-mongo.js || restgym_log "The initialization of MongoDB completed with warnings."
fi

restgym_run_api 8080 \
    java -javaagent:/infrastructure/jacoco/org.jacoco.agent-0.8.7-runtime.jar=includes=*,output=tcpserver,port=12345,address=* \
        -Dfile.encoding=UTF-8 \
        -Dserver.port=8080 \
        -Dspring.data.mongodb.host=localhost \
        -Dspring.data.mongodb.port=27017 \
        -Dspring.data.mongodb.database=HospitalDB \
        -jar /api/gestaohospitalar.jar
