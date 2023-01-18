import socket
import ctypes
import time
import os
import zmq
from contextlib import ExitStack

import psutil as psutil
import serial as serial


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


if __name__ == '__main__':
    p = psutil.Process(os.getpid())
    p.nice(psutil.HIGH_PRIORITY_CLASS)
    coms = ['COM8', 'COM9']
    sps = []
    commands = []
    with OSCARContextManager(sps) as stack:
        for i, com in enumerate(coms):
            sps.append(serial.Serial(port=com, baudrate=500000, write_timeout=None, timeout=None, dsrdtr=True))
            stack.enter_context(sps[i].__enter__())
            sps[i].dtr = True
            sps[i].reset_input_buffer()
            sps[i].reset_output_buffer()
            commands.append(bytes())

        context = zmq.Context()
        server = context.socket(zmq.ROUTER)
        server.setsockopt(zmq.ROUTER_MANDATORY, 1)
        server.setsockopt(zmq.RCVHWM, 0)
        server.setsockopt(zmq.SNDHWM, 0)
        server.bind("tcp://127.0.0.1:9296")
        clients = []
        while True:
            try:
                while True:
                    identity, request = server.recv_multipart(flags=zmq.NOBLOCK)
                    if identity not in clients:
                        clients.append(identity)
                        server.send_multipart([identity, b"ACK"])
                        print('New connection with identity ' + str(identity))
                    elif request == b"CLOSE":
                        clients.remove(identity)
                        print('Connection closed with identity ' + str(identity))
                        if len(clients) == 0:
                            for sp in sps:
                                reset = Reset()
                                reset.b.command = 4
                                sp.write(reset.data.to_bytes(1, 'little'))
                    else:
                        msgs = request.decode('utf-8')[:-1].split('\n')
                        for msg in msgs:
                            comps = msg.split(' ')
                            if comps[0] == 'DOut':
                                print(msg)
                                command = DigitalOut()
                                command.b.command = 0
                                command.b.address = int(comps[2])
                                sps[int(comps[1])].write(command.data.to_bytes(1, 'little'))
                            elif comps[0] == 'GPIOOut':
                                command = GPIOOut()
                                command.b.command = 2
                                command.b.address = int(comps[2][1])
                                sps[int(comps[1])].write(command.data.to_bytes(1, 'little'))
                            elif comps[0] == 'AOut':
                                command = AnalogOut()
                                command.b.command = 1
                                command.b.address = int(comps[2][1])
                                scaled = int(comps[3])
                                command.b.value = scaled
                                sps[int(comps[1])].write(command.data.to_bytes(3, 'little'))
                            elif comps[0] == 'RegGPIO':
                                command = RegisterGPIO()
                                command.b.command = 3
                                command.b.address = int(comps[2][1])
                                command.b.type = int(comps[3])
                                sps[int(comps[1])].write(command.data.to_bytes(1, 'little'))
                            elif comps[0] == 'Reset':
                                command = Reset()
                                command.b.command = 4
                                sps[int(comps[1])].write(command.data.to_bytes(1, 'little'))
                            elif comps[0] == 'AInParams':
                                command = AInParams()
                                command.b.command = 5
                                command.b.fs = int(comps[2])
                                command.b.ref = int(comps[3])
                                sps[int(comps[1])].write(command.data.to_bytes(1, 'little'))
            except zmq.ZMQError:
                pass

            for i, sp in enumerate(sps):
                nb = sp.in_waiting
                if nb > 0:
                    msg = sp.read(nb)
                    for b in msg:
                        commands[i] = commands[i] + b.to_bytes(1, 'little')
                        data = int.from_bytes(commands[i], 'little')
                        cid = data & 0x7
                        out = ""
                        if cid == 0:
                            address = data >> 3 & 0x7
                            input_id = str(address)
                            out = 'DIn {} {}\n'.format(i, input_id)
                            print(out)
                            commands[i] = bytes()
                        elif cid == 1:
                            if len(commands[i]) == 2:
                                data2 = int.from_bytes(commands[i], 'little')
                                command = AnalogIn()
                                command.data = data2
                                input_id = "A" + str(command.b.address)
                                out = 'AIn {} {} {}\n'.format(i, input_id, command.b.value)
                                commands[i] = bytes()
                        elif cid == 2:
                            address = data >> 3 & 0x3
                            input_id = "A" + str(address)
                            out = 'GPIOIn {} {}\n'.format(i, input_id)
                            commands[i] = bytes()
                        if len(out) > 0:
                            failed = []
                            for identity in clients:
                                try:
                                    server.send_multipart([identity, out.encode('utf-8')])
                                except zmq.ZMQError as e:
                                    if e.errno == zmq.EHOSTUNREACH:
                                        failed.append(identity)
                            for f in failed:
                                clients.remove(f)
                                print('Connection lost with identity ' + str(f))
            time.sleep(0)
