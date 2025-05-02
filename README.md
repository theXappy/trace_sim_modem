## 1. Background: What We’re Trying to Capture

When a modem communicates with a SIM card, the two exchange APDUs (Application Protocol Data Units) over a serial interface based on ISO 7816.  
These APDUs include commands like reading files, authenticating with the network, and selecting applications on the SIM.

Sniffing this communication can be useful for debugging, reverse engineering, or simply understanding what a modem is doing under the hood. However, capturing this data isn't as straightforward as tapping into a normal UART, because:
- The communication happens at a relatively high baud rate (often auto-negotiated).
- The protocol starts with a cold reset and an Answer To Reset (ATR), which isn't an APDU but still part of the handshake.
- There's no standard connector for monitoring this traffic — you need to physically tap into the electrical lines between the modem and SIM.
- The interface is **half-duplex**, with both the modem and the SIM sharing the same I/O line. Unlike typical UART setups (e.g., PC ↔ device), we're capturing both directions of traffic on the same wire, and must distinguish between them passively.

MY goal in this guide is to sniff these APDUs in transit, decode them, and view them in a structured way (e.g., in Wireshark) for further analysis.

We'll walk through a complete workflow: from physically accessing the SIM communication lines, to capturing and decoding the data stream, all the way to viewing it in a user-friendly format.

## 2. Hardware Setup: Tapping the SIM Lines

To capture the communication between a modem and a SIM card, we need physical access to the electrical lines connecting them.  
Most modems use a standard ISO 7816 interface, which includes several pins, but we're mainly interested in just two:

- **I/O** – **The main bidirectional data line we want to sniff**
- **GND** – Common ground (required for signal reference)

Here's a diagram:  
<img src="https://github.com/user-attachments/assets/71cb3c30-c4e9-4b23-8764-5f2ccddc96a7" width="400"/>  

Luckily, both are easy to spot:  
* GND is the non-recntangular one which is connected to the middle area between the ther pads.  
* I/O (or "Data") is the one towards the "missing" corner of the card.

