import struct
import base64
import imghdr
import sublime
import sublime_plugin
import os
import re

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

class HoverPreview(sublime_plugin.EventListener):
    def on_hover(self, view, point, hover_zone):
        if (hover_zone == sublime.HOVER_TEXT):
            hovered_text = view.substr(view.line(point)).strip()
            path = re.findall(r'"([^"]*)"', hovered_text)

            next_quote = view.find('"', point).a
            all_quotes = view.find_all('"')

            final_region = [item for item in all_quotes if item.a == next_quote][0]
            index = all_quotes.index(final_region) - 1
            initial_region = all_quotes[index]

            path = view.substr(sublime.Region(initial_region.b, final_region.a))

            path = path.split('/')[-1]

            pattern = re.compile('([-@\w]+\.(?:jpg|gif|png))')


            if (pattern.match(path) and path and path != ""):
                sel = path

                cur_path = sublime.active_window().folders()[0]

                dir_files = os.listdir(cur_path)

                file_name = ""
                for root, dirs, files in os.walk(cur_path):
                    for file in files:
                        if file.endswith(sel):
                             # print(os.path.join(root, file))
                             file_name = os.path.join(root, file)
                if (file_name and os.path.isfile(file_name)):
                    imageInfo = get_image_size(file_name)
                    if imageInfo and imageInfo[0] and imageInfo[0] != 0:
                        encoded = str(base64.b64encode(open(file_name, "rb").read()), "utf-8")

                        # print(imageInfo)
                        view.show_popup('<img src="data:image/png;base64,' + encoded + '" width="'+ str(imageInfo[0]) +'" height="'+ str(imageInfo[1]) +'">', flags=sublime.HIDE_ON_MOUSE_MOVE_AWAY, location=point)
                        return
                    else:
                        return
                else:
                    return
            else:
                return
        else:
            return
        
