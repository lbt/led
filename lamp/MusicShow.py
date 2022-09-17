import asyncio
import logging
import random
import time

import dsp
import numpy as np
from scipy.ndimage.filters import gaussian_filter1d
from microphone import Microphone
from .StripShow import StripShow

import config

logger = logging.getLogger(__name__)

################################################################
# Painter Classes


def memoize(function):
    """Provides a decorator for memoizing functions"""
    from functools import wraps
    memo = {}

    @wraps(function)
    def wrapper(*args):
        if args in memo:
            return memo[args]
        else:
            rv = function(*args)
            memo[args] = rv
            return rv
    return wrapper


@memoize
def _normalized_linspace(size):
    return np.linspace(0, 1, size)


def interpolate(y, new_length):
    """Intelligently resizes the array by linearly interpolating the values

    Parameters
    ----------
    y : np.array
        Array that should be resized

    new_length : int
        The length of the new interpolated array

    Returns
    -------
    z : np.array
        New array with length of new_length that contains the interpolated
        values of y.
    """
    if len(y) == new_length:
        return y
    x_old = _normalized_linspace(len(y))
    x_new = _normalized_linspace(new_length)
    z = np.interp(x_new, x_old, y)
    return z


class MusicShow(StripShow):
    # Use a class instance of the Microphone This is instantiated by
    # the first class.  An alternate strategy is to set the
    # MusicShow.mic as part of setting up the StripController
    mic = None

    def __init__(self, controller, args):
        super().__init__(controller, args)

        self._gamma = np.load(config.GAMMA_TABLE_PATH)
        """Gamma lookup table used for nonlinear brightness correction"""

        # Number of audio samples to read every time frame
        self.samples_per_frame = int(config.MIC_RATE / config.FPS)
        # Array containing the rolling audio sample window
        self.y_roll = np.random.rand(
            config.N_ROLLING_HISTORY, self.samples_per_frame) / 1e16
        self.fft_window = np.hamming(int(config.MIC_RATE / config.FPS) *
                                     config.N_ROLLING_HISTORY)
        self.mel_gain = dsp.ExpFilter(np.tile(1e-1, config.N_FFT_BINS),
                                      alpha_decay=0.01, alpha_rise=0.99)
        self.mel_smoothing = dsp.ExpFilter(np.tile(1e-1, config.N_FFT_BINS),
                                           alpha_decay=0.5, alpha_rise=0.99)
        if not MusicShow.mic:
            MusicShow.mic = Microphone(config.MIC_RATE, config.FPS)
        self.mic = MusicShow.mic
        logger.debug("Made %s", self.mic)

    def to_mel(self, audio_samples):
        # Thie was microphone_update() in visualization.py
        # Normalize samples between 0 and 1
        y = audio_samples / 2.0**15
        # Construct a rolling window of audio samples
        self.y_roll[:-1] = self.y_roll[1:]
        self.y_roll[-1, :] = np.copy(y)
        y_data = np.concatenate(self.y_roll, axis=0).astype(np.float32)

        vol = np.max(np.abs(y_data))
        if vol < 0:  # config.MIN_VOLUME_THRESHOLD:
            # print('No audio input. Volume below threshold. Volume:', vol)
            return None
        else:
            # Transform audio input into the frequency domain
            N = len(y_data)
            N_zeros = 2**int(np.ceil(np.log2(N))) - N
            # Pad with zeros until the next power of two
            y_data *= self.fft_window
            y_padded = np.pad(y_data, (0, N_zeros), mode='constant')
            YS = np.abs(np.fft.rfft(y_padded)[:N // 2])
            # Construct a Mel filterbank from the FFT data
            mel = np.atleast_2d(YS).T * dsp.mel_y.T
            # Scale data to values more suitable for visualization
            # mel = np.sum(mel, axis=0)
            mel = np.sum(mel, axis=0)
            mel = mel**2.0
            # Gain normalization
            self.mel_gain.update(np.max(gaussian_filter1d(mel, sigma=1.0)))
            mel /= self.mel_gain.value
            mel = self.mel_smoothing.update(mel)
            return mel
            # # Map filterbank output onto LED strip
            # output = self.visualization_effect(mel)
            # self.pixels = output
            # return self.update()

    def prepare_for_strip(self, pixels):
        # Truncate values and cast to integer
        pixels = np.clip(pixels, 0, 255).astype(int)
        # Optional gamma correction
        # Note: is the p value here is related to p in the Effects class?
        if config.SOFTWARE_GAMMA_CORRECTION:
            p = self._gamma[pixels]
        else:
            p = pixels
        # Encode 24-bit LED values in 32 bit integers
        r = np.left_shift(p[0][:].astype(int), 8)
        g = np.left_shift(p[1][:].astype(int), 16)
        b = p[2][:].astype(int)
        return np.bitwise_or(np.bitwise_or(r, g), b)

    async def showHasFinished(self):
        logger.debug("Releasing mic %s client %s", self.mic, self)
        await self.mic.unsubscribe_stream(self)


class MusicScroll(MusicShow):
    """Effect that originates in the center and scrolls outwards"""

    N_FFT_BINS = 16
    """Number of frequency bins to use when transforming audio to frequency domain

    Fast Fourier transforms are used to transform time-domain audio data to the
    frequency domain. The frequencies present in the audio signal are assigned
    to their respective frequency bins. This value indicates the number of
    frequency bins to use.

    A small number of bins reduces the frequency resolution of the
    visualization but improves amplitude resolution. The opposite is
    true when using a large number of bins. More bins is not always
    better!

    There is no point using more bins than there are pixels on the LED strip.

    """
    async def paint(self):
        pixels = np.tile(1.0, (3, self.numPixels // 2))
        logger.debug(f"Frame init {self.numPixels} {pixels} ")
        gain = dsp.ExpFilter(np.tile(0.01, config.N_FFT_BINS),
                             alpha_decay=0.001, alpha_rise=0.99)
        await self.mic.subscribe_stream(self)
        while self.running:
            y = self.mic.audiodata
            if y is None:
                await asyncio.sleep(0.1)
                yield True
                continue
            y = self.to_mel(y)
            y = y**2.0
            gain.update(y)
            y /= gain.value
            y *= 255.0
            b = int(np.max(y[:len(y) // 3]))
            r = int(np.max(y[len(y) // 3: 2 * len(y) // 3]))
            g = int(np.max(y[2 * len(y) // 3:]))
            # Scrolling effect window
            pixels[:, 1:] = pixels[:, :-1]
            pixels *= 0.98
            pixels = gaussian_filter1d(pixels, sigma=0.3)
            await asyncio.sleep(0)
            # Create new color originating at the center
            pixels[0, 0] = r
            pixels[1, 0] = g
            pixels[2, 0] = b
            # Update the LED strip
            mirrored_pixels = np.concatenate((pixels[:, ::-1], pixels), axis=1)
            p = self.prepare_for_strip(mirrored_pixels)
            self.setPixelColor(slice(0, len(p)), p)
            yield True
            await asyncio.sleep(0)
        logger.debug("%s: paint has finished", self.__class__.__name__)


class MusicEnergy(MusicShow):
    """Effect that expands from the center with increasing sound energy"""

    async def paint(self):
        pixels = np.tile(1.0, (3, self.numPixels // 2))
        logger.debug(f"Frame init {self.numPixels} {pixels} ")
        gain = dsp.ExpFilter(np.tile(0.01, config.N_FFT_BINS),
                             alpha_decay=0.001, alpha_rise=0.99)
        p_filt = dsp.ExpFilter(np.tile(1, (3, self.numPixels // 2)),
                               alpha_decay=0.1, alpha_rise=0.99)

        await self.mic.subscribe_stream(self)
        while self.running:
            y = self.mic.audiodata
            if y is None:
                await asyncio.sleep(0.1)
                yield True
                continue
            y = self.to_mel(y)
            y = np.copy(y)
            gain.update(y)
            y /= gain.value
            # Scale by the width of the LED strip
            y *= float((self.numPixels // 2) - 1)*2
            # Map color channels according to energy in the different freq bands
            scale = 0.9
            r = int(np.mean(y[:len(y) // 3]**scale))
            g = int(np.mean(y[len(y) // 3: 2 * len(y) // 3]**scale))
            b = int(np.mean(y[2 * len(y) // 3:]**scale))
            # Assign color to different frequency regions
            pixels[0, :g] = 255.0
            pixels[0, g:] = 0.0
            pixels[1, :r] = 255.0
            pixels[1, r:] = 0.0
            pixels[2, :b] = 255.0
            pixels[2, b:] = 0.0
            await asyncio.sleep(0)
            p_filt.update(pixels)
            pixels = np.round(p_filt.value)
            # Apply substantial blur to smooth the edges
            pixels[0, :] = gaussian_filter1d(pixels[0, :], sigma=4.0)
            pixels[1, :] = gaussian_filter1d(pixels[1, :], sigma=4.0)
            pixels[2, :] = gaussian_filter1d(pixels[2, :], sigma=4.0)
            # Set the new pixel value
            # Update the LED strip
            mirrored_pixels = np.concatenate((pixels[:, ::-1], pixels), axis=1)
            p = self.prepare_for_strip(mirrored_pixels)
            self.setPixelColor(slice(0, len(p)), p)
            yield True
            await asyncio.sleep(0)
        logger.debug("%s: paint has finished", self.__class__.__name__)

class MusicSpectrum(MusicShow):
    """Effect that maps the Mel filterbank frequencies onto the LED strip"""

    async def paint(self):
        pixels = np.tile(1.0, (3, self.numPixels // 2))
        logger.debug(f"Frame init {self.numPixels} {pixels} ")
        common_mode = dsp.ExpFilter(np.tile(0.01, self.numPixels // 2),
                                    alpha_decay=0.99, alpha_rise=0.01)
        _prev_spectrum = np.tile(0.01, self.numPixels // 2)
        r_filt = dsp.ExpFilter(np.tile(0.01, self.numPixels // 2),
                               alpha_decay=0.2, alpha_rise=0.99)
        g_filt = dsp.ExpFilter(np.tile(0.01, self.numPixels // 2),
                               alpha_decay=0.05, alpha_rise=0.3)
        b_filt = dsp.ExpFilter(np.tile(0.01, self.numPixels // 2),
                               alpha_decay=0.1, alpha_rise=0.5)
        await self.mic.subscribe_stream(self)
        while self.running:
            y = self.mic.audiodata
            if y is None:
                await asyncio.sleep(0.1)
                yield True
                continue
            y = self.to_mel(y)
            y = np.copy(interpolate(y, self.numPixels // 2))
            common_mode.update(y)
            diff = y - _prev_spectrum
            _prev_spectrum = np.copy(y)
            # Color channel mappings
            r = r_filt.update(y - common_mode.value)
            g = np.abs(diff)
            b = b_filt.update(np.copy(y))
            # Mirror the color channels for symmetric output
            r = np.concatenate((r[::-1], r))
            g = np.concatenate((g[::-1], g))
            b = np.concatenate((b[::-1], b))
            pixels = np.array([r, g, b]) * 255
            p = self.prepare_for_strip(pixels)
            self.setPixelColor(slice(0, len(p)), p)
            yield True
            await asyncio.sleep(0)
        logger.debug("%s: paint has finished", self.__class__.__name__)

    def visualize_sparkle(self, y):
        s = random.randrange(self.numPixels)
        # print(s)
        pixels *= 0.3

        pixels[0, s-1:s] = 255
        pixels[1, s-1:s] = 255
        pixels[2, s-1:s] = 255

        return pixels

    def visualize_sparkle_colour(self, y):
        s = random.randrange(self.numPixels)
        # print(s)
        pixels *= 0.8

        pixels[0, s-1:s] = random.randrange(255)
        pixels[1, s-1:s] = random.randrange(255)
        pixels[2, s-1:s] = random.randrange(255)

        return pixels
