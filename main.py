import base64
import hashlib
import os
import os.path as osp
import re
import shutil
import subprocess
import tempfile

from urllib.parse import quote, unquote
from urllib.request import urlopen
try:
    from typing import List, Optional, Tuple
    assert List and Optional and Tuple
except ImportError:
    pass

import sublime  # type: ignore
import sublime_plugin  # type: ignore

from sublime import View

from .utils.get_image_size import get_image_size, UnknownImageFormat  # type: ignore
from .utils.settings import Settings  # type: ignore


TEMPLATE = """
    <img style="width: %dpx;height: %dpx;" src="data:image/%s;base64,%s">
    <div>%dx%d %s</div>
    <div>
        <a href="open">Open</a> | <a href="save">Save</a> | <a href="save_as">Save as</a>
    </div>
    """
TEMP_DIR = tempfile.gettempdir()
IMAGE_DATA_URL_RE = re.compile(r"data:image/(jpeg|png|gif|bmp);base64,"
                               r"([a-zA-Z0-9+/ ]+={0,2})")
image_url_re = re.compile("")
image_file_re = re.compile("")
image_file_name_re = re.compile("")
all_formats = []  # type: List[str]
format_to_convert = ()  # type: Tuple[str, ...]


def on_change(s):
    global all_formats,\
        format_to_convert,\
        image_url_re,\
        image_file_re,\
        image_file_name_re

    Settings.update(s)
    all_formats = ["png", "jpg", "jpeg", "bmp",
                   "gif"] + Settings.formats_to_convert
    format_to_convert = tuple('.' + ext for ext in Settings.formats_to_convert)
    formats_ored = '|'.join(all_formats)
    image_url_re = re.compile(r"(?:(https?)://)?"                  # http(s)://
                              r"(?:[^./\"'\s]+\.){1,3}[^/\"'.\s]+/"     # host
                              r"(?:[^/\"'\s]+/)*"                       # path
                              r"([^\"'/\s]+?\.(?:%s))" % formats_ored)  # name

    image_file_re = re.compile(r"(?:"            # drive
                               r"\w:\\|"         # Windows (e.g C:\)
                               r"\\\\|"          # Linux (\\)
                               r"\.{0,2}[\\/]"   # Mac OS and/or relative
                               r")"
                               r"(?:[-.@\w]+?[\\/])*"      # body
                               r"[-.@\w]+?"                # name
                               r"\.(?:%s)" % formats_ored  # extension
                               )
    image_file_name_re = re.compile(r"[-.@\w]+"                 # name
                                    r"\.(?:%s)" % formats_ored  # extension
                                    )


def plugin_loaded():
    loaded_settings = sublime.load_settings("Image Preview.sublime-settings")
    loaded_settings.clear_on_change("image_preview")
    on_change(loaded_settings)
    loaded_settings.add_on_change(
        "image_preview", lambda ls=loaded_settings: on_change(ls))


def magick(inp, out):
    """Convert the image from one format to another."""

    subprocess.call(["magick", inp, out], shell=os.name == "nt")


def get_data(view: View, path: str) -> 'Tuple[int, int, int, int, int]':
    """
    Return a tuple of (width, height, real_width, real_height, size).

    `real_width` and `real_height` are the real dimensions of the image file
    `width` and `height` are adjusted to the viewport
    `size` is the size of the image file
    """

    # Allow max automatic detection and remove gutter
    max_width, max_height = view.viewport_extent()
    max_width *= 0.75
    max_height *= 0.75
    max_ratio = max_height / max_width

    try:
        real_width, real_height, size = get_image_size(path)
    except UnknownImageFormat:
        return -1, -1, -1, -1, -1

    # First check height since it's the smallest vector
    if real_height / real_width >= max_ratio and real_height > max_height:
        width = real_width * max_height / real_height
        height = max_height
    elif real_height / real_width <= max_ratio and real_width > max_width:
        width = max_width
        height = real_height * max_width / real_width
    else:
        width = real_width
        height = real_height

    return width, height, real_width, real_height, size


def check_recursive(base_folders, name) -> 'Optional[Tuple[str, str]]':
    """
    Return the path to the base folder and the path to the file if it is
    present in the project.
    """

    for base_folder in base_folders:
        for root, dirs, files in os.walk(base_folder):
            for f in files:
                if f == name:
                    return osp.dirname(base_folder), root
    return None


def get_file(view: View, string: str, name: str) -> 'Tuple[str, Optional[str]]':
    """
    Try to get a file from the given `string` and test whether it's in the
    project directory.
    """

    # if it's an absolute path get it
    if osp.isabs(string):
        return string, None

    # if search_mode: "project", search only in project
    elif Settings.search_mode == "project":
        # Get base project folders
        base_folders = sublime.active_window().folders()
        # if "recursive": true, recursively search for the name
        if Settings.recursive:
            ch_rec = check_recursive(base_folders, name)
            if ch_rec:
                base_folder, root = ch_rec
                return osp.join(root, name), base_folder
            return "", None
        else:
            # search only in base folders for the relative path
            for base_folder in base_folders:
                file_name = osp.normpath(osp.join(base_folder, string))
                if osp.exists(file_name):
                    return file_name, base_folder
            return "", None
    # if search_mode: "file" join the relative path to the file path
    else:
        return osp.normpath(osp.join(osp.dirname(view.file_name()), string)), None


