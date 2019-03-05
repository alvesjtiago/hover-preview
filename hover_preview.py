import base64
import re
import os
import tempfile
import subprocess
import shutil
import hashlib
from urllib.parse import quote, unquote
from urllib.request import urlopen

import sublime
import sublime_plugin

from .get_image_size import get_image_size, UnknownImageFormat


TEMPLATE = """
    <a href="resize">
        <img style="width: %dpx;height: %dpx;" src="data:image/png;base64,%s">
    </a>
    <div>%dx%d %dKB</div>
    <div>
        <a href="open">Open</a> | <a href="save">Save</a> | <a href="save_as">Save as</a>
    </div>
    """

DATA_URL_TEMPLATE = """
    <a href="resize">
        <img style="width: %dpx;height: %dpx;" src="data:image/%s;base64,%s">
    </a>
    <div>%dx%d %dKB</div>
    <div>
        <a href="open">Open</a> | <a href="save">Save</a> | <a href="save_as">Save as</a>
    </div>
    """

IMAGE_DATA_URL_RE = re.compile(
    r"data:image/(jpeg|png|gif|bmp);base64,([a-zA-Z0-9+/]+={0,2})")


def hover_preview_callback():
    """Get the settings and store them in global variables."""

    global MAX_WIDTH, MAX_HEIGHT, FORMAT_TO_CONVERT, ALL_FORMATS,\
        IMAGE_FOLDER_NAME, SEARCH_MODE, RECURSIVE, IMAGE_PATH_RE, IMAGE_URL_RE

    default_formats = ["png", "jpg", "jpeg",
                       "bmp", "gif", "ico", "svg", "svgz", "webp"]
    MAX_WIDTH, MAX_HEIGHT = settings.get("max_dimensions", [320, 240])
    FORMAT_TO_CONVERT = tuple(settings.get(
        "formats_to_convert", [".svg", ".svgz", ".webp"]))
    ALL_FORMATS = "|".join(settings.get('all_formats', default_formats))
    IMAGE_FOLDER_NAME = settings.get("image_folder_name", "Hovered Images")
    SEARCH_MODE = settings.get("search_mode", "project")
    RECURSIVE = settings.get("recursive", True)
    IMAGE_PATH_RE = re.compile(r"([-@\w.]+\.(?:" + ALL_FORMATS + "))")
    IMAGE_URL_RE = re.compile(
        r"(?:(https?):)?//[^\"']+/([^\"']+?\.(?:" + ALL_FORMATS + "))")


def plugin_loaded():
    global settings

    settings = sublime.load_settings("Hover Preview.sublime-settings")
    settings.clear_on_change("hover_preview")
    hover_preview_callback()
    settings.add_on_change("hover_preview", hover_preview_callback)


def magick(inp, out):
    """Convert the image from one format to another."""

    subprocess.call(["magick", inp, out], shell=os.name == "nt")


def get_dimensions(view: sublime.View, path: str) -> (int, int):
    """Return the width and height from the given path."""

    # Allow max automatic detection and remove gutter
    max_width, max_height = view.viewport_extent()
    max_width *= 0.75
    max_height *= 0.75
    max_ratio = max_height / max_width

    # Get image get_dimensions
    try:
        width, height, _ = get_image_size(path)
    except UnknownImageFormat:
        return (-1, -1)

    # First check height since it's the smallest vector
    if height / width >= max_ratio and height > max_height:
        ratio = max_height / height
        width *= ratio
        height *= ratio
    elif height / width <= max_ratio and width > max_width:
        ratio = max_width / width
        width *= ratio
        height *= ratio

    return (width, height)


def fix_oversize(width: int, height: int) -> (int, int):
    """Shrink the popup if its bigger than max_width x max_height."""

    new_width, new_height = width, height
    if width > MAX_WIDTH or height > MAX_HEIGHT:
        if width > height:
            ratio = MAX_WIDTH / width
            new_width = MAX_WIDTH
            new_height = height * ratio
        else:
            ratio = MAX_HEIGHT / height
            new_height = MAX_HEIGHT
            new_width = width * ratio
    return (new_width, new_height)


