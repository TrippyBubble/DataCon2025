from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from pipeline import collecting
import time
from os import path
import ssl
import pandas as pd

try:
    _create_unverified_https_context = ssl._create_unverified_context
except AttributeError:
    # Legacy Python that doesn't verify HTTPS certificates by default
    pass
else:
    # Handle target environment that doesn't support HTTPS verification
    ssl._create_default_https_context = _create_unverified_https_context

import warnings

warnings.filterwarnings('ignore')
warnings.filterwarnings("ignore", category=DeprecationWarning)




class FileChangeHandler(FileSystemEventHandler):
    def __init__(self, file_to_watch):
        self.file_to_watch = file_to_watch

    def on_modified(self, event):
        if event.src_path.endswith(self.file_to_watch):
            print('Получены данные')
            df = pd.read_csv(path.join('data', 'new'))
            result = collecting(df)
            print("Pipeline завершён. Результат:", result)

def watch_file(file_to_watch):
    path = "./data"  # Папка для отслеживания
    event_handler = FileChangeHandler(file_to_watch)
    observer = Observer()
    observer.schedule(event_handler, path, recursive=False)
    observer.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()

if __name__ == "__main__":
    watch_file("new")  # Укажите имя файла для отслеживания





