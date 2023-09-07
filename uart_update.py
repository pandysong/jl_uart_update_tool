import serial
import struct
import argparse
import time
from crcmod import mkCrcFun
import sys

CMD_UART_UPDATE_START = 0x1
CMD_UART_UPDATE_READ = 0x2
CMD_UART_UPDATE_END = 0x3
CMD_UART_UPDATE_UPDATE_LEN = 0x4
CMD_UART_JEEP_ALIVE = 0x5
CMD_UART_UPDATE_READY = 0x6

# CRC16/XMODEM


def crc16_xmodem(s):
    crc16 = mkCrcFun(0x11021, rev=False, initCrc=0x0000, xorOut=0x0000)
    return crc16(s)


def cmd_packet(cmd):
    # 0x06 CMD_UART_UPDATE_READY
    p = struct.pack("BBH", 0xAA, 0x55, len(cmd)) + cmd
    crc = crc16_xmodem(p)
    return p + struct.pack("H", crc)


def get_data(ser):

    for x in range(20):
        rx_data = ser.read(256)
        print("got {}".format(rx_data.hex()))
        if len(rx_data):
            return rx_data


def cutout_a_message(data):

    if len(data) < 4:
        return None, data
    magic1, magic2, length = struct.unpack("<BBH", data[:4])
    total_len = 4 + length + 2
    if magic1 == 0xaa and magic2 == 0x55:
        if len(data) < total_len:
            return None, data  # None means need more data
        else:
            crc_expected = struct.unpack("<H", data[total_len-2:total_len])[0]
            crc_calc = crc16_xmodem(data[:total_len-2])
            if crc_expected == crc_calc:
                return data[4:total_len-2], data[total_len:]
            else:
                print("crc not match {} vs {}".format(crc_expected, crc_calc))
                return None, data[total_len:]
    else:
        print("magic number not match {}{}, ignore {}".format(hex(magic1),
                                                              hex(magic2), hex(magic1)))
        return None, data[1:]


CMD_INDEX = 0

DEBUG = 0

UPGRADE_BAUDRATE = 1000000


def handle_messages_loop(ser, fw):

    data = b''
    while True:

        d = ser.read(64)
        if not d:
            continue
        else:
            if DEBUG:
                print("read data from serial port {}".format(d.hex()))

        data += d
        if len(data):
            msg, data = cutout_a_message(data)

            if not msg:
                continue

            if DEBUG:
                print("get msg {}".format(msg.hex()))

            cmd = msg[CMD_INDEX]

            if cmd == CMD_UART_UPDATE_START:
                print(">> CMD_UART_UPDATE_START")
                reply = cmd_packet(struct.pack("B", CMD_UART_UPDATE_START) +
                                   struct.pack("I", UPGRADE_BAUDRATE))
                ser.write(reply)
                ser.flush()
                print("wait for flush to take effect")
                time.sleep(0.02)
                print("flush buffer before changing baudrate")
                total_sent = 0
                print(">> >> set baudrate to {}".format(UPGRADE_BAUDRATE))
                ser.baudrate = UPGRADE_BAUDRATE
                print(">> >> change baudrate done")
            elif cmd == CMD_UART_UPDATE_READ:

                print(">> CMD_UART_UPDATE_READ")
                print(">> {}".format(msg.hex()))

                offset, length = struct.unpack("<II", msg[1:9])
                print("    offset {} length {}".format(offset, length))
                fw.seek(offset)
                fw_bytes = fw.read(length)
                if DEBUG:
                    print("read {} bytes from file in offset {} ".format(
                        len(fw_bytes), offset))
                # 1 byte msg, 8 bytes addr, len
                tx_msg = msg[:9]
                tx_msg = cmd_packet(tx_msg + fw_bytes)
                total_sent += len(fw_bytes)

                if DEBUG:
                    print("total_sent {}".format(total_sent))
                else:
                    print("<< CMD_UART_UPDATE_READ")
                ser.write(tx_msg)     # write command

            elif cmd == CMD_UART_UPDATE_END:
                print(">> CMD_UART_UPDATE_END, errcode {}".format(msg[1]))
                if msg[1] == 0:
                    print("Success")
                    break
                else:
                    print("Fail")

            elif cmd == CMD_UART_UPDATE_UPDATE_LEN:
                print(">> CMD_UART_UPDATE_UPDATE_LEN")
            elif cmd == CMD_UART_JEEP_ALIVE:
                print(">> CMD_UART_JEEP_ALIVE")
            elif cmd == CMD_UART_UPDATE_READY:
                print(">> CMD_UART_UPDATE_READY")
            else:
                print("-- Unknown cmd -- ", cmd)


def upgrade(serial_port, file_path):

    with serial.Serial(serial_port, 9600, timeout=0.005) as ser, open(file_path, 'rb') as fw:
        print(ser.name)         # check which port was really used

        print("send CMD_UART_UPDATE_READY")
        cmd = cmd_packet(struct.pack("B", CMD_UART_UPDATE_READY))
        ser.write(cmd)     # write command
        print("sent {}".format(cmd.hex()))

        handle_messages_loop(ser, fw)

        ser.close()
        fw.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="jieli UART SW upgrading tool")
    parser.add_argument(
        "serial_port", help="Serial port device path (e.g., /dev/ttyUSB0 or COM1)")
    parser.add_argument(
        "ufw_fw_file", help="the path to the fw or ufw file")

    args = parser.parse_args()
    upgrade(args.serial_port, args.ufw_fw_file)
