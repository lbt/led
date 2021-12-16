import asyncio
import logging
import threading

import numpy as np
import pyaudio

logger = logging.getLogger(__name__)

MIC_RATE = 48000
FPS = 15


class Microphone:
    def __init__(self):
        self.p = pyaudio.PyAudio()
        self.frames_per_buffer = int(MIC_RATE / FPS)
        logger.debug(f"working on {FPS} fps and {self.frames_per_buffer} frames")
        self.stream = None
        # It's written from the run_in_executor Thread and read from
        # the async main thread so it needs locking
        self._audiodata = None
        self._audiodata_lock = threading.Lock()

        # This is used to lock access to the pyaudio object when
        # closing because it's likely blocking in the other thread
        self._p_lock = threading.Lock()

        self.task = None

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
        logger.debug(f"Opening stream")
        self. stream = self.p.open(format=pyaudio.paInt16,
                                   input_device_index=1,
                                   channels=1,
                                   rate=MIC_RATE,
                                   input=True,
                                   frames_per_buffer=self.frames_per_buffer)

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
                return

    def pause_stream(self):
        if self.stream:
            with self._p_lock:
                self.stream.stop_stream()

    async def close(self):
        logger.debug(f"Closing mic")
        if self.stream:
            with self._p_lock:
                self.stream.close()
        if self.task:
            logger.debug(f"Waiting for thread/task")
            await self.task
        self.p.terminate()
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
