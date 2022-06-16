echo TODO
exit
python3 -u scripts/cloudless.py cloudless-serve-graph-fat |& tee test-proxy-1.log &
python3 -u scripts/cloudless.py 4000 cloudless-serve-graph-fat |& tee test-proxy-2.log &
sleep 1
echo connect-instance
python3 -u ./connect-instance http://localhost:4000 9999 |& tee test-proxy-3.log
echo cloudless-to-cloudless
sleep 1
python3 -u ./cloudless-to-cloudless http://localhost:4000 ws://localhost:3124 myproxy |& tee test-proxy-4.log &
echo cloudless-to-cloudless FINISHED
sleep 1
curl http://localhost:4000/instance/9999/ctx/myresult
curl http://localhost:3124/proxy/myproxy/9999/ctx/myresult
#python3 test-proxy-ws.py ws://localhost:5138/ctx 1
#python3 test-proxy-ws.py ws://localhost:4000/instance/9999/ctx 1
python3 test-proxy-ws.py ws://localhost:3124/proxy/myproxy/9999/ctx 1
echo SHUTDOWN
cloudless=$(ps -f | awk '$8 == "python3" {print $2}')
kill -INT $cloudless
