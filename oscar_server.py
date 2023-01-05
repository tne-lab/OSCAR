import socket
import ctypes
import time
import os
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
    coms = ['COM8']
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

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            port = 9296
            s.bind(('127.0.0.1', port))
            s.listen()
            while True:
                conn, addr = s.accept()
                print('Connection Established: ' + str(addr))
                conn.setblocking(False)
                t = time.perf_counter()
                cps = 0
                with conn:
                    while True:
                        cps += 1
                        for i, sp in enumerate(sps):
                            nb = sp.in_waiting
                            if nb > 0:
                                msg = sp.read(nb)
                                for b in msg:
                                    commands[i] = commands[i] + b.to_bytes(1, 'little')
                                    data = int.from_bytes(commands[i], 'little')
                                    cid = data & 0x7
                                    if cid == 0:
                                        address = data >> 3 & 0x7
                                        input_id = str(address)
                                        msg = 'DIn {} {}\n'.format(i, input_id)
                                        print(msg)
                                        conn.send(msg.encode('utf-8'))
                                        commands[i] = bytes()
                                    elif cid == 1:
                                        if len(commands[i]) == 2:
                                            data2 = int.from_bytes(commands[i], 'little')
                                            command = AnalogIn()
                                            command.data = data2
                                            input_id = "A" + str(command.b.address)
                                            msg = 'AIn {} {} {}\n'.format(i, input_id, command.b.value)
                                            conn.send(msg.encode('utf-8'))
                                            commands[i] = bytes()
                                    elif cid == 2:
                                        address = data >> 3 & 0x3
                                        input_id = "A" + str(address)
                                        msg = 'GPIOIn {} {}\n'.format(i, input_id)
                                        conn.send(msg.encode('utf-8'))
                                        commands[i] = bytes()
                        try:
                            msg = conn.recv(4096).decode()
                            if len(msg) == 0:
                                break
                            msgs = msg[:-1].split('\n')
                        except BlockingIOError:
                            msgs = []
                        except ConnectionResetError:
                            break
                        for msg in msgs:
                            comps = msg.split(' ')
                            if comps[0] == 'DOut':
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
                        time.sleep(0)
                for sp in sps:
                    reset = Reset()
                    reset.b.command = 4
                    sp.write(reset.data.to_bytes(1, 'little'))
                time.sleep(0)
