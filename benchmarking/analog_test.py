import zmq
import time


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

    client.send(b'AInParams 0 3 1\nRegGPIO 0 A0 3\n')

    t = time.perf_counter()

    while time.perf_counter() - t < test_dur:
        msg = client.recv().decode('utf-8')
        msgs = msg[:-1].split('\n')
        msg = msgs[-1]
        comps = msg.split(' ')
        if comps[0] == 'AIn':
            # print(comps)
            # print(comps[3])
            scaled = int(comps[3]) / 1023 * 2.5
            if scaled < 0:
                scaled = 0
            elif scaled > 2.5:
                scaled = 2.5
            scaled = round(scaled * 65535 / 2.5)
            # print(scaled)
            client.send('AOut 0 O0 {}\n'.format(scaled).encode('utf-8'))

    client.send(b'Reset 0\n')
    client.send(b'CLOSE')