def save(file: str, name: str, kind: str, folder=None, convert=False):
    """Save the image if it's not already in the project folders."""

    # all folders in the project
    base_folders = sublime.active_window().folders()
    # create the image folder in the first folder
    image_folder = osp.join(base_folders[0], Settings.image_folder_name)
    # exact or converted copy of the image
    copy = osp.join(image_folder, name)
    # a relative version of the image_folder for display in the status message
    image_folder_rel = osp.relpath(
        image_folder, osp.dirname(base_folders[0]))

    if osp.exists(copy):
        sublime.status_message("%s is already in %s" %
                               (name, image_folder_rel))
        return

    if kind == "file" and folder:
        sublime.status_message("%s is already in %s" %
                               (name, osp.relpath(osp.dirname(file), folder)))
        return

    ch_rec = check_recursive(base_folders, name)
    if ch_rec:
        folder, root = ch_rec
        sublime.status_message("%s is already in %s" %
                               (name, osp.relpath(root, folder)))
        return

    if not osp.exists(image_folder):
        os.mkdir(image_folder)

    if convert:
        # create a converted copy
        magick(file, copy)
    else:
        # create an exact copy
        shutil.copyfile(file, copy)

    sublime.status_message("%s saved in %s" % (name, image_folder_rel))


def convert(file: str, kind: str, name=None):
    """Convert the image to the format chosen from the quick panel and save it."""

    basename, ext = osp.splitext(name or osp.basename(file))
    all_formats = Settings.all_formats.copy()
    # remove the extension of the file
    all_formats.remove(ext[1:])

    def on_done(i):
        if i != -1:
            save(file, basename + '.' + all_formats[i], kind, convert=True)

    sublime.active_window().show_quick_panel(all_formats, on_done)