def get_string(view: sublime.View, point: int) -> str:
    """Return the string of the region containing `point` and delimeted by "", '' or ()."""

    next_double_quote = view.find('"', point).a
    next_single_quote = view.find("'", point).a
    next_parentheses = view.find(r"\)", point).a

    symbols_dict = {
        next_double_quote: '"',
        next_single_quote: "'",
        next_parentheses: ')'
    }

    symbols = []
    if next_double_quote != -1:
        symbols.append(next_double_quote)
    if next_single_quote != -1:
        symbols.append(next_single_quote)
    if next_parentheses != -1:
        symbols.append(next_parentheses)

    # Check if symbols exist from the mouse pointer forward
    if not symbols:
        return

    closest_symbol = min(symbols)
    symbol = symbols_dict[closest_symbol]

    # All quotes in view
    all_quotes = view.find_all(r"\(|\)" if symbol == ')' else symbol)

    # Get the final region of quoted string
    for item in all_quotes:
        if item.a == closest_symbol:
            final_region = item
            break
    # If there are no matches return
    else:
        return

    # Get the initial region of quoted string
    initial_region = all_quotes[all_quotes.index(final_region) - 1]

    if point < initial_region.b or point > final_region.a:
        return

    # String path for file
    return view.substr(sublime.Region(initial_region.b, final_region.a))


def check_recursive(base_folders, name):
    """
    Return the path to the base folder and the path to the file if it is
    present in the project.
    """

    for base_folder in base_folders:
        for root, dirs, files in os.walk(base_folder):
            for f in files:
                if f == name:
                    return os.path.dirname(base_folder), root


def get_file(view: sublime.View, string: str, name: str) -> (str, bool):
    """
    Try to get a file from the given `string` and test whether it's in the
    project directory.
    """

    # if it's an absolute path get it
    if os.path.isabs(string):
        return (string, None)

    # if search_mode: "project", search only in project
    elif SEARCH_MODE == "project":
        # Get base project folders
        base_folders = sublime.active_window().folders()
        # if "recursive": true, recursively search for the name
        if RECURSIVE:
            ch_rec = check_recursive(base_folders, name)
            if ch_rec:
                base_folder, root = ch_rec
            return (os.path.join(root, name), base_folder)
        else:
            # search only in base folders for the relative path
            for base_folder in base_folders:
                file_name = os.path.normpath(os.path.join(base_folder, string))
                if os.path.exists(file_name):
                    return (file_name, base_folder)
    # if search_mode: "file" join the relative path to the file path
    else:
        return (os.path.normpath(os.path.join(
            os.path.dirname(view.file_name()), string)), None)


def save(file: str, name: str, kind: str, folder=None, convert=False) -> None:
    """Save the image if it's not already in the project folders."""

    # all folders in the project
    base_folders = sublime.active_window().folders()
    # create the image folder in the first folder
    image_folder = os.path.join(base_folders[0], IMAGE_FOLDER_NAME)
    # exact or converted copy of the image
    copy = os.path.join(image_folder, name)
    # a relative version of the image_folder for display in the status message
    image_folder_rel = os.path.relpath(
        image_folder, os.path.dirname(base_folders[0]))

    if os.path.exists(copy):
        sublime.status_message("%s is already in %s" %
                               (name, image_folder_rel))
        return

    if kind == "file" and folder:
        sublime.status_message("%s is already in %s" %
                               (name, os.path.relpath(os.path.dirname(file), folder)))
        return

    ch_rec = check_recursive(base_folders, name)
    if ch_rec:
        folder, root = ch_rec
        sublime.status_message("%s is already in %s" %
                               (name, os.path.relpath(root, folder)))
        return

    if not os.path.exists(image_folder):
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

    basename, ext = os.path.splitext(name or os.path.basename(file))
    all_formats = ALL_FORMATS.split('|')
    # remove the extension of the file
    all_formats.remove(ext[1:])

    def on_done(i):
        if i != -1:
            save(file, basename + '.' + all_formats[i], kind, convert=True)

    sublime.active_window().show_quick_panel(all_formats, on_done)


