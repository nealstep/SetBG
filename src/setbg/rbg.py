from datetime import datetime
from PIL import UnidentifiedImageError
from setbg.common import SetBGException
from typing import Self
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from setbg.common import BG_HOME, BOUNCE, D_EXCLUDE, LNAME, SLEEP

from random import seed, shuffle

from logging import getLogger
from os import getpid, kill, listdir, walk
from os.path import isdir, realpath, expanduser
from setbg.common import (
    base_arg_handler,
    base_args,
    check_env,
    check_image,
)
from setbg.setbg import set_background, rsbg
from signal import signal, SIGUSR1
from time import sleep

from os.path import join as pjoin

NAME = "RBG"
DESC = "RBG: A Background Changer"

log = getLogger(LNAME)


class RBGWakeup(Exception):
    "Custom exception to wake up RBG on USR1 signal"

    pass


class Images:
    "Image List and Directory Handler" ""

    def __init__(self: Self) -> None:
        "initialize arrays for per directory list and flat image list"
        self.dir_images: dict[str, list[str]] = {}
        self.images: list[str] = []
        self.index = 0
        seed()

    @property
    def empty(self: Self) -> bool:
        "do we have any directories"
        return len(self.dir_images) == 0

    def update_images(self: Self) -> None:
        "update flat image list from directories"
        self.images = []
        for d in self.dir_images:
            self.images.extend(self.dir_images[d])
        shuffle(self.images)
        if self.index >= len(self.images):
            self.index = 0

    def update_dir_tree(self: Self, dir: str) -> None:
        "update images in a directory tree"
        log.info(f"Updating directory tree: {dir}")
        self.dir_images[dir] = []
        for root, dirs, files in walk(dir):
            dirs[:] = [d for d in dirs if d not in D_EXCLUDE]
            if files:
                for fn in files:
                    fp = pjoin(root, fn)
                    try:
                        fp = check_image(fp)
                        self.dir_images[dir].append(fp)
                    except SetBGException:
                        pass

    def update_dir(self: Self, dir: str) -> None:
        "update images in a directory"
        log.info(f"Updating directory: {dir}")
        self.dir_images[dir] = []
        files = listdir(dir)
        for fn in files:
            fp = pjoin(dir, fn)
            try:
                fp = check_image(fp)
                self.dir_images[dir].append(fp)
            except SetBGException:
                pass

    def get_next_image(self: Self) -> str:
        "get next image in the list"
        if not self.images:
            raise SetBGException("No images available")
        index = self.index
        self.index += 1
        if self.index >= len(self.images):
            self.index = 0
        return self.images[index]


images = Images()


class FSHandler(FileSystemEventHandler):
    "File System Event Handler for Directory Changes"

    last_when = datetime.now()
    last_dir = ""

    def on_modified(self, event):
        "rescan modified directories, ignore if less than a quarter second"
        if event.is_directory:
            if self.last_dir == event.src_path:
                if (datetime.now() - self.last_when).total_seconds() < BOUNCE:
                    return
            self.last_when = datetime.now()
            self.last_dir = event.src_path
            images.update_dir(event.src_path)
            images.update_images()


def signal_handler(signum, frame):
    "handle USR1 signal to update images"
    log.info("Received USR1 signal, updating images")
    raise RBGWakeup


def rbg(dirs: list[str], wait: float, notify: bool) -> None:
    "feed the background changer"
    if notify:
        observer = Observer()
    signal(SIGUSR1, signal_handler)
    for dn in dirs:
        dname = realpath(expanduser(dn))
        if not isdir(dname):
            log.warning("Skipping non directory: {}".format(dname))
            continue
        log.info("Adding directory: {}".format(dname))
        images.update_dir_tree(dname)
        if notify:
            observer.schedule(FSHandler(), path=dname, recursive=True)
    if images.empty:
        raise SetBGException("No directories found, exiting")
    images.update_images()
    if not images.images:
        raise SetBGException("No images found, exiting")
    if notify:
        observer.start()
    while True:
        try:
            image = images.get_next_image()
            print(f"Setting background to: {image}")
            set_background(image)
            sleep(wait)
        except RBGWakeup:
            log.info("Interrupted, next image")
        except UnidentifiedImageError:
            log.warning(f"Unidentified image file, skipping: {image}")
        except SetBGException as e:
            if notify:
                observer.stop()
            raise e
        except KeyboardInterrupt:
            log.info("Exiting RBG")
            if notify:
                observer.stop()
            break


def cli_rbg() -> None:
    "handle command line arguments for RBG"
    log.info("{} Started".format(NAME))
    try:
        check_env()
        parser = base_args(DESC)
        parser.add_argument(
            "-s", "--sleep", default=SLEEP, help="Time to pause between images"
        )
        parser.add_argument(
            "-n", "--notify", action="set_true", help="Use notification for directory changes"
        )
        parser.add_argument(
            "DIRS", nargs="+", help="Directories to choose images from"
        )
        args = base_arg_handler(parser)
        wait = float(args.sleep)
        notify = bool(args.notify)
        log.debug(f"sleep: {wait}")
        with open(pjoin(BG_HOME, "rbg.pid"), "w") as fp:
            fp.write(str(getpid()))
        rbg(args.DIRS, wait, notify)
        rsbg()
    except SetBGException as e:
        log.error(str(e))
        raise e


def cli_rbgn():
    with open(pjoin(BG_HOME, "rbg.pid")) as fp:
        pid = int(fp.read())
        kill(pid, SIGUSR1)


if __name__ == "__main__":
    "run the command line interface for RBG"
    cli_rbg()
