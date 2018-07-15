# Hover Preview

A Sublime Text 3 plugin to preview images simply by hovering on a file name or an image url.

![Screenshot of Hover Preview, a plugin for Sublime Text 3 by @alvesjtiago](hover_preview.png)

## Installation

### Package Control

Hover Preview has been approved on Package Control! 🎉
Search for "Hover Image Preview" and install.

### Manual

_macOS_
```
cd ~/Library/Application\ Support/Sublime\ Text\ 3/Packages
git clone --depth=1 https://github.com/alvesjtiago/hover-preview.git
```

_Ubuntu_
```
cd ~/.config/sublime-text-3/Packages
git clone --depth=1 https://github.com/alvesjtiago/hover-preview.git
```

_Windows_
```
cd "%APPDATA%\Sublime Text 3\Packages"
git clone --depth=1 https://github.com/alvesjtiago/hover-preview.git
```

Or manually create a folder named "hover-preview" on your Packages folder and copy the content of this repo to it.

## Configuration

#### max_dimensions:

- max\_width x max\_height for which the pop-up is considered too big and should be resized, (default: `[320, 240]`).

#### search_mode: 

- `"project" (default):` searches for the hovered file name in the project.
- `"file":` joins the file path to the hovered file name and see if it makes a valid image path.

#### recursive:

- `true (default)`: takes only the name part of the hovered file name and performs a recursive search in the project (directories and subdirectories).
- `false`: sees if the hovered file name exists in the base folders of the project (directories only).

#### all_formats:

- all image formats to look for, (default: `["png", "jpg", "jpeg", "bmp", "gif", "ico", "svg", "svgz", "webp"]`).

#### formats\_to\_convert:

- images that require conversion before rendering, (default: `[".svg", ".svgz", ".webp"]`).

**Notes**

- if `"recursive": true` the path part is irrelevant, if you don't like this behavior you can set this to `false` and/or set `"search_mode"` to `"file"`.
- `"recursive"` is only relevant if `"search_mode"` is set to `"project"`.

## Requirements

- to preview images that need conversion the plugin requires [Imagemagick](https://www.imagemagick.org/script/download.php) and that `magick` command is in your path.


## Contribute

Hover Preview is a small utility created by [Tiago Alves](https://twitter.com/alvesjtiago).
Any help on this project is more than welcome. Or if you find any problems, please comment or open an issue with as much information as you can provide.