def handle_as_url(view: View, point: int, string: str, name: str):
    """Handle the given `string` as a url."""

    # Let's assume this url as input:
    # (https://upload.wikimedia.org/wikipedia/commons/8/84/Example.svg)

    # Download the image
    # FIXME: avoid nested try-except clauses
    try:
        try:
            f = urlopen(unquote(string))  # <==
        except Exception:
            try:
                url_path = quote(string).replace("%3A", ':', 1)
                f = urlopen(url_path)
            except Exception:
                f = urlopen(string)
    # don't fill the console with stack-trace when there`s no connection !!
    except Exception as e:
        print(e)
        return

    # file needs conversion ?
    need_conversion = name.endswith(format_to_convert)  # => True
    basename, ext = osp.splitext(name)  # => ("Example", ".svg")
    # create a temporary file
    tmp_file = osp.join(TEMP_DIR,
                        "tmp_image" + (ext if need_conversion else ".png")
                        )  # => "TEMP_DIR/tmp_image.svg"

    # Save downloaded data in the temporary file
    content = f.read()
    with open(tmp_file, "wb") as dst:
        dst.write(content)

    # if the file needs conversion, convert it then read data from the resulting png
    if need_conversion:
        # keep the image's temporary file and name for later use
        conv_file = tmp_file  # => "TEMP_DIR/tmp_image.svg"
        conv_name = name  # => "Example.svg"

        # => "TEMP_DIR/tmp_image.png"
        png = osp.splitext(tmp_file)[0] + ".png"

        # use the magick command of Imagemagick to convert the image to png
        magick(tmp_file, png)

        # set temp_file and name to the png file
        tmp_file = png  # => "TEMP_DIR/tmp_image.png"
        name = basename + ".png"  # => "Example.png"

        # read data from the resulting png
        with open(tmp_file, "rb") as dst:
            content = dst.read()

    width, height, real_width, real_height, size = get_data(view, tmp_file)
    encoded = str(base64.b64encode(content), "utf-8")

    def on_navigate(href):

        if href == "save":
            if need_conversion:
                save(conv_file, conv_name, "url")
            else:
                save(tmp_file, name, "url")
        elif href == "save_as":
            if need_conversion:
                convert(conv_file, "url", conv_name)
            else:
                convert(tmp_file, "url", name)
        else:
            sublime.active_window().open_file(tmp_file)

    view.show_popup(
        TEMPLATE % (width, height, "png", encoded, real_width, real_height,
                    str(size // 1024)+"KB" if size >= 1024 else str(size)+'B'),
        sublime.HIDE_ON_MOUSE_MOVE_AWAY,
        point,
        *view.viewport_extent(),
        on_navigate=on_navigate
    )


def handle_as_data_url(view: View, point: int, ext: str, encoded: str):
    """Handle the string as a data url."""

    # create a temporary file
    tmp_file = osp.join(TEMP_DIR, "tmp_data_image." + ext)
    file_hash = int(hashlib.sha1(encoded.encode('utf-8')
                                 ).hexdigest(), 16) % (10 ** 8)
    name = str(file_hash) + "." + ext

    # Save downloaded data in the temporary file
    try:
        dst = open(tmp_file, "wb")
        dst.write(base64.b64decode(encoded))
    except Exception as e:
        print(e)
        return
    finally:
        dst.close()

    width, height, real_width, real_height, size = get_data(view, tmp_file)

    def on_navigate(href):

        if href == "save":
            save(tmp_file, name, "data_url")
        elif href == "save_as":
            convert(tmp_file, "data_url", name)
        else:
            sublime.active_window().open_file(tmp_file)

    view.show_popup(
        TEMPLATE % (width, height, ext, encoded, real_width, real_height,
                    str(size // 1024)+"KB" if size >= 1024 else str(size)+'B'),
        sublime.HIDE_ON_MOUSE_MOVE_AWAY,
        point,
        *view.viewport_extent(),
        on_navigate=on_navigate
    )


def handle_as_file(view: View, point: int, string: str):
    """Handle the given `string` as a file."""
    # "screenshot.png"

    name = osp.basename(string)
    file, folder = get_file(view, string, name)

    # if file doesn't exist, return
    if not osp.isfile(file):
        return

    # does the file need conversion ?
    need_conversion = file.endswith(format_to_convert)

    # if the file needs conversion, convert it and read data from the resulting png
    if need_conversion:
        # keep the image's file and name for later use
        conv_file = file
        conv_name = name

        # create a temporary file
        tmp_file = osp.join(TEMP_DIR, "tmp_png.png")
        name = osp.splitext(name)[0] + ".png"

        # use the magick command of Imagemagick to convert the image to png
        magick(file, tmp_file)

        file = tmp_file

    with open(file, "rb") as f:
        encoded = str(base64.b64encode(f.read()), "utf-8")

    width, height, real_width, real_height, size = get_data(view, file)

    def on_navigate(href):

        if href == "save":
            if need_conversion:
                save(conv_file, conv_name, "file")
            else:
                save(file, name, "file", folder)
        elif href == "save_as":
            convert(conv_file if need_conversion else file, "file")
        else:
            sublime.active_window().open_file(file)

    view.show_popup(
        TEMPLATE % (width, height, "png", encoded, real_width, real_height,
                    str(size // 1024)+"KB" if size >= 1024 else str(size)+'B'),
        sublime.HIDE_ON_MOUSE_MOVE_AWAY,
        point,
        *view.viewport_extent(),
        on_navigate=on_navigate)


def preview_image(view: View, point: int):
    """Find the image path or url and Preview the image if possible."""

    line = view.line(point)

    string = view.substr(line)
    # the offset of point relative to the start of the line
    offset_point = point - line.a

    # search for the match in the string that contains the point

    # ==================URL=====================
    for match in image_url_re.finditer(string):
        if match.start() <= offset_point <= match.end():
            string, protocol, name = match.group(0, 1, 2)
            # if the url doesn't start with http or https try adding it
            # "www.gettyimages.fr/gi-resources/images/Embed/new/embed2.jpg"
            if not protocol:
                string = "http://" + string
            # don't block ST while handling the url
            return sublime.set_timeout_async(lambda: handle_as_url(
                view, point, string, name), 0)

    # =================DATA URL=================
    for match in IMAGE_DATA_URL_RE.finditer(string):
        if match.start() <= offset_point <= match.end():
            return handle_as_data_url(view, point, *match.groups())

    # =================FILE=====================
    # find full and relative paths (e.g ./screenshot.png)
    for match in image_file_re.finditer(string):
        if match.start() <= offset_point <= match.end():
            return handle_as_file(view, point, match.group(0))

    # find file name (e.g screenshot.png)
    for match in image_file_name_re.finditer(string):
        if match.start() <= offset_point <= match.end():
            return handle_as_file(view, point, match.group(0))


class HoverPreviewImage(sublime_plugin.EventListener):

    def on_hover(self, view: View, point: int, hover_zone: int):

        if not Settings.preview_on_hover or hover_zone != sublime.HOVER_TEXT:
            return

        preview_image(view, point)


class PreviewImageCommand(sublime_plugin.TextCommand):

    def run(self, edit, event=None):
        if event:
            preview_image(self.view, self.view.window_to_text(
                (event['x'], event['y'])))
        else:
            preview_image(self.view, self.view.selection[0].a)

    def is_visible(self, event):
        point = self.view.window_to_text((event['x'], event['y']))
        line = self.view.line(point)

        string = self.view.substr(line)
        point -= line.a

        for pattern in (image_url_re, IMAGE_DATA_URL_RE,
                        image_file_re, image_file_name_re):
            for match in pattern.finditer(string):
                if match.start() <= point <= match.end():
                    return True
        return False

    def want_event(self):
        return True
