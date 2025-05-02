import argparse
import struct
import sys
from scapy.utils import PcapWriter

P2P_DIRECTION = 1
PDU_NEXT_TYPE = b"gsm_sim"

# Parse command-line arguments
parser = argparse.ArgumentParser(description="Convert binary UART data, exported from PulseView, to PCAP format.")
parser.add_argument("-i", "--input", help="Input file path. If not provided, reads from STDIN.")
parser.add_argument("-o", "--output", help="Output file path. If not provided, writes to STDOUT.")
args = parser.parse_args()

# Read input data
if args.input:
    with open(args.input, "rb") as f:
        data = f.read()
else:
    data = sys.stdin.buffer.read()

# Determine output
if args.output:
    output = open(args.output, "wb")
else:
    output = sys.stdout.buffer

LINKTYPE_WIRESHARK_UPPER_PDU = 252

pcap = PcapWriter(output, linktype=LINKTYPE_WIRESHARK_UPPER_PDU)
offset = 0

while offset + 8 < len(data):
    header = data[offset:offset+5]
    if len(header) < 5:
        break

    expected_length = header[4]
    header_len = 5
    response_len = 1
    status_len = 2
    total_length = header_len + response_len + expected_length + status_len

    if offset + total_length > len(data):
        break

    # Read all WITHOUT the response.
    packet = data[offset:offset + header_len]
    payload_offset = offset + header_len + response_len
    packet += data[payload_offset:payload_offset + expected_length + status_len]
    offset += total_length

    upper_pdu_header = b"\x00\x0c" + struct.pack(">H", len(PDU_NEXT_TYPE)) + PDU_NEXT_TYPE
    upper_pdu_header = upper_pdu_header + b"\x00\x23\x00\x04" + struct.pack(">I", P2P_DIRECTION)
    upper_pdu_header = upper_pdu_header + b"\x00\x00\x00\x00"
    full_packet = upper_pdu_header + packet
    pcap.write(full_packet)

pcap.close()
if args.output:
    output.close()
