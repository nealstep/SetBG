from argparse import ArgumentParser, Namespace

from logging import INFO, WARNING, DEBUG
from os import devnull

from glob import glob
from logging import basicConfig, getLogger
from mimetypes import guess_type
from os import mkdir
from os.path import expanduser, exists, isdir, isfile, realpath
from platform import system
from screeninfo import get_monitors
from shutil import which
from subprocess import check_output

# constants
LNAME = "SetBG"
BG_HOME = expanduser("~/.bg")
BG_NAME = "bg.jpg"
RSBG_IMG = glob(expanduser("~/Documents/RSBG.*"))[0]
RESOLUTION = "1920x1080"
ENC = "utf-8"
SLEEP = 180
LG_FORMAT = "%(levelname)s:%(name)s:%(message)s"
D_EXCLUDE = set([".thumbnails"])
LG_LEVELS = {"info": INFO, "warning": WARNING, "debug": DEBUG}
LG_LEVEL = "warning"
SCALE_MAX = 2
FLIP_FIRST = False
TEXT_POS = "10,10"
WM_NAME = 'wmctrl -m | grep Name | cut -f 2 -d " "'

# globals
res_set = False
w = h = 2**20  # default to a large value
r: list[int] = [0, 0]
system_name = system()
window_manager: list[str] = []

basicConfig(level=LG_LEVELS[LG_LEVEL], format=LG_FORMAT, encoding=ENC)
log = getLogger(LNAME)


class SetBGException(Exception):
    pass


def base_args(desc: str) -> ArgumentParser:
    parser = ArgumentParser(description=desc)
    parser.add_argument(
        "-S",
        "--size",
        default=RESOLUTION,
        help=f"Overide screen size. Default ({RESOLUTION})",
    )
    parser.add_argument(
        "-L",
        "--log-level",
        choices=LG_LEVELS,
        default=LG_LEVEL,
        help=f"Log level default ({LG_LEVEL}): {', '.join(LG_LEVELS)}",
    )
    return parser


def check_image(image: str, check_exists=False) -> str:
    image = realpath(expanduser(image))
    if check_exists:
        if not isfile(image):
            raise SetBGException(f"{image} does not exist")
    mt = guess_type(image)
    if mt[0] and not mt[0].startswith("image"):
        raise SetBGException(f"{image} not an image")
    return image


def check_env() -> None:
    global window_manager, RSBG_IMG
    if not exists(BG_HOME):
        mkdir(BG_HOME)
    else:
        if not isdir(BG_HOME):
            raise SetBGException(f"{BG_HOME} not a directory")
    RSBG_IMG = check_image(RSBG_IMG)
    if system_name == "Linux":
        if not which("wmctrl"):
            raise SetBGException("wmctrl not found")
        with open(devnull, "w") as null:
            output = check_output(WM_NAME, shell=True, stderr=null).strip()
            window_manager.append(output.decode(ENC))


def get_resolution(res: str) -> None:
    "get the system resolution"
    global res_set, w, h
    if res_set:
        return
    res_set = True
    for m in get_monitors():
        if m.width < w:
            w = m.width
        if m.height < h:
            h = m.height
    if w == 2**20 or h == 2**20:
        (wd, hd) = res.split("x")
        w = int(wd)
        h = int(hd)
        log.warning("Unable to determine screen resolution, using default")
    r[0] = w
    r[1] = h
    log.debug(f"screen resolution {r[0]}x{r[1]}")


def base_arg_handler(parser: ArgumentParser) -> Namespace:
    args = parser.parse_args()
    if args.log_level:
        log.setLevel(LG_LEVELS[args.log_level])
    get_resolution(args.size)
    return args
