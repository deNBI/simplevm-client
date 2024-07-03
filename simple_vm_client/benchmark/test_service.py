import argparse
import logging
import time

import gevent
from gevent import monkey
from gevent.pool import Pool
from thrift.protocol import TBinaryProtocol
from thrift.transport import TSocket, TTransport

from simple_vm_client.ttypes import *
from simple_vm_client.VirtualMachineService import *

# Apply monkey patching to make standard library cooperative with gevent
monkey.patch_all()

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")
logger = logging.getLogger(__name__)


def _create_connection(timeout=50000):
    host = "0.0.0.0"
    port = 9090
    transport = TSocket.TSocket(host=host, port=port)
    transport.setTimeout(timeout)
    transport = TTransport.TBufferedTransport(transport)
    protocol = TBinaryProtocol.TBinaryProtocol(transport)
    thrift_client = Client(protocol)
    return thrift_client, transport


def fetch_volume(volume_id, run_id, timeout=50000):
    client, transport = _create_connection(timeout)
    start_time = time.time()
    try:
        transport.open()
        vol = client.get_volume(volume_id)
        success = True
        logging.info(vol)
    except Exception as e:
        success = False
        error_message = str(e)
    finally:
        transport.close()
        end_time = time.time()
        elapsed_time = end_time - start_time
        if success:
            logger.info(
                f"[{run_id}]Successfully fetched volume {volume_id}. Time taken: {elapsed_time:.2f} seconds"
            )
        else:
            logger.error(
                f"Error fetching volume {volume_id}: {error_message}. Time taken: {elapsed_time:.2f} seconds"
            )
        return volume_id, success, error_message if not success else None


def parallel_requests(volume_ids, num_requests=600, max_concurrent_requests=32):
    start_time = time.time()

    pool = Pool(max_concurrent_requests)  # Limit the number of concurrent greenlets
    greenlets = []

    for i in range(num_requests):
        for volume_id in volume_ids:
            greenlet = pool.spawn(fetch_volume, volume_id, i)
            greenlets.append(greenlet)

    # Wait for all greenlets to complete
    gevent.joinall(greenlets)

    end_time = time.time()
    elapsed_time = end_time - start_time
    logger.info(
        f"All requests completed. Total elapsed time: {elapsed_time:.2f} seconds"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Parallel Volume Fetcher")
    parser.add_argument(
        "--num-requests",
        type=int,
        default=64,
        help="Total number of requests to be made",
    )
    parser.add_argument(
        "--max-concurrent-requests",
        type=int,
        default=32,
        help="Maximum number of concurrent requests",
    )
    parser.add_argument("--volume-id", type=str, help="Volume ID to get")

    args = parser.parse_args()
    print(f"{args.num_requests} Requests -- {args.max_concurrent_requests} conccurent")

    volume_ids = [args.volume_id]
    parallel_requests(volume_ids, args.num_requests, args.max_concurrent_requests)
