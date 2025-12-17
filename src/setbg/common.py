from argparse import ArgumentParser, Namespace

from logging import INFO, WARNING, DEBUG
from os import devnull

from glob import glob
from importlib.metadata import version
from logging import basicConfig, getLogger
from mimetypes import guess_type
from os import mkdir
from os.path import expanduser, exists, isdir, isfile, realpath
from platform import system
from screeninfo import get_monitors
from shutil import which
from subprocess import check_output

# constants
BG_HOME = expanduser("~/.bg")  # directory to store computed images
BG_NAME = "bg.jpg"  # name of computed image
BOUNCE = 0.25  # bounce time for directory scans
D_EXCLUDE = set(
    [".thumbnails", "@eaDir"]
)  # directories to exclude from search
ENC = "utf-8"  # default encoding
FLIP_FIRST = False  # Flip first image in tiling operation
LG_FORMAT = "%(levelname)s:%(name)s:%(message)s"  # default log format
LG_LEVEL = "warning"  # default log level
LG_LEVELS = {"info": INFO, "warning": WARNING, "debug": DEBUG}
LNAME = "SetBG"  # logger name
RESOLUTION = "1920x1080"  # default resolution
RSBG_IMG = glob(expanduser("~/Documents/RSBG.*"))[0]  # default image to use
SCALE_MAX = 2  # maximum scale factor for images
SLEEP = 300  # default sleep time
WM_NAME = 'wmctrl -m | grep Name | cut -f 2 -d " "'  # Get WM name
TOLERANCE = 10  # pixels tolerance for resolution matching

# globals
r: list[int] = [0, 0]  # resolution
res_set = False  # has the resolution been set?
system_name = system()  # system name
w = h = 2**20  # default to a large value
window_manager: list[str] = []  # window manager name

# Set up logging
basicConfig(level=LG_LEVELS[LG_LEVEL], format=LG_FORMAT, encoding=ENC)
log = getLogger(LNAME)


class SetBGException(Exception):
    """Custom exception for SetBG errors."""

    pass


def check_image(image: str, check_exists=False) -> str:
    "check image exists and is an image"
    image = realpath(expanduser(image))
    if check_exists:
        if not isfile(image):
            raise SetBGException(f"{image} does not exist")
    mt = guess_type(image)
    if mt[0] and mt[0].startswith("image"):
        pass
    else:
        raise SetBGException(f"{image} not an image")
    return image


def check_env() -> None:
    "check the environment is setup"
    global window_manager, RSBG_IMG
    if not exists(BG_HOME):
        mkdir(BG_HOME)
    else:
        if not isdir(BG_HOME):
            raise SetBGException(f"{BG_HOME} not a directory")
    RSBG_IMG = check_image(RSBG_IMG)
    log.debug(f"System name: {system_name}")
    if system_name == "Linux":
        if not which("wmctrl"):
            raise SetBGException("wmctrl not found, please install")
        with open(devnull, "w") as null:
            output = check_output(WM_NAME, shell=True, stderr=null).strip()
            window_manager.append(output.decode(ENC))
            log.debug(f"Window manager: {window_manager[0]}")


def get_resolution(res: str) -> None:
    "get the system resolution"
    global res_set, w, h, r
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


def base_args(desc: str, size=True) -> ArgumentParser:
    "standard arguments for SetBG and RSBG"
    parser = ArgumentParser(description=desc)
    if size:
        parser.add_argument(
            "-S",
            "--size",
            default=RESOLUTION,
            help=f"Overide screen size. Default ({RESOLUTION})",
        )
    parser.add_argument(
        "--version",
        action="version",
        help="show version number",
        version=version("setbg"),
    )
    parser.add_argument(
        "-L",
        "--log-level",
        choices=LG_LEVELS,
        default=LG_LEVEL,
        help=f"Log level default ({LG_LEVEL}): {', '.join(LG_LEVELS)}",
    )
    return parser


def base_arg_handler(parser: ArgumentParser, size=True) -> Namespace:
    "handle base arguments for SetBG and RSBG"
    args = parser.parse_args()
    log.debug(f"Arguments: {args}")
    if args.log_level:
        log.setLevel(LG_LEVELS[args.log_level])
    if size:
        if args.size:
            res_set = True  # noqa: F841
            r[0] = int(args.size.split("x")[0])
            r[1] = int(args.size.split("x")[1])
            log.debug(f"Using resolution: {r[0]}x{r[1]}")
        else:
            get_resolution(args.size)
    return args
