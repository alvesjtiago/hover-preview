import sublime
import sublime_plugin
import base64
import os
import re

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
                    encoded = str(base64.b64encode(
                                    open(file_name, "rb").read()
                                ), "utf-8")
                    view.show_popup('<img src="data:image/png;base64,' + 
                                        encoded + 
                                    '">', 
                                     flags=sublime.HIDE_ON_MOUSE_MOVE_AWAY, 
                                     location=point)
                    return
                return
            return
        return
        
