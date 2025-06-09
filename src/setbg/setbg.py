from PIL.Image import Resampling, Transpose
from setbg.common import SetBGException

# from PIL.Image import BICUBIC, ANTIALIAS, FLIP_LEFT_RIGHT
from setbg.common import (
    RSBG_IMG,
    LNAME,
    BG_HOME,
    BG_NAME,
    ENC,
    SCALE_MAX,
    FLIP_FIRST,
)
from setbg.common import r, system_name, window_manager

from logging import getLogger
from math import ceil, floor
from PIL.ImageOps import crop, expand
from setbg.common import (
    check_env,
    check_image,
    base_args,
    base_arg_handler,
)
from subprocess import check_call, check_output

from os.path import join as pjoin
from PIL.Image import open as imopen, new as imnew

NAME = "SetBG"
DESC = "SetBG: A Background Setter"

log = getLogger(LNAME)


def scale_image(img, size):
    "scale image to fit screen resolution"
    ratios = [0, 0]
    isize = [0, 0]
    for ra in range(len(ratios)):
        ratios[ra] = size[ra] / float(img.size[ra])
    ratio = min(ratios)
    if ratio > SCALE_MAX:
        ratio = SCALE_MAX
    log.debug("Ratios: {} -> {}".format(ratios, ratio))
    if ratio != 1.0:
        for i in range(len(isize)):
            isize[i] = int(round(img.size[i] * ratio))
        log.debug("New Size: {}".format(isize))
        if ratio > 1.0:
            scaled_img = img.resize(isize, Resampling.BICUBIC)
        else:
            scaled_img = img.resize(isize, Resampling.LANCZOS)
    else:
        scaled_img = img
    log.info("Scaled size: {}".format(scaled_img.size))
    return scaled_img


def tile_image(img, size, rfunc=floor):
    "tile image to fit screen resolution"
    ratios = [0, 0]
    for ra in range(len(ratios)):
        ratios[ra] = int(rfunc(size[ra] / float(img.size[ra])))
    log.debug("Ratios: {}".format(ratios))
    if not all([x == 1 for x in ratios]):
        isize = (img.size[0] * ratios[0], img.size[1] * ratios[1])
        tiled_img = imnew("RGB", isize)
        # if we are tiling add border
        img = crop(img, border=1)
        img = expand(img, border=1, fill="black")
        for x in range(ratios[0]):
            x_loc = img.size[0] * x
            for y in range(ratios[1]):
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
    return tiled_img


def make_strip(orig, size):
    log.debug("Strip: {}".format(size))
    base_img = scale_image(orig, size)
    tiled_img = tile_image(base_img, size, rfunc=ceil)
    return tiled_img


def x_stripe(x_strip, orig, x_size, striped_img, size):
    log.debug("X Stripe")
    xs_size = (x_strip, size[1])
    x_img = make_strip(orig, xs_size)
    striped_img.paste(x_img.transpose(Transpose.FLIP_LEFT_RIGHT), (0, 0))
    striped_img.paste(x_img, (x_strip + x_size, 0))
    return


def stripe_image(img, orig, size):
    "add stripes to image"
    x_strip = int(((size[0] - img.size[0]) / 2) + 0.9)
    y_strip = int(size[1] - img.size[1])
    log.debug("Strips: {} {}".format(x_strip, y_strip))
    if x_strip or y_strip:
        striped_img = imnew("RGB", size)
        if x_strip and y_strip:
            log.debug("Dual Strips")
            x_stripe(x_strip, orig, img.size[0], striped_img, size)
            ys_size = (size[0] - (x_strip * 2), y_strip)
            log.debug("Y Strip")
            y_img = make_strip(orig, ys_size)
            striped_img.paste(y_img, (x_strip, 0))
            striped_img.paste(img, (x_strip, y_strip))
        elif x_strip:
            log.debug("Single X Strip")
            x_stripe(x_strip, orig, img.size[0], striped_img, size)
            striped_img.paste(img, (x_strip, 0))
        elif y_strip:
            log.debug("Single Y Strip")
            ys_size = (size[0], y_strip)
            y_img = make_strip(orig, ys_size)
            striped_img.paste(y_img, (0, 0))
            striped_img.paste(img, (0, y_strip))
    else:
        striped_img = img
    return striped_img


def xfwm4(bg_name: str) -> None:
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
    from ctypes import windll  # type: ignore

    windll.user32.SystemParametersInfoW(20, 0, bg_name, 3)


def set_background(img: str) -> None:
    log.debug(f"image file: {img}")
    image = imopen(img)
    log.debug("image size {}x{}".format(*image.size))
    bg_name = pjoin(BG_HOME, BG_NAME)
    new_img = scale_image(image, r)
    new_img = tile_image(new_img, r)
    new_img = stripe_image(new_img, image, r)
    new_img.save(bg_name)
    if system_name == "Linux":
        if window_manager[0] == "Xfwm4":
            xfwm4(bg_name)
        else:
            raise SetBGException(
                f"Unsupported WM for setting background: {window_manager[0]}"
            )
    elif system_name == "Windows":
        windows(bg_name)
    else:
        raise SetBGException(
            f"Unsupported OS for setting background: {system_name}"
        )


def cli_setbg() -> None:
    try:
        check_env()
        parser = base_args(DESC)
        parser.add_argument("FILE", help="File to set on background")
        args = base_arg_handler(parser)
        img = check_image(args.FILE, True)
        set_background(img)
    except SetBGException as e:
        log.error(str(e))
        raise e


def rsbg() -> None:
    set_background(RSBG_IMG)


def cli_rsbg() -> None:
    try:
        check_env()
        parser = base_args(DESC)
        base_arg_handler(parser)
        rsbg()
    except SetBGException as e:
        log.error(str(e))
        raise e


if __name__ == "__main__":
    cli_setbg()
