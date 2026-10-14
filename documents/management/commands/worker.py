import time
from django.core.management.base import BaseCommand
from django.db import OperationalError, close_old_connections
from documents.processing import process_next


class Command(BaseCommand):
    help = 'Process queued documents in a Windows-compatible Python worker.'

    def add_arguments(self, parser):
        parser.add_argument('--once', action='store_true', help='Process at most one document.')
        parser.add_argument('--drain', action='store_true', help='Process the queue and exit.')

    def handle(self, *args, **options):
        self.stdout.write('FolderDocs worker ready. Ctrl+C to stop.')
        try:
            while True:
                close_old_connections()
                try:
                    worked = process_next()
                except OperationalError:
                    if options['once'] or options['drain']:
                        raise
                    time.sleep(2)
                    continue
                if options['once'] or (options['drain'] and not worked):
                    break
                if not worked:
                    time.sleep(2)
        except KeyboardInterrupt:
            self.stdout.write('Worker stopped.')
