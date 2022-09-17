import asyncio
import logging
import threading

import numpy as np
import pyaudio

logger = logging.getLogger(__name__)


class Microphone:
    def __init__(self, mic_rate, fps):
        self.mic_rate = mic_rate
        self.p = pyaudio.PyAudio()
        self.frames_per_buffer = int(self.mic_rate / fps)
        logger.debug("working on %s fps and %s frames",
                     fps, self.frames_per_buffer)
        self.stream = None
        # It's written from the run_in_executor Thread and read from
        # the async main thread so it needs locking to avoid reading
        # whilst it's being written
        self._audiodata = None
        self._audiodata_lock = threading.Lock()

        # This is used to lock access to the pyaudio object when
        # closing because it's likely blocking in the other thread
        self._p_lock = threading.Lock()

        # This is used to lock access to the client list
        self._c_lock = threading.Lock()

        self.stream_playing_task = None
        self.stream_stop_playing = False

        # Keep a record of clients so we can stop the stream if we
        # have none left
        self.clients = {}

    def __del__(self):
        logger.debug("Terminating PyAudio")
        self.p.terminate()

    @property
    def audiodata(self):
        with self._audiodata_lock:
            if self._audiodata is None:
                logger.debug("No frame yet")
                return None
            c = self._audiodata.copy()
            return c

    async def subscribe_stream(self, client):
        with self._c_lock:
            self.stream_stop_playing = False

            if not self.stream_playing_task or self.stream_playing_task.done():
                logger.debug("Starting stream for %s in a thread", self)
                loop = asyncio.get_event_loop()
                self.stream_playing_task = loop.run_in_executor(None, self._run_stream)
            # Add this client
            self.clients[client] = True
            logger.debug("mic has %s clients after subscribe", len(self.clients))

    async def unsubscribe_stream(self, client):
        with self._c_lock:
            # Remove this client
            try:
                del self.clients[client]
            except KeyError:
                logger.warn("Client already unsubscribed")
                pass
            if not self.clients:
                self.stream_stop_playing = True
                await self.stream_playing_task
            logger.debug("mic has %s clients after unsubscribe", len(self.clients))

    def _run_stream(self):
        self._ensure_stream()
        if self.stream.is_stopped():
            self.stream.start_stream()
        while True:
            try:
                with self._p_lock:
                    if self.stream_stop_playing:
                        logger.debug("_run_stream exiting as asked")
                        break
                    frames = self.stream.read(self.frames_per_buffer,
                                              exception_on_overflow=False)
                    # logger.debug("_run_stream frame stop=%s", self.stream_stop_playing)

                y = np.fromstring(frames, dtype=np.int16).astype(np.float32)
                with self._audiodata_lock:
                    self._audiodata = y
            except IOError:
                logger.debug("_run_stream exiting due to IOError")
                break
        self.stream.stop_stream()
        logger.debug("Thread exiting for %s", self)

    def _ensure_stream(self):
        while not self.stream:
            logger.debug("No stream available, making one")
            try:
                p = pyaudio.PyAudio()
                # look for the Loopback device with 2 channels
                index = 1  # Fallback if we can't find anything
                logger.debug("Scanning audio devices:")
                for i in range(p.get_device_count()):
                    dev = p.get_device_info_by_index(i)
                    logger.debug("%d : %s : %s",
                                  i, dev['name'], dev['maxInputChannels'])
                    if (dev['name'].startswith("Loopback") and
                        dev['maxInputChannels'] == 2):
                        logger.debug("found %d : %s : %s",
                                     i, dev['name'], dev['maxInputChannels'])
                        index = i
                        break
                self.stream = self.p.open(
                    format=pyaudio.paInt16,
                    input_device_index=index,
                    channels=1,
                    rate=self.mic_rate,
                    input=True,
                    frames_per_buffer=self.frames_per_buffer)
            except OSError as e:
                logger.debug("Error opening stream %s", e)

    async def pause_stream(self):
        logger.debug("Pausing stream for %s in a thread", self)
        #return
        if self.stream:
            self.stream_stop_playing = True
            await self.stream_playing_task

    async def close(self):
        logger.debug("Closing mic %s", self)
        if self.stream_playing_task:
            logger.debug("Waiting for stream_playing_task thread")
            self.stream_stop_playing = True
            await self.stream_playing_task
        if self.stream:
            with self._p_lock:
                self.stream.close()
                self.stream = None
        logger.debug("Mic is closed")

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
