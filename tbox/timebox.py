"""Provides class TimeBox that encapsulates the TimeBox communication."""

import select
from bluetooth import BluetoothSocket, RFCOMM
from .messages import TimeBoxMessages
from .divoom_image import DivoomImage
import datetime
import time
import os
from PIL import ImageColor
from PIL import ImageFont

class TimeBox:
    """Class TimeBox encapsulates the TimeBox communication."""

    DEFAULTHOST = "11:75:58:48:2F:DA"

    COMMANDS = {
        "switch radio": 0x05,
        "set volume": 0x08,
        "get volume": 0x09,
        "set mute": 0x0a,
        "get mute": 0x0b,
        "set date time": 0x18,
        "set image": 0x44,
        "set view": 0x45,
        "set animation frame": 0x49,
        "get temperature": 0x59,
        "get radio frequency": 0x60,
        "set radio frequency": 0x61
    }

    socket = None
    messages = None
    message_buf = []

    def __init__(self):
        self.messages = TimeBoxMessages()
        self.divoomImage = DivoomImage()

    def connect(self, host=None, port=4):
        """Open a connection to the TimeBox."""
        # Create the client socket
        if host is None:
            host = self.DEFAULTHOST
        #print("connecting to %s at %s" % (self.host, self.port))
        self.socket = BluetoothSocket(RFCOMM)
        self.socket.connect((host, port))
        self.socket.setblocking(0)

    def close(self):
        """Closes the connection to the TimeBox."""
        self.socket.close()

    def receive(self, num_bytes=1024):
        """Receive n bytes of data from the TimeBox and put it in the input buffer.
        Returns the number of bytes received."""
        ready = select.select([self.socket], [], [], 0.1)
        if ready[0]:
            data = self.socket.recv(num_bytes)
            self.message_buf += data
            return len(data)
        else:
            return 0

    def send_raw(self, data):
        """Send raw data to the TimeBox."""
        return self.socket.send(data)

    def send_payload(self, payload):
        """Send raw payload to the TimeBox. (Will be escaped, checksumed and
        messaged between 0x01 and 0x02."""
        msg = self.messages.make_message(payload)
        return self.socket.send(bytes(msg))

    def set_time(self, time=None):
      if not time:
        time=datetime.datetime.now()
      args = []
      args.append(int(str(time.year)[2:]))
      args.append(int(str(time.year)[0:2]))
      args.append(int(time.month))
      args.append(int(time.day))
      args.append(int(time.hour))
      args.append(int(time.minute))
      args.append(int(time.second))
      args.append(0)
      self.send_command("set date time", args)

    def send_command(self, command, args=None):
        """Send command with optional arguments"""
        if args is None:
            args = []
        if isinstance(command, str):
            command = self.COMMANDS[command]
        length = len(args)+3
        length_lsb = length & 0xff
        length_msb = length >> 8
        payload = [length_lsb, length_msb, command] + args
        self.send_payload(payload)

    def decode(self, msg):
        """remove leading 1, trailing 2 and checksum and un-escape"""
        return self.messages.decode(msg)

    def has_message(self):
        """Check if there is a complete message *or leading garbage data* in the input buffer."""
        if len(self.message_buf) == 0:
            return False
        if self.message_buf[0] != 0x01:
            return True
        #endmarks = [x for x in self.message_buf if x == 0x02]
        #return  len(endmarks) > 0
        return 0x02 in self.message_buf

    def buffer_starts_with_garbage(self):
        """Check if the input buffer starts with data other than a message."""
        if len(self.message_buf) == 0:
            return False
        return self.message_buf[0] != 0x01

    def remove_garbage(self):
        """Remove data from the input buffer that is not the start of a message."""
        pos = self.message_buf.index(0x01) if 0x01 in self.message_buf else len(self.message_buf)
        res = self.message_buf[0:pos]
        self.message_buf = self.message_buf[pos:]
        return res

    def remove_message(self):
        """Remove a message from the input buffer and return it. Assumes it has been checked that
        there is a complete message without leading garbage data"""
        if not 0x02 in self.message_buf:
            raise Exception('There is no message')
        pos = self.message_buf.index(0x02) + 1
        res = self.message_buf[0:pos]
        self.message_buf = self.message_buf[pos:]
        return res

    def drop_message_buffer(self):
        """Drop all dat currently in the message buffer,"""
        self.message_buf = []

    def set_static_image(self, image):
        """Set the image on the TimeBox"""
        msg = self.messages.static_image_message(image)
        self.socket.send(bytes(msg))

    def set_dynamic_images(self, images, frame_delay=1):
        """Set the image on the TimeBox"""
        fnum = 0
        for img in images:
            msg = self.messages.dynamic_image_message(img, fnum, frame_delay)
            fnum = fnum + 1
            self.socket.send(bytes(msg))

    def show_temperature(self, color=None):
        """Show temperature on the TimeBox in Celsius"""
        args = [0x01, 0x00]
        if not color is None:
            args += color
        self.send_command("set view", args)

    def show_clock(self, color=None):
        """Show clock on the TimeBox in the color"""
        args = [0x00, 0x01]
        if not color is None:
            args += color
        self.send_command("set view", args)

    def disable_display(self):
        """Disable Display on the TimeBox"""
        args = [0x02, 0x01]
        self.send_command("set view", args)

    def show_string(self, texts, font=None):
        """
          Display text, call is blocking
        """
        if (type(texts) is not list) or (len(texts)==0) or (type(texts[0]) is not tuple):
            raise Exception("a list of tuple is expected")
        img_result = self.divoomImage.create_default_image((0,0))
        for txt, color in texts:
            img_result = self.divoomImage.draw_text_to_image(txt, color, empty_start=False, empty_end=False, font=font)
        self.set_static_image(self.divoomImage.build_img(img_result))

    def show_text(self, txt, speed=20, font=None):
        """
          Display text & scroll, call is blocking
        """
        if (type(txt) is not list) or (len(txt)==0) or (type(txt[0]) is not tuple):
            raise Exception("a list of tuple is expected")
        im = self.divoomImage.draw_multiple_to_image(txt, font)
        slices = self.divoomImage.horizontal_slices(im)
        for i, s in enumerate(slices):
            #s.save("./debug/%s.bmp"%i)
            self.set_static_image(self.divoomImage.build_img(s))
            time.sleep(1.0/speed)

    def show_text2(self, txt, font=None):
        """
        Use dynamic_image_message to display scolling text
        Cannot go faster than 1fps
        """
        if (type(txt) is not list) or (len(txt)==0) or (type(txt[0]) is not tuple):
            raise Exception("a list of tuple is expected")
        imgs = []
        im = self.divoomImage.draw_multiple_to_image(txt, font)
        slices = self.divoomImage.horizontal_slices(im)
        for i, s in enumerate(slices):
            # s.save("./debug/%s.bmp"%i)
            imgs.append(self.divoomImage.build_img(s))
        print (len(imgs))
        self.set_dynamic_images(imgs)

    def show_static_image(self, path):
      self.set_static_image(self.divoomImage.load_image(path))

    def show_animated_image(self, path, frame_delay=1):
      self.set_dynamic_images(self.divoomImage.load_gif_frames(path), frame_delay)

    def clear_input_buffer(self):
        """Read all input from TimeBox and remove from buffer. """
        while self.receive() > 0:
            self.drop_message_buffer()

    def clear_input_buffer_quick(self):
        """Quickly read most input from TimeBox and remove from buffer. """
        while self.receive(512) == 512:
            self.drop_message_buffer()
