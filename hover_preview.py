import sublime
import sublime_plugin
import base64
import re
import os
import shutil
import urllib.parse
import urllib.request
import tempfile
import subprocess
from .get_image_size import get_image_size, UnknownImageFormat

IMAGE_PATH = re.compile(
    r'([-@\w.]+\.(?:png|jpg|jpeg|bmp|gif|svg|svgz))', re.IGNORECASE)
IMAGE_URL = re.compile(
    r'(https?)?:?//[^"\']+/(.+?\.(?:png|jpg|jpeg|bmp|gif|svg|svgz))', re.IGNORECASE)
SVG = ('.svg', '.svgz')
TEMPLATE = '''
    <a href="resize">
        <img style="width: %dpx;height: %dpx;" src="data:image/png;base64,%s">
    </a>
    <div>%dx%d %dKB</div>
    <div>
        <a href="open" style="text-decoration: none">Open</a>
        <a href="save" style="text-decoration: none">Save</a>
        %s
    </div>
    '''


class HoverPreview(sublime_plugin.EventListener):
    settings = sublime.load_settings('Hover Preview.sublime-settings')
    max_width = 250
    max_height = 250

    def width_and_height_from_path(self, path: str, view: sublime.View) -> (int, int):
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
            width = width * ratio
            height = height * ratio
        elif height / width <= max_ratio and width > max_width:
            ratio = max_width / width
            width = width * ratio
            height = height * ratio

        return (width, height)

    def fix_oversize(self, width: int, height: int) -> (int, int):
        ''' Shrinks the popup if its bigger than HoverPreview.max_width x HoverPreview.max_height'''
        new_width, new_height = width, height
        if width > HoverPreview.max_width or height > HoverPreview.max_height:
            if width > height:
                ratio = HoverPreview.max_width / width
                new_width = HoverPreview.max_width
                new_height = height * ratio
            else:
                ratio = HoverPreview.max_height / height
                new_height = HoverPreview.max_height
                new_width = width * ratio
        return (new_width, new_height)

    def resize(self, view: sublime.View, width: int, height: int, real_width: int,
               real_height: int, size: int, encoded: str, too_big: str, save_as: str) -> None:
        ''' Resizes the popup'''
        if getattr(self, too_big, True):
            setattr(self, too_big, False)
            new_width, new_height = self.fix_oversize(width, height)
            view.update_popup(TEMPLATE % (
                new_width, new_height, encoded, real_width, real_height, size // 1024, save_as))
        else:
            setattr(self, too_big, True)
            view.update_popup(TEMPLATE % (
                width, height, encoded, real_width, real_height, size // 1024, save_as))

    def get_path(self, view: sublime.View, point: int) -> str:
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

    def save(self, href: str, file: str, name: str, too_big: str, in_project: bool = False) -> None:
        base_folders = sublime.active_window().folders()
        dst = os.path.join(base_folders[0], 'HovImgPrev')
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
        is_svg = name.endswith(SVG)
        tmp_file = os.path.join(
            tempfile.gettempdir(), "tmp_image.png" if not is_svg else 'tmp_image.svg')
        content = f.read()
        with open(tmp_file, "wb") as dst:
            dst.write(content)
        # if it's an svg file we need to save it, convert it then read data from the resulting png
        save_as = ''
        if is_svg:
            save_as = '<a href="save as png">Save As Png</a>'
            svg_file = tmp_file
            svg_name = name
            png = os.path.splitext(tmp_file)[0] + '.png'
            name = os.path.splitext(name)[0] + '.png'
            # use the magick command of Imagemagick
            subprocess.call(['magick', tmp_file, png], shell=True)
            tmp_file = png
            with open(tmp_file, "rb") as dst:
                content = dst.read()

        real_width, real_height, size = get_image_size(tmp_file)
        width, height = self.width_and_height_from_path(tmp_file, view)
        encoded = str(base64.b64encode(content), "utf-8")
        def on_navigate(href):
            if href == 'resize':
                self.resize(view, width, height, real_width,
                            real_height, size, encoded, 'too_bigu', save_as)
            elif href == 'save':
                if not is_svg:
                    self.save(href, tmp_file, name, 'too_bigu')
                else:
                    self.save(href, svg_file, svg_name, 'too_bigu')
            elif href == 'save as png':
                self.save(href, tmp_file, name, 'too_bigu')
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
            elif HoverPreview.settings.get('search_mode') == "project":
                in_project = True
                # Get base project folders
                base_folders = sublime.active_window().folders()
                if HoverPreview.settings.get('recursive'):
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
                                    break
                else:
                    # search only in base folders for the relative path
                    for base_folder in base_folders:
                        file_name = os.path.normpath(
                            os.path.join(base_folder, path))
                        if os.path.exists(file_name):
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
            is_svg = file_name.endswith(SVG)
            if is_svg:
                svg_file = file_name
                svg_name = name
                tmp_file = os.path.join(tempfile.gettempdir(), "tmppng.png")
                name = os.path.splitext(name)[0] + '.png'
                subprocess.call(['magick', file_name, tmp_file], shell=True)
                file_name = tmp_file
                save_as = '<a href="save as png">Save As Png</a>'

            with open(file_name, "rb") as f:
                encoded = str(base64.b64encode(f.read()), "utf-8")

            real_width, real_height, size = get_image_size(file_name)
            width, height = self.width_and_height_from_path(file_name, view)

            def on_navigate(href):
                if href == 'resize':
                    self.resize(view, width, height, real_width,
                                real_height, size, encoded, 'too_bigf', save_as)
                elif href == 'save':
                    if not is_svg:
                        self.save(href, file_name, name,
                                  'too_bigf', in_project)
                    else:
                        self.save(href, svg_file, svg_name,
                                  'too_bigf', in_project)
                elif href == 'save as png':
                    self.save(href, file_name, name, 'too_bigf', in_project)
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
        if hover_zone == sublime.HOVER_TEXT:
            path = self.get_path(view, point)
            if not path:
                return
            # ST is sometimes unable to read the settings file
            try:
                HoverPreview.max_width, HoverPreview.max_height = HoverPreview.settings.get(
                    'max_dimensions', [250, 250])
            except:
                HoverPreview.settings = sublime.load_settings(
                    'Hover Preview.sublime-settings')
                HoverPreview.max_width, HoverPreview.max_height = HoverPreview.settings.get(
                    'max_dimensions', [250, 250])

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
