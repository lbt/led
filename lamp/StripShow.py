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
    '''Define functions which animate LEDs in various ways.'''

    def __init__(self, controller, strip, name):
        self.controller = controller
        self.strip = strip
        self.name = name
        self.painter = "rainbowChase"
        self.running = True
        self.args = None

    def start(self):
        self.task = asyncio.create_task(self.show())
        j = json.dumps(self.args, separators=(',', ':')).encode("utf-8")
        logger.debug(f"strip/{self.name}/{self.painter} = {j}")
        logger.debug(f"The show must go on. Let's {self.painter}")

    async def setPainter(self, painter, rawpayload):
        logger.debug(f"setPainter({painter}, {rawpayload})")

        if not hasattr(self, painter):
            logger.debug("setPainter: invalid painter: {painter}")
            return
        # handle empty string as {}
        self.args = json.loads(rawpayload.decode("utf-8") or "null")
            # if self.painter != painter:
        if True:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                logger.debug(f"The {self.painter} show is over")
            self.painter = painter
            self.running = True
            self.start()
        else:
            # This won't work unless args is checked in the yielding loop
            self.running = True  # One shot runners should run again

        self.controller.publish(f"strip/{self.name}/{self.painter}",
                          json.dumps(self.args, separators=(',', ':')
                          ).encode("utf-8"))

    async def show(self):
        while True:
            if self.running:
                async for frame in getattr(self, self.painter)():
                    self.strip.show()
            else:
                await asyncio.sleep(0.01)

    def hue_to_rgb(self, h):
        """Convert a 0-255 hue into a Colour() """
        return Colour(*([int(c * 255) for c in colorsys.hsv_to_rgb(h/255, 1, 1)]))

    ################################################################
    # Painters
    async def rainbowChase(self):
        """Draw rainbow that uniformly distributes itself across all pixels."""
        t = time.time() * 10
        for i in range(self.strip.numPixels()):
            # Spread the Hue range over the pixels, but also cycle it over time
            h = (i / self.strip.numPixels()) * 255  # scale to 0-255
            self.strip.setPixelColor(i, self.hue_to_rgb((t + h) % 255))
        await asyncio.sleep(1/60)
#        print(f"{t}")
        yield True

    async def rainbowFade(self):
        """Fade through all the colours of a Rainbow"""
        while True:
            t = time.time() * 10
            colour = self.hue_to_rgb(t % 255)
            for i in range(self.strip.numPixels()):
                #print(f"{colour}")
                self.strip.setPixelColor(i, colour)
            yield True
            await asyncio.sleep(1/60)

    async def solidColour(self):
        """Set the entire display to a colour."""
        if self.args is not None:
            self.colour = Colour(*self.args["colour"])
        else:
            self.colour = Colour(255,0,0)
        for i in range(self.strip.numPixels()):
            # print(f"{i}")
            self.strip.setPixelColor(i, self.colour)
        yield True
        self.running = False

    async def solidColourWipe(self):
        """Wipe colour across display a pixel at a time."""
        wait_ms = 50
        self.colour = Colour(*self.args["colour"])
        for i in range(self.strip.numPixels()):
            self.strip.setPixelColor(i, self.colour)
            yield True
            await asyncio.sleep(wait_ms/1000.0)
        self.running = False

    async def theaterChase(self):
        """Movie theater light style chaser animation."""
        line = 8
        wait_ms = 50
        while True:
            for q in range(line):
                for i in range(0, self.strip.numPixels(), line):
                    self.strip.setPixelColor(i+q, self.colour)
                yield True
                await asyncio.sleep(wait_ms/1000.0)
                for i in range(0, self.strip.numPixels(), line):
                    self.strip.setPixelColor(i+q, 0)

    def theaterChaseRainbow(self):
        """Rainbow movie theater light style chaser animation."""
        wait_ms = 50
        for j in range(256):
            for q in range(3):
                for i in range(0, self.strip.numPixels(), 3):
                    self.strip.setPixelColor(i+q, hue_to_rgb((i+j) % 255))
                yield True
                time.sleep(wait_ms/1000.0)
                for i in range(0, self.strip.numPixels(), 3):
                    self.strip.setPixelColor(i+q, 0)
