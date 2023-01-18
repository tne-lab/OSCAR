import ctypes
import threading
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

def serial_thread(sp):
    cur_command = bytes()
    while True:
        if sp.in_waiting > 0:
            msg = sp.read(sp.in_waiting)
        else:
            msg = sp.read(1)
        for b in msg:
            cur_command = cur_command + b.to_bytes(1, 'little')
            data = int.from_bytes(cur_command, 'little')
            cid = data & 0x7
            out = ""
            if cid == 0:
                address = data >> 3 & 0x7
                input_id = str(address)
                out = 'DIn {} {}\n'.format(i, input_id)
                print(out)
                cur_command = bytes()
            elif cid == 1:
                if len(commands[i]) == 2:
                    data2 = int.from_bytes(cur_command, 'little')
                    command = AnalogIn()
                    command.data = data2
                    input_id = "A" + str(command.b.address)
                    out = 'AIn {} {} {}\n'.format(i, input_id, command.b.value)
                    cur_command = bytes()
            elif cid == 2:
                address = data >> 3 & 0x3
                input_id = "A" + str(address)
                out = 'GPIOIn {} {}\n'.format(i, input_id)
                cur_command = bytes()
            if len(out) > 0:
                failed = []
                for identity in clients:
                    try:
                        server.send_multipart(identity, b"", out.encode('utf-8'))
                    except zmq.EHOSTUNREACH:
                        failed.append(identity)
                for f in failed:
                    clients.remove(f)


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
            t = threading.Thread(target=serial_thread, args=sps[i])
            t.run()

        context = zmq.Context()
        context.setsockopt(zmq.ROUTER_MANDATORY, 1)
        server = context.socket(zmq.ROUTER)
        server.bind("ipc://oscar.ipc")
        clients = []
        while True:
            identity, empty, request = server.recv_multipart()
            if identity not in clients:
                clients.append(identity)
                server.send_multipart([identity, b"", b"ACK"])
            elif request == b"CLOSE":
                clients.remove(identity)
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
