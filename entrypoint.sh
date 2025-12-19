#!/bin/bash
set -e
mkdir -p /results/$API/$TOOL/$RUN/code-coverage
cp -r /api/specifications /results/$API/$TOOL/$RUN/
mkdir -p /data/db
mkdir -p /results/$API/$TOOL/$RUN/logs

echo "Starting MongoDB..."
mongod --fork --logpath /var/log/mongodb.log --dbpath /data/db
echo "Waiting for MongoDB to start..."
sleep 10

echo "Initializing MongoDB database..."
if [ -f /api/database/init-mongo.js ]; then
  mongo HospitalDB /api/database/init-mongo.js || echo "MongoDB initialization completed with warnings"
fi

echo "Starting JaCoCo coverage collector..."
sh /infrastructure/jacoco/collect-coverage-interval.sh &
JACOCO_PID=$!

echo "Starting Gestao Hospitalar API in background..."
java -javaagent:/infrastructure/jacoco/org.jacoco.agent-0.8.7-runtime.jar=includes=*,output=tcpserver,port=12345,address=* -Dfile.encoding=UTF-8 -Dserver.port=8080 -Dspring.data.mongodb.host=localhost -Dspring.data.mongodb.port=27017 -Dspring.data.mongodb.database=HospitalDB -jar /api/gestaohospitalar.jar > /results/$API/$TOOL/$RUN/logs/gestaohospitalar-stdout.log 2> /results/$API/$TOOL/$RUN/logs/gestaohospitalar-stderr.log &
API_PID=$!

echo "Waiting for API to start..."
for i in {1..60}; do
  if curl -s http://localhost:8080/v1/hospitais/ > /dev/null 2>&1; then
    echo "API is ready!"
    break
  fi
  if [ $i -eq 60 ]; then
    echo "API failed to start in time"
    exit 1
  fi
  sleep 1
done

echo "Starting mitmproxy..."
mitmdump -p 9090 --mode reverse:http://localhost:8080/ -s /infrastructure/mitmproxy/store-interactions.py -s /api/auth.py > /results/$API/$TOOL/$RUN/logs/mitmproxy.log 2>&1 &
MITM_PID=$!

echo "Waiting for mitmproxy to start..."
sleep 10

echo "All services started. Waiting for API process..."
wait $API_PID
