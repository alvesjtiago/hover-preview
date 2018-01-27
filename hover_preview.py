import sublime
import sublime_plugin
import base64
import os
import re
import urllib.parse
import urllib.request
import tempfile
from . import get_image_size

IMAGE_FORMATS = 'jpg|jpeg|bmp|gif|png'
MAX_WIDTH = 250
MAX_HEIGHT = 250


class HoverPreview(sublime_plugin.EventListener):
    def width_and_height_from_path(path, view):
        # Allow max automatic detection and remove gutter
        max_width = view.viewport_extent()[0] - 60
        max_height = view.viewport_extent()[1] - 60
        max_ratio = max_height / max_width

        # Get image dimensions
        try:
            width, height = get_image_size.get_image_size(path)[:2]
        except get_image_size.UnknownImageFormat:
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

    def fix_oversize(width, height):
        '''shrinks the popup if its bigger than MAX_WIDTH x MAX_HEIGHT'''
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

    def resizef(view, width, height, real_width, real_height, size, encoded):
        '''resizes file-based images (f for file)'''
        if HoverPreview.too_bigf:
            HoverPreview.too_bigf = False
            new_width, new_height = HoverPreview.fix_oversize(width, height)
            view.update_popup(
                '<a href="resizef"><img style="width: {}px;height: {}px;" src="data:image/png;base64,{}"></a><div>{}x{} {}Ko    <a href="open" style="text-decoration: none">open</a></div>'.
                format(new_width, new_height, encoded, real_width, real_height,
                       size // 1024))
        else:
            HoverPreview.too_bigf = True
            view.update_popup(
                '<a href="resizef"><img style="width: {}px;height: {}px;" src="data:image/png;base64,{}"></a><div>{}x{} {}Ko    <a href="open" style="text-decoration: none">open</a></div>'.
                format(width, height, encoded, real_width, real_height, size //
                       1024))

    def resizeu(view, width, height, real_width, real_height, size, encoded):
        '''resizes the url-based images (u for url)'''
        if HoverPreview.too_bigu:
            HoverPreview.too_bigu = False
            new_width, new_height = HoverPreview.fix_oversize(width, height)
            view.update_popup(
                '<a href="resizeu"><img style="width: {}px;height: {}px;" src="data:image/png;base64,{}"></a><div>{}x{} {}Ko</div>'.
                format(new_width, new_height, encoded, real_width, real_height,
                       size // 1024))
        else:
            HoverPreview.too_bigu = True
            view.update_popup('<a href="resizeu"><img style="width: {}px;height: {}px;" src="data:image/png;base64,{}"></a><div>{}x{} {}Ko</div>'.format(
                width, height, encoded, real_width, real_height, size // 1024))

    def on_hover(self, view, point, hover_zone):
        if hover_zone == sublime.HOVER_TEXT:
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
            if len(symbols) == 0:
                return

            closest_symbol = min(symbols)
            symbol = symbols_dict[closest_symbol]

            # All quotes in view
            if symbol == ")":
                all_quotes = view.find_all(r"\(|\)")
                all_match = [
                    item for item in all_quotes if (item.a == closest_symbol)
                ]
            else:
                all_quotes = view.find_all(symbol)
                all_match = [
                    item for item in all_quotes if item.a == closest_symbol
                ]

            # If there are no matches return
            if not all_match:
                return

            # Get final and initial region of quoted string
            final_region = all_match[0]
            index = all_quotes.index(final_region) - 1
            initial_region = all_quotes[index]

            if point < initial_region.b or point > final_region.a:
                return

            # String path for file
            path = view.substr(
                sublime.Region(initial_region.b, final_region.a))

            ### Handle URL's ###
            # Check URL (from http://codereview.stackexchange.com/questions/19663/http-url-validating)
            url = re.compile(
                r'^(?:http|ftp)s?://'  # http:// or https://
                r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+(?:[A-Z]{2,6}\.?|[A-Z0-9-]{2,}\.?)|'  # domain...
                r'localhost|'  # localhost...
                r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}|'  # ...or ipv4
                r'\[?[A-F0-9]*:[A-F0-9:]+\]?)'  # ...or ipv6
                r'(?::\d+)?'  # optional port
                r'(?:/?|[/?]\S+)$',
                re.IGNORECASE)
            # Regex for images
            imageURL = re.compile('.+(?:' + IMAGE_FORMATS + ')', re.IGNORECASE)
            # Display and return if it's a URL with an image extension
            if url.match(path) and imageURL.match(path):
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

                tmp_file_path = os.path.join(tempfile.gettempdir(),
                                             "tmp_image.png")
                urllib.request.urlretrieve(url_path, tmp_file_path)
                real_width, real_height, size = get_image_size.get_image_size(
                    tmp_file_path)
                width, height = HoverPreview.width_and_height_from_path(
                    tmp_file_path, view)

                encoded = str(base64.b64encode(f.read()), "utf-8")
                view.show_popup(
                    '<a href="resizeu"><img style="width: {}px;height: {}px;" src="data:image/png;base64,{}"></a><div>{}x{} {}Ko</div>'.
                    format(width, height, encoded, real_width, real_height,
                           size // 1024),
                    flags=sublime.HIDE_ON_MOUSE_MOVE_AWAY,
                    location=point,
                    max_width=view.viewport_extent()[0],
                    max_height=view.viewport_extent()[1],
                    on_navigate=
                    lambda href: HoverPreview.resizeu(view, width, height, real_width, real_height, size, encoded)
                )
                # the url-based image's popup is too big
                HoverPreview.too_bigu = True
                return
            ### End handle URL's ###

            path = path.strip().split('/')[-1]

            # Regex for images
            pattern = re.compile('([-@\w.]+\.(?:' + IMAGE_FORMATS + '))',
                                 re.IGNORECASE)

            if path and pattern.match(path):

                # Get base project folder
                base_folders = sublime.active_window().folders()

                # Find the first file that matches path
                file_name = ""
                for base_folder in base_folders:
                    for root, dirs, files in os.walk(base_folder):
                        for file in files:
                            if file.endswith(path):
                                file_name = os.path.join(root, file)
                                break

                # Check that file exists
                if file_name and os.path.isfile(file_name):
                    encoded = str(
                        base64.b64encode(open(file_name, "rb").read()),
                        "utf-8")

                    real_width, real_height, size = get_image_size.get_image_size(
                        file_name)
                    width, height = HoverPreview.width_and_height_from_path(
                        file_name, view)

                    view.show_popup(
                        '<a href="resizef"><img style="width: {}px;height: {}px;" src="data:image/png;base64,{}"></a><div>{}x{} {}Ko    <a href="open" style="text-decoration: none">open</a></div>'.format(width, height, encoded, real_width, real_height, size // 1024),
                        flags=sublime.HIDE_ON_MOUSE_MOVE_AWAY,
                        location=point,
                        max_width=view.viewport_extent()[0],
                        max_height=view.viewport_extent()[1],
                        on_navigate=lambda href: HoverPreview.resizef(view, width, height, real_width, real_height, size, encoded) if href == "resizef" else sublime.active_window().run_command("open_file", { "file": file_name}))
                    # the file-based image's popup is too big
                    HoverPreview.too_bigf = True
                    return
                return
            return
        return
