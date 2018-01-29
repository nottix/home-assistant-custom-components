"""
TimeBox platform for notify component.

Connects to a Divoom TimeBox over bluetooth.

Simone Notargiacomo <notargiacomo.s@gmail.com>
"""
import json, os
import time
import logging
import voluptuous as vol

import homeassistant.helpers.config_validation as cv
from homeassistant.components.notify import (
    ATTR_DATA, PLATFORM_SCHEMA, BaseNotificationService)
from homeassistant.const import CONF_MAC

REQUIREMENTS = ['PyBluez==0.22',
                'colour==0.1.5',
                'pillow',
                'webcolors']

_LOGGER = logging.getLogger(__name__)

CONF_IMAGE_DIR = 'image_dir'
CONF_FONT_DIR = 'font_dir'

PARAM_TYPE = 'type'
PARAM_MODE = 'mode'
PARAM_COLOR = 'color'
PARAM_IMAGE = 'image'
PARAM_IMAGE_FILE = 'image-file'
PARAM_FILE_NAME = 'file-name'
PARAM_ANIM = 'anim'
PARAM_ANIM_FILE = 'anim-file'
PARAM_DELAY = 'delay'
PARAM_FONT = 'font'

VALID_MODES = {'off', 'clock', 'temp', 'image', 'image-file', 'animation', 'animation-file', 'text'}

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Required(CONF_MAC): cv.string,
    vol.Required(CONF_IMAGE_DIR): cv.string,
    vol.Required(CONF_FONT_DIR): cv.string
})

def get_service(hass, config, discovery_info=None):
    """Get the TimeBox notification service."""
    image_dir = hass.config.path(config[CONF_IMAGE_DIR])
    font_dir = hass.config.path(config[CONF_FONT_DIR])
    return TimeBoxNotificationService(config[CONF_MAC],
                                      image_dir, font_dir)

