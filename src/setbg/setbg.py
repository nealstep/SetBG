from PIL.Image import Resampling, Transpose, Image
from setbg.common import SetBGException

from setbg.common import (
    BG_HOME,
    BG_NAME,
    BG_SWITCH,
    ENC,
    FLIP_FIRST,
    LNAME,
    RSBG_IMG,
    SCALE_MAX,
    TOLERANCE,
)
from setbg.common import r, system_name, window_manager

from logging import getLogger
from math import ceil, floor
from os import remove, symlink
from os.path import exists
from PIL.ImageOps import crop, expand
from setbg.common import (
    base_arg_handler,
    base_args,
    check_env,
    check_image,
)
from subprocess import check_call, check_output

from os.path import join as pjoin
from PIL.Image import open as imopen, new as imnew

NAME = "SetBG"
DESC = "SetBG: A Background Setter"

log = getLogger(LNAME)


def scale_image(img: Image, size: tuple[int, int]) -> Image:
    "scale image to fit screen resolution"
    ratios: list[float] = [0, 0]
    isize: list[int] = [0, 0]
    for ra in range(len(ratios)):
        ratios[ra] = size[ra] / float(img.size[ra])
    ratio = min(ratios)
    if ratio > SCALE_MAX:
        ratio = SCALE_MAX
    log.debug(f"scale ratios: {ratios} -> {ratio}")
    scale = 0
    for i in range(len(isize)):
        isize[i] = int(round(img.size[i] * ratio))
        if abs(isize[i] - r[i]) < TOLERANCE:
            isize[i] = r[i]
        if isize[i] > img.size[i]:
            scale = 1
        elif isize[i] < img.size[i]:
            scale = -1
    if scale:
        log.debug(f"scale to new size: {isize}")
        if scale > 0:
            scaled_img = img.resize(isize, Resampling.BICUBIC)
        else:
            scaled_img = img.resize(isize, Resampling.LANCZOS)
    else:
        scaled_img = img
    log.debug(f"scaled size: {scaled_img.size}")
    return scaled_img


def tile_image(img: Image, size: tuple[int, int], rfunc=floor):
    "tile image to fit screen resolution"
    ratios: list[float] = [0, 0]
    for ra in range(len(ratios)):
        ratios[ra] = int(rfunc(size[ra] / float(img.size[ra])))
    log.debug(f"tile ratios: {ratios}")
    if not all([x == 1 for x in ratios]):
        isize = (
            round(img.size[0] * ratios[0]),
            round(img.size[1] * ratios[1]),
        )
        tiled_img = imnew("RGB", isize)
        # if we are tiling add border
        try:
            img = crop(img, border=1)
            img = expand(img, border=1, fill="black")
        except Exception as e:
            print(img.info)
            log.error(f"exception (): {e}")
            exit(1)
        for x in range(round(ratios[0])):
            x_loc = img.size[0] * x
            for y in range(round(ratios[1])):
                y_loc = img.size[1] * y
                if FLIP_FIRST:
                    flip = 1
                else:
                    flip = 0
                if (x + flip) % 2:
                    tiled_img.paste(img, (x_loc, y_loc))
                else:
                    tiled_img.paste(
                        img.transpose(Transpose.FLIP_LEFT_RIGHT),
                        (x_loc, y_loc),
                    )
    else:
        tiled_img = img
    log.debug(f"tiled size: {tiled_img.size}")
    return tiled_img


def make_strip(orig: Image, size: tuple[int, int]):
    log.debug(f"strip size: {size}")
    base_img = scale_image(orig, size)
    tiled_img = tile_image(base_img, size, rfunc=ceil)
    return tiled_img


def x_stripe(
    x_strip: int,
    orig: Image,
    x_size: int,
    striped_img: Image,
    size: tuple[int, int],
):
    log.debug("x stripe: {x_size}")
    xs_size = (x_strip, size[1])
    x_img = make_strip(orig, xs_size)
    striped_img.paste(x_img.transpose(Transpose.FLIP_LEFT_RIGHT), (0, 0))
    striped_img.paste(x_img, (x_strip + x_size, 0))
    return


