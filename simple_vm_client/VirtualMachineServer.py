import signal
import ssl
import sys

import click
import yaml
from thrift.protocol import TBinaryProtocol
from thrift.server import TServer
from thrift.transport import TSocket, TSSLSocket, TTransport

from simple_vm_client.VirtualMachineHandler import VirtualMachineHandler
from simple_vm_client.VirtualMachineService import Processor

USERNAME = "OS_USERNAME"
PASSWORD = "OS_PASSWORD"
PROJECT_NAME = "OS_PROJECT_NAME"
PROJECT_ID = "OS_PROJECT_ID"
USER_DOMAIN_ID = "OS_USER_DOMAIN_NAME"
AUTH_URL = "OS_AUTH_URL"
PROJECT_DOMAIN_ID = "OS_PROJECT_DOMAIN_ID"
FORC_API_KEY = "FORC_API_KEY"


@click.command()
@click.argument("config")
def startServer(config: str) -> None:
    def catch_shutdown(signal: int, frame: object) -> None:
        click.echo(f"Caught SIGTERM. Shutting down. Signal: {signal} Frame: {frame}")
        handler.keyboard_interrupt_handler_playbooks()
        click.echo("SIGTERM was handled. Exiting with Exitcode: -1.")
        sys.exit(-1)

    signal.signal(signal.SIGTERM, catch_shutdown)
    click.echo("Start Cloud-Client-Portal Server")

    CONFIG_FILE = config
    with open(CONFIG_FILE, "r") as ymlfile:
        cfg = yaml.load(ymlfile, Loader=yaml.SafeLoader)
        HOST = cfg["server"]["host"]
        PORT = cfg["server"]["port"]
        USE_SSL = cfg["server"].get("use_ssl", True)
        if USE_SSL:
            CERTFILE = cfg["server"]["certfile"]
            CA_CERTS_PATH = cfg["server"].get("ca_certs_path", None)

        THREADS = cfg["server"]["threads"]
    click.echo(f"Server is running on port {PORT}")
    handler = VirtualMachineHandler(CONFIG_FILE)
    processor = Processor(handler)

    if USE_SSL:
        click.echo("Use SSL")
        ssl_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
        ssl_context.load_cert_chain(CERTFILE)
        if CA_CERTS_PATH:
            click.echo("CA Certs present. Verify...")
            ssl_context.load_verify_locations(CA_CERTS_PATH)

        transport = TSSLSocket.TSSLServerSocket(
            host=HOST, port=PORT, ssl_context=ssl_context
        )
    else:
        click.echo("Does not use SSL")
        transport = TSocket.TServerSocket(host=HOST, port=PORT)
    tfactory = TTransport.TBufferedTransportFactory()
    pfactory = TBinaryProtocol.TBinaryProtocolFactory()
    server = TServer.TThreadPoolServer(
        processor, transport, tfactory, pfactory, daemon=True
    )
    server.setNumThreads(THREADS)
    click.echo(f"Started with {THREADS} threads!")

    server.serve()


if __name__ == "__main__":
    startServer()
