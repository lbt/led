import time
import argparse
import colorsys
from rpi_ws281x import Color
from collections import deque
import itertools
import asyncio
import logging
logger = logging.getLogger(__name__)


class StripShow:
    '''Define functions which animate LEDs in various ways.'''

    def __init__(self, strip):
        self.strip = strip
        self.painter = "rainbowChase"
        self.running = True
        self.args = "0,0,255"

    def start(self):
        self.task = asyncio.create_task(self.show())
        logger.debug(f"The show must go on. Let's {self.painter}")

    async def setPainter(self, painter, args):
        if self.painter != painter:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                logger.debug(f"The {self.painter} show is over")
            self.painter = painter
            self.args = args
            self.start()
        else:
            self.args = args

    async def show(self):
        while True:
            if self.running:
                async for frame in getattr(self, self.painter)():
                    self.strip.show()
            else:
                await asyncio.sleep(0.01)
    
                
    def hue_to_rgb(self, h):
        """Convert a 0-255 hue into a Color() """
        return Color(*([int(c * 255) for c in colorsys.hsv_to_rgb(h/255, 1, 1)]))

    def setColorFromArgs(self):
        if self.args is not None:
            (r, g, b) = self.args.split(",")
            logger.debug(f"set Color({r}, {g}, {b})")
            self.color = Color(r, g, b)
            self.args = None

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
            color = self.hue_to_rgb(t % 255)
            for i in range(self.strip.numPixels()):
                #print(f"{color}")
                self.strip.setPixelColor(i, color)
            yield True
            await asyncio.sleep(1/60)

    async def solidColor(self):
        """Set the entire display to a color."""
        self.setColorFromArgs()
        for i in range(self.strip.numPixels()):
            # print(f"{i}")
            self.strip.setPixelColor(i, self.color)
        yield True
        self.running = False

    async def solidColorWipe(self):
        """Wipe color across display a pixel at a time."""
        self.setColorFromArgs()
        for i in range(self.strip.numPixels()):
            self.strip.setPixelColor(i, color)
            yield True
            await asyncio.sleep(wait_ms/1000.0)
        self.running = False

    async def theaterChase(self):
        """Movie theater light style chaser animation."""
        line = 8
        self.setColorFromArgs()
        while True:
            for q in range(line):
                for i in range(0, self.strip.numPixels(), line):
                    self.strip.setPixelColor(i+q, self.color)
                yield True
                await asyncio.sleep(wait_ms/1000.0)
                for i in range(0, self.strip.numPixels(), line):
                    self.strip.setPixelColor(i+q, 0)

    def theaterChaseRainbow(self, wait_ms=50):
        """Rainbow movie theater light style chaser animation."""
        for j in range(256):
            for q in range(3):
                for i in range(0, self.strip.numPixels(), 3):
                    self.strip.setPixelColor(i+q, hue_to_rgb((i+j) % 255))
                yield True
                time.sleep(wait_ms/1000.0)
                for i in range(0, self.strip.numPixels(), 3):
                    self.strip.setPixelColor(i+q, 0)