def stripe_image(img: Image, orig: Image, size: tuple[int, int]) -> Image:
    "add stripes to image"
    x_strip = int(((size[0] - img.size[0]) / 2) + 0.9)
    y_strip = int(size[1] - img.size[1])
    log.debug(f"strips: {x_strip} {y_strip}")
    if x_strip or y_strip:
        striped_img = imnew("RGB", size)
        if x_strip and y_strip:
            log.debug("dual strips")
            x_stripe(x_strip, orig, img.size[0], striped_img, size)
            ys_size = (size[0] - (x_strip * 2), y_strip)
            log.debug("y strip")
            y_img = make_strip(orig, ys_size)
            striped_img.paste(y_img, (x_strip, 0))
            striped_img.paste(img, (x_strip, y_strip))
        elif x_strip:
            log.debug("single x strip")
            x_stripe(x_strip, orig, img.size[0], striped_img, size)
            striped_img.paste(img, (x_strip, 0))
        elif y_strip:
            log.debug("single y strip")
            ys_size = (size[0], y_strip)
            y_img = make_strip(orig, ys_size)
            striped_img.paste(y_img, (0, 0))
            striped_img.paste(img, (0, y_strip))
    else:
        striped_img = img
    return striped_img


def xfwm4(bg_name: str) -> None:
    "set background xfwm4"
    bg1_name = pjoin(BG_HOME, BG_SWITCH[0])
    bg2_name = pjoin(BG_HOME, BG_SWITCH[1])
    if exists(bg1_name):
        remove(bg1_name)
        if exists(bg2_name):
            # clean both exist not good
            remove(bg2_name)
        # choose bg2
        # copy(bg_name, bg2_name)
        try:
            symlink(BG_NAME, bg2_name)
        except OSError:
            log.warning(
                f"Failed to create symlink: {BG_NAME} -> {BG_SWITCH[1]}"
            )
        bg_name = bg2_name
    else:
        if exists(bg2_name):
            remove(bg2_name)
        # choose bg1
        # copy(bg_name, bg1_name)
        try:
            symlink(BG_NAME, bg1_name)
        except OSError:
            log.warning(
                f"Failed to create symlink: {BG_NAME} -> {BG_SWITCH[0]}"
            )
        bg_name = bg1_name
    lines = check_output(
        ["xfconf-query", "--channel", "xfce4-desktop", "--list"]
    ).decode(ENC)
    for line in lines.split("\n"):
        prop = line.strip()
        if prop.find("image-style") > 0:
            check_call(
                ["xfconf-query", "--channel", "xfce4-desktop", "--property"]
                + [prop, "--set", "1"]
            )
        if prop.find("last-image") > 0 or prop.find("image-path") > 0:
            check_call(
                ["xfconf-query", "--channel", "xfce4-desktop", "--property"]
                + [prop, "--set", bg_name]
            )


def windows(bg_name: str) -> None:
    "set background for Windows"
    from ctypes import windll  # type: ignore

    windll.user32.SystemParametersInfoW(20, 0, bg_name, 3)


def gen_image(img: str, dst: str) -> None:
    "generate background image of preset size"
    log.debug(f"Generating image: {dst}")
    image: Image = imopen(img)
    if image.mode != "RGB":
        image = image.convert("RGB")
    log.debug(f"image size: {image.size}")
    res = (r[0], r[1])
    print(f"Screen resolution: {res[0]}x{res[1]}")
    new_img = scale_image(image, res)
    new_img = tile_image(new_img, res)
    new_img = stripe_image(new_img, image, res)
    new_img.save(dst)


def set_background(img: str) -> None:
    "set background image"
    log.debug(f"image file: {img}")
    bg_name = pjoin(BG_HOME, BG_NAME)
    gen_image(img, bg_name)
    if system_name == "Linux":
        if window_manager[0] == "Xfwm4":
            xfwm4(bg_name)
        else:
            raise SetBGException(f"Unsupported Linux WM: {window_manager[0]}")
    elif system_name == "Windows":
        windows(bg_name)
    else:
        raise SetBGException(f"Unsupported OS: {system_name}")


def cli_setbg() -> None:
    "main entry point for SetBG CLI"
    try:
        check_env()
        parser = base_args(DESC)
        parser.add_argument("FILE", help="File to set on background")
        args = base_arg_handler(parser)
        img = check_image(args.FILE, True)
        set_background(img)
    except SetBGException as e:
        log.error(str(e))


def rsbg() -> None:
    "set background to default image"
    set_background(RSBG_IMG)


def cli_rsbg() -> None:
    "main entry point for RSBG CLI"
    try:
        check_env()
        parser = base_args(DESC)
        base_arg_handler(parser)
        rsbg()
    except SetBGException as e:
        log.error(str(e))


if __name__ == "__main__":
    "Run as a script to set background from command line"
    cli_setbg()
