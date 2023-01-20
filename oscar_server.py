import ctypes
import threading
import os
import time

import select
import zmq
from contextlib import ExitStack

import psutil as psutil
import serial as serial
from pySerialTransfer import pySerialTransfer as txfer


class AnalogOutBits(ctypes.LittleEndianStructure):
    _fields_ = [
        ("command", ctypes.c_uint32, 3),
        ("address", ctypes.c_uint32, 2),
        ("value", ctypes.c_uint32, 16)
    ]


class AnalogOut(ctypes.Union):
    _fields_ = [("b", AnalogOutBits),
                ("data", ctypes.c_uint32)]


class AnalogInBits(ctypes.LittleEndianStructure):
    _fields_ = [
        ("command", ctypes.c_uint16, 3),
        ("address", ctypes.c_uint16, 2),
        ("value", ctypes.c_uint16, 10)
    ]


class AnalogIn(ctypes.Union):
    _fields_ = [("b", AnalogInBits),
                ("data", ctypes.c_uint16)]


class DigitalOutBits(ctypes.LittleEndianStructure):
    _fields_ = [
        ("command", ctypes.c_uint8, 3),
        ("address", ctypes.c_uint8, 5)
    ]


class DigitalOut(ctypes.Union):
    _fields_ = [("b", DigitalOutBits),
                ("data", ctypes.c_uint8)]


class GPIOOutBits(ctypes.LittleEndianStructure):
    _fields_ = [
        ("command", ctypes.c_uint8, 3),
        ("address", ctypes.c_uint8, 2)
    ]


class GPIOOut(ctypes.Union):
    _fields_ = [("b", GPIOOutBits),
                ("data", ctypes.c_uint8)]


class RegisterGPIOBits(ctypes.LittleEndianStructure):
    _fields_ = [
        ("command", ctypes.c_uint8, 3),
        ("address", ctypes.c_uint8, 2),
        ("type", ctypes.c_uint8, 2)
    ]


class RegisterGPIO(ctypes.Union):
    _fields_ = [("b", RegisterGPIOBits),
                ("data", ctypes.c_uint8)]


class ResetBits(ctypes.LittleEndianStructure):
    _fields_ = [
        ("command", ctypes.c_uint8, 3)
    ]


class Reset(ctypes.Union):
    _fields_ = [("b", RegisterGPIOBits),
                ("data", ctypes.c_uint8)]


class AInParamsBits(ctypes.LittleEndianStructure):
    _fields_ = [
        ("command", ctypes.c_uint8, 3),
        ("fs", ctypes.c_uint8, 2),
        ("ref", ctypes.c_uint8, 1)
    ]


class AInParams(ctypes.Union):
    _fields_ = [("b", AInParamsBits),
                ("data", ctypes.c_uint8)]


class OSCARContextManager(ExitStack):
    
    def __init__(self, ports):
        super(OSCARContextManager, self).__init__()
        self.ports = ports

    def __exit__(self, exc_type, exc_value, exc_tb):
        for spi in self.ports:
            r = Reset()
            r.b.command = 4
            spi.write(r.data.to_bytes(1, 'little'))
        super(OSCARContextManager, self).__exit__(exc_type, exc_value, exc_tb)


def serial_thread(serial_index):
    link = links[serial_index]
    cur_command = bytes()
    count = 0
    t = time.perf_counter()
    while True:
        # select.select([link.connection], [], [])
        avail = link.available()
        if write_times[serial_index] is not None and time.perf_counter() - write_times[serial_index] > 0.005:
            write_times[serial_index] = time.perf_counter()
            for i, b in enumerate(write_buffers[serial_index]):
                link.tx_obj(b, start_pos=i, val_type_override='B')
            write_events[serial_index].wait()
            write_events[serial_index].clear()
            link.send(write_indices[serial_index])
            write_events[serial_index].set()
        if avail:
            msg = bytes(link.rx_obj(list, list_format='B', obj_byte_size=avail))
            if msg[0] == 0x37:
                # print(time.perf_counter() - write_times[serial_index])
                write_times[serial_index] = None
                write_buffers[serial_index] = write_buffers[write_indices[serial_index]:]
                write_indices[serial_index] = 0
            elif msg[0] == 0x3F:
                print('malformed')
                write_times[serial_index] = time.perf_counter()
                write_indices[serial_index] = len(write_buffers[serial_index])
                for i, b in enumerate(write_buffers[serial_index]):
                    link.tx_obj(b, start_pos=i, val_type_override='B')
                write_events[serial_index].wait()
                write_events[serial_index].clear()
                link.send(write_indices[serial_index])
                write_events[serial_index].set()
            else:
                write_events[serial_index].wait()
                write_events[serial_index].clear()
                ack = link.tx_obj('7')
                link.send(ack)
                write_events[serial_index].set()
                for b in msg:
                    cur_command = cur_command + b.to_bytes(1, 'little')
                    data = int.from_bytes(cur_command, 'little')
                    cid = data & 0x7
                    out = ""
                    if cid == 0:
                        address = data >> 3 & 0x7
                        input_id = str(address)
                        out = 'DIn {} {}\n'.format(serial_index, input_id)
                        cur_command = bytes()
                    elif cid == 1:
                        if len(cur_command) == 2:
                            data2 = int.from_bytes(cur_command, 'little')
                            command = AnalogIn()
                            command.data = data2
                            input_id = "A" + str(command.b.address)
                            out = 'AIn {} {} {}\n'.format(serial_index, input_id, command.b.value)
                            cur_command = bytes()
                    elif cid == 2:
                        address = data >> 3 & 0x3
                        input_id = "A" + str(address)
                        out = 'GPIOIn {} {}\n'.format(serial_index, input_id)
                        cur_command = bytes()
                    if len(out) > 0:
                        count += 1
                        # print(out)
                        failed = []
                        for identity in clients:
                            try:
                                server.send_multipart([identity, out.encode('utf-8')])
                            except zmq.ZMQError as e:
                                print(e)
                                if e.errno == zmq.EHOSTUNREACH:
                                    failed.append(identity)
                        for f in failed:
                            clients.remove(f)
                            print('Connection lost with identity ' + str(f))
                        if len(clients) == 0:
                            for i in range(len(write_buffers)):
                                reset = Reset()
                                reset.b.command = 4
                                write_buffers[i] += reset.data.to_bytes(1, 'little')
        elif link.status <= 0:
            write_events[serial_index].wait()
            write_events[serial_index].clear()
            nack = link.tx_obj('?')
            link.send(nack)
            write_events[serial_index].set()
        if time.perf_counter() - t > 1:
            print(count)
            count = 0
            t = time.perf_counter()
        time.sleep(0)


