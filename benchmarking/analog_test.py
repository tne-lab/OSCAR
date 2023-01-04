import socket
import time

test_dur = 40
client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
client.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
client.connect(('localhost', 9296))
client.setblocking(False)

client.send(b'AInParams 0 3 1\nRegGPIO 0 A0 3\n')

t = time.perf_counter()

while time.perf_counter() - t < test_dur:
    try:
        msg = client.recv(4096).decode()
        msgs = msg[:-1].split('\n')
        msg = msgs[-1]
        comps = msg.split(' ')
        if comps[0] == 'AIn':
            # print(comps[3])
            scaled = int(comps[3]) / 1023 * 2.5
            if scaled < 0:
                scaled = 0
            elif scaled > 2.5:
                scaled = 2.5
            scaled = round(scaled * 65535 / 2.5)
            # print(scaled)
            client.send('AOut 0 O0 {}\n'.format(scaled).encode('utf-8'))
    except BlockingIOError:
        msgs = []

client.send(b'Reset 0\n')
