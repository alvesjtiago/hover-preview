# Image Preview

The Sublime Text 3 image previewing plugin.

![Screenshot of Image Preview, a plugin for Sublime Text 3 by @alvesjtiago](screenshot.png)

## Usage

- if "preview_on_hover" is set to true (the default), hover over an image filename (full, relative or just the name), a url or a data-url
- Open the context menu and click on `Preview Image` (it's only visible when on an image identifier)
- you can bind the "preview_image" command to a key or a mouse gesture (it is not bound by default)

## Installation

### Package Control

Search for "Image Preview" and install.

### Manual

_macOS_
```sh
cd ~/Library/Application\ Support/Sublime\ Text\ 3/Packages
git clone --depth=1 https://github.com/alvesjtiago/sublime-image-preview.git
```

_Ubuntu_
```sh
cd ~/.config/sublime-text-3/Packages
git clone --depth=1 https://github.com/alvesjtiago/sublime-image-preview.git
```

_Windows_
```sh
cd "%APPDATA%\Sublime Text 3\Packages"
git clone --depth=1 https://github.com/alvesjtiago/sublime-image-preview.git
```

Or manually create a folder named "Preview Image" on your Packages folder and copy the content of this repo to it.

## Requirements

- to preview images that need conversion the plugin requires [Imagemagick](https://www.imagemagick.org/script/download.php) and that `magick` command is in your path.


## Contribute

Image Preview is a small utility created by [Tiago Alves](https://twitter.com/alvesjtiago).
Any help on this project is more than welcome. Or if you find any problems, please comment or open an issue with as much information as you can provide.
