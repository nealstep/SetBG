from datetime import datetime
from pathlib import Path
from PIL import UnidentifiedImageError
from socket import socket, timeout
from typing import Self
from watchdog.events import FileSystemEventHandler
from watchdog.observers.api import BaseObserver

from socket import AF_INET, SOCK_DGRAM

from random import seed, shuffle
from watchdog.observers import Observer

from logging import getLogger
from os import getpid, listdir, walk, mkdir
from os.path import isdir, realpath, expanduser

from os.path import join as pjoin

from setbg.common import SetBGException

from setbg.common import BG_HOME, BOUNCE, D_EXCLUDE, LNAME, SLEEP

from setbg.common import (
    base_arg_handler,
    base_args,
    check_env,
    check_image,
)
from setbg.setbg import set_background, rsbg, gen_image


NAME = "RBG"
DESC = "RBG: A Background Changer"

log = getLogger(LNAME)

ADDRESS = ("localhost", 37432)
MSG_EXIT = "X"
MSG_NEXT = "N"
WAIT = 0.25

observer: BaseObserver | None = None


def is_directory(dname: str) -> Path:
    "Return a path if its a directory"
    dpath = Path(dname).expanduser()
    if not dpath.is_dir():
        raise NotADirectoryError
    return dpath.resolve(True)


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

    def on_modified(self: Self, event):
        "rescan modified directories, ignore if less than a quarter second"
        if event.is_directory:
            if self.last_dir == event.src_path:
                if (datetime.now() - self.last_when).total_seconds() < BOUNCE:
                    return
            self.last_when = datetime.now()
            self.last_dir = event.src_path
            images.update_dir(str(event.src_path))
            images.update_images()


def signal_handler(signum: int, _) -> None:
    "handle signals"
    global observer
    log.info("Signal received, exiting")
    if observer:
        observer.stop()
    rsbg()
    exit(0)


def rbg(dirs: list[str], wait: float, notify: bool) -> None:
    "feed the background changer"
    global observer
    if notify:
        observer = Observer()
    else:
        observer = None
    # listen here
    udp_socket = socket(AF_INET, SOCK_DGRAM)
    udp_socket.bind(ADDRESS)
    udp_socket.settimeout(WAIT)
    for dn in dirs:
        dname = realpath(expanduser(dn))
        if not isdir(dname):
            log.warning("Skipping non directory: {}".format(dname))
            continue
        log.info("Adding directory: {}".format(dname))
        images.update_dir_tree(dname)
        if observer:
            observer.schedule(FSHandler(), path=dname, recursive=True)
    if images.empty:
        raise SetBGException("No images found, exiting")
    images.update_images()
    image = None
    if not images.images:
        raise SetBGException("No images found, exiting")
    if observer:
        observer.start()
    while True:
        try:
            image = images.get_next_image()
            log.info(f"Setting background to: {image}")
            print(f"Image: {image}")
            set_background(image)
            for _ in range(int(wait / WAIT)):
                try:
                    x = udp_socket.recvfrom(1024)[0].decode()
                    if x == MSG_EXIT:
                        log.info("exit requested")
                        raise KeyboardInterrupt
                    else:
                        log.info("change requested")
                        break
                except timeout:
                    pass
        except UnidentifiedImageError:
            log.warning(f"Unidentified image file, skipping: {image}")
        except SetBGException as e:
            if observer:
                observer.stop()
            raise e
        except KeyboardInterrupt:
            log.info("Exiting RBG")
            if observer:
                observer.stop()
            break


def gtbg(dirs: list[str], tree: Path) -> None:
    "Generate image tree of preset size"
    for dn in dirs:
        dname = realpath(expanduser(dn))
        if not isdir(dname):
            log.warning("Skipping non directory: {}".format(dname))
            continue
        log.info("Adding directory: {}".format(dname))
        images.update_dir_tree(dname)
    for d in images.dir_images:
        for image in images.dir_images[d]:
            log.info(f"Processing: {image}")
            img_path = tree / Path(image).relative_to(Path(d))
            if not img_path.parent.exists():
                mkdir(img_path.parent)
            img_path = img_path.with_suffix(".jpg")
            try:
                log.debug(f"Generating: {img_path}")
                gen_image(image, str(img_path))
            except UnidentifiedImageError:
                log.warning(f"Unidentified image file, skipping: {image}")
    nm_file = tree / ".nomedia"
    nm_file.touch(exist_ok=True)


# TODO #1 add run as a demon
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
            "-n",
            "--notify",
            action="store_true",
            help="Use notification for directory changes",
        )
        parser.add_argument(
            "-g",
            "--gen-tree",
            type=is_directory,
            help="Generate a tree of prescaled images",
        )
        parser.add_argument(
            "DIRS",
            nargs="+",
            help="Directories to choose images from",
        )
        args = base_arg_handler(parser)
        wait = float(args.sleep)
        notify = bool(args.notify)
        if args.gen_tree:
            assert isinstance(args.gen_tree, Path)
            gtbg(args.DIRS, args.gen_tree)
            return
        log.debug(f"sleep: {wait}")
        with open(pjoin(BG_HOME, "rbg.pid"), "w") as fp:
            fp.write(str(getpid()))
        rbg(args.DIRS, wait, notify)
        rsbg()
    except SetBGException as e:
        log.error(str(e))
        raise e


def cli_rbgn():
    parser = base_args(DESC, size=False)
    parser.add_argument("-x", "--exit", action="store_true", help="exit")
    args = base_arg_handler(parser, size=False)
    if args.exit:
        msg = MSG_EXIT
    else:
        msg = MSG_NEXT
    sock = socket(AF_INET, SOCK_DGRAM)
    sock.sendto(msg.encode(), ADDRESS)


if __name__ == "__main__":
    "run the command line interface for RBG"
    cli_rbg()
