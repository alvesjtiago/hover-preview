import sublime
import sublime_plugin
import struct
import base64
import imghdr
import os
import re

''' 
Method to get image size based on input image.

Obtained from:
http://stackoverflow.com/questions/8032642/how-to-obtain-image-size-using-standard-python-class-without-using-external-lib
'''
def get_image_size(fname):
    '''Determine the image type of fhandle and return its size.
    from draco'''
    with open(fname, 'rb') as fhandle:
        head = fhandle.read(24)
        if len(head) != 24:
            return
        if imghdr.what(fname) == 'png':
            check = struct.unpack('>i', head[4:8])[0]
            if check != 0x0d0a1a0a:
                return
            width, height = struct.unpack('>ii', head[16:24])
        elif imghdr.what(fname) == 'gif':
            width, height = struct.unpack('<HH', head[6:10])
        elif imghdr.what(fname) == 'jpeg':
            try:
                fhandle.seek(0) # Read 0xff next
                size = 2
                ftype = 0
                while not 0xc0 <= ftype <= 0xcf:
                    fhandle.seek(size, 1)
                    byte = fhandle.read(1)
                    while ord(byte) == 0xff:
                        byte = fhandle.read(1)
                    ftype = ord(byte)
                    size = struct.unpack('>H', fhandle.read(2))[0] - 2
                # We are at a SOFn block
                fhandle.seek(1, 1)  # Skip `precision' byte.
                height, width = struct.unpack('>HH', fhandle.read(4))
            except Exception: #IGNORE:W0703
                return
        else:
            return
        return width, height
'''
End of image size method.
'''

class HoverPreview(sublime_plugin.EventListener):
    def on_hover(self, view, point, hover_zone):
        if (hover_zone == sublime.HOVER_TEXT):
            hovered_line_text = view.substr(view.line(point)).strip()

            next_double_quote = view.find('"', point).a
            next_single_quote = view.find("'", point).a
            next_parentheses = view.find(r"\)", point).a

            symbols_dict = { next_double_quote: '"', 
                             next_single_quote: "'",
                             next_parentheses: ')' }

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
                all_match = [item for item in all_quotes if (item.a == closest_symbol)]
            else:
                all_quotes = view.find_all(symbol)
                all_match = [item for item in all_quotes if item.a == closest_symbol]

            # If there are no matches return
            if len(all_match) == 0:
                return

            # Get final and initial region of quoted string
            final_region = all_match[0]
            index = all_quotes.index(final_region) - 1
            initial_region = all_quotes[index]

            # String path for file
            path = view.substr(sublime.Region(initial_region.b, final_region.a))
            path = path.strip().split('/')[-1]

            # Regex for images
            pattern = re.compile('([-@\w]+\.(?:jpg|gif|png))')

            if (path and path != "" and pattern.match(path)):

                # Get base project folder
                base_folder = sublime.active_window().folders()[0]

                # Find the first file that matches path
                file_name = ""
                for root, dirs, files in os.walk(base_folder):
                    for file in files:
                        if file.endswith(path):
                             file_name = os.path.join(root, file)
                             break

                # Check that file exists
                if (file_name and os.path.isfile(file_name)):
                    imageInfo = get_image_size(file_name)
                    if imageInfo and imageInfo[0] and imageInfo[0] != 0:
                        encoded = str(base64.b64encode(
                                        open(file_name, "rb").read()
                                    ), "utf-8")
                        view.show_popup('<img src="data:image/png;base64,' + 
                                            encoded + 
                                        '" width="' + 
                                            str(imageInfo[0]) + 
                                        '" height="'+ 
                                            str(imageInfo[1]) + 
                                        '">', 
                                         flags=sublime.HIDE_ON_MOUSE_MOVE_AWAY, 
                                         location=point)
                        return
                    return
                return
            return
        return
        
