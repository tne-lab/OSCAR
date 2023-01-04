import socket
import time

high_load = False
test_dur = 40
client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
client.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
client.connect(('localhost', 9296))
client.setblocking(False)

if high_load:
    client.send(b'RegGPIO 0 A0 3\nRegGPIO 0 A1 3\n')

t = time.perf_counter()

while time.perf_counter() - t < test_dur:
    try:
        msg = client.recv(4096).decode()
        msgs = msg[:-1].split('\n')
    except BlockingIOError:
        msgs = []
    for msg in msgs:
        comps = msg.split(' ')
        if comps[0] == 'DIn':
            client.send(b'DOut 0 0\n')

client.send(b'Reset 0\n')
