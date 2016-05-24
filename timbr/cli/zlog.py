import zmq
import argparse
import logging
from logging import StreamHandler, Formatter
from logging.handlers import SysLogHandler
logger = logging.getLogger("")  # setup the root logger


def setup_logger(debug=False):
    if debug:
        level = logging.DEBUG
    else:
        level = logging.INFO
    logger.setLevel(logging.DEBUG)
    formatter = Formatter('%(asctime)s %(name)-12s%(levelname)-8s %(message)s', datefmt='%m-%d %H:%M')
    consoleh = StreamHandler()
    consoleh.setLevel(level)
    consoleh.setFormatter(formatter)
    # syslogh = SysLogHandler()
    # syslogh.setLevel(level)
    # syslogh.setFormatter(formatter)
    logger.addHandler(consoleh)
    # logger.addHandler(syslogh)


_ctx = zmq.Context()
_socket = _ctx.socket(zmq.SUB)

def main():
    setup_logger()
    parser = argparse.ArgumentParser()
    parser.add_argument("endpoint", help="ZeroMQ PUB endpoint to subscribe to")
    args = parser.parse_args()

    _socket.connect(args.endpoint)
    _socket.setsockopt(zmq.SUBSCRIBE, "")
    while(True):
        msg = _socket.recv_multipart()
        logger.info(msg)

if __name__ == "__main__":
    main()
