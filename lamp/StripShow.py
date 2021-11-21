import time
import argparse
import colorsys
from rpi_ws281x import Color as Colour
from collections import deque
import itertools
import asyncio
import json
import logging
logger = logging.getLogger(__name__)


class StripShow:
    '''Define various ways to animate LEDs in a SubStrip.

    StripShow manages an internal task which runs show() forever.

    show() calls the current painter on each iteration and then calls
    strip.show() to actually update the strip.

    The painter updates the LED values and pauses as needed,

    Painters have access to the decoded message payload via the
    self.args attribute

    '''

    class Painter:
        """Helper class to hold private attributes for a painter
        """
        def __init__(self, args):
            self.method = args["painter"]
            self.args = args

        def _as_payload(self):
            return json.dumps(self.args, separators=(',', ':')).encode("utf-8")

        def __repr__(self):
            return self.method

    def __init__(self, controller, strip, name):
        self.controller = controller
        self.strip = strip
        self.name = name
        self.painter = self.Painter({"painter": "rainbowChase"})
        self.running = True
        self.args = None

    def start(self):
        self.task = asyncio.create_task(self.show())
        self.running = True
        logger.debug(f"The show must go on. Let's {self.painter}")

    async def setPainter(self, rawpayload):
        """Sets the Painter using a json structure.

        The raw payload is interpreted as a utf-8 json string
        containing a hash with a 'painter' key and the args to the
        particular painter.
        """
        logger.debug(f"setPainter({rawpayload})")
        args = json.loads(rawpayload.decode("utf-8") or "null")
        try:
            method = args["painter"]
        except (TypeError, KeyError):
            logger.debug("No 'painter' found in payload")
            return
        if not hasattr(self, method):
            logger.debug("setPainter: invalid painter method: {method}")
            return
        self.stopPainter()
        # Now everything has stopped we can set the global painter and args
        self.painter = self.Painter(args)
        self.start()

        self.controller.publish(f"strip/{self.name}/painter",
                                self.painter._as_payload())

    async def stopPainter(self):
        """Stops the current Painter."""
        logger.debug(f"stopPainter()")
        self.task.cancel()
        try:
            await self.task
        except asyncio.CancelledError:
            logger.debug(f"The {self.painter} show is over")

    async def show(self):
        while True:
            if self.running:
                async for frame in getattr(self, self.painter.method)():
                    self.strip.show()
            else:
                await asyncio.sleep(0.1)

    def hue_to_rgb(self, h):
        """Utility function for Painters. Converts a 0-255 hue into a
        Colour()"""
        return Colour(*(
            [int(c * 255) for c in colorsys.hsv_to_rgb(h/255, 1, 1)]))

    ################################################################
    # Painter functions

    async def rainbowChase(self):
        """Draw rainbow that uniformly distributes itself across all pixels."""
        try:
            reverse = self.painter.args.get("reverse", False)
            speed = self.painter.args.get("speed", 10)
        except Exception as e:
            logger.error(f"Error handling rainbowChase args: {e}")
            self.running = False
            return
        n = self.strip.numPixels()
        reverse = -1 if reverse else 1
        while True:
            t = time.time() * speed
            for i in range(n):
                # Spread the Hue range over the pixels, but also cycle it over time
                h = (i / n) * 255  # scale to 0-255
                self.strip.setPixelColor(i, self.hue_to_rgb((t + h * reverse) % 255))
            await asyncio.sleep(1/60)
            yield True

    async def rainbowFade(self):
        """Fade through all the colours of a Rainbow"""
        try:
            speed = self.painter.args.get("speed", 10)
        except Exception as e:
            logger.error(f"Error handling rainbowFade args: {e}")
            self.running = False
            return
        while True:
            t = time.time() * speed
            colour = self.hue_to_rgb(t % 255)
            for i in range(self.strip.numPixels()):
                self.strip.setPixelColor(i, colour)
            yield True
            await asyncio.sleep(1/60)

    async def solidColour(self):
        """Set the entire display to a colour."""
        try:
            colour = Colour(*self.painter.args["colour"])
        except (KeyError, AttributeError):
            colour = Colour(255, 0, 0)
        for i in range(self.strip.numPixels()):
            self.strip.setPixelColor(i, colour)
        # No need to run again
        self.running = False
        yield True

    async def solidColourWipe(self):
        """Wipe colour across display a pixel at a time."""
        wait_ms = self.painter.args.get("wait_ms", 50)
        colour = Colour(*self.painter.args["colour"])
        for i in range(self.strip.numPixels()):
            self.strip.setPixelColor(i, colour)
            yield True
            await asyncio.sleep(wait_ms/1000.0)
        self.running = False

    async def theaterChase(self):
        """Movie theater light style chaser animation."""
        try:
            reverse = self.painter.args.get("reverse", False)
            line = self.painter.args.get("line_length", 8)
            wait_ms = self.painter.args.get("wait_ms", 50)
            colour = Colour(*self.painter.args.get("colour", (255, 0, 0)))
        except Exception as e:
            logger.error(f"Error handling theaterChase args: {e}")
            self.running = False
            return
        num = self.strip.numPixels()
        reverse = -1 if reverse else 1
        while True:
            for q in range(line):
                for i in range(0, num, line):
                    self.strip.setPixelColor(i+(q*reverse), colour)
                yield True
                await asyncio.sleep(wait_ms/1000.0)
                for i in range(0, num, line):
                    self.strip.setPixelColor(i+(q*reverse), 0)

    async def theaterChaseRainbow(self):
        """Rainbow movie theater light style chaser animation."""
        try:
            reverse = self.painter.args.get("reverse", False)
            line = self.painter.args.get("line_length", 8)
            wait_ms = self.painter.args.get("wait_ms", 50)
        except Exception as e:
            logger.error(f"Error handling theaterChaseRainbow args: {e}")
            self.running = False
            return
        num = self.strip.numPixels()
        reverse = -1 if reverse else 1
        j = 0
        while True:
            for q in range(line):
                for i in range(0, num, line):
                    self.strip.setPixelColor(i+(q*reverse), self.hue_to_rgb((i+j) % 255))
                yield True
                await asyncio.sleep(wait_ms/1000.0)
                for i in range(0, num, line):
                    self.strip.setPixelColor(i+(q*reverse), 0)
            j = (j+1) % 256
