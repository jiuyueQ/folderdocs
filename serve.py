import argparse
from waitress import serve
from folderdocs.wsgi import application

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8765)
    args = parser.parse_args()
    print(f'FolderDocs: http://127.0.0.1:{args.port}', flush=True)
    serve(application, host='127.0.0.1', port=args.port, threads=4, max_request_body_size=525 * 1024 * 1024)