class TimeBoxNotificationService(BaseNotificationService):
    """Implement the notification service for TimeBox."""

    def __init__(self, mac, image_dir, font_dir):
        from PIL import ImageFont
        from .tbox.timebox import TimeBox
        self._mac = mac
        self._image_dir = image_dir
        self._font_dir = font_dir
        if not os.path.isdir(image_dir):
            _LOGGER.error("image_dir {0} does not exist, timebox will not work".format(image_dir))
        if not os.path.isdir(font_dir):
            _LOGGER.error("font_dir {0} does not exist, timebox will not work".format(font_dir))

        self._timebox = TimeBox(_LOGGER, host=mac)
        self._timebox.connect()
        # self._timebox.set_time()
        # color = [120, 0, 0]
        # self._timebox.show_clock(color=color)

    def display_anim_file(self, fn, frame_delay=1):
        self._timebox.show_animated_image(fn, frame_delay)

    def display_anim(self, image_data, frame_delay=1):
        self._timebox.set_dynamic_images(image_data, frame_delay)

    def display_image_file(self, fn):
        image_data = self.load_image_file(fn)
        if image_data is not None:
            self.display_image(image_data)

    def display_image(self, image_data):
        if self.valid_image(image_data):
            from .tbox.timeboximage import TimeBoxImage
            image = TimeBoxImage()
            image.image = image_data
            self._timebox.set_static_image(image)
        else:
            _LOGGER.error("Invalid image data received")

    def hex2rgb(self, hexcode):
        import webcolors
        rgb = webcolors.hex_to_rgb(hexcode)
        return list(rgb)

    def valid_color(self, color):
        """Verifies a color is valid
        (Array of three ints, range 0-15)"""
        valid = False
        if isinstance(color, str):
            self.hex2rgb(color)
            valid = True
        if (isinstance(color, list) and len(color) == 3):
            valid = True
            for chan in color:
                valid = valid and (0 <= chan <= 15)
        if not valid:
            _LOGGER.warn("{0} was not a valid color".format(color))
        return valid

    def valid_image(self, image):
        """Verifies an image array is valid.
        An image should consist of a 2D array, 11x11. Each array
        element is again an arry, containing a valid colour
        (see valid_color())."""
        valid = False
        if (isinstance(image, list) and len(image) == 11):
            valid = True
            for row in image:
                if (isinstance(row, list) and len(row) == 11):
                    for pixel in row:
                        if not self.valid_color(pixel):
                            valid = False
                            break
                else:
                    valid = False
                    break
        if not valid:
            _LOGGER.error("Invalid image data received")
        return valid

    def load_image_file(self, image_file_name):
        """Loads image data from a file and returns it."""
        fn = os.path.join(self._image_dir,
                          "{0}.json".format(image_file_name))
        try:
            fh = open(fn)
        except:
            _LOGGER.error("Unable to open {0}".format(fn))
            return None
        try:
            image = json.load(fh)
            return image
        except Exception as e:
            _LOGGER.error("{0} does not contain a valid image in JSON format".format(fn))
            _LOGGER.error(e)
            return None

    def convert_color(self, color):
        """We expect all colors passed in to be in the range 0-15.
        But some parts of the timebox API expect 0-255. This function
        converts a passed in color array to something the API can
        work with. Does not do validation itself."""
        return [color[0]*16, color[1]*16, color[2]*16]

    def send_message(self, message="", **kwargs):
        if kwargs.get(ATTR_DATA) is None:
            _LOGGER.error("Service call needs a message type")
            return False

        data = kwargs.get(ATTR_DATA)

        fontfile = 'slkscr.pil'
        from PIL import ImageFont
        font = ImageFont.load(os.path.join(self._font_dir, fontfile))
        if data.get(PARAM_FONT):
            fontfile = data.get(PARAM_FONT)

        if fontfile.endswith(".pil"):
            font = ImageFont.load(os.path.join(self._font_dir, fontfile))
        elif fontfile.endswith(".ttf"):
            font = ImageFont.truetype(os.path.join(self._font_dir, fontfile), 11)

        if data.get(PARAM_MODE) == "off":
            self._timebox.disable_display()
            # self._timebox.set_static_image(self._blank_image)

        elif data.get(PARAM_MODE) == "clock":
            color = data.get(PARAM_COLOR)
            if isinstance(color, str):
                color = self.hex2rgb(color)
            elif self.valid_color(color):
                color = self.convert_color(color)
            else:
                color = [255, 255, 255]
            self._timebox.show_clock(color=color)

        elif data.get(PARAM_MODE) == "temp":
            color = data.get(PARAM_COLOR)
            if self.valid_color(color):
                color = self.convert_color(color)
            else:
                color = [255, 255, 255]
            self._timebox.show_temperature(color=color)

        elif data.get(PARAM_MODE) == "image":
            image_data = data.get(PARAM_IMAGE)
            self.display_image(image_data)

        elif data.get(PARAM_MODE) == "image-file":
            image_filename = data.get(PARAM_IMAGE_FILE)
            if (image_filename.endswith('.png')) or (image_filename.endswith('.bmp')):
                fn = os.path.join(self._image_dir, image_filename)
                _LOGGER.info("Showing image file '{0}'".format(fn))
                self._timebox.show_static_image(fn)
            elif image_filename.endswith('.json'):
                self.display_image_file(image_filename)

        elif data.get(PARAM_MODE) == 'text':
            text = []
            for txt, color in data['text']:
                text.append((txt, color))
            if 'speed' in data:
                self._timebox.show_text(text, font=font, speed=data['speed'])
            else:
                self._timebox.show_text(text, font=font)

        elif data.get(PARAM_MODE) == 'text2':
            text = []
            for txt, color in data['text']:
                text.append((txt, color))
            self._timebox.show_text2(text, font=font)

        elif data.get(PARAM_MODE) == 'str':
            text = []
            for txt, color in data['text']:
                text.append((txt, color))
            self._timebox.show_string(text, font=font)

        elif data.get(PARAM_MODE) == "animation":
            image_data = data.get(PARAM_ANIM)
            self.display_anim(image_data)

        elif data.get(PARAM_MODE) == "animation-file":
            image_file = data.get(PARAM_ANIM_FILE)
            delay = data.get(PARAM_DELAY)
            fn = os.path.join(self._image_dir, image_file)
            _LOGGER.info("Showing anim image file '{0}'".format(fn))
            self.display_anim_file(fn, delay)

        else:
            _LOGGER.error("Invalid mode '{0}', must be one of 'off', 'clock', 'temp', 'image', 'animation'".format(data.get(PARAM_MODE)))
            return False

        if data.get(PARAM_TYPE) != "persist":
            time.sleep(5)
            color = [255, 0, 0]
            self._timebox.show_clock(color=color)

        return True