if __name__ == '__main__':
    p = psutil.Process(os.getpid())
    p.nice(psutil.HIGH_PRIORITY_CLASS)
    coms = ['COM11']
    sps = []
    links = []
    write_indices = []
    write_buffers = []
    write_times = []
    write_events = []
    with OSCARContextManager(sps) as stack:
        threads = []
        for i, com in enumerate(coms):
            links.append(txfer.SerialTransfer(com, baud=1000000, restrict_ports=False, debug=False, timeout=0.005))
            links[i].connection.dsrdtr = False
            links[i].connection.rtscts = False
            links[i].open()
            write_indices.append(0)
            write_buffers.append(bytearray())
            write_times.append(None)
            write_events.append(threading.Event())
            write_events[i].set()
            # sps.append(serial.Serial(port=com, baudrate=500000, write_timeout=None, timeout=None))
            # stack.enter_context(sps[i].__enter__())
            # sps[i].dtr = True
            # sps[i].reset_input_buffer()
            # sps[i].reset_output_buffer()
            t = threading.Thread(target=serial_thread, args=[i])
            t.start()
        context = zmq.Context()
        server = context.socket(zmq.ROUTER)
        server.setsockopt(zmq.ROUTER_MANDATORY, 1)
        server.setsockopt(zmq.RCVHWM, 0)
        server.setsockopt(zmq.SNDHWM, 0)
        server.bind("tcp://127.0.0.1:9296")
        clients = []
        while True:
            try:
                identity, request = server.recv_multipart()
                while True:
                    if identity not in clients:
                        clients.append(identity)
                        server.send_multipart([identity, b"ACK"])
                        print('New connection with identity ' + str(identity))
                    elif request == b"CLOSE":
                        clients.remove(identity)
                        print('Connection closed with identity ' + str(identity))
                        if len(clients) == 0:
                            for i in range(len(write_buffers)):
                                reset = Reset()
                                reset.b.command = 4
                                write_buffers[i] += reset.data.to_bytes(1, 'little')
                    else:
                        msgs = request.decode('utf-8')[:-1].split('\n')
                        print(msgs)
                        for msg in msgs:
                            comps = msg.split(' ')
                            if comps[0] == 'DOut':
                                command = DigitalOut()
                                command.b.command = 0
                                command.b.address = int(comps[2])
                                write_buffers[int(comps[1])].extend(command.data.to_bytes(1, 'little'))
                                # sps[int(comps[1])].write(command.data.to_bytes(1, 'little'))
                            elif comps[0] == 'GPIOOut':
                                command = GPIOOut()
                                command.b.command = 2
                                command.b.address = int(comps[2][1])
                                write_buffers[int(comps[1])].extend(command.data.to_bytes(1, 'little'))
                                # sps[int(comps[1])].write(command.data.to_bytes(1, 'little'))
                            elif comps[0] == 'AOut':
                                command = AnalogOut()
                                command.b.command = 1
                                command.b.address = int(comps[2][1])
                                scaled = int(comps[3])
                                command.b.value = scaled
                                write_buffers[int(comps[1])].extend(command.data.to_bytes(3, 'little'))
                                # sps[int(comps[1])].write(command.data.to_bytes(3, 'little'))
                            elif comps[0] == 'RegGPIO':
                                command = RegisterGPIO()
                                command.b.command = 3
                                command.b.address = int(comps[2][1])
                                command.b.type = int(comps[3])
                                write_buffers[int(comps[1])].extend(command.data.to_bytes(1, 'little'))
                                # sps[int(comps[1])].write(command.data.to_bytes(1, 'little'))
                            elif comps[0] == 'Reset':
                                command = Reset()
                                command.b.command = 4
                                write_buffers[int(comps[1])].extend(command.data.to_bytes(1, 'little'))
                                # sps[int(comps[1])].write(command.data.to_bytes(1, 'little'))
                            elif comps[0] == 'AInParams':
                                command = AInParams()
                                command.b.command = 5
                                command.b.fs = int(comps[2])
                                command.b.ref = int(comps[3])
                                write_buffers[int(comps[1])].extend(command.data.to_bytes(1, 'little'))
                                # sps[int(comps[1])].write(command.data.to_bytes(1, 'little'))
                    identity, request = server.recv_multipart(flags=zmq.NOBLOCK)
            except zmq.ZMQError:
                pass
            for i in range(len(write_buffers)):
                if len(write_buffers[i]) > 0 and write_indices[i] == 0:
                    write_indices[i] = len(write_buffers[i])
                    print(write_indices[i])
                    for j, b in enumerate(write_buffers[i]):
                        links[i].tx_obj(b, start_pos=j, val_type_override='B')
                    write_events[i].wait()
                    write_events[i].clear()
                    links[i].send(write_indices[i])
                    write_events[i].set()
                    write_times[i] = time.perf_counter()
            time.sleep(0)