class HoverPreview(sublime_plugin.EventListener):

    def __init__(self):
        self.file_popup_is_large = True
        self.url_popup_is_large = True
        self.data_url_popup_is_large = True

    def handle_as_url(self, view: sublime.View, point: int, string: str, name: str) -> None:
        """Handle the given `string` as a url."""

        # Let's assume this url as input:
        # (https://upload.wikimedia.org/wikipedia/commons/8/84/Example.svg)

        # Download the image
        # FIXME: avoid nested try-except clauses
        try:
            try:
                f = urlopen(unquote(string))  # <==
            except:
                try:
                    url_path = quote(string).replace("%3A", ':', 1)
                    f = urlopen(url_path)
                except:
                    f = urlopen(string)
        # don't fill the console with stack-trace when there`s no connection !!
        except Exception as e:
            print(e)
            return

        # file needs conversion ?
        need_conversion = name.endswith(FORMAT_TO_CONVERT)  # => True
        basename, ext = os.path.splitext(name)  # => ("Example", ".svg")
        # create a temporary file
        tmp_file = os.path.join(tempfile.gettempdir(),
                                "tmp_image" +
                                (ext if need_conversion else ".png")
                                )  # => "TEMPDIR/tmp_image.svg"

        # Save downloaded data in the temporary file
        content = f.read()
        with open(tmp_file, "wb") as dst:
            dst.write(content)

        # if the file needs conversion, convert it then read data from the resulting png
        if need_conversion:
            # keep the image's temporary file and name for later use
            conv_file = tmp_file  # => "TEMPDIR/tmp_image.svg"
            conv_name = name  # => "Example.svg"

            # => "TEMPDIR/tmp_image.png"
            png = os.path.splitext(tmp_file)[0] + ".png"

            # use the magick command of Imagemagick to convert the image to png
            magick(tmp_file, png)

            # set temp_file and name to the png file
            tmp_file = png  # => "TEMPDIR/tmp_image.png"
            name = basename + ".png"  # => "Example.png"

            # read data from the resulting png
            with open(tmp_file, "rb") as dst:
                content = dst.read()

        real_width, real_height, size = get_image_size(tmp_file)
        width, height = get_dimensions(view, tmp_file)
        encoded = str(base64.b64encode(content), "utf-8")

        def on_navigate(href):
            if href == "resize":
                if self.url_popup_is_large:
                    self.url_popup_is_large = False
                    new_width, new_height = fix_oversize(width, height)
                    view.update_popup(TEMPLATE % (new_width, new_height,
                                                  encoded, real_width,
                                                  real_height, size // 1024))
                else:
                    self.url_popup_is_large = True
                    view.update_popup(TEMPLATE % (width, height, encoded,
                                                  real_width, real_height,
                                                  size // 1024))
            elif href == "save":
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
                sublime.active_window().open_file(file)

        view.show_popup(
            TEMPLATE % (width, height, encoded, real_width,
                        real_height, size // 1024),
            sublime.HIDE_ON_MOUSE_MOVE_AWAY,
            point,
            *view.viewport_extent(),
            on_navigate=on_navigate
        )
        # the url-based image's popup is too big
        self.url_popup_is_large = True

    def handle_as_data_url(self, view: sublime.View, point: int, ext: str, encoded: str) -> None:
        """Handle the string as a data url."""

        # create a temporary file
        tmp_file = os.path.join(tempfile.gettempdir(), "tmp_data_image." + ext)
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

        real_width, real_height, size = get_image_size(tmp_file)
        width, height = get_dimensions(view, tmp_file)

        def on_navigate(href):
            if href == "resize":
                if self.data_url_popup_is_large:
                    self.data_url_popup_is_large = False
                    new_width, new_height = fix_oversize(width, height)
                    view.update_popup(DATA_URL_TEMPLATE % (new_width,
                                                           new_height, ext,
                                                           encoded, real_width,
                                                           real_height,
                                                           size // 1024))
                else:
                    self.data_url_popup_is_large = True
                    view.update_popup(DATA_URL_TEMPLATE % (width, height, ext,
                                                           encoded, real_width,
                                                           real_height,
                                                           size // 1024))
            elif href == "save":
                save(tmp_file, name, "data_url")
            elif href == "save_as":
                convert(tmp_file, "data_url", name)
            else:
                sublime.active_window().open_file(tmp_file)

        view.show_popup(
            DATA_URL_TEMPLATE % (width, height, ext, encoded, real_width,
                                 real_height, size // 1024),
            sublime.HIDE_ON_MOUSE_MOVE_AWAY,
            point,
            *view.viewport_extent(),
            on_navigate=on_navigate
        )
        # the data-url-based image's popup is too big
        self.data_url_popup_is_large = True

    def handle_as_file(self, view: sublime.View, point: int, string: str, name: str) -> None:
        """Handle the given `string` as a file."""
        # "hover_preview.png"

        file, folder = get_file(view, string, name)

        # if file doesn't exist, return
        if not os.path.isfile(file):
            return

        # does the file need conversion ?
        need_conversion = file.endswith(FORMAT_TO_CONVERT)

        # if the file needs conversion, convert it and read data from the resulting png
        if need_conversion:
            # keep the image's file and name for later use
            conv_file = file
            conv_name = name

            # create a temporary file
            tmp_file = os.path.join(tempfile.gettempdir(), "tmp_png.png")
            name = os.path.splitext(name)[0] + ".png"

            # use the magick command of Imagemagick to convert the image to png
            magick(file, tmp_file)

            file = tmp_file

        with open(file, "rb") as f:
            encoded = str(base64.b64encode(f.read()), "utf-8")

        real_width, real_height, size = get_image_size(file)
        width, height = get_dimensions(view, file)

        def on_navigate(href):
            if href == "resize":
                if self.file_popup_is_large:
                    self.file_popup_is_large = False
                    new_width, new_height = fix_oversize(width, height)
                    view.update_popup(TEMPLATE % (new_width, new_height,
                                                  encoded, real_width,
                                                  real_height, size // 1024))
                else:
                    self.file_popup_is_large = True
                    view.update_popup(TEMPLATE % (width, height, encoded,
                                                  real_width, real_height,
                                                  size // 1024))
            elif href == "save":
                if need_conversion:
                    save(conv_file, conv_name, "file")
                else:
                    save(file, name, "file", folder)
            elif href == "save_as":
                convert(conv_file if need_conversion else file, "file")
            else:
                sublime.active_window().open_file(file)

        view.show_popup(
            TEMPLATE % (width, height, encoded, real_width,
                        real_height, size // 1024),
            sublime.HIDE_ON_MOUSE_MOVE_AWAY,
            point,
            *view.viewport_extent(),
            on_navigate=on_navigate)
        # the file-based image's popup is too big
        self.file_popup_is_large = True

    def on_hover(self, view: sublime.View, point: int, hover_zone: int) -> None:

        if hover_zone != sublime.HOVER_TEXT:
            return

        string = get_string(view, point)
        if not string:
            return

        # DATA URL
        image_data_url = IMAGE_DATA_URL_RE.match(string)
        if image_data_url:
            ext, encoded = image_data_url.groups()
            return self.handle_as_data_url(view, point, ext, encoded)

        # URL
        image_url = IMAGE_URL_RE.match(string)
        if image_url:
            protocol, name = image_url.groups()
            # if the url doesn't start with http or https try adding it
            # "//www.gettyimages.fr/gi-resources/images/Embed/new/embed2.jpg"
            if not protocol:
                string = "http://" + string.lstrip('/')
            # don't block the app while handling the url
            return sublime.set_timeout_async(lambda: self.handle_as_url(
                view, point, string, name), 0)

        # FILE
        name = os.path.basename(string)
        if IMAGE_PATH_RE.match(name):
            return self.handle_as_file(view, point, string, name)
