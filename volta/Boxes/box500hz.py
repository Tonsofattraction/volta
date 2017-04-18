""" 500Hz Volta Box
"""
import serial
import logging
import queue
import pandas as pd
import time
import numpy as np
from volta.common.interfaces import VoltaBox
from volta.common.util import Drain, TimeChopper
from volta.common.resource import manager as resource

logger = logging.getLogger(__name__)


class VoltaBox500Hz(VoltaBox):
    def __init__(self, config):
        VoltaBox.__init__(self, config)
        self.sample_rate = config.get('sample_rate', 500)
        self.source = config.get('source', '/dev/cu.wchusbserial1420')
        self.chop_ratio = config.get('chop_ratio', 1)
        self.baud_rate = config.get('baud_rate', 115200)
        self.grab_timeout = config.get('grab_timeout', 1)
        # initialize data source
        self.source_opener = resource.get_opener(self.source)
        self.source_opener.baud_rate = self.baud_rate
        self.source_opener.read_timeout = self.grab_timeout
        self.data_source = self.source_opener()
        logger.debug('Data source initialized: %s', self.data_source)

    def start_test(self, results):
        """ pipeline
                read source data ->
                chop by samplerate w/ ratio ->
                make pandas DataFrame ->
                drain DataFrame to queue `results`
        Args:
            results: object answers to put() and get() methods

        Returns:
            puts pandas DataFrame to specified queue
        """

        # clean up dirty buffer
        for _ in range(self.sample_rate):
            self.data_source.readline()

        self.reader = BoxPlainTextReader(
            self.data_source, self.sample_rate
        )
        self.pipeline = Drain(
            TimeChopper(
                self.reader, self.sample_rate, self.chop_ratio
            ),
            results
        )
        logger.info('Starting grab thread...')
        self.pipeline.start()
        logger.debug('Waiting grabber thread finish...')

    def end_test(self):
        self.reader.close()
        self.pipeline.close()
        self.pipeline.join(10)
        self.data_source.close()


def string_to_np(data):
    start_time = time.time()
    chunk = np.fromstring(data, dtype=float, sep='\n')
    # logger.debug("Chunk decode time: %.2fms", (time.time() - start_time) * 1000)
    return chunk


class BoxPlainTextReader(object):
    """
    Read chunks from source, convert and return numpy.array
    """

    def __init__(self, source, cache_size=1024 * 1024 * 10):
        self.closed = False
        self.cache_size = cache_size
        self.source = source
        self.buffer = ""

    def _read_chunk(self):
        data = self.source.read(self.cache_size)
        if data:
            parts = data.rsplit('\n', 1)
            if len(parts) > 1:
                ready_chunk = self.buffer + parts[0] + '\n'
                self.buffer = parts[1]
                return string_to_np(ready_chunk)
            else:
                self.buffer += parts[0]
        else:
            self.buffer += self.source.readline()
        return None

    def __iter__(self):
        while not self.closed:
            yield self._read_chunk()
        yield self._read_chunk()

    def close(self):
        self.closed = True


# ==================================================

def main():
    logging.basicConfig(
        level="DEBUG",
        format='%(asctime)s [%(levelname)s] [Volta 500hz] %(filename)s:%(lineno)d %(message)s')
    logger.info("Volta 500 hz box ")
    cfg = {
        'source': '/dev/cu.wchusbserial1420'
        # 'source': '/Users/netort/output.bin'
    }
    worker = VoltaBox500Hz(cfg)
    logger.info('worker args: %s', worker.__dict__)
    grabber_q = queue.Queue()
    worker.start_test(grabber_q)
    time.sleep(10)
    logger.info('test finishing...')
    worker.end_test()
    logger.info('Queue size after test: %s', grabber_q.qsize())
    logger.info('Sample: %s', grabber_q.get())
    logger.info('Sample: %s', grabber_q.get())
    logger.info('Sample: %s', grabber_q.get())
    logger.info('test finished')

if __name__ == "__main__":
    main()