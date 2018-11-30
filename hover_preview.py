import base64
import re
import os
import shutil
import urllib.parse
import urllib.request
import tempfile
import subprocess
from .get_image_size import get_image_size, UnknownImageFormat

import sublime
import sublime_plugin

TEMPLATE = """
    <a href="resize">
        <img style="width: %dpx;height: %dpx;" src="data:image/png;base64,%s">
    </a>
    <div>%dx%d %dKB</div>
    <div>
        <a href="open">Open</a> | <a href="save">Save</a>%s | <a href="convert_to">Convert</a>
    </div>
    """

def hp_callback():
    global MAX_WIDTH, MAX_HEIGHT, FORMAT_TO_CONVERT, ALL_FORMATS, IMAGE_PATH, IMAGE_URL, IMAGE_FOLDER_NAME

    MAX_WIDTH, MAX_HEIGHT = settings.get("max_dimensions", [320, 240])
    FORMAT_TO_CONVERT = tuple(settings.get("formats_to_convert",
                                           [".svg", ".svgz", ".webp"]))
    ALL_FORMATS = "|".join(settings.get('all_formats', ["png", "jpg", "jpeg",
                                        "bmp", "gif", "ico", "svg", "svgz",
                                        "webp"]))
    IMAGE_FOLDER_NAME = settings.get("image_folder_name", "Hovered Images")
    IMAGE_PATH = re.compile(r'([-@\w.]+\.(?:' + ALL_FORMATS + '))')
    IMAGE_URL = re.compile(r'(https?)?:?//[^"\']+/([^"\']+?\.(?:' + ALL_FORMATS + '))')

def plugin_loaded():
    global settings
    settings = sublime.load_settings("Hover Preview.sublime-settings")
    settings.clear_on_change("hp")
    hp_callback()
    settings.add_on_change("hp", hp_callback)

def magick(inp, out):
    if os.name == "nt":
        subprocess.call(["magick", inp, out], shell=True)
    else:
        subprocess.call(["magick", inp, out])

def get_dimensions(view: sublime.View, path: str) -> (int, int):
    """ returns the width and height from the given path """
    # Allow max automatic detection and remove gutter
    max_width = view.viewport_extent()[0] - 60
    max_height = view.viewport_extent()[1] - 60
    max_ratio = max_height / max_width

    # Get image get_dimensions
    try:
        width, height, _ = get_image_size(path)
    except UnknownImageFormat:
        width, height = -1, -1

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
    ''' Shrinks the popup if its bigger than max_width x max_height '''
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
    if symbol == ')':
        all_quotes = view.find_all(r"\(|\)")
    else:
        all_quotes = view.find_all(symbol)

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

def get_file(view: sublime.View, string: str, name: str) -> (str, bool):
    """
    try to get a file from the given `string` and tests whether it's in the
    project directory
    """
    # if it's an absolute path get it
    if os.path.isabs(string):
        return (string, False)

    # if search_mode: "project", search only in project
    elif settings.get("search_mode") == "project":
        # in_project = True
        # Get base project folders
        base_folders = sublime.active_window().folders()
        # if "recursive": true, recursively search for the name
        if settings.get("recursive"):
            for base_folder in base_folders:
                for root, dirs, files in os.walk(base_folder):
                    for file in files:
                        # Find the first file that matches string
                        if file.endswith(name):
                            return (os.path.join(root, file), True)
            return ("", True)
        else:
            # search only in base folders for the relative path
            for base_folder in base_folders:
                file_name = os.path.normpath(os.path.join(base_folder, string))
                if os.path.exists(file_name):
                    return (file_name, True)
    # if search_mode: "file" join the relative path to the file path
    else:
        return (os.path.normpath(os.path.join(
            os.path.dirname(view.file_name()), string)), False)

def save(href: str, file: str, name: str, kind: str, in_project=False) -> None:
    base_folders = sublime.active_window().folders()
    dst = os.path.join(base_folders[0], IMAGE_FOLDER_NAME)
    copy = os.path.join(dst, name)
    if os.path.exists(copy):
        sublime.status_message("%s is already in %s" % (name, dst))
        return
    if kind == "file" and in_project:
        sublime.status_message("%s is already in %s" % (name, os.path.dirname(file)))
        return
    for base_folder in base_folders:
        for root, dirs, files in os.walk(base_folder):
            for f in files:
                if f.endswith(name):
                    sublime.status_message("%s is already in %s" % (name, root))
                    return
    try:
        shutil.copyfile(file, copy)
    except:
        os.mkdir(dst)
        shutil.copyfile(file, copy)
    sublime.status_message("%s saved in %s" % (name, dst))

def convert(file: str, name=None):
    window = sublime.active_window()
    basename, format = os.path.splitext(name or os.path.basename(file))
    all_formats = ALL_FORMATS.split('|')
    all_formats.remove(format[1:])
    folder = os.path.join(window.folders()[0], IMAGE_FOLDER_NAME)

    def on_done(i):
        if i != -1:
            if not os.path.exists(folder):
                os.makedirs(folder)
            to = basename + '.' + all_formats[i]
            magick(file, os.path.join(folder, to))
            sublime.status_message("%s saved in %s" % (to, folder))
    window.show_quick_panel(all_formats, on_done)

