from datetime import datetime
from pathlib import Path
from PIL import UnidentifiedImageError
from socket import socket, timeout
from typing import Self

from watchdog.events import FileSystemEventHandler
from watchdog.observers.api import BaseObserver

from socket import AF_INET, SOCK_DGRAM

from random import seed, sample, shuffle
from watchdog.observers import Observer
from setbg.common import r, res_set, system_name, TREE_UMASK
from shutil import rmtree

from logging import getLogger
from os import getpid, listdir, system, walk, mkdir, umask
from os.path import isdir, realpath, expanduser
from yaml import safe_load

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


def is_file(fname: str) -> Path:
    "Return a path if its a file"
    fpath = Path(fname).expanduser()
    if not fpath.is_file():
        raise FileNotFoundError
    return fpath.resolve(True)


class Images:
    "Image List and Directory Handler" ""

    def __init__(self: Self) -> None:
        "initialize arrays for per directory list and flat image list"
        self.reset()
        seed()

    def reset(self: Self) -> None:
        "reset the image lists and index"
        self.dir_images: dict[str, list[str]] = {}
        self.images: list[str] = []
        self.index = 0

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

    def get_sample(self: Self, limit: int) -> list[str]:
        "get a sample of images from the list"
        if not self.images:
            raise SetBGException("No images available")
        if limit <= 0 or limit >= len(self.images):
            return self.images
        return sample(self.images, limit)


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
            # log.info(f"Setting background to: {image}")
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


def gtbg(dir: Path, tree: Path, limit: int) -> None:
    "Generate image tree of preset size"
    if not dir.is_dir():
        log.warning("Skipping non directory: {}".format(dir))
        return
    if system_name == "Linux":
        umask(TREE_UMASK)
    images.update_dir_tree(str(dir))
    images.update_images()
    log.debug(f"Processing directory: {dir}")
    imgs = images.get_sample(limit)
    log.info(f"images selected: {imgs}")
    for image in imgs:
        log.debug(f"Processing: {image}")
        img_path = tree / Path(image).relative_to(Path(dir))
        if not img_path.parent.exists():
            mkdir(img_path.parent)
        img_path = img_path.with_suffix(".jpg")
        try:
            log.debug(f"Generating: {img_path}")
            gen_image(image, str(img_path))
        except UnidentifiedImageError:
            log.warning(f"Unidentified image file, skipping: {image}")


def make_old(dst: Path) -> None:
    if dst.exists():
        dsto = dst.with_suffix(".old")
        if dsto.exists():
            if dsto.is_dir():
                log.warning(f"removing tree: {dsto}")
                rmtree(dsto)
        dst.rename(dsto)
    dst.mkdir(exist_ok=True)


def trbg(fpath: Path, limit: int) -> None:
    "Generate image trees from a file list"
    global res_set
    if system_name == "Linux":
        umask(TREE_UMASK)
    with fpath.open("r") as file:
        setup = safe_load(file)
        res_set = True
        for dir in setup["dirs"]:
            r[0] = int(dir["res"].split("x")[0])
            r[1] = int(dir["res"].split("x")[1])
            dst = Path(dir["dst"])
            make_old(dst)
            nm_file = dst / ".nomedia"
            nm_file.touch(exist_ok=True)
            log.info(
                f"Processing: {dir['srcs']} -> {dst} ({r[0]}x{r[1]}, {limit})"
            )
            # need to pass subdirs here srcs
            subdirs = []
            for src_s in dir["srcs"]:
                src = Path(src_s).expanduser().resolve(True)
                subdirs = [x for x in src.iterdir() if x.is_dir()]
                for subd in subdirs:
                    sdst = dst / subd.name
                    log.info(f"Processing subdir: {subd} -> {sdst}")
                    sdst.mkdir(exist_ok=True)
                    gtbg(subd, sdst, limit)
                    images.reset()


# TODO #1 add run as a demon
def cli_rbg() -> None:
    "handle command line arguments for RBG"
    log.info("{} Started".format(NAME))
    try:
        check_env()
        parser = base_args(DESC)
        parser.add_argument(
            "-s",
            "--sleep",
            default=SLEEP,
            help="Time to pause between images",
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
            "-t",
            "--tree-generation",
            type=is_file,
            help="Generate image tree from file list (add dummy dir to cli)",
        )
        parser.add_argument(
            "-l",
            "--limit",
            default=0,
            help="Limit the number of images in generated tree",
        )
        parser.add_argument(
            "DIRS",
            nargs="+",
            help="Directories to choose images from",
        )
        args = base_arg_handler(parser)
        wait = float(args.sleep)
        notify = bool(args.notify)
        limit = int(args.limit)
        if args.gen_tree:
            assert isinstance(args.gen_tree, Path)
            make_old(args.gen_tree)
            for dir in args.DIRS:
                d = Path(dir).expanduser().resolve(True)
                gtbg(d, args.gen_tree, limit)
                images.reset()
            return
        if args.tree_generation:
            assert isinstance(args.tree_generation, Path)
            trbg(args.tree_generation, limit)
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
