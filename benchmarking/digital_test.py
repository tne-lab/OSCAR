import zmq
import time

high_load = True
test_dur = 40
context = zmq.Context.instance()
client = context.socket(zmq.DEALER)
client.setsockopt(zmq.RCVHWM, 0)
client.setsockopt(zmq.SNDHWM, 0)
client.connect("tcp://{}:{}".format('127.0.0.1', 9296))
poll = zmq.Poller()
poll.register(client, zmq.POLLIN)
client.send(b"READY")
sockets = dict(poll.poll(1000))
if sockets:
    client.recv()

    if high_load:
        client.send(b'RegGPIO 0 A0 3\nRegGPIO 0 A1 3\n')

    t = time.perf_counter()

    while time.perf_counter() - t < test_dur:
        msg = client.recv().decode('utf-8')
        msgs = msg[:-1].split('\n')
        for msg in msgs:
            comps = msg.split(' ')
            if comps[0] == 'DIn':
                client.send(b'DOut 0 0\n')

    client.send(b'Reset 0\n')
    client.send(b'CLOSE')