class HoverPreview(sublime_plugin.EventListener):
    __slots__ = ("file_popup_is_large", "url_popup_is_large")

    def __init__(self):
        self.file_popup_is_large = True
        self.url_popup_is_large = True

    def handle_as_url(self, view: sublime.View, point: int, string: str, name: str) -> None:
        """ Handles the given `string` as a url """
        # Let's assume this url as input:
        # (https://upload.wikimedia.org/wikipedia/commons/8/84/Example.svg)

        # Download the image
        # FIXME: avoid nested try-except clauses
        try:
            try:
                f = urllib.request.urlopen(urllib.parse.unquote(string))  # <==
            except:
                try:
                    url_path = urllib.parse.quote(string).replace("%3A", ':', 1)
                    f = urllib.request.urlopen(url_path)
                except:
                    f = urllib.request.urlopen(string)
        # don't fill the console with stack-trace when there`s no connection !!
        except Exception as e:
            print(e)
            return

        # file needs conversion ?
        need_conversion = name.endswith(FORMAT_TO_CONVERT)  # => True
        basename, ext = os.path.splitext(name)  # => ("Example", ".svg")
        # create a temporary file
        tmp_file = os.path.join(tempfile.gettempdir(),
                                "tmp_image" + (ext if need_conversion else ".png"))  # => "TEMPDIR/tmp_image.svg"

        # Save downloaded data in the temporary file
        content = f.read()
        with open(tmp_file, "wb") as dst:
            dst.write(content)
        save_as = ""
        # if the file needs conversion, convert it then read data from the resulting png
        if need_conversion:
            # add a `save_as` link
            save_as = ' | <a href="save as png">Save as png</a>'

            # keep the image's temporary file and name for later use
            conv_file = tmp_file  # => "TEMPDIR/tmp_image.svg"
            conv_name = name  # => "Example.svg"

            png = os.path.splitext(tmp_file)[0] + ".png"  # => "TEMPDIR/tmp_image.png"

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
                    view.update_popup(TEMPLATE % (new_width, new_height, encoded,
                                                  real_width, real_height,
                                                  size // 1024, save_as))
                else:
                    self.url_popup_is_large = True
                    view.update_popup(TEMPLATE % (width, height, encoded,
                                                  real_width, real_height,
                                                  size // 1024, save_as))
            elif href == "save":
                if need_conversion:
                    save(href, conv_file, conv_name, "url")
                else:
                    save(href, tmp_file, name, "url")
            elif href == "save as png":
                save(href, tmp_file, name, "url")
            elif href == "convert_to":
                if need_conversion:
                    convert(conv_file, conv_name)
                else:
                    convert(tmp_file, name)
            else:
                sublime.active_window().open_file(file)

        view.show_popup(
            TEMPLATE % (width, height, encoded, real_width,
                        real_height, size // 1024, save_as),
            sublime.HIDE_ON_MOUSE_MOVE_AWAY,
            point,
            *view.viewport_extent(),
            on_navigate=on_navigate
        )
        # the url-based image's popup is too big
        self.url_popup_is_large = True

    def handle_as_file(self, view: sublime.View, point: int, string: str) -> None:
        """ handles the given `string` as a file """
        # "hover_preview.png"

        name = os.path.basename(string)

        if not IMAGE_PATH.match(name):
            return

        file, in_project = get_file(view, string, name)

        # if file doesn't exist, return
        if not os.path.isfile(file):
            return
        
        # does the file need conversion ?
        need_conversion = file.endswith(FORMAT_TO_CONVERT)
        save_as = ""

        # if the file needs conversion, convert it and read data from the resulting png
        if need_conversion:
            # add `save as png` link
            save_as = ' | <a href="save as png">Save as png</a>'

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
                                                  real_height, size // 1024,
                                                  save_as))
                else:
                    self.file_popup_is_large = True
                    view.update_popup(TEMPLATE % (width, height, encoded,
                                                  real_width, real_height,
                                                  size // 1024, save_as))
            elif href == "save":
                if need_conversion:
                    save(href, conv_file, conv_name, "file")
                else:
                    save(href, file, name, "file", in_project)
            elif href == "save as png":
                save(href, file, name, "file")
            elif href == "convert_to":
                convert(conv_file if need_conversion else file)
            else:
                sublime.active_window().open_file(file)

        view.show_popup(
            TEMPLATE % (width, height, encoded, real_width,
                        real_height, size // 1024, save_as),
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

        image = IMAGE_URL.match(string)
        # if it's an image url handle as url
        if image:
            image = image.groups()
            # if the url doesn't start with http or https try adding it
            # "//www.gettyimages.fr/gi-resources/images/Embed/new/embed2.jpg"
            if not image[0]:
                string = "http://" + string.lstrip('/')
            # don't block the app while handling the url
            sublime.set_timeout_async(lambda: self.handle_as_url(
                view, point, string, image[1]), 0)
        # if it's not an image url handle as file
        else:
            self.handle_as_file(view, point, string)