What you need:
- A modem with accesible pins on its sim card slot. I'm using a cheap [3G USB modem](https://www.amazon.ae/7-2Mbps-Wireless-Network-Adapter-Digital/dp/B0C59MHKHJ). 
- Test clips or probing pins (for connecting to the I/O and GND lines). I used [these ones](https://www.aliexpress.com/item/1005006025817781.html?spm=a2g0o.order_list.order_list_main.22.520a1802y1kAGI) but they require extra cables and soldering. You can find pre-soldered ones.
- A logic analyzer (e.g., Saleae Logic, or a cheaper fx2lafw-compatible clone. [Here's one from AliExpress](https://www.aliexpress.com/item/1005007349261117.html?spm=a2g0o.order_list.order_list_main.29.520a1802y1kAGI))
- (Optional) A smart card reader. Would help with reading ATR but you can work without it.

### Wiring 

If you're lucky, your board will have 6 visible pins connecting the SIM slot to the board.  
Mine had 6 just under the "entrace" so it was easy to see which of the 3 at the front (which include both GND and I/O) went where.  
Here's a picture of my board. (Note the pins are "mirrored" from the SIM diagram as sims go upside-down into the slot)  
![hsupa_pinout](https://github.com/user-attachments/assets/d8adb01e-3a39-4ab3-8fc2-8332ed3bb231)

Before making any connection, you might need to insert your SIM right now as the clips might not allow you to do it when connected.
With both Analzyer and the modem disconnected from a power source, connect both GND pins on both devices.  
Then connect the modem's I/O pin to the analyzer's first channel. On my device it was CH1.

Once you’ve made these connections, you're almost ready to capture data with your logic analyzer.  
<img src="https://github.com/user-attachments/assets/0735ef4f-adf1-4dcf-8f73-54ff9c49a022" height="300"/>
<img src="https://github.com/user-attachments/assets/cebf4528-7784-46b8-ab3d-b7015351cde2" height="300"/>  


## 3. Using `pysim-shell` as a Reference Tool

Before sniffing the raw SIM interface, it's helpful to generate known, predictable traffic. [`pysim-shell`](https://github.com/osmocom/pysim) is a CLI tool that allows you to invoke high-level commands to a SIM card — either through a smart card reader or via a modem that supports [AT commands](https://en.wikipedia.org/wiki/Hayes_AT_command_set).

The second option is especially useful for us: by controlling the modem, we can create traffic at predictable times and know exactly what byte patterns to expect.

Many USB modems (including those commonly found on AliExpress) expose a one or more USB serial devices.  
![{4E5E6DF5-A06E-4833-952A-60B47A7F1F90}](https://github.com/user-attachments/assets/668e3501-f854-4ae4-a0ba-8a5f93b4e28c)  
One of them is usually an AT commands interface.  
To find the correct one:  
- Connect to each exposed serial port using PuTTY (or similar).
- Type `AT` and press Enter. If you receive `OK`, you’ve found the right interface.

> Tip: the modems I've seen use 9600 baud (PuTTY’s default), but if you don’t get a response, try common alternatives like 19200 or 115200.

### Example Commands

By default, pysim-shell assumes a smartcard reader exists and tried to use it.  
If we want to direct it to a serial port of a mode, we need to specify the port & baud rate:

```bash
pySim-shell.py --modem-device COM11 --modem-baud 9600
```

Then you'd be greated with the emulated shell. This is not a full linux bash, it supports a very specific set of commands. [Read about them here](https://downloads.osmocom.org/docs/pysim/master/html/shell.html#pysim-commands).
We'd only need 2 to achieve out goal: `select` and `read_binary`.

1)
`select` is used to traverse the "file system" of the card. The root dir is called `MF` and we're trying to get to `MF/DF.GSM/EF.IMSI`.  
Use this command to get there:
```
pySIM-shell (00:MF)> select DF.GSM/EF.IMSI
```
When the command succeeds, you get this output (This is NOT the content of the file):  
<img src="https://github.com/user-attachments/assets/f39b565a-fc8a-409b-b6ea-763067bedc6a" height="200"/>  

Next use `read_binary` to get the content of the selected "file". Expected output (I censored my card's IMSI):  
```
pySIM-shell (00:MF/DF.GSM/EF.IMSI)> read_binary
08X9XXXXXXXXXXXXXX
```
This will be the pattern we'd look for in raw traffic.  
I suggest using the EF.IMSI since its content is distinguishable (not many repetations/zeroes, not too short).  
Having said that, our strategy should work for other large enough "files". 

## 4. Capturing with PulseView

With the SIM I/O line tapped and the logic analyzer connected, we can now capture the actual communication using [PulseView](https://sigrok.org/wiki/PulseView), the GUI frontend for the sigrok suite.

PulseView lets you visualize digital signals and apply protocol decoders — in our case, we’ll be using the UART decoder to make sense of the raw I/O line.

To setup your analyzer & PulseView for the first time follow [this YouTube tutorial](https://www.youtube.com/watch?v=3IA_6MwInVg).

### Basic Capture Workflow

0. Make sure both Analzyer and Modem are connected before capturing. We *don't* want to capture the device start-up this time.  
1. **Launch PulseView** and select your logic analyzer device.
2. Set the sample rate — Usually we aim for **at least 4x the expected baud rate**. Since I didn't know the right one, I used the highest available (25 MHz).
3. Set the sampling length - I used 500 M, which was more than enough to trigger the EF.IMSI read several times.
4. Start capturing.
5. Using pysim-shell, send the `read_binary` command.

Once captured, the waveform will include bursts of serial data — but there’s a catch: **we don’t know the exact baud rate yet.**  
It should look something like this:
![image](https://github.com/user-attachments/assets/16dc45f3-4652-4365-a770-2bb61e2efc70)

## 5. Analyzing as UART

While this SIM interface looks like UART at a glance, it's **not officially defined as "just UART"**.  
It's based on the ISO 7816 standard — specifically, ISO 7816-3 for the electrical interface and ISO 7816-4 for the APDU-level protocol.

In ISO 7816-3, the electrical signaling is asynchronous, byte-oriented, and half-duplex — all characteristics that **make it possible to decode using a UART decoder**.

For our purposes — sniffing and interpreting APDUs exchanged between the modem and SIM — **PulseView's UART decoder works well enough**, because:
- The electrical signal is compatible (1 start bit, 8 data bits, 1 stop bit)
- The data exchanged is byte-aligned
- We're not trying to *drive* the interface, only to **passively read** the traffic

Once you have a raw capture, the next step is to decode the UART protocol on top of the I/O line.  
But before you can decode anything, you need to know the correct UART settings — especially the **baud rate**.
Using the wrong rate gives us undecodable garbage.

---

### 5.1 (Side Quest) ATR Capture

While working on this research I encountered this [blog post by Jason Gin](https://ripitapart.com/2019/12/21/recovering-the-sim-card-pin-from-the-zte-wf721-cellular-home-phone/).  
Jason was sniffing the I/O connection between his router's modem and his sim card to figure out which PIN did the router set on the card.  
Sounds overlapping with my effort. He too had to figure out the baud rate of the interface and suggested the formal way: ATR.

After a SIM reset, the card sends an **[ATR (Answer To Reset)](https://en.wikipedia.org/wiki/Answer_to_reset#:~:text=An%20Answer%20To%20Reset%20(ATR,the%20card's%20nature%20and%20state.)** — a sequence of bytes that defines the supported protocols, voltages, and timings. You’ll almost always see this in the first burst after powering up the SIM.

To get the ATR, I had to use different tools and software:
I was able to capture the ATR using a smartcard reader Wireshark + [USBPcap](https://desowin.org/usbpcap/).  
I then decoded the **ATR using this tool** that Jason suggested.  
It seemed very promising, even calculating for me the possible baud rate values:
```
Fi=512, Di=8, 64 cycles/ETU (62500 bits/s at 4.00 MHz, 78125 bits/s for fMax=5 MHz)
```

It seemed that I need to figure out the frequence to know which of the two baud rates to use (I'm assuming it's boolean and not a range. I don't know much about clock frequencies).  
Jason mentioned his used the 4.00 MHz bause rate so I used mine (62.5K) and it worked!  

What to do if you don't have a smartcard reader? You'd need to bruteforce this thing. 
Luckily the PulseView decoder is pretty responsive so just play around with the values until bytes start lining up.  
Read the next section to see how the reference for pysim is used to confirm the baud rate and use it as you "validation" check for each value you try.

---

### 5.2 Confirming the Baud Rate with pysim as Reference

After setting a UART decoder in PulseView and baud rate of 62.5K, I zoomed in to the 2nd burst.  
I assumed the 1st would be the Modem's request for EF.IMSI's content (relaying my PC's request) and the 2nd would be the content itself.
Side by side, it's easy to find the EF.IMSI content seen in pysim-shell within the data (censored again, but I marked matching bytes with the same colors):  
![image](https://github.com/user-attachments/assets/aabca203-a34d-437b-887d-2081a515b8e1)

Not sure about the 0xB0 byte before but I do know that SIM card operations end with 2-byte result code.  
This one shows `90 00` which means "Normal ending" (success).  
For me that's is the final nail in the coffin and now I know I have the right settings.  
If want to go the extra mile, you can bruteforce the "parity bit".  
Mine was "odd", but when set to "none"/"even" the data bytes still came out fine so it doesn't affect decoding.  

## 6. From PulseView to Wireshark

Once you’ve captured and decoded the UART traffic using PulseView, the next step is to export it and convert it into a format that Wireshark can understand.

### Exporting with `sigrok-cli`

You can use the following command to extract a clean stream of UART bytes from your `.sr` capture file:

```bash
sigrok-cli -i input.sr -P uart:rx=D0:baudrate=62500 -B uart=rx > output_uart.bin
```
Adjust `D0` according to the channel you've seen in PulseView. 

Note: The `-B uart=rx` part is important — without it, `sigrok-cli` will output both RX and TX streams.
Since both are connected to the same logic analyzer pin, you’ll end up with duplicated data unless you filter for just rx.

The output will be a raw binary stream (output.bin) of decoded UART bytes — this represents the APDUs exchanged over the SIM interface.

---
### Converting to PCAP for Wireshark
To view these APDUs in Wireshark, we need to wrap them in a proper pcap file and cause the `gsm_sim` dissector (parser) to be called.  
We'll achieve that using a special link-layer type called Wireshark Upper PDU (type 252), it's a meta-dissector that allows passing payload to arbitrary dissectors.

You can use the provided Python script in this repo: `
```
uart_bin_to_gsmsim_pcap.py -i output_uart.bin -o output_gsm_sim.pcap
```

This script:
* Wraps each APDU packet with the required "Upper PDU" header
* Uses shallow parsing to find APDU packet boundaries (based on length byte at offset 0x04)
* Writes the result as a .pcap that Wireshark can open and dissect

After running the script, open the resulting .pcap in Wireshark and you'd see something like this:
![image](https://github.com/user-attachments/assets/04e9e01a-84e1-4599-890d-758d68cbc368)

Now you can trace back what the modem and SIM exchanged — down to each command and response — using a full-featured network protocol analyzer.
Note that our little exchange with `pysim` ended up as 3 "commands":  
`select` -> `get response` (used because the `select` response were too large, I think) -> `read binary`

---

## Wrap Up

Sniffing SIM APDUs may seem obscure, but with the right tools and a bit of protocol knowledge, it’s surprisingly accessible.  
By tapping the SIM I/O line, capturing with PulseView, decoding as UART, and converting the output for Wireshark, you gain full visibility into the low-level dialog between a modem and a SIM card.  
Good Luck :)
