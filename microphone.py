import asyncio
import logging
import threading

import numpy as np
import pyaudio

import config
# Just need
# MIC_RATE = 48000
# FPS = 50

logger = logging.getLogger(__name__)



class Microphone:
    def __init__(self):
        self.p = pyaudio.PyAudio()
        self.frames_per_buffer = int(config.MIC_RATE / config.FPS)
        logger.debug(f"working on {config.FPS} fps and {self.frames_per_buffer} frames")
        self.stream = None
        # It's written from the run_in_executor Thread and read from
        # the async main thread so it needs locking
        self._audiodata = None
        self._audiodata_lock = threading.Lock()

        # This is used to lock access to the pyaudio object when
        # closing because it's likely blocking in the other thread
        self._p_lock = threading.Lock()

        self.task = None

    def __del__(self):
        logger.debug("Terminating PyAudio")
        self.p.terminate()

    @property
    def audiodata(self):
        with self._audiodata_lock:
            if self._audiodata is None:
                logger.debug(f"No frame yet")
                return None
            else:
                c = self._audiodata.copy()
                return c

    def start_stream(self):
        logger.debug(f"Opening stream for {self}")
        while not self.stream:
            try:
                p = pyaudio.PyAudio()
                # look for the Loopback device with 1 channel
                index = 1  # Fallback if we can't find anything
                for i in range(p.get_device_count()):
                    dev = p.get_device_info_by_index(i)
                    print((i, dev['name'],dev['maxInputChannels']))
                    if dev['name'].startswith("Loopback") and dev['maxInputChannels'] == 1:
                        print(("found ", i, dev['name'],dev['maxInputChannels']))
                        index = i
                        break
                self.stream = self.p.open(format=pyaudio.paInt16,
                                          input_device_index=index,
                                          channels=1,
                                          rate=config.MIC_RATE,
                                          input=True,
                                          frames_per_buffer=self.frames_per_buffer)
            except OSError as e:
                logger.debug(f"Error opening stream {e}")

        loop = asyncio.get_event_loop()
        self.task = loop.run_in_executor(None, self._start_stream)

    def _start_stream(self):
        while True:
            try:
                with self._p_lock:
                    frames = self.stream.read(self.frames_per_buffer,
                                              exception_on_overflow=False)

                y = np.fromstring(frames, dtype=np.int16).astype(np.float32)
                with self._audiodata_lock:
                    self._audiodata = y
            except IOError:
                logger.debug("_start_stream exiting due to IOError")
                return

    def pause_stream(self):
        if self.stream:
            with self._p_lock:
                self.stream.stop_stream()

    async def close(self):
        logger.debug(f"Closing mic {self}")
        if self.stream:
            with self._p_lock:
                self.stream.close()
        if self.task:
            logger.debug(f"Waiting for thread/task")
            await self.task
        logger.debug(f"Mic is closed")

    # If we want callback see:
    # https://stackoverflow.com/questions/53993334/converting-a-python-function-with-a-callback-to-an-asyncio-awaitable
    # def make_iter(self):
    #     loop = asyncio.get_event_loop()
    #     queue = asyncio.Queue()
    #     def put(*args):
    #         loop.call_soon_threadsafe(queue.put_nowait, args)
    #     async def get():
    #         while True:
    #             yield await queue.get()
    #     return get(), put

    # async def main(self):
    #     stream_get, stream_put = make_iter()
    #     stream = pa.open(stream_callback=stream_put)
    #     stream.start_stream()
    #     async for in_data, frame_count, time_info, status in stream_get:
    #         pass
    #     # ...
    #     overflows = 0
    #     prev_ovf_time = time.time()
    #     while True:
    #         try:
    #             y = np.fromstring(
    #                 self.stream.read(self.frames_per_buffer,
    #                                  exception_on_overflow=False),
    #                 dtype=np.int16)
    #             y = y.astype(np.float32)
    #             self.stream.read(
    #                 self.stream.get_read_available(),
    #                 exception_on_overflow=False)
    #             self.callback(y)
    #         except IOError:
    #             overflows += 1
    #             if time.time() > prev_ovf_time + 1:
    #                 prev_ovf_time = time.time()
    #                 logger.debug(f'Audio buffer has overflowed {overflows} times')
