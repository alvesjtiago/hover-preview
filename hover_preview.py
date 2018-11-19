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

TEMPLATE = '''
    <a href="resize">
        <img style="width: %dpx;height: %dpx;" src="data:image/png;base64,%s">
    </a>
    <div>%dx%d %dKB</div>
    <div>
        <a href="open">Open</a> | <a href="save">Save</a>%s | <a href="convert_to">Convert</a>
    </div>
    '''

def hp_callback():
    global MAX_WIDTH, MAX_HEIGHT, FORMAT_TO_CONVERT, ALL_FORMATS, IMAGE_PATH, IMAGE_URL, IMAGE_FOLDER_NAME

    MAX_WIDTH, MAX_HEIGHT = settings.get('max_dimensions', [320, 240])
    FORMAT_TO_CONVERT = tuple(settings.get('formats_to_convert', ['.svg', '.svgz', '.webp']))
    ALL_FORMATS = "|".join(settings.get('all_formats', ["png", "jpg", "jpeg",
                                                        "bmp", "gif", "ico", "svg", "svgz", "webp"]))
    IMAGE_FOLDER_NAME = settings.get('image_folder_name', 'Hovered Images')
    IMAGE_PATH = re.compile(r'([-@\w.]+\.(?:' + ALL_FORMATS + '))')
    IMAGE_URL = re.compile(r'(https?)?:?//[^"\']+/([^"\']+?\.(?:' + ALL_FORMATS + '))')

def plugin_loaded():
    global settings
    settings = sublime.load_settings('Hover Preview.sublime-settings')
    settings.clear_on_change('hp')
    hp_callback()
    settings.add_on_change('hp', hp_callback)

def magick(inp, out):
    if os.name == 'nt':
        subprocess.call(['magick', inp, out], shell=True)
    else:
        subprocess.call(['magick', inp, out])

def width_and_height_from_path(path: str, view: sublime.View) -> (int, int):
    '''returns the width and height from the given path'''
    # Allow max automatic detection and remove gutter
    max_width = view.viewport_extent()[0] - 60
    max_height = view.viewport_extent()[1] - 60
    max_ratio = max_height / max_width

    # Get image dimensions
    try:
        width, height = get_image_size(path)[:2]
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

def get_path(view: sublime.View, point: int) -> str:
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
    if symbol == ")":
        all_quotes = view.find_all(r"\(|\)")
        all_match = (item for item in all_quotes
                     if item.a == closest_symbol)
    else:
        all_quotes = view.find_all(symbol)
        all_match = (item for item in all_quotes
                     if item.a == closest_symbol)

    # If there are no matches return
    if not all_match:
        return

    # Get final and initial region of quoted string
    final_region = next(all_match)
    index = all_quotes.index(final_region) - 1
    initial_region = all_quotes[index]

    if point < initial_region.b or point > final_region.a:
        return

    # String path for file
    return view.substr(
        sublime.Region(initial_region.b, final_region.a))

def save(href: str, file: str, name: str, too_big: str, in_project: bool = False) -> None:
    base_folders = sublime.active_window().folders()
    dst = os.path.join(base_folders[0], IMAGE_FOLDER_NAME)
    copy = os.path.join(dst, name)
    if os.path.exists(copy):
        sublime.status_message("%s is already in %s" % (name, dst))
        return
    if too_big == 'too_bigf' and in_project:
        sublime.status_message("%s is already in %s" %
                               (name, os.path.dirname(file)))
        return
    for base_folder in base_folders:
        for root, dirs, files in os.walk(base_folder):
            for f in files:
                if f.endswith(name):
                    sublime.status_message(
                        "%s is already in %s" % (name, root))
                    return
    try:
        shutil.copyfile(file, copy)
    except:
        os.mkdir(dst)
        shutil.copyfile(file, copy)
    sublime.status_message("%s saved in %s" % (name, dst))

def convert(file: str, name=None):
    window = sublime.active_window()
    basename, format = os.path.splitext(name if name else os.path.basename(file))
    all_formats = ALL_FORMATS.split('|')
    all_formats.remove(format[1:])
    folder_path = os.path.join(window.folders()[0], IMAGE_FOLDER_NAME)
    if not os.path.exists(folder_path):
        os.makedirs(folder_path)
    window.show_quick_panel(all_formats, lambda i: magick(file, os.path.join(folder_path, basename + '.' + all_formats[i])) if i != -1 else None)

