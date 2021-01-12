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
        self.painter = "colorFade"
        self.running = True
        self.args = "0,0,255"

    def start(self):
        self.task = asyncio.create_task(self.show())


    async def setPainter(self, painter, args):
        if self.painter != painter:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                print("The show is over")
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

    async def rainbowCycle2(self):
        """Draw rainbow that uniformly distributes itself across all pixels."""
        t = time.time() * 10
        for i in range(self.strip.numPixels()):
            # Spread the Hue range over the pixels, but also cycle it over time
            h = (i / self.strip.numPixels()) * 255  # scale to 0-255
            self.strip.setPixelColor(i, self.hue_to_rgb((t + h) % 255))
        await asyncio.sleep(1/60)
#        print(f"{t}")
        yield True

    async def colorSet(self):
        """Set the entire display to a color."""
        if self.args is not None:
            (r, g, b) = self.args.split(",")
            self.color = Color(r, g, b)
            self.args = None

        for i in range(self.strip.numPixels()):
            # print(f"{i}")
            self.strip.setPixelColor(i, self.color)
        yield True
        self.running = False

    async def colorFade(self):
        """Set the entire display to a color."""
        while True:
            t = time.time() * 10
            color = self.hue_to_rgb(t % 255)
            for i in range(self.strip.numPixels()):
                #print(f"{color}")
                self.strip.setPixelColor(i, color)
            yield True
            await asyncio.sleep(1/60)


    async def colorWipe(self, color, wait_ms=50):
        """Wipe color across display a pixel at a time."""
        for i in range(self.strip.numPixels()):
            self.strip.setPixelColor(i, color)
            yield True
            await asyncio.sleep(wait_ms/1000.0)
        self.running = False

    def theaterChase(self, color, wait_ms=50, iterations=10):
        """Movie theater light style chaser animation."""
        for j in range(iterations):
            for q in range(3):
                for i in range(0, self.strip.numPixels(), 3):
                    self.strip.setPixelColor(i+q, color)
                yield True
                time.sleep(wait_ms/1000.0)
                for i in range(0, self.strip.numPixels(), 3):
                    self.strip.setPixelColor(i+q, 0)

    def theaterChase2(self, color, wait_ms=50, iterations=20):
        """Movie theater light style chaser animation."""
        line = 8
        for j in range(iterations):
            for q in range(line):
                for i in range(0, self.strip.numPixels(), line):
                    self.strip.setPixelColor(i+q, color)
                yield True
                time.sleep(wait_ms/1000.0)
                for i in range(0, self.strip.numPixels(), line):
                    self.strip.setPixelColor(i+q, 0)

    def rainbow(self, wait_ms=20, iterations=1):
        """Draw rainbow that fades across all pixels at once."""
        for j in range(256*iterations):
            for i in range(self.strip.numPixels()):
                self.strip.setPixelColor(i, hue_to_rgb((i+j) & 255))
            yield True
            time.sleep(wait_ms/1000.0)

    def rainbowCycle(self, wait_ms=20, iterations=5):
        """Draw rainbow that uniformly distributes itself across all pixels."""
        for j in range(256*iterations):
            for i in range(self.strip.numPixels()):
                self.strip.setPixelColor(
                    i, self.hue_to_rgb(
                        (int(i * 256 / self.strip.numPixels()) + j) & 255))
            yield True
            time.sleep(wait_ms/1000.0)

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
