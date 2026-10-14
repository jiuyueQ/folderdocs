import argparse
import socket
from waitress import serve
from folderdocs.wsgi import application

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8765)
    args = parser.parse_args()
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    if hasattr(socket, 'SO_EXCLUSIVEADDRUSE'):
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
    listener.bind(('127.0.0.1', args.port))
    listener.listen(128)
    print(f'FolderDocs: http://127.0.0.1:{args.port}', flush=True)
    try:
        serve(application, sockets=[listener], threads=4, max_request_body_size=525 * 1024 * 1024)
    finally:
        listener.close()