class HoverPreview(sublime_plugin.EventListener):
    __slots__ = ["too_bigf", "too_bigu"]

    def __init__(self):
        self.too_bigf = True
        self.too_bigu = True

    def resize(self, view: sublime.View, width: int, height: int, real_width: int,
               real_height: int, size: int, encoded: str, too_big: str, save_as: str) -> None:
        ''' Resizes the popup'''
        if getattr(self, too_big, True):
            setattr(self, too_big, False)
            new_width, new_height = fix_oversize(width, height)
            view.update_popup(TEMPLATE % (
                new_width, new_height, encoded, real_width, real_height, size // 1024, save_as))
        else:
            setattr(self, too_big, True)
            view.update_popup(TEMPLATE % (
                width, height, encoded, real_width, real_height, size // 1024, save_as))

    def handle_url(self, view: sublime.View, point: int, path: str, name: str) -> None:
        try:
            try:
                url_path = urllib.parse.unquote(path)
                f = urllib.request.urlopen(url_path)
            except:
                try:
                    url_path = urllib.parse.quote(path).replace(
                        "%3A", ":", 1)
                    f = urllib.request.urlopen(url_path)
                except:
                    url_path = path
                    f = urllib.request.urlopen(url_path)
        # don't fill the console with stack trace when theres no connection !!
        except Exception as e:
            print(e)
            return
        # (https://upload.wikimedia.org/wikipedia/commons/8/84/Example.svg)
        need_magick = name.endswith(FORMAT_TO_CONVERT)
        basename, ext = os.path.splitext(name)
        tmp_file = os.path.join(
            tempfile.gettempdir(), 'tmp_image' + ext if need_magick else "tmp_image.png")
        content = f.read()
        with open(tmp_file, "wb") as dst:
            dst.write(content)
        # if the file needs conversion, convert it then read data from the resulting png
        save_as = ''
        if need_magick:
            save_as = ' | <a href="save as png">Save as png</a>'
            conv_file = tmp_file
            conv_name = name
            png = os.path.splitext(tmp_file)[0] + '.png'
            name = basename + '.png'
            # use the magick command of Imagemagick
            magick(tmp_file, png)
            tmp_file = png
            with open(tmp_file, "rb") as dst:
                content = dst.read()

        real_width, real_height, size = get_image_size(tmp_file)
        width, height = width_and_height_from_path(tmp_file, view)
        encoded = str(base64.b64encode(content), "utf-8")

        def on_navigate(href):
            if href == 'resize':
                self.resize(view, width, height, real_width,
                            real_height, size, encoded, 'too_bigu', save_as)
            elif href == 'save':
                if not need_magick:
                    save(href, tmp_file, name, 'too_bigu')
                else:
                    save(href, conv_file, conv_name, 'too_bigu')
            elif href == 'save as png':
                save(href, tmp_file, name, 'too_bigu')
            elif href == 'convert_to':
                convert(conv_file if need_magick else tmp_file, conv_name if need_magick else name)
            else:
                sublime.active_window().run_command(
                    'open_file', {'file': tmp_file})

        view.show_popup(
            TEMPLATE % (width, height, encoded, real_width,
                        real_height, size // 1024, save_as),
            sublime.HIDE_ON_MOUSE_MOVE_AWAY,
            point,
            *view.viewport_extent(),
            on_navigate=on_navigate
        )
        # the url-based image's popup is too big
        self.too_bigu = True

    def handle_file(self, view: sublime.View, point: int, path: str) -> None:
        name = os.path.basename(path)
        if IMAGE_PATH.match(name):
            in_project = False
            # if it's an absolute path get it
            if os.path.isabs(path):
                file_name = path

            # if search_mode: "project", search only in project
            elif settings.get('search_mode') == "project":
                # Get base project folders
                base_folders = sublime.active_window().folders()
                if settings.get('recursive'):
                    path = name
                    file_name = ""
                    break_now = False
                    for base_folder in base_folders:
                        # break out of the outer loop
                        if break_now:
                            break
                        for root, dirs, files in os.walk(base_folder):
                            for file in files:
                                # Find the first file that matches path
                                if file.endswith(path):
                                    file_name = os.path.join(root, file)
                                    break_now = True
                                    in_project = True
                                    break
                else:
                    # search only in base folders for the relative path
                    for base_folder in base_folders:
                        file_name = os.path.normpath(
                            os.path.join(base_folder, path))
                        if os.path.exists(file_name):
                            in_project = True
                            break
            # if search_mode: "file" join the relative path to the file path
            else:
                file_name = os.path.normpath(os.path.join(
                    os.path.dirname(view.file_name()), path))
        else:
            return

        # Check that file exists
        if os.path.isfile(file_name):
            save_as = ''
            need_magick = file_name.endswith(FORMAT_TO_CONVERT)
            if need_magick:
                conv_file = file_name
                conv_name = name
                tmp_file = os.path.join(tempfile.gettempdir(), "tmppng.png")
                name = os.path.splitext(name)[0] + '.png'
                magick(file_name, tmp_file)
                file_name = tmp_file
                save_as = ' | <a href="save as png">Save as png</a>'

            with open(file_name, "rb") as f:
                encoded = str(base64.b64encode(f.read()), "utf-8")

            real_width, real_height, size = get_image_size(file_name)
            width, height = width_and_height_from_path(file_name, view)

            def on_navigate(href):
                if href == 'resize':
                    self.resize(view, width, height, real_width,
                                real_height, size, encoded, 'too_bigf', save_as)
                elif href == 'save':
                    if not need_magick:
                        save(href, file_name, name, 'too_bigf', in_project)
                    else:
                        save(href, conv_file, conv_name, 'too_bigf')
                elif href == 'save as png':
                    save(href, file_name, name, 'too_bigf')
                elif href == 'convert_to':
                    convert(conv_file if need_magick else file_name)
                else:
                    sublime.active_window().run_command(
                        'open_file', {'file': file_name})

            view.show_popup(
                TEMPLATE % (width, height, encoded, real_width,
                            real_height, size // 1024, save_as),
                sublime.HIDE_ON_MOUSE_MOVE_AWAY,
                point,
                *view.viewport_extent(),
                on_navigate=on_navigate)
            # the file-based image's popup is too big
            self.too_bigf = True

    def on_hover(self, view: sublime.View, point: int, hover_zone: int) -> None:
        if hover_zone != sublime.HOVER_TEXT:
            return
        path = get_path(view, point)
        if not path:
            return

        image = IMAGE_URL.match(path)
        # if it's an image url handle_url
        if image:
            image = image.groups()
            # if the url doesn't start with http or https try adding it
            # "//www.gettyimages.fr/gi-resources/images/Embed/new/embed2.jpg"
            if not image[0]:
                path = 'http://' + path.lstrip('/')
            # don't block the app while handling the url
            sublime.set_timeout_async(lambda: self.handle_url(
                view, point, path, image[1]), 0)
        # if it's not an image url handle_file
        else:
            self.handle_file(view, point, path)
